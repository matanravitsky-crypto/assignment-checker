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
# אם בתוך תיקיית הקורס יש תיקייה בשם הזה, המערכת עובדת בתוכה ולא נוגעת בשאר התיקייה של המרצה
SYSTEM_SUBFOLDER = "מערכת בדיקת תרגילים"

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


def _is_course_folder(name: str) -> bool:
    return name == FOLDER_NAME or name.endswith(f" - {FOLDER_NAME}") or name.startswith(f"{FOLDER_NAME} - ")


def _system_dir(course_folder: Path) -> Path:
    sub = course_folder / SYSTEM_SUBFOLDER
    return sub if sub.is_dir() else course_folder


def find_root() -> Path:
    """מחזיר את תיקיית הקורס ב-OneDrive, או זורק FolderNotFound עם הסבר מה לעשות."""
    explicit = os.environ.get("ASSIGNMENT_CHECKER_ROOT")
    if explicit:
        path = Path(explicit)
        if not path.is_dir():
            raise FolderNotFound(f"ASSIGNMENT_CHECKER_ROOT מצביע על תיקייה שלא קיימת: {path}")
        return _system_dir(path)

    # "Add shortcut to My files" שם את התיקייה בתוך OneDrive של האוניברסיטה.
    # הכפתור "Sync" שם אותה בתיקייה בשם הארגון, למשל
    # C:\Users\<שם>\Ben-Gurion University of the Negev\נדב מאיר - YallaLinearit
    home = Path.home()
    bases = onedrive_roots() + sorted(
        p for p in home.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in ("AppData", "Downloads", "Desktop", "Documents")
    )
    for base in bases:
        try:
            children = [base, *(c for c in base.iterdir() if c.is_dir())]
        except OSError:
            continue
        for folder in children:
            if folder.is_dir() and _is_course_folder(folder.name):
                return _system_dir(folder)
            try:
                for sub in folder.iterdir():
                    if sub.is_dir() and _is_course_folder(sub.name):
                        return _system_dir(sub)
            except OSError:
                continue

    searched = "\n".join(f"  - {r}" for r in onedrive_roots()) or "  (לא נמצאה אף תיקיית OneDrive)"
    raise FolderNotFound(
        f"לא מצאתי את התיקייה {FOLDER_NAME} במחשב.\n"
        f"חיפשתי ב:\n{searched}\n\n"
        "מה לעשות:\n"
        f"  1. בדפדפן, בתוך התיקייה {FOLDER_NAME}, ללחוץ על Sync (בשורת הכפתורים העליונה).\n"
        "  2. אם נפתח חלון של OneDrive, להתחבר עם חשבון האוניברסיטה ולאשר בטלפון.\n"
        "  3. לחכות דקה שהתיקייה תופיע במחשב, ולהריץ שוב.\n"
        "אפשר גם להגדיר נתיב ידנית במשתנה הסביבה ASSIGNMENT_CHECKER_ROOT."
    )
