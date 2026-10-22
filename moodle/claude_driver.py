"""Upload one ZIP to Moodle with Claude in Chrome: one locked-down headless run of the Claude Code CLI per ZIP.

Moodle has no API, so `ClaudeChromeDriver.upload_zip` (the `MoodleDriver` of send.py) runs

    claude -p --chrome ... "<the prompt of claude_upload.md>"

in the user's own logged-in Chrome and turns the CLI's JSON output into an `UploadResult`.

What the run gets (the flags are in `build_command`):
- Tools: the Chrome tools plus the built-in Read tool (`--tools "Read"`), nothing else: no Bash, no Edit, no Write.
  Read is there because Chrome's `file_upload` reads the ZIP through the session's Read permission; in `-p` mode
  reads inside the working folder and `--add-dir` need no prompt, so Read is not in `--allowedTools`. The run can
  read only its temp folder (below), which holds the one ZIP. `--strict-mcp-config` keeps other MCP servers out.
  The connection check (`check`) never uploads, so it keeps `--tools ""`: no built-in tools at all.
- Folder: a fresh temporary folder outside OneDrive (`tempfile.mkdtemp`), holding only a copy of the ZIP. It is
  the run's working folder and its only `--add-dir`, and it is deleted when the run ends. The run never starts in
  the shared upload folder: anyone on the team can write there, and with `--setting-sources project` a
  `.claude/settings.json` (hooks) or `CLAUDE.md` in the working folder would be loaded. Before the run, the copy
  is hashed against the ZIP's hash in the batch list.
- Settings: `--setting-sources project` (the empty temp folder has none), so not the user's settings, hooks or plugins.
Claude never types a Moodle password: a login page ends the run with "needs_login".

Resolved: with `--tools ""` the first real test had Chrome's `file_upload` refused ("no permission to read the
file"). The user approved read access for the upload run on 2026-10-22, scoped to the temp folder with the one ZIP.

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

from moodle import upload_log
from moodle.send import UploadResult

UPLOAD_URL = ("https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id={id}&plugin=file"
              "&pluginsubtype=assignfeedback&action=viewpluginpage&pluginaction=uploadzip")
GRADING_URL = "https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id={id}&action=grading"
DOWNLOAD_URL = "https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id={id}&action=downloadall"

# Starting values: the test assignment (plan task 11) sets them from real runs
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_BUDGET_USD = 2.0
TIMEOUT_S = 600
CHECK_BUDGET_USD = 0.5  # "is everything ready" opens one page, so it gets less
CHECK_TIMEOUT_S = 180
AUTH_TIMEOUT_S = 30
DOWNLOAD_BUDGET_USD = 1.0  # opens two pages and maybe ticks one box
DOWNLOAD_TIMEOUT_S = 300
MESSAGE_MAX = 300

NOT_LOGGED_IN = "Claude Code לא מחובר במחשב הזה. מריצים פעם אחת: claude auth login"
NOT_INSTALLED = "Claude Code לא מותקן במחשב הזה (הפקודה claude לא נמצאה)."
NO_COPY = "לא הצלחנו להכין עותק של {name} להעלאה (הקובץ חסר או נעול). שום דבר לא הועלה."
COPY_CHANGED = "העותק של {name} שונה מהקובץ שהוכן. שום דבר לא הועלה: צריך להכין שוב."
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
DOWNLOAD_STATUSES = ("started", "needs_login", "error")
DOWNLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(DOWNLOAD_STATUSES)},
        "message": {"type": "string", "maxLength": MESSAGE_MAX},
    },
    "required": ["status", "message"],
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

DOWNLOAD_PROMPT = """You start the download of all submissions of one Moodle assignment, for a university course. Use only the Chrome tools.

Rules (never break them):
- Go only to these two addresses: {grading_url} and {download_url}. Never open assignment settings or any other page.
- If a login page appears, do not type anything anywhere. Stop and return status "needs_login".
- Never type anything. Never take a screenshot. Never write any person's name in your answer.
- Never change grades, submissions or assignment settings. The only thing you may click is the one checkbox in step 2.

Steps:
1. Open {grading_url}. Check the address has id={assignment_id} and the page is the grading page of the assignment "{title}". If not, return "error".
2. In the options of that page (usually near the bottom), find the checkbox "הורדת הגשות בתיקיות" (in English "Download submissions in folders").
   If it is there and not checked, click it once so that it is checked (it is a personal display option, not an assignment setting). If it is not there, go on.
3. Open {download_url}. Chrome then downloads one ZIP file with all the submissions; the page itself may not change. Do not click anything there.
   If Moodle shows an error message instead (say, there are no submissions), return "error" with that message.
4. Return "started".

Return only the structured result. "message" says what happened in one short sentence.
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


def build_command(prompt: str, add_dir: Path, *, model: str, budget_usd: float, schema: dict, claude: str,
                  tools: str = "") -> list[str]:
    """The command line of one run. Every flag of the locked-down run is here, so the findings of plan task 1 change one place.

    --tools, --allowedTools and --add-dir take a list: each is followed by another flag, so the prompt (last) is not read as one more value.
    `tools` is the built-in tools of the run: "" for none (the connection check), "Read" for an upload (file_upload needs it).
    """
    return [
        claude, "-p",
        "--chrome",                                         # the user's own logged-in Chrome
        "--no-session-persistence",                         # nothing of the run is kept
        "--setting-sources", "project",                     # not the user's settings, hooks or plugins
        "--strict-mcp-config",                              # no MCP servers beyond the ones named for the run
        "--tools", tools,                                   # the built-in tools: "" = none, "Read" = Read only (never Bash, Edit, Write). --allowedTools alone does not restrict
        "--allowedTools", "mcp__claude-in-chrome",          # the Chrome tools need no permission prompt. Read is not listed: reads inside cwd and --add-dir are allowed in -p mode
        "--output-format", "json",
        "--max-budget-usd", str(budget_usd),
        "--json-schema", json.dumps(schema, separators=(",", ":")),
        "--add-dir", str(add_dir),                          # the run's own temp folder only (a copy of the ZIP, or nothing): all that Read can reach
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

    def execute(self, claude: str, prompt: str, folder: Path, schema: dict, budget_usd: float, timeout_s: float,
                tools: str = ""):
        """Run the CLI with `folder` as its only folder. May raise: the callers turn that into a result."""
        cmd = build_command(prompt, folder, model=self.model, budget_usd=budget_usd, schema=schema, claude=claude,
                            tools=tools)
        # stdin closed: a headless run must not wait for input nobody types
        return self.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout_s,
                        cwd=folder, stdin=subprocess.DEVNULL)

    def upload_zip(self, info: dict, zip_path: Path, expected: int, dry_run: bool,
                   sha256: str | None = None) -> UploadResult:
        """`sha256`: the ZIP's hash in the batch list (run_batch always passes it); the copy the run gets must match it."""
        claude = self.claude or find_claude()
        if not claude:
            return UploadResult("error", message=NOT_INSTALLED)
        name = Path(zip_path).name
        run_dir = None
        try:
            # The run's own folder, outside OneDrive, with only a copy of the ZIP (see the module docstring)
            run_dir = Path(tempfile.mkdtemp(prefix="moodle-upload-")).absolute()
            copy = run_dir / name  # file_upload needs the whole path
            try:
                shutil.copyfile(zip_path, copy)
            except OSError:
                return UploadResult("error", message=NO_COPY.format(name=name))
            if sha256 is not None and upload_log.file_hash(copy) != sha256:
                return UploadResult("error", message=COPY_CHANGED.format(name=name))
            prompt = render_prompt(info, copy, expected, dry_run)
            # Read only: file_upload reads the ZIP through it, and it reaches only run_dir
            proc = self.execute(claude, prompt, run_dir, RESULT_SCHEMA, self.budget_usd, self.timeout_s, tools="Read")
        except Exception as error:  # the driver must never raise (see the module docstring)
            message = failure_message(error, self.timeout_s)
            if isinstance(error, subprocess.TimeoutExpired):
                message += " ייתכן שהקובץ כבר יובא. העלאה חוזרת של אותו ZIP בטוחה."
            return UploadResult("error", message=message)
        finally:
            if run_dir is not None:
                shutil.rmtree(run_dir, ignore_errors=True)
        return result_of(*read_run(proc))

    def check(self, info: dict) -> dict:
        """Are Chrome and Moodle ready? {"chrome": bool, "moodle": bool, "message": str}. Never raises."""
        claude = self.claude or find_claude()
        if not claude:
            return {"chrome": False, "moodle": False, "message": NOT_INSTALLED}
        timeout_s = min(self.timeout_s, CHECK_TIMEOUT_S)
        try:
            prompt = CHECK_PROMPT.format(grading_url=GRADING_URL.format(id=assignment_id(info)))
            # No ZIP to carry and nothing to upload, so the run gets an empty folder and no built-in tools (tools="")
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

    def download(self, info: dict) -> dict:
        """Start the download of all submissions in the user's Chrome. {"status": "started"|"needs_login"|"error", "message": str}.

        Chrome saves the ZIP to Downloads; the caller waits for it there (moodle.ingest.wait_for_download).
        The run gets an empty folder and no built-in tools, like the connection check. Never raises."""
        claude = self.claude or find_claude()
        if not claude:
            return {"status": "error", "message": NOT_INSTALLED}
        timeout_s = min(self.timeout_s, DOWNLOAD_TIMEOUT_S)
        try:
            mid = assignment_id(info)
            prompt = DOWNLOAD_PROMPT.format(grading_url=GRADING_URL.format(id=mid), download_url=DOWNLOAD_URL.format(id=mid),
                                            assignment_id=mid, title=info.get("title") or info.get("name") or "")
            with tempfile.TemporaryDirectory(prefix="moodle-download-", ignore_cleanup_errors=True) as empty:
                proc = self.execute(claude, prompt, Path(empty), DOWNLOAD_SCHEMA, DOWNLOAD_BUDGET_USD, timeout_s)
        except Exception as error:  # never raise: the caller shows the message
            return {"status": "error", "message": failure_message(error, timeout_s)}
        answer, problem = read_run(proc)
        if answer is None:
            return {"status": "error", "message": problem}
        status = answer.get("status")
        if status not in DOWNLOAD_STATUSES:
            return {"status": "error", "message": UNEXPECTED}
        message = str(answer.get("message") or "")[:MESSAGE_MAX] or DEFAULT_MESSAGES.get(status, "")
        return {"status": status, "message": message}


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
