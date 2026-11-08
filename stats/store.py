"""השמירה והקריאה של קובצי הסטטיסטיקה בתיקייה המשותפת. בלי חישוב (זה compute.py).

    Exercise Checking System/
      Statistics/
        README.txt
        Linear Algebra/Assignment 0.json       (לפי מספר המקום: שם התיקייה של המטלה משתנה כשנכנסת הכותרת העברית)
        Discrete Mathematics/Assignment 0.json
        All assignments.csv

הקובץ הוא תמונת מצב נגזרת: אפשר למחוק אותו ולחשב מחדש בכל רגע. לכן:
- נכתב דרך קובץ זמני ו-os.replace, ורק כשהתוכן השתנה (בלי computed_at ו-computed_by), כדי שקריאה לא תגרום
  לכתיבה, לכתיבה אין סיבה לגרור את OneDrive, והאתר לא ייטען מחדש בלי סיבה.
- עותק מתנגש שלו (OneDrive: "Assignment 0-DESKTOP-ABC.json") נמחק: אין בו שום דבר שאי אפשר לחשב מחדש. עותקים
  מתנגשים של כל קובץ אחר (המפתח, הציונים) לא נוגעים כאן.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from moodle import paths

from . import compute

_CONFLICT = re.compile(r"^(Assignment \d+|.+)-[^-]+\.json$")  # "Assignment 0-DESKTOP-ABC.json": OneDrive's conflict copy

README = """\
סטטיסטיקה (Statistics)
======================

לכל מטלה קובץ אחד, "<קורס>/Assignment N.json", עם המספרים של הבדיקה: כמה הוגשו ונבדקו, ממוצע, חציון, סטיית תקן,
התפלגות, ולכל שאלה ממוצע, אחוז הצלחה וטעויות נפוצות; כמה מחכות לאדם ולמה; מי בדק כמה.
רק מספרים: אין מספרי הגשה, אין מזהים, אין שמות של סטודנטים.
"All assignments.csv": שורה לכל מטלה ולכל שאלה, לניתוח באקסל.

הקבצים מחושבים מהציונים ומהערות הבדיקה שבתיקיית כל מטלה, ומתעדכנים לבד אחרי כל בדיקה ואישור. אפשר למחוק אותם:
הפעם הבאה שמישהו פותח את האתר או מריץ "python -m stats rebuild" הם נבנים מחדש. עותק "-<מחשב>" שנוצר מ-OneDrive
נמחק לבד.

קוראים אותם באתר (לשונית "סטטיסטיקה") או בשורת הפקודה: python -m stats show <מזהה מטלה>
"""


def stats_dir(root: Path) -> Path:
    return Path(root) / paths.STATISTICS


def file_for(root: Path, course: str, folder: str) -> Path:
    """איפה קובץ הסטטיסטיקה של המטלה: לפי מספר המקום, ובלי מספר לפי שם התיקייה."""
    n = compute.slot(folder)
    return stats_dir(root) / course / (paths.STATS_FILE.format(n) if n is not None else f"{folder}.json")


def read_file(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _comparable(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in ("computed_at", "computed_by")}


def write(path: Path, data: dict) -> bool:
    """כותב את הסטטיסטיקה אם היא שונה ממה שבקובץ (בלי מתי ומי). מחזיר אם נכתב."""
    path = Path(path)
    current = read_file(path)
    if current is not None and _comparable(current) == _comparable(data):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    os.replace(tmp, path)
    return True


def remove_conflict_copies(path: Path) -> list[str]:
    """מוחק עותקים מתנגשים של קובץ הסטטיסטיקה הזה בלבד ("Assignment 0-<PC>.json" ליד "Assignment 0.json")."""
    path = Path(path)
    removed = []
    if not path.parent.is_dir():
        return removed
    stem = path.stem
    for p in path.parent.glob(f"{stem}-*.json"):
        if p.name != path.name and p.is_file() and _CONFLICT.match(p.name) and p.name.startswith(f"{stem}-"):
            try:
                p.unlink()
                removed.append(p.name)
            except OSError:
                pass
    return removed


def ensure_readme(root: Path) -> None:
    d = stats_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    readme = d / paths.README
    if not readme.exists():
        readme.write_text(README, encoding="utf-8-sig")
