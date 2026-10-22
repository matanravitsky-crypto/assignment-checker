"""איפה נמצאת התיקייה של מערכת הבדיקה.

המערכת לא מדברת עם OneDrive דרך האינטרנט. היא קוראת וכותבת לתיקייה שמסונכרנת
למחשב (דרך אפליקציית OneDrive), ו-OneDrive מעלה את השינויים לענן לבד.

המערכת עובדת רק בתוך התיקייה של הצוות, "Exercise Checking System", שבתוך
תיקיית הקורס YallaLinearit. בשאר התיקייה של המרצה היא לא נוגעת.

איך מוצאים את התיקייה, לפי הסדר:
1. משתנה הסביבה ASSIGNMENT_CHECKER_ROOT, אם הוגדר: נתיב לתיקיית המערכת עצמה,
   או לתיקיית הקורס שהיא בתוכה.
2. חיפוש במחשב: תיקייה בשם YallaLinearit (או "<בעלים> - YallaLinearit", כפי שהכפתור
   Sync קורא לה) בתוך OneDrive, או בתיקייה בשם הארגון (למשל C:\\Users\\<שם>\\BGU).
"""
from __future__ import annotations

import os
from pathlib import Path

FOLDER_NAME = "YallaLinearit"
SYSTEM_FOLDERS = ("Exercise Checking System", "מערכת בדיקת תרגילים")


class FolderNotFound(Exception):
    pass


def onedrive_roots() -> list[Path]:
    """כל תיקיות OneDrive שמסונכרנות למחשב הזה."""
    roots: list[Path] = []
    for var in ("OneDriveCommercial", "OneDrive", "OneDriveConsumer"):
        value = os.environ.get(var)
        if value and Path(value).is_dir():
            roots.append(Path(value))
    roots += sorted(p for p in Path.home().glob("OneDrive*") if p.is_dir())
    unique: list[Path] = []
    for p in roots:
        if p.resolve() not in [u.resolve() for u in unique]:
            unique.append(p)
    return unique


def _is_course_folder(name: str) -> bool:
    return name == FOLDER_NAME or name.endswith(f" - {FOLDER_NAME}") or name.startswith(f"{FOLDER_NAME} - ")


def _system_dir(folder: Path) -> Path | None:
    for name in SYSTEM_FOLDERS:
        if (folder / name).is_dir():
            return folder / name
    return None


def _course_folders() -> list[Path]:
    home = Path.home()
    bases = onedrive_roots() + sorted(
        p for p in home.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in ("AppData", "Downloads", "Desktop", "Documents")
    )
    found = []
    for base in bases:
        try:
            level1 = [base, *(c for c in base.iterdir() if c.is_dir())]
        except OSError:
            continue
        for folder in level1:
            if _is_course_folder(folder.name):
                found.append(folder)
            try:
                found += [s for s in folder.iterdir() if s.is_dir() and _is_course_folder(s.name)]
            except OSError:
                continue
    return found


def find_root() -> Path:
    """מחזיר את תיקיית המערכת (Exercise Checking System), או זורק FolderNotFound עם הסבר."""
    explicit = os.environ.get("ASSIGNMENT_CHECKER_ROOT")
    if explicit:
        path = Path(explicit)
        if not path.is_dir():
            raise FolderNotFound(f"ASSIGNMENT_CHECKER_ROOT מצביע על תיקייה שלא קיימת: {path}")
        return _system_dir(path) or path

    courses = _course_folders()
    for folder in courses:
        system = _system_dir(folder)
        if system:
            return system

    if courses:
        raise FolderNotFound(
            f"מצאתי את תיקיית הקורס ({courses[0]}), אבל אין בה את התיקייה \"{SYSTEM_FOLDERS[0]}\".\n"
            "המערכת עובדת רק בתוך התיקייה הזו. אולי היא עוד לא הסתנכרנה: כדאי לחכות דקה ולנסות שוב."
        )
    raise FolderNotFound(
        f"לא מצאתי את התיקייה {FOLDER_NAME} במחשב.\n\n"
        "מה לעשות:\n"
        f"  1. בדפדפן, בתוך התיקייה {FOLDER_NAME}, ללחוץ על Sync (בשורת הכפתורים העליונה).\n"
        "  2. אם נפתח חלון של OneDrive, להתחבר עם חשבון האוניברסיטה ולאשר בטלפון.\n"
        "  3. לחכות דקה שהתיקייה תופיע במחשב, ולנסות שוב.\n"
        "אפשר גם להגדיר נתיב ידנית במשתנה הסביבה ASSIGNMENT_CHECKER_ROOT."
    )
