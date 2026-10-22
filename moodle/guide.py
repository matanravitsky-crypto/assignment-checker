"""Hebrew "read me" files that explain the shared folder to whoever opens it.

The folder names stay in English because the scripts depend on them; these
files say what each one is. They are rebuilt from assignment.json, so they
stay right as assignments are added.
"""

import json
from pathlib import Path

from moodle import status

GUIDE_NAME = "קרא אותי.txt"


def read_info(assignment_dir: Path) -> dict:
    info_file = assignment_dir / "assignment.json"
    if not info_file.exists():
        return {"id": assignment_dir.name}
    with open(info_file, encoding="utf-8") as f:
        return json.load(f)


def title(info: dict) -> str:
    parts = [info.get("course"), info.get("name")]
    return " - ".join(p for p in parts if p) or "(אין פרטים: חסר assignment.json)"


def top_guide(data_dir: Path) -> str:
    assignments = sorted(p for p in (data_dir / "submissions").iterdir() if p.is_dir()) \
        if (data_dir / "submissions").is_dir() else []
    lines = [
        "מערכת בדיקת תרגילים - מבנה התיקיות",
        "=" * 34,
        "",
        "כאן נשמרות ההגשות של הסטודנטים, ממוספרות ובלי שמות, ומה שהבדיקה מחזירה.",
        "הקוד של הפרויקט נמצא ב-GitHub: https://github.com/matanravitsky-crypto/assignment-checker",
        "",
        "submissions\\        תיקייה לכל מטלה, לפי מספר המטלה במודל:",
    ]
    for folder in assignments:
        lines.append(f"  {folder.name}  =  {title(read_info(folder))}")
    lines += [
        "raw\\                קובצי ה-ZIP כמו שמודל נתן אותם (גיבוי. לא צריך לפתוח)",
        "",
        "מתחילים מתיקיית המטלה: בכל אחת יש קובץ \"קרא אותי\" שמסביר מה יש בה.",
        "",
        "כללים:",
        "- לא מעתיקים מכאן קבצים ל-GitHub (הריפו ציבורי).",
        "- רק אורי מוריד ממודל ומעלה למודל, כדי שתהיה טבלת מפתח אחת לכל מטלה.",
    ]
    return "\n".join(lines) + "\n"


def assignment_guide(assignment_dir: Path) -> str:
    info = read_info(assignment_dir)
    report = status.status(assignment_dir)
    lines = [
        title(info),
        "=" * 34,
        f"מספר המטלה במודל: {info.get('id', assignment_dir.name)}",
    ]
    if info.get("due"):
        lines.append(f"מועד הגשה: {info['due'][:16].replace('T', ' ')}")
    for question in info.get("questions") or []:
        lines.append(f"שאלות: {question['sheet']}, {', '.join(str(n) for n in question['numbers'])}")
    lines += [
        "",
        f"anon\\           {report['anon_files']} הגשות ממוספרות (0001.pdf ...). מכאן בודקים.",
        "                 0023-2.pdf = קובץ שני של אותו סטודנט.",
        "assignment.json  פרטי המטלה: שאלות, כללי הגשה, ציון מקסימלי, מחוון.",
        "mapping.csv      טבלת המפתח: איזה מספר שייך לאיזה סטודנט. לא פותחים בזמן בדיקה.",
        "",
        "מה הבדיקה מחזירה (יוצרים כאן):",
        "results.csv      עמודות number,grade,feedback - שורה לכל הגשה.",
        "marked\\         העבודה של כל סטודנט עם ההערות עליה, באותו מספר (0023.pdf). עד 1-2 MB לקובץ.",
        "upload\\         נוצר אוטומטית: מה שעולה בחזרה למודל.",
        "",
        "מצב נוכחי:",
        f"  ציונים: {'עוד אין' if report['results_rows'] is None else report['results_rows']}",
        f"  עבודות מסומנות: {report['marked_files']}",
    ]
    if info.get("notes"):
        lines += ["", f"הערה: {info['notes']}"]
    return "\n".join(lines) + "\n"


def write_guides(data_dir: Path) -> list[Path]:
    written = []
    submissions = data_dir / "submissions"
    if submissions.is_dir():
        for folder in sorted(p for p in submissions.iterdir() if p.is_dir()):
            path = folder / GUIDE_NAME
            path.write_text(assignment_guide(folder), encoding="utf-8-sig")
            written.append(path)
    path = data_dir / GUIDE_NAME
    path.write_text(top_guide(data_dir), encoding="utf-8-sig")
    written.append(path)
    return written
