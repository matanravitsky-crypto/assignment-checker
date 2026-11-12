"""Claude Code on this computer: find it, ask whether it is signed in, and read what a headless run (`claude -p`) answered.

Nothing here knows Moodle or Chrome: moodle/claude_driver.py (the runs in Chrome) and grading/claude_cli.py (the grading
runs) both use it, so grading can go out to a skill without the Moodle driver. Part of the core (docs/Modularity.md).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

AUTH_TIMEOUT_S = 30
MESSAGE_MAX = 300
STDERR_MAX = 200
NOT_LOGGED_IN = "Claude Code לא מחובר במחשב הזה. מריצים פעם אחת: claude auth login"
NOT_INSTALLED = "Claude Code לא מותקן במחשב הזה (הפקודה claude לא נמצאה)."
UNEXPECTED = "תשובה לא צפויה מ-Claude Code: אי אפשר לקרוא את התוצאה."
AUTH_PROBLEM = re.compile(r"authenticat|oauth|not logged in|/login|invalid api key", re.IGNORECASE)


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


def crashed(proc) -> bool:
    """Claude Code ended with an error code and wrote nothing at all: it failed before it could answer."""
    return bool(getattr(proc, "returncode", 0)) and not str(getattr(proc, "stdout", "") or "").strip()


def stderr_tail(proc) -> str:
    """The last line Claude Code wrote to stderr, short: why it failed, when it says so."""
    lines = [line.strip() for line in str(getattr(proc, "stderr", "") or "").splitlines() if line.strip()]
    return lines[-1][:STDERR_MAX] if lines else ""


def read_run(proc) -> tuple[dict | None, str]:
    """read_answer for a finished process. A non-zero exit never counts as an answer."""
    code = getattr(proc, "returncode", 0)
    answer, problem = read_answer(proc.stdout)
    if code and (answer is not None or problem == UNEXPECTED):
        tail = stderr_tail(proc)
        return None, f"Claude Code נכשל (קוד יציאה {code})." + (f" הוא כתב: {tail}" if tail else "")
    return answer, problem


def failure_message(error: Exception, timeout_s: float) -> str:
    """Hebrew for a run that did not finish. The type of the error only: its text could hold anything."""
    if isinstance(error, subprocess.TimeoutExpired):
        return f"Claude Code לא סיים תוך {round(timeout_s / 60)} דקות ונעצר."
    if isinstance(error, FileNotFoundError):
        return NOT_INSTALLED
    return f"Claude Code לא הצליח לרוץ ({type(error).__name__})."


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
