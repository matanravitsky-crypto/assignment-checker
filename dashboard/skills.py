"""הסקילים של הצוות בכל מחשב שמריץ את המערכת: נבנים מהקוד של המחשב הזה בכל הפעלה של השרת.

    exercise-grader   בדיקה של הגשה אחת, בדיוק כמו המערכת (grading/skill/SKILL.md, grading/one_submission.py)

השרת עולה מחדש אחרי כל עדכון מ-GitHub (dashboard/updater.py), ולכן כל חבר צוות מקבל את הסקיל כמו שהוא ב-main,
בתיקיית הסקילים שלו (~/.claude/skills), ו-Claude Code מוצא אותו בכל שיחה. tools/extract_skill.install בונה רק כשצריך:
סקיל שעדכני לא נוגעים בו; סקיל שהכלי בנה ונשאר מאחור נבנה שוב; סקיל שהכלי לא בנה (ה-exercise-grader הידני שעבר
כ-ZIP) מועתק קודם כולו ל-~/.claude/skill-backups/ ורק אז מוחלף. ברקע, וכישלון לא עוצר את השרת.
INSTALL_SKILLS=off ב-.env מכבה את זה.
"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path

from moodle import settings

TEAM_SKILLS = ["grading"]  # החלקים שהסקיל שלהם מותקן אצל כל אחד (tools/extract_skill.py)


def enabled() -> bool:
    return settings.get("INSTALL_SKILLS", "on").lower() not in ("off", "0", "no", "false")


def refresh(skills: Path | None = None, backups: Path | None = None) -> list[dict]:
    """בונה כל סקיל של הצוות שחסר או שנשאר מאחור. מחזיר מה נעשה לכל אחד ({"skill", "action", ...} או "error")."""
    from tools import extract_skill  # כלי המפתחים שבונה סקיל מהקוד כמו שהוא

    out = []
    for part in TEAM_SKILLS:
        try:
            out.append(extract_skill.install(part, skills, backups))
        except (Exception, SystemExit) as e:  # noqa: BLE001  (extract_skill מסרב ב-SystemExit)
            out.append({"skill": part, "action": "error", "error": str(e) or traceback.format_exc(limit=1)})
    return out


def _run() -> None:
    for r in refresh():
        if r["action"] == "error":
            print(f"הסקיל {r['skill']} לא הותקן: {r['error']}")
        elif r["action"] != "up_to_date":
            print(f"הסקיל {r['skill']}: {r['action']} ({r['path']})"
                  + (f", הקודם נשמר ב-{r['backup']}" if r.get("backup") else ""))


def start() -> None:
    """בהפעלת השרת: מעדכן את הסקילים ברקע, אם לא כבו (INSTALL_SKILLS=off)."""
    if enabled():
        threading.Thread(target=_run, name="team-skills", daemon=True).start()
