"""בדיקה דרך Claude Code (הפקודה claude), כשאין ANTHROPIC_API_KEY.

Claude Code מחובר במחשב עם החשבון של הצוות (כמו בהעלאה למודל), ולכן אפשר לבדוק בלי מפתח API:
הבדיקה נספרת במנוי של Claude ולא מחויבת בנפרד. לכל הגשה רצה ריצה אחת נעולה של

    claude -p --tools "" --input-format stream-json --json-schema <SCHEMA> ...

מה הריצה מקבלת:
- הבקשה כמו שהיא נשלחת ל-API: הטקסט, תמונות העמודים (והפתרון הרשמי, אם נשלח) כבלוקים בהודעה אחת ב-stdin
  (stream-json). כך Claude רואה את כל העמודים בתור אחד, ולא קורא אותם אחד-אחד עם כלי: כשקרא כל עמוד בתור משלו
  (2026-10-23), הגשה לקחה 17–23 תורות, וכל תור קרא שוב את כל ההקשר (כ-170 אלף טוקנים), ובערך 1.5$ להגשה.
  מה שמשותף לכל ההגשות (המחוון) מסומן למטמון, ונקרא ממנו בהגשה הבאה (ראו stream_message).
- בלי כלים בכלל (--tools ""): בלי Read, Bash, Edit, Write, בלי כרום ובלי שרתי MCP.
- תיקייה זמנית חדשה וריקה מחוץ ל-OneDrive כתיקיית העבודה (רק קובץ ההנחיות), שנמחקת בסוף.
  טבלת המפתח והשמות לא מגיעים לשם לעולם.
- ההנחיות (SYSTEM של grade.py) כ---system-prompt-file.
- --setting-sources project בתיקייה ריקה: בלי ההגדרות, ה-hooks והתוספים של המשתמש.

החוזה זהה ל-claude_ask של grade.py: מקבלים את הבקשה שבנה build_request ומחזירים טקסט JSON בסכמה שלה.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from moodle import claude_driver

BUDGET_USD = 5.0
TIMEOUT_S = 900
CACHE_TTL = "1h"


def available() -> bool:
    """Claude Code מותקן ומחובר במחשב הזה."""
    return claude_driver.find_claude() is not None and claude_driver.auth_status()["logged_in"] is True


def stream_message(req: dict) -> str:
    """ההודעה של הבקשה כשורת stream-json: אותם בלוקים כמו ב-API (טקסט, תמונה, מסמך).

    סימון המטמון שאחרי מה שמשותף לכל ההגשות נשאר, עם ttl של שעה: בלי הסימון Claude Code שומר במטמון רק את ההודעה
    כולה, ושום הגשה לא קוראת את המחוון מהמטמון של קודמתה. ובסימון של 5 דקות ה-API מסרב, כי הסימון של Claude Code
    עצמו (על ההנחיות, לפני ההודעה) הוא של שעה (נבדק 2026-10-23)."""
    content = []
    for message in req["messages"]:
        for block in message["content"]:
            if block.get("type") in ("text", "image", "document"):
                block = dict(block)
                if "cache_control" in block:
                    block["cache_control"] = {"type": "ephemeral", "ttl": CACHE_TTL}
                content.append(block)
    return json.dumps({"type": "user", "message": {"role": "user", "content": content}}, ensure_ascii=False) + "\n"


def request_schema(req: dict, default: dict) -> dict:
    """הסכמה שהבקשה עצמה מבקשת (היא תלויה במטלה: לפי שאלות או לפי סעיפים)."""
    return ((req.get("output_config") or {}).get("format") or {}).get("schema") or default


def build_command(claude: str, system_file: Path, schema: dict, model: str, effort: str | None) -> list[str]:
    cmd = [
        claude, "-p",
        "--no-chrome",
        "--no-session-persistence",
        "--setting-sources", "project",       # התיקייה הזמנית ריקה: בלי ההגדרות וה-hooks של המשתמש
        "--strict-mcp-config",                # בלי שרתי MCP
        "--tools", "",                        # בלי כלים: העמודים כבר בהודעה
        "--system-prompt-file", str(system_file),
        "--input-format", "stream-json",
        "--output-format", "stream-json", "--verbose",  # stream-json בקלט מחייב אותו גם בפלט
        "--max-budget-usd", str(BUDGET_USD),
        "--json-schema", json.dumps(schema, separators=(",", ":")),
        "--model", model,
    ]
    if effort:
        cmd += ["--effort", effort]
    return cmd


def read_stream(proc) -> tuple[dict | None, str]:
    """התשובה מתוך הפלט (שורת JSON לכל הודעה, והאחרונה מסוג result). יציאה בקוד שגיאה אף פעם לא נחשבת תשובה."""
    lines = []
    for line in (proc.stdout or "").splitlines():
        try:
            lines.append(json.loads(line))
        except ValueError:
            continue
    answer, problem = claude_driver.read_answer(json.dumps(lines) if lines else proc.stdout)
    if getattr(proc, "returncode", 0) and (answer is not None or problem == claude_driver.UNEXPECTED):
        return None, f"Claude Code נכשל (קוד יציאה {proc.returncode})."
    return answer, problem


def cli_ask(claude: str, schema: dict, effort: str | None = None, run=subprocess.run,
            error: type[Exception] = RuntimeError, not_logged_in: type[Exception] = RuntimeError):
    """Ask (ראו grade.py) שרץ דרך Claude Code. `error` ו-`not_logged_in` הם סוגי השגיאות של grade.py."""

    def ask(req: dict) -> str:
        folder = Path(tempfile.mkdtemp(prefix="grading-")).absolute()
        try:
            system_file = folder / "system.txt"
            system_file.write_text(req.get("system") or "", encoding="utf-8")
            cmd = build_command(claude, system_file, request_schema(req, schema), req["model"], effort)
            try:
                proc = run(cmd, input=stream_message(req), capture_output=True, text=True, encoding="utf-8",
                           timeout=TIMEOUT_S, cwd=folder)
            except Exception as e:
                raise error(claude_driver.failure_message(e, TIMEOUT_S)) from e
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        answer, problem = read_stream(proc)
        if answer is None:
            if problem == claude_driver.NOT_LOGGED_IN:
                raise not_logged_in()
            raise error(problem)
        return json.dumps(answer, ensure_ascii=False)

    return ask
