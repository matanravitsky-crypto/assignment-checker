"""בדיקה דרך Claude Code (הפקודה claude), כשאין ANTHROPIC_API_KEY.

Claude Code מחובר במחשב עם החשבון של הצוות (כמו בהעלאה למודל), ולכן אפשר לבדוק בלי מפתח API:
הבדיקה נספרת במנוי של Claude ולא מחויבת בנפרד. לכל הגשה רצה ריצה אחת נעולה של

    claude -p --tools "" --input-format stream-json --json-schema <SCHEMA> ...

הבקשה כולה (הוראות, מחוון, ועמודי ההגשה כתמונות) נשלחת בהודעה אחת ב-stdin. אין כלי Read ואין סבבים: ריצה קודמת
קראה כל עמוד בסבב נפרד, וכל סבב קרא מחדש את כל ההקשר (כ-13 סבבים ו-1.1 דולר להגשה). עכשיו זה סבב אחד.

מה שחוסך את רוב העלות:
- ההקשר המשותף (המחוון, ההנחיות) נשלח עם cache_control של שעה, וכל ההגשות באותה מטלה קוראות אותו מהמטמון.
  זה עובד רק אם תחילת הבקשה זהה בין ההרצות, ולכן תיקיית העבודה קבועה (Claude Code כותב אותה להנחיות המערכת)
  וקובץ ההנחיות נקרא לפי תוכנו.
- ברירת המחדל כאן היא Sonnet בחשיבה בינונית (grade.CLI_MODEL): כ-0.04 דולר להגשה במקום 1.1 עם Opus.

מה הריצה מקבלת: רק את הבקשה. תיקיית עבודה ריקה מחוץ ל-OneDrive, בלי כלים בכלל (ולא Read), בלי כרום ובלי שרתי MCP.
טבלת המפתח והשמות לא מגיעים לשם לעולם. --setting-sources project בתיקייה ריקה: בלי ההגדרות, ה-hooks והתוספים של המשתמש.

החוזה זהה ל-claude_ask של grade.py: מקבלים את הבקשה שבנה build_request ומחזירים טקסט JSON בסכמה SCHEMA.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from moodle import claude_driver

BUDGET_USD = 5.0
TIMEOUT_S = 900
CACHE_TTL = "1h"


USAGE_LOG = "Grading usage.jsonl"


def log_usage(stdout: str, model: str, pages: int | None = None) -> None:
    """One line per run in the data folder: tokens and cost only (no names, no content). Never fails the grading.

    A healthy run of a warmed-up assignment has cache_read >= the shared context (~85k) and cache_write of the
    page images only (~1.5k per page); cache_write near 100k means the shared prefix was rewritten."""
    try:
        data = json.loads(stdout)
        usage = data.get("usage") or {}
        row = {"at": datetime.now().isoformat(timespec="seconds"), "model": model, "pages": pages,
               "input": usage.get("input_tokens"), "output": usage.get("output_tokens"),
               "thinking": (usage.get("output_tokens_details") or {}).get("thinking_tokens"),
               "cache_read": usage.get("cache_read_input_tokens"),
               "cache_write": usage.get("cache_creation_input_tokens"),
               "turns": data.get("num_turns"), "cost_usd": data.get("total_cost_usd")}
        from moodle import paths
        with (paths.data_dir() / USAGE_LOG).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


def available() -> bool:
    """Claude Code מותקן ומחובר במחשב הזה."""
    return claude_driver.find_claude() is not None and claude_driver.auth_status()["logged_in"] is True


def work_folder() -> Path:
    """תיקיית עבודה קבועה וריקה: Claude Code כותב אותה להנחיות המערכת, ושינוי בה שובר את המטמון בין הרצות."""
    folder = Path(tempfile.gettempdir()) / "grading-claude-run"
    folder.mkdir(exist_ok=True)
    return folder.absolute()


def system_file(folder: Path, text: str) -> Path:
    """קובץ ההנחיות, בשם שנקבע לפי התוכן: ריצות מקבילות עם אותן הנחיות כותבות את אותו קובץ."""
    path = folder / f"system-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}.txt"
    if not path.exists():
        tmp = path.with_suffix(f".{id(text)}.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return path


def message_line(req: dict) -> str:
    """הודעת המשתמש בפורמט stream-json: כל הבלוקים של הבקשה, וה-cache_control של המשותף בתוקף של שעה."""
    blocks = [{**b, "cache_control": {"type": "ephemeral", "ttl": CACHE_TTL}} if "cache_control" in b else b
              for m in req["messages"] for b in m["content"]]
    return json.dumps({"type": "user", "message": {"role": "user", "content": blocks}}, ensure_ascii=False)


def build_command(claude: str, system_path: Path, schema: dict, model: str, effort: str | None) -> list[str]:
    cmd = [
        claude, "-p",
        "--no-chrome",
        "--no-session-persistence",
        "--setting-sources", "project",       # התיקייה ריקה: בלי ההגדרות וה-hooks של המשתמש
        "--strict-mcp-config",                # בלי שרתי MCP
        "--tools", "",                        # בלי שום כלי: התמונות כבר בהודעה
        "--system-prompt-file", str(system_path),
        "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
        "--max-budget-usd", str(BUDGET_USD),
        "--json-schema", json.dumps(schema, separators=(",", ":")),
        "--model", model,
    ]
    if effort:
        cmd += ["--effort", effort]
    return cmd


def _events(stdout: str) -> list[dict]:
    out = []
    for line in (stdout or "").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            out.append(event)
    return out


def cli_ask(claude: str, schema: dict, effort: str | None = None, run=subprocess.run,
            error: type[Exception] = RuntimeError, not_logged_in: type[Exception] = RuntimeError):
    """Ask (ראו grade.py) שרץ דרך Claude Code. `error` ו-`not_logged_in` הם סוגי השגיאות של grade.py."""

    def ask(req: dict) -> str:
        folder = work_folder()
        cmd = build_command(claude, system_file(folder, req.get("system") or ""), schema, req["model"], effort)
        try:
            proc = run(cmd, input=message_line(req) + chr(10), capture_output=True, text=True, encoding="utf-8",
                       timeout=TIMEOUT_S, cwd=folder)
        except Exception as e:
            raise error(claude_driver.failure_message(e, TIMEOUT_S)) from e
        events = _events(proc.stdout)
        result = next((e for e in reversed(events) if e.get("type") == "result"), None)
        log_usage(json.dumps(result) if result else "", req["model"], pages=sum(
            1 for m in req["messages"] for b in m["content"] if b.get("type") == "image"))
        answer, problem = claude_driver.read_run(type("Run", (), {"stdout": json.dumps(result) if result else "",
                                                                    "returncode": proc.returncode})())
        if answer is None:
            if problem == claude_driver.NOT_LOGGED_IN:
                raise not_logged_in()
            raise error(problem)
        return json.dumps(answer, ensure_ascii=False)

    return ask
