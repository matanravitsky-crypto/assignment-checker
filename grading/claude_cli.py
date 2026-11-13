"""בדיקה דרך Claude Code (הפקודה claude), כשאין ANTHROPIC_API_KEY.

Claude Code מחובר במחשב עם החשבון של הצוות (כמו בהעלאה למודל), ולכן אפשר לבדוק בלי מפתח API:
הבדיקה נספרת במנוי של Claude ולא מחויבת בנפרד. לכל הגשה רצה ריצה אחת נעולה של

    claude -p --tools Read --json-schema <SCHEMA> ...

מה הריצה מקבלת:
- תיקייה זמנית חדשה מחוץ ל-OneDrive, ובה רק תמונות העמודים של ההגשה הזו (והפתרון הרשמי, אם נשלח).
  זו תיקיית העבודה שלה וה---add-dir היחיד שלה, והיא נמחקת בסוף. טבלת המפתח והשמות לא מגיעים לשם לעולם.
- כלים: Read בלבד (כדי לקרוא את התמונות). בלי Bash, Edit, Write, בלי כרום ובלי שרתי MCP.
- ההנחיות (SYSTEM של grade.py) כ---system-prompt-file, והבקשה עצמה ב-stdin (שורת פקודה ארוכה נשברת ב-Windows).
- --setting-sources project בתיקייה ריקה: בלי ההגדרות, ה-hooks והתוספים של המשתמש.

החוזה זהה ל-claude_ask של grade.py: מקבלים את הבקשה שבנה build_request ומחזירים טקסט JSON בסכמה SCHEMA.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

from moodle import claude_code, paths

BUDGET_USD = 5.0
TIMEOUT_S = 900
EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp", "application/pdf": ".pdf"}

READ_ALL = ("לפני שאתה עונה, קרא עם הכלי Read את כל הקבצים שברשימה, לפי הסדר: הם העמודים של ההגשה "
            "(והמכוון והפתרון הרשמי, אם הם ברשימה). אל תקרא שום קובץ אחר. בסוף החזר רק את התוצאה המובנית.")


def log_usage(stdout: str, model: str, seconds: float | None = None, key: str = "") -> None:
    """One line per run in the data folder: tokens, cost, how long the run took and which assignment it graded
    (its statistics key, "<course>/Assignment N"). Numbers only, no names and no content. Never fails the grading.
    The statistics database (stats/) sums these per assignment: time per work and cost per model."""
    try:
        data = json.loads(stdout)
        usage = data.get("usage") or {}
        row = {"at": datetime.now().isoformat(timespec="seconds"), "model": model,
               "input": usage.get("input_tokens"), "output": usage.get("output_tokens"),
               "cache_read": usage.get("cache_read_input_tokens"),
               "cache_write": usage.get("cache_creation_input_tokens"),
               "turns": data.get("num_turns"), "cost_usd": data.get("total_cost_usd")}
        if seconds is not None:
            row["seconds"] = round(seconds, 1)
        if key:
            row["key"] = key
        with (paths.data_dir() / paths.USAGE_LOG).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


def available() -> bool:
    """Claude Code מותקן ומחובר במחשב הזה."""
    return claude_code.find_claude() is not None and claude_code.auth_status()["logged_in"] is True


def write_request(req: dict, folder: Path) -> str:
    """כותב לתיקייה את התמונות ואת הפתרון שבבקשה, ומחזיר את הטקסט שנשלח ל-Claude Code במקומם."""
    lines: list[str] = []
    files = 0
    for message in req["messages"]:
        for block in message["content"]:
            kind = block.get("type")
            if kind == "text":
                lines.append(block["text"])
                continue
            source = block.get("source") or {}
            if kind not in ("image", "document") or source.get("type") != "base64":
                continue
            files += 1
            path = folder / f"{files:03d}{EXT.get(source.get('media_type'), '.bin')}"
            path.write_bytes(base64.b64decode(source["data"]))
            what = (block.get("title") or "קובץ") if kind == "document" else "תמונת העמוד"
            lines.append(f"{what}: {path}")
    lines += ["", READ_ALL]
    return "\n".join(lines)


def build_command(claude: str, folder: Path, system_file: Path, schema: dict, model: str,
                  effort: str | None) -> list[str]:
    cmd = [
        claude, "-p",
        "--no-chrome",
        "--no-session-persistence",
        "--setting-sources", "project",       # התיקייה הזמנית ריקה: בלי ההגדרות וה-hooks של המשתמש
        "--strict-mcp-config",                # בלי שרתי MCP
        "--tools", "Read",                    # רק קריאה של התמונות. --allowedTools לבד לא מגביל
        "--system-prompt-file", str(system_file),
        "--output-format", "json",
        "--max-budget-usd", str(BUDGET_USD),
        "--json-schema", json.dumps(schema, separators=(",", ":")),
        "--add-dir", str(folder),
        "--model", model,
    ]
    if effort:
        cmd += ["--effort", effort]
    return cmd


def cli_ask(claude: str, schema: dict, effort: str | None = None, run=subprocess.run,
            error: type[Exception] = RuntimeError, not_logged_in: type[Exception] = RuntimeError):
    """Ask (ראו grade.py) שרץ דרך Claude Code. `error` ו-`not_logged_in` הם סוגי השגיאות של grade.py."""

    def ask(req: dict) -> str:
        folder = Path(tempfile.mkdtemp(prefix="grading-")).absolute()
        try:
            prompt = write_request(req, folder)
            system_file = folder / "system.txt"
            system_file.write_text(req.get("system") or "", encoding="utf-8")
            cmd = build_command(claude, folder, system_file, schema, req["model"], effort)
            started = time.monotonic()
            try:
                proc = run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                           timeout=TIMEOUT_S, cwd=folder)
            except Exception as e:
                raise error(claude_code.failure_message(e, TIMEOUT_S)) from e
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        log_usage(proc.stdout, req["model"], time.monotonic() - started, str(req.get("assignment") or ""))
        answer, problem = claude_code.read_run(proc)
        if answer is None:
            if problem == claude_code.NOT_LOGGED_IN:
                raise not_logged_in()
            raise error(problem)
        return json.dumps(answer, ensure_ascii=False)

    return ask
