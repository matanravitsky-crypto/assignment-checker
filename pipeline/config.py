"""איפה נמצאת תיקיית OneDrive של הקורס, ואיך היא בנויה.

המערכת לא מדברת עם OneDrive דרך האינטרנט. היא כותבת לתיקייה שמסונכרנת למחשב
(דרך אפליקציית OneDrive), ו-OneDrive מעלה את הקבצים לענן לבד.

איך מוצאים את התיקייה, לפי הסדר:
1. משתנה הסביבה ASSIGNMENT_CHECKER_ROOT, אם הוגדר (נתיב מלא לתיקייה).
2. תיקייה בשם YallaLinearit בתוך אחת מתיקיות OneDrive של המחשב
   (למשל C:\\Users\\<שם>\\OneDrive - Ben-Gurion University of the Negev\\YallaLinearit).
"""
from __future__ import annotations

import os
from pathlib import Path

FOLDER_NAME = "YallaLinearit"

# שמות התיקיות בתוך כל מטלה. המספר בתחילת השם שומר על הסדר של השלבים.
INBOX = "0-קליטה"          # כאן שמים את קובץ ה-ZIP שהורד ממודל
INBOX_DONE = "נקלטו"        # תת-תיקייה: קבצי ZIP שכבר נקלטו
SUBMISSIONS = "1-הגשות"     # תיקייה לכל סטודנט עם הקבצים המקוריים
CHECKED = "2-נבדקו"         # ה-PDF המסומן אחרי הבדיקה
RETURNED = "3-הוחזרו"       # מה שכבר הועלה חזרה למודל
GRADES_FILE = "ציונים.xlsx"
LOG_FILE = "יומן.txt"


class FolderNotFound(Exception):
    pass


def onedrive_roots() -> list[Path]:
    """כל תיקיות OneDrive שמסונכרנות למחשב הזה."""
    roots: list[Path] = []
    for var in ("OneDriveCommercial", "OneDrive", "OneDriveConsumer"):
        value = os.environ.get(var)
        if value and Path(value).is_dir():
            roots.append(Path(value))
    home = Path.home()
    roots += sorted(p for p in home.glob("OneDrive*") if p.is_dir())
    unique: list[Path] = []
    for p in roots:
        if p.resolve() not in [u.resolve() for u in unique]:
            unique.append(p)
    return unique


def find_root() -> Path:
    """מחזיר את תיקיית הקורס ב-OneDrive, או זורק FolderNotFound עם הסבר מה לעשות."""
    explicit = os.environ.get("ASSIGNMENT_CHECKER_ROOT")
    if explicit:
        path = Path(explicit)
        if not path.is_dir():
            raise FolderNotFound(f"ASSIGNMENT_CHECKER_ROOT מצביע על תיקייה שלא קיימת: {path}")
        return path

    for root in onedrive_roots():
        for candidate in (root / FOLDER_NAME, *root.glob(f"*/{FOLDER_NAME}")):
            if candidate.is_dir():
                return candidate

    searched = "\n".join(f"  - {r}" for r in onedrive_roots()) or "  (לא נמצאה אף תיקיית OneDrive)"
    raise FolderNotFound(
        f"לא מצאתי את התיקייה {FOLDER_NAME} במחשב.\n"
        f"חיפשתי ב:\n{searched}\n\n"
        "מה לעשות:\n"
        "  1. באפליקציית OneDrive: הגדרות → חשבון → הוסף חשבון, ולהתחבר עם חשבון האוניברסיטה.\n"
        f"  2. בדפדפן, על התיקייה {FOLDER_NAME}: Add shortcut to My files.\n"
        "  3. לחכות דקה שהתיקייה תופיע במחשב, ולהריץ שוב.\n"
        "אפשר גם להגדיר נתיב ידנית במשתנה הסביבה ASSIGNMENT_CHECKER_ROOT."
    )
