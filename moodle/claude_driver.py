"""Upload one ZIP to Moodle with Claude in Chrome: one locked-down headless run of the Claude Code CLI per ZIP.

Moodle has no API, so `ClaudeChromeDriver.upload_zip` (the `MoodleDriver` of send.py) runs

    claude -p --chrome ... "<the prompt of claude_upload.md>"

in the user's own logged-in Chrome and turns the CLI's JSON output into an `UploadResult`. The run can use the
Chrome tools only (`--tools ""` switches the built-in tools off), and see only the folder the ZIP is in. It never gets
Bash, file tools, other MCP servers, hooks or the user's settings (the flags are in `build_command`). Claude never types a Moodle password: a login page ends the
run with "needs_login".

The driver never raises. `run_batch` lets a driver's exception propagate, so every failure (no `claude`, a
timeout, a non-zero exit, output nobody can read, Claude not logged in) comes back as `UploadResult("error")`
with a Hebrew message for the user. Our own messages say numbers only; what Claude writes in "message" passes
through as it is, capped at 300 characters, and the prompt tells it to name nobody.

`check` and `auth_status` are for the site's "is everything ready" button: Chrome and Moodle are reachable,
and Claude Code is logged in. Nothing here is run by the tests: they give the driver a fake `run`.
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from moodle.send import UploadResult

UPLOAD_URL = ("https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id={id}&plugin=file"
              "&pluginsubtype=assignfeedback&action=viewpluginpage&pluginaction=uploadzip")
GRADING_URL = "https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id={id}&action=grading"

# Starting values: the test assignment (plan task 11) sets them from real runs
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_BUDGET_USD = 2.0
TIMEOUT_S = 600
CHECK_BUDGET_USD = 0.5  # "is everything ready" opens one page, so it gets less
CHECK_TIMEOUT_S = 180
AUTH_TIMEOUT_S = 30
MESSAGE_MAX = 300

NOT_LOGGED_IN = "Claude Code לא מחובר במחשב הזה. מריצים פעם אחת: claude auth login"
NOT_INSTALLED = "Claude Code לא מותקן במחשב הזה (הפקודה claude לא נמצאה)."
UNEXPECTED = "תשובה לא צפויה מ-Claude Code: אי אפשר לקרוא את התוצאה."

STATUSES = ("imported", "dry_run_ok", "needs_login", "mismatch", "error")
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(STATUSES)},
        "rows": {"type": ["integer", "null"]},
        "imported": {"type": ["integer", "null"]},
        "skipped": {"type": ["integer", "null"]},
        "message": {"type": "string", "maxLength": MESSAGE_MAX},
    },
    "required": ["status", "rows", "imported", "skipped", "message"],
    "additionalProperties": False,
}
CHECK_SCHEMA = {
    "type": "object",
    "properties": {"chrome": {"type": "boolean"}, "moodle_logged_in": {"type": "boolean"}},
    "required": ["chrome", "moodle_logged_in"],
    "additionalProperties": False,
}

TEMPLATE = Path(__file__).with_name("claude_upload.md")
# {expected} is filled in render_prompt. the button יבוא קבצי משוב imports at once in BGU's Moodle: there is no screen to check first
DRY_RUN_MODE = ('This is a dry run: attach the file, then click ביטול. Never click יבוא קבצי משוב. '
                'Return "dry_run_ok" with rows = {expected}, and stop.')
CHECK_PROMPT = """You check that the Chrome tools and Moodle are ready. Use only the Chrome tools.

Rules (never break them):
- Go only to this address: {grading_url}.
- Do not type anything anywhere and do not click anything. Never take a screenshot.
- Never write any person's name in your answer.

Steps:
1. Open {grading_url}.
2. "chrome" is true if the Chrome tools worked.
3. "moodle_logged_in" is true if the page is the grading page of an assignment, shown to a logged-in Moodle user. It is false for a login page or an error page.

Return only the structured result.
"""

# A failed run whose output is one of these means Claude Code itself is not logged in
AUTH_PROBLEM = re.compile(r"authenticat|oauth|not logged in|/login|invalid api key", re.IGNORECASE)
# What to say when Claude gives a failing status without a message
DEFAULT_MESSAGES = {
    "needs_login": "Moodle מבקש התחברות. מתחברים ל-Moodle בכרום ומריצים שוב.",
    "mismatch": "מספר הקבצים ש-Moodle עיבד שונה מהצפוי.",
    "error": "Claude לא פירט מה השתבש.",
}


def find_claude() -> str | None:
    """The `claude` command: on the PATH, or where the official installer puts it (~/.local/bin).

    A fresh install is often not on the PATH of a server that was already running.
    """
    found = shutil.which("claude")
    if found:
        return found
    for name in ("claude.exe", "claude"):
        candidate = Path.home() / ".local" / "bin" / name
        if candidate.is_file():
            return str(candidate)
    return None


def assignment_id(info: dict) -> str:
    """The Moodle id from Assignment details.json. Digits only: it goes into the prompt and the address."""
    value = str(info["id"])
    if not value.isdigit():
        raise ValueError(f"מזהה מטלה לא תקין: {value!r}")
    return value


def render_prompt(info: dict, zip_path: Path, expected: int, dry_run: bool) -> str:
    """The text of claude_upload.md for this ZIP (a str.format template: keep literal braces out of it)."""
    return TEMPLATE.read_text(encoding="utf-8").format(
        upload_url=UPLOAD_URL.format(id=assignment_id(info)),
        assignment_id=assignment_id(info),
        title=info.get("title") or info.get("name") or "",
        zip_path=zip_path,
        expected=expected,
        mode=DRY_RUN_MODE.format(expected=expected) if dry_run else "",
    )


def build_command(prompt: str, add_dir: Path, *, model: str, budget_usd: float, schema: dict, claude: str) -> list[str]:
    """The command line of one run. Every flag of the locked-down run is here, so the findings of plan task 1 change one place.

    --tools, --allowedTools and --add-dir take a list: each is followed by another flag, so the prompt (last) is not read as one more value.
    """
    return [
        claude, "-p",
        "--chrome",                                         # the user's own logged-in Chrome
        "--no-session-persistence",                         # nothing of the run is kept
        "--setting-sources", "project",                     # not the user's settings, hooks or plugins
        "--strict-mcp-config",                              # no MCP servers beyond the ones named for the run
        "--tools", "",                                      # switches every built-in tool off (Bash, Edit, Write, Read...). --allowedTools alone does not
        "--allowedTools", "mcp__claude-in-chrome",          # what is left: the Chrome tools only. Needs no permission prompt
        "--output-format", "json",
        "--max-budget-usd", str(budget_usd),
        "--json-schema", json.dumps(schema, separators=(",", ":")),
        "--add-dir", str(add_dir),                          # the upload folder only
        "--model", model,
        prompt,
    ]


def object_in(text) -> dict | None:
    """The JSON object inside a text (possibly in a ``` fence), or None."""
    if not isinstance(text, str):
        return None
    try:
        value = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()))
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def read_answer(stdout: str | None) -> tuple[dict | None, str]:
    """The structured answer in the CLI's JSON output, or (None, why in Hebrew).

    The answer is in `structured_output`; if it is not, in the `result` text as JSON.
    """
    try:
        data = json.loads(stdout or "")
    except ValueError:
        return None, UNEXPECTED
    if isinstance(data, list):  # a list of messages: the last "result" one is the answer
        data = next((d for d in reversed(data) if isinstance(d, dict) and d.get("type") == "result"), None)
    if not isinstance(data, dict):
        return None, UNEXPECTED
    if data.get("is_error") or str(data.get("subtype") or "").startswith("error"):
        text = str(data.get("result") or data.get("subtype") or "").strip()
        if AUTH_PROBLEM.search(text):
            return None, NOT_LOGGED_IN
        return None, f"Claude Code נכשל: {text[:MESSAGE_MAX]}" if text else "Claude Code נכשל."
    answer = data.get("structured_output")
    answer = answer if isinstance(answer, dict) else object_in(data.get("result"))
    return (answer, "") if answer is not None else (None, UNEXPECTED)


def read_run(proc) -> tuple[dict | None, str]:
    """read_answer for a finished process. A non-zero exit never counts as an answer."""
    code = getattr(proc, "returncode", 0)
    answer, problem = read_answer(proc.stdout)
    if code and (answer is not None or problem == UNEXPECTED):
        return None, f"Claude Code נכשל (קוד יציאה {code})."
    return answer, problem


def count_or_none(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def result_of(answer: dict | None, problem: str) -> UploadResult:
    """An UploadResult from read_answer's (answer, problem)."""
    if answer is None:
        return UploadResult("error", message=problem)
    status = answer.get("status")
    if status not in STATUSES:
        return UploadResult("error", message=UNEXPECTED)
    message = str(answer.get("message") or "")[:MESSAGE_MAX] or DEFAULT_MESSAGES.get(status, "")
    return UploadResult(status, count_or_none(answer.get("rows")), count_or_none(answer.get("imported")),
                        count_or_none(answer.get("skipped")), message)


def parse_result(stdout: str) -> UploadResult:
    return result_of(*read_answer(stdout))


def failure_message(error: Exception, timeout_s: float) -> str:
    """Hebrew for a run that did not finish. The type of the error only: its text could hold anything."""
    if isinstance(error, subprocess.TimeoutExpired):
        return f"Claude Code לא סיים תוך {round(timeout_s / 60)} דקות ונעצר."
    if isinstance(error, FileNotFoundError):
        return NOT_INSTALLED
    return f"Claude Code לא הצליח לרוץ ({type(error).__name__})."


class ClaudeChromeDriver:
    """The `MoodleDriver` for Moodle through Claude in Chrome. `run` is subprocess.run, a fake in tests."""

    def __init__(self, model: str = DEFAULT_MODEL, budget_usd: float = DEFAULT_BUDGET_USD,
                 timeout_s: int = TIMEOUT_S, run=subprocess.run, claude: str | None = None):
        self.model = model
        self.budget_usd = budget_usd
        self.timeout_s = timeout_s
        self.run = run
        self.claude = claude

    def execute(self, claude: str, prompt: str, folder: Path, schema: dict, budget_usd: float, timeout_s: float):
        """Run the CLI with `folder` as its only folder. May raise: the callers turn that into a result."""
        cmd = build_command(prompt, folder, model=self.model, budget_usd=budget_usd, schema=schema, claude=claude)
        # stdin closed: a headless run must not wait for input nobody types
        return self.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout_s,
                        cwd=folder, stdin=subprocess.DEVNULL)

    def upload_zip(self, info: dict, zip_path: Path, expected: int, dry_run: bool) -> UploadResult:
        claude = self.claude or find_claude()
        if not claude:
            return UploadResult("error", message=NOT_INSTALLED)
        try:
            zip_path = Path(zip_path).absolute()  # file_upload needs the whole path
            prompt = render_prompt(info, zip_path, expected, dry_run)
            proc = self.execute(claude, prompt, zip_path.parent, RESULT_SCHEMA, self.budget_usd, self.timeout_s)
        except Exception as error:  # the driver must never raise (see the module docstring)
            message = failure_message(error, self.timeout_s)
            if isinstance(error, subprocess.TimeoutExpired):
                message += " ייתכן שהקובץ כבר יובא. העלאה חוזרת של אותו ZIP בטוחה."
            return UploadResult("error", message=message)
        return result_of(*read_run(proc))

    def check(self, info: dict) -> dict:
        """Are Chrome and Moodle ready? {"chrome": bool, "moodle": bool, "message": str}. Never raises."""
        claude = self.claude or find_claude()
        if not claude:
            return {"chrome": False, "moodle": False, "message": NOT_INSTALLED}
        timeout_s = min(self.timeout_s, CHECK_TIMEOUT_S)
        try:
            prompt = CHECK_PROMPT.format(grading_url=GRADING_URL.format(id=assignment_id(info)))
            # No ZIP to carry, so the run gets an empty folder and nothing else
            with tempfile.TemporaryDirectory(prefix="moodle-check-", ignore_cleanup_errors=True) as empty:
                proc = self.execute(claude, prompt, Path(empty), CHECK_SCHEMA, CHECK_BUDGET_USD, timeout_s)
        except Exception as error:  # never raise: the answer is a dict for the site
            return {"chrome": False, "moodle": False, "message": failure_message(error, timeout_s)}
        answer, problem = read_run(proc)
        if answer is None:
            return {"chrome": False, "moodle": False, "message": problem}
        chrome = answer.get("chrome") is True
        moodle = chrome and answer.get("moodle_logged_in") is True
        if not chrome:
            message = "הכלים של Chrome לא עבדו. בודקים שהתוסף Claude in Chrome מותקן ושכרום פתוח."
        elif not moodle:
            message = "אין התחברות ל-Moodle בכרום. מתחברים ל-Moodle ידנית ובודקים שוב."
        else:
            message = "Chrome ו-Moodle מוכנים."
        # "answered": Claude really looked (the other results above are failures to run). Only these are worth remembering
        return {"chrome": chrome, "moodle": moodle, "message": message, "answered": True}


def auth_status(run=subprocess.run, claude: str | None = None) -> dict:
    """Is Claude Code logged in on this computer? {"logged_in": bool, "message": str}. Never raises.

    `claude auth status --json` prints {"loggedIn": ..., ...} (and exits non-zero when logged out). Nothing of
    that output is passed on but the yes or no: it holds the account's details.
    """
    claude = claude or find_claude()
    if not claude:
        return {"logged_in": False, "message": NOT_INSTALLED}
    try:
        proc = run([claude, "auth", "status", "--json"], capture_output=True, text=True, encoding="utf-8",
                   timeout=AUTH_TIMEOUT_S, stdin=subprocess.DEVNULL)
        data = json.loads(proc.stdout or "")
    except FileNotFoundError:
        return {"logged_in": False, "message": NOT_INSTALLED}
    except Exception:  # a timeout, odd output...: we only could not check
        data = None
    if not isinstance(data, dict) or "loggedIn" not in data:
        return {"logged_in": False, "message": "לא הצלחנו לבדוק אם Claude Code מחובר."}
    if data["loggedIn"] is True:
        return {"logged_in": True, "message": "Claude Code מחובר."}
    return {"logged_in": False, "message": NOT_LOGGED_IN}
