"""הגדרות שנמצאות רק במחשב שמריץ את המערכת.

הן נשמרות בקובץ ".env" בתיקיית הריפו. הקובץ לא עולה ל-GitHub (הוא ב-.gitignore) ולא ל-OneDrive:
    ANTHROPIC_API_KEY=...
למודל אין API: ההורדה וההעלאה נעשות בדפדפן (ראו CLAUDE.md).

שמות התיקיות והקבצים בתיקייה המשותפת הם ב-moodle/paths.py. כאן: מה שכל מחשב בוחר לעצמו. כולן לא חובה:
    ASSIGNMENT_CHECKER_ROOT   תיקיית המערכת (או תיקיית הקורס), כשהיא לא נמצאת לבד (shared_folder.py)
    ASSIGNMENT_DATA           תיקיית הנתונים לשורת הפקודה; גוברת על ASSIGNMENT_CHECKER_ROOT (paths.py)
    ASSIGNMENT_WORK           התיקייה המקומית של ה-ZIP המחולץ (paths.py)
    DOWNLOADS_DIR             לאן כרום מוריד (paths.downloads_dir, ברירת מחדל ~/Downloads)
    GRADER_NAME               השם שלי בצוות (moodle/claims.py)
    GRADING_MODEL             המודל של הבדיקה (grading.default_model, ברירת מחדל grading.grade.DEFAULT_MODEL)
    MOODLE_MODEL              המודל של ההורדה וההעלאה דרך כרום (ברירת מחדל moodle/claude_driver.DEFAULT_MODEL)
    ועוד, ליד מי שקורא אותן: SCHEDULE_* (dashboard/scheduler.py), AUTO_UPDATE ו-UPDATE_CHECK_MINUTES
    (dashboard/updater.py), PUBLIC_STATUS_GIST (dashboard/public_status.py), INSTALL_SKILLS (dashboard/skills.py),
    CLAUDE_UPDATE_WAIT_S (start.bat).
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """טוען את .env מתיקיית הריפו לתוך משתני הסביבה, בלי לדרוס משתנים שכבר מוגדרים."""
    env = REPO_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def save_env(key: str, value: str) -> None:
    """כותב (או מחליף) שורה KEY=value ב-.env, ומעדכן גם את משתנה הסביבה בתהליך הזה."""
    env = REPO_DIR / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    lines = [ln for ln in lines if ln.split("=", 1)[0].strip() != key] + [f"{key}={value}"]
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value


def claude_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def get(name: str, default: str) -> str:
    """ההגדרה name מ-.env או מהסביבה, ובלעדיה default. נקראת כשמשתמשים בה (אחרי load_env), לא בייבוא."""
    return (os.environ.get(name) or "").strip() or default
