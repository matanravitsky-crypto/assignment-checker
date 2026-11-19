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
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from moodle import claude_code, paths

BUDGET_USD = 5.0
TIMEOUT_S = 900
KILL_WAIT_S = 30  # אחרי שהזמן עבר והריצה נהרגה: כמה מחכים לסוף שלה לפני שמוותרים עליה
EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp", "application/pdf": ".pdf"}

# כל העמודים בהודעה אחת (Ori #106, Noa #114): כל סבב נוסף קורא שוב את כל ההקשר מהמטמון ומוסיף זמן.
# קובץ אחרי קובץ היו כ-13 סבבים לעבודה; בבת אחת 2 עד 3
AT_ONCE = "קרא את כולם בבת אחת: בהודעה אחת, קריאת Read לכל קובץ, ולא קובץ אחרי קובץ."

READ_ALL = ("לפני שאתה עונה, קרא עם הכלי Read את כל הקבצים שברשימה: הם העמודים של ההגשה "
            "(והמכוון והפתרון הרשמי, אם הם ברשימה). " + AT_ONCE + " אל תקרא שום קובץ אחר. מספר העמוד הוא המספר "
            "שבשם הקובץ (page-03 = עמוד 3), לא מקום הקובץ ברשימה. בסוף החזר רק את התוצאה המובנית.")


# החיתוכים של מעבר הזום נקראים כמו קודם, לפי הסדר: הוא עולה כמה סנטים לעבודה, ואין סיבה לשנות בו משהו
READ_CROPS = ("לפני שאתה עונה, קרא עם הכלי Read את כל הקבצים שברשימה, לפי הסדר: הם החיתוכים (crop-01 = חיתוך 1). "
              "אל תקרא שום קובץ אחר. בסוף החזר רק את התוצאה המובנית.")

USAGE_LOG = paths.USAGE_LOG


def log_usage(stdout: str, model: str, purpose: str = "grade") -> None:
    """One line per run in the data folder: tokens and cost only (no names, no content). Never fails the grading."""
    try:
        data = json.loads(stdout)
        usage = data.get("usage") or {}
        row = {"at": datetime.now().isoformat(timespec="seconds"), "model": model, "purpose": purpose,
               "input": usage.get("input_tokens"), "output": usage.get("output_tokens"),
               "cache_read": usage.get("cache_read_input_tokens"),
               "cache_write": usage.get("cache_creation_input_tokens"),
               "turns": data.get("num_turns"), "cost_usd": data.get("total_cost_usd"),
               # זמן הריצה, כדי למדוד גם זמן ולא רק עלות לכל עבודה (docs/Token reduction plan.md, שלב ה)
               "seconds": round(data["duration_ms"] / 1000, 1) if isinstance(data.get("duration_ms"), (int, float)) else None}
        with (paths.data_dir() / USAGE_LOG).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


def available() -> bool:
    """Claude Code מותקן ומחובר במחשב הזה."""
    return claude_code.find_claude() is not None and claude_code.auth_status()["logged_in"] is True


def system_text(req: dict) -> str:
    """ה-system של הבקשה כטקסט אחד: הוראות הבדיקה, ואחריהן הטקסט המשותף של המטלה (build_request של grade.py).
    הוא זהה בכל ההגשות של המטלה, ולכן Claude Code כותב אותו למטמון פעם אחת וקורא ממנו בכל ריצה שאחריה
    (--system-prompt-file; המטמון חי כשעה מהקריאה האחרונה)."""
    system = req.get("system") or ""
    if isinstance(system, str):
        return system
    return "\n\n".join(b.get("text", "") for b in system if b.get("type") == "text")


def write_request(req: dict, folder: Path) -> str:
    """כותב לתיקייה את התמונות ואת הפתרון שבבקשה, ומחזיר את הטקסט שנשלח ל-Claude Code במקומם (ההודעה).
    רק מה שמשתנה מהגשה להגשה נמצא כאן: שמות הקבצים (התיקייה הזמנית שונה בכל ריצה) ומספרי העמודים."""
    lines: list[str] = []
    pages = docs = 0
    crops = req.get("file_prefix") == "crop"  # מעבר הזום (locate.py): חיתוכים ולא עמודים
    for message in req["messages"]:
        for block in message["content"]:
            kind = block.get("type")
            if kind == "text":
                lines.append(block["text"])
                continue
            source = block.get("source") or {}
            if kind not in ("image", "document") or source.get("type") != "base64":
                continue
            ext = EXT.get(source.get("media_type"), ".bin")
            # העמודים נקראים לפי מספר העמוד, והמסמכים בנפרד. כשהכול היה 001, 002... (הפתרון 001, עמוד 1 = 002)
            # Claude דיווח לפעמים את מספר הקובץ כמספר העמוד, והסימונים נפלו עמוד אחד מאוחר מדי (2026-11-11)
            if kind == "image" and crops:
                pages += 1
                path = folder / f"crop-{pages:02d}{ext}"
                what = f"תמונת חיתוך {pages}"
            elif kind == "image":
                pages += 1
                path = folder / f"page-{pages:02d}{ext}"
                what = f"תמונת עמוד {pages}"
            else:
                docs += 1
                path = folder / f"attachment-{docs}{ext}"
                what = block.get("title") or "קובץ"
            path.write_bytes(base64.b64decode(source["data"]))
            lines.append(f"{what}: {path}")
    lines += ["", READ_CROPS if crops else READ_ALL]
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


def _kill_tree(proc: subprocess.Popen) -> None:
    """הורג את הריצה ואת כל מה שהיא הפעילה (ב-Windows לפי עץ התהליכים, אחרת לפי קבוצת התהליכים שלה)."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=KILL_WAIT_S)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def run_bounded(cmd: list[str], *, input: str | None = None, capture_output: bool = False, timeout: float | None = None,
                **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run עם מגבלת זמן שמחזיקה. כשהזמן עבר, נהרגים הריצה וכל מה שהיא הפעילה, ואחרי זה מחכים לה עוד
    KILL_WAIT_S לכל היותר; אחר כך TimeoutExpired, כמו ב-subprocess.run.

    subprocess.run הורג רק את הריצה עצמה, וב-Windows מחכה אחרי זה בלי הגבלה עד שהפלט שלה נסגר. תהליך שהיא הפעילה
    ומחזיק אותו פתוח, או ריצה שלא מתה, עצרו כך את כל הבדיקה (2026-11-18: קריאות נתקעו יותר משעה, עם מגבלה של 15 דקות)."""
    pipes = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE} if capture_output else {}
    group = {} if sys.platform == "win32" else {"start_new_session": True}
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if input is not None else None, **pipes, **group, **kwargs)
    try:
        out, err = proc.communicate(input, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=KILL_WAIT_S)
        except subprocess.TimeoutExpired:
            pass  # משהו עוד מחזיק את הפלט או שהריצה לא מתה: מוותרים עליה ולא מחכים לנצח
        raise subprocess.TimeoutExpired(cmd, timeout) from None
    except BaseException:
        _kill_tree(proc)
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def cli_ask(claude: str, schema: dict, effort: str | None = None, run=run_bounded,
            error: type[Exception] = RuntimeError, not_logged_in: type[Exception] = RuntimeError):
    """Ask (ראו grade.py) שרץ דרך Claude Code. `error` ו-`not_logged_in` הם סוגי השגיאות של grade.py."""

    def ask(req: dict) -> str:
        folder = Path(tempfile.mkdtemp(prefix="grading-")).absolute()
        try:
            prompt = write_request(req, folder)
            system_file = folder / "system.txt"
            # אותם בייטים בכל מערכת (בלי CRLF): הקובץ הזה הוא מפתח המטמון
            system_file.write_text(system_text(req), encoding="utf-8", newline="\n")
            cmd = build_command(claude, folder, system_file, schema, req["model"], effort)
            try:
                proc = run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                           timeout=TIMEOUT_S, cwd=folder)
            except Exception as e:
                raise error(claude_code.failure_message(e, TIMEOUT_S)) from e
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        log_usage(proc.stdout, req["model"], "locate" if req.get("file_prefix") == "crop" else "grade")
        answer, problem = claude_code.read_run(proc)
        if answer is None:
            if problem == claude_code.NOT_LOGGED_IN:
                raise not_logged_in()
            raise error(problem)
        return json.dumps(answer, ensure_ascii=False)

    return ask
