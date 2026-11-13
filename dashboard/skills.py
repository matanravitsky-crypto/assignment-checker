"""הסקילים של הצוות בכל מחשב שמריץ את המערכת: נבנים מהקוד של המחשב הזה בכל הפעלה של השרת.

    exercise-grader   בדיקה של הגשה אחת, בדיוק כמו המערכת (grading/skill/SKILL.md, grading/one_submission.py)

השרת עולה מחדש אחרי כל עדכון מ-GitHub (dashboard/updater.py), ולכן כל חבר צוות מקבל את הסקילים כמו שהם ב-main,
בתיקיית הסקילים שלו (~/.claude/skills), ו-Claude Code מוצא אותם בכל שיחה.

  להוסיף סקיל לצוות   החלק צריך <חלק>/skill/SKILL.md, ומוסיפים אותו ל-TEAM_SKILLS. tools/extract_skill.install בונה רק
                      כשצריך: סקיל שעדכני לא נוגעים בו; סקיל שהכלי בנה ונשאר מאחור נבנה שוב; סקיל שהכלי לא בנה
                      (ה-exercise-grader הידני שעבר כ-ZIP) מועתק קודם כולו ל-~/.claude/skill-backups/ ורק אז מוחלף.
  להוריד סקיל          מוציאים אותו מ-TEAM_SKILLS. בהפעלה הבאה כל שרת מוחק אותו (extract_skill.retire), אבל רק סקיל
                      שהשרת עצמו התקין ("team" ב-MANIFEST.json): סקיל שמישהו בנה או התקין ביד לא נמחק לעולם.
                      סקיל ששמו השתנה (name: ב-SKILL.md) נמחק בשמו הישן ונבנה בחדש.
  לבדוק               tests/integration/test_every_skill.py בונה ומריץ לבד כל חלק שיש לו skill/, בלי בדיקה שנכתבה לו.

ברקע, וכישלון לא עוצר את השרת. INSTALL_SKILLS=off ב-.env מכבה את כל זה (גם את המחיקה).
"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path

from moodle import settings

TEAM_SKILLS = ["grading"]  # החלקים שהסקיל שלהם מותקן אצל כל אחד (tools/extract_skill.py)


def enabled() -> bool:
    return settings.get("INSTALL_SKILLS", "on").lower() not in ("off", "0", "no", "false")


def _error(skill: str, e: BaseException) -> dict:
    return {"skill": skill, "action": "error", "error": str(e) or traceback.format_exc(limit=1)}


def refresh(skills: Path | None = None, backups: Path | None = None) -> list[dict]:
    """מוחק סקיל של הצוות שירד מהרשימה, ובונה כל סקיל של הצוות שחסר או שנשאר מאחור.
    מחזיר מה נעשה לכל אחד ({"skill", "action", ...} או "error")."""
    from tools import extract_skill  # כלי המפתחים שבונה סקיל מהקוד כמו שהוא

    out = []
    try:  # שם שאי אפשר לקרוא (SKILL.md חסר) עוצר את המחיקה כולה: לא מוחקים לפי רשימה חלקית
        keep = [extract_skill.skill_name(part) for part in TEAM_SKILLS]
        out += extract_skill.retire(keep, skills)
    except (Exception, SystemExit) as e:  # noqa: BLE001  (extract_skill מסרב ב-SystemExit)
        out.append(_error("retire", e))
    for part in TEAM_SKILLS:
        try:
            out.append(extract_skill.install(part, skills, backups, team=True))
        except (Exception, SystemExit) as e:  # noqa: BLE001
            out.append(_error(part, e))
    return out


def _run() -> None:
    for r in refresh():
        if r["action"] == "error":
            print(f"הסקיל {r['skill']} לא עודכן: {r['error']}")
        elif r["action"] != "up_to_date":
            print(f"הסקיל {r['skill']}: {r['action']} ({r['path']})"
                  + (f", הקודם נשמר ב-{r['backup']}" if r.get("backup") else ""))


def start() -> None:
    """בהפעלת השרת: מעדכן את הסקילים ברקע, אם לא כבו (INSTALL_SKILLS=off)."""
    if enabled():
        threading.Thread(target=_run, name="team-skills", daemon=True).start()
