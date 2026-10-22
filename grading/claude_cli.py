"""בדיקה דרך Claude Code (הפקודה claude), כשאין ANTHROPIC_API_KEY.

Claude Code מחובר במחשב עם החשבון של הצוות (כמו בהעלאה למודל), ולכן אפשר לבדוק בלי מפתח API:
הבדיקה נספרת במנוי של Claude ולא מחויבת בנפרד. לכל הגשה רצה ריצה אחת נעולה של

    claude -p --tools "" --input-format stream-json --json-schema <SCHEMA> ...

מה הריצה מקבלת:
- תמונות העמודים (והפתרון הרשמי, אם נשלח) בתוך ההודעה עצמה, ב-stdin, כמו בקריאה ל-API. Claude לא קורא שום
  קובץ, ולכן אין לו שום כלי: בלי Read, Bash, Edit, Write, בלי כרום ובלי שרתי MCP. כך הכל קורה בתור אחד, במקום
  תור לכל עמוד שבו Claude קורא מחדש את כל מה שכבר נשלח.
- ההנחיות (SYSTEM של grade.py) ופרטי המטלה שמשותפים לכל ההגשות (השאלות, המחוון, התיקייה הפדגוגית) ב-system prompt,
  שאותו Claude Code שומר במטמון: מההגשה השנייה והלאה הם נקראים מהמטמון בזול, במקום להיכתב אליו מחדש בכל הגשה.
- תיקייה זמנית חדשה מחוץ ל-OneDrive, ריקה חוץ מקובץ ה-system prompt. היא תיקיית העבודה, ונמחקת בסוף.
  טבלת המפתח והשמות לא מגיעים לשם לעולם.
- --setting-sources project בתיקייה ריקה: בלי ההגדרות, ה-hooks והתוספים של המשתמש.

החוזה זהה ל-claude_ask של grade.py: מקבלים את הבקשה שבנה build_request ומחזירים טקסט JSON בסכמה SCHEMA.
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

# השלב האחרון ב-READ_STEPS של grade.py: אותן תמונות בגודל המלא, עם בקשה לעבור עליהן עמוד אחרי עמוד
READ_ONE_BY_ONE = ("עבור על העמודים אחד אחרי השני, לפי הסדר, ובדוק כל עמוד בתשומת לב לפני שאתה עונה: "
                   "בפעם הקודמת חלק מהעבודה לא היה קריא.")


def available() -> bool:
    """Claude Code מותקן ומחובר במחשב הזה."""
    return claude_driver.find_claude() is not None and claude_driver.auth_status()["logged_in"] is True


def split_request(req: dict) -> tuple[str, list[dict]]:
    """(ה-system prompt, התוכן של ההודעה). מה שמסומן ב-cache_control משותף לכל ההגשות, ולכן עובר ל-system prompt."""
    system = [req.get("system") or ""]
    content = []
    for message in req["messages"]:
        for block in message["content"]:
            if block.get("cache_control") and block.get("type") == "text":
                system.append(block["text"])
            else:
                content.append({k: v for k, v in block.items() if k != "cache_control"})
    if req.get("_one_by_one"):
        content.append({"type": "text", "text": READ_ONE_BY_ONE})
    return "\n\n".join(t for t in system if t), content


def build_command(claude: str, system_file: Path, schema: dict, model: str, effort: str | None) -> list[str]:
    cmd = [
        claude, "-p",
        "--no-chrome",
        "--no-session-persistence",
        "--setting-sources", "project",       # התיקייה הזמנית ריקה: בלי ההגדרות וה-hooks של המשתמש
        "--strict-mcp-config",                # בלי שרתי MCP
        "--tools", "",                        # בלי שום כלי: הכל כבר בהודעה. --allowedTools לבד לא מגביל
        "--system-prompt-file", str(system_file),
        "--input-format", "stream-json",      # ההודעה, עם התמונות, ב-stdin
        "--output-format", "stream-json", "--verbose",
        "--max-budget-usd", str(BUDGET_USD),
        "--json-schema", json.dumps(schema, separators=(",", ":")),
        "--model", model,
    ]
    if effort:
        cmd += ["--effort", effort]
    return cmd


def output_as_list(stdout: str | None) -> str:
    """stream-json הוא שורת JSON לכל הודעה. claude_driver.read_answer מקבל רשימה כזו ומוצא בה את ה-result."""
    lines = []
    for line in (stdout or "").splitlines():
        try:
            lines.append(json.loads(line))
        except ValueError:
            continue
    return json.dumps(lines, ensure_ascii=False) if lines else (stdout or "")


def cli_ask(claude: str, schema: dict, effort: str | None = None, run=subprocess.run,
            error: type[Exception] = RuntimeError, not_logged_in: type[Exception] = RuntimeError):
    """Ask (ראו grade.py) שרץ דרך Claude Code. `error` ו-`not_logged_in` הם סוגי השגיאות של grade.py."""

    def ask(req: dict) -> str:
        folder = Path(tempfile.mkdtemp(prefix="grading-")).absolute()
        try:
            system, content = split_request(req)
            system_file = folder / "system.txt"
            system_file.write_text(system, encoding="utf-8", newline="\n")  # אותו טקסט בכל מחשב, כדי שהמטמון יתאים
            message = json.dumps({"type": "user", "message": {"role": "user", "content": content}}, ensure_ascii=False)
            cmd = build_command(claude, system_file, schema, req["model"], effort)
            try:
                proc = run(cmd, input=message + "\n", capture_output=True, text=True, encoding="utf-8",
                           timeout=TIMEOUT_S, cwd=folder)
            except Exception as e:
                raise error(claude_driver.failure_message(e, TIMEOUT_S)) from e
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        proc = subprocess.CompletedProcess(proc.args, proc.returncode, output_as_list(proc.stdout), proc.stderr)
        answer, problem = claude_driver.read_run(proc)
        if answer is None:
            if problem == claude_driver.NOT_LOGGED_IN:
                raise not_logged_in()
            raise error(problem)
        return json.dumps(answer, ensure_ascii=False)

    return ask
