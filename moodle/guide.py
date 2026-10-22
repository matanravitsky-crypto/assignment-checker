"""Hebrew "read me" files that explain the shared folder to whoever opens it.

One at the top, one per course and one per assignment. They are rebuilt from
each assignment's details file, so they stay right as assignments are added.
"""

from pathlib import Path

from moodle import paths, status


def title(folder: Path) -> str:
    """The assignment's name as Moodle shows it, in Hebrew when known."""
    return paths.read_info(folder).get("title") or folder.name


def top_guide(courses: dict[str, list[Path]]) -> str:
    lines = [
        "מערכת בדיקת תרגילים (Exercise Checking System)",
        "==============================================",
        "",
        "כאן נשמרות הגשות הסטודנטים, ממוספרות ובלי שמות, וכל מה שהבדיקה מחזירה.",
        "יש תיקייה לכל קורס, ובתוכה תיקייה לכל מטלה.",
        "",
    ]
    for course, assignments in courses.items():
        lines.append(f"{course}:")
        lines += [f"  - {folder.name}  ({title(folder)})" for folder in assignments] or ["  (עוד אין מטלות)"]
    lines += [
        "",
        f"בכל תיקיית מטלה יש קובץ {paths.README} שמסביר מה יש בה ומאיפה מתחילים.",
        "",
        "כללים:",
        "- רק אורי מוריד ממודל ומעלה למודל, כדי שתהיה טבלת מפתח אחת לכל מטלה.",
        "- לא מעתיקים מכאן קבצים ל-GitHub: הריפו של הקוד ציבורי.",
        "  הקוד: https://github.com/matanravitsky-crypto/assignment-checker",
    ]
    return "\n".join(lines) + "\n"


def course_guide(course: str, assignments: list[Path]) -> str:
    lines = [course, "=" * len(course), "", "המטלות בקורס:"]
    if not assignments:
        lines.append("  עוד אין. כל מטלה שתורד ממודל תקבל כאן תיקייה משלה, באותו מבנה כמו בשאר הקורסים.")
    for folder in assignments:
        report = status.status(folder)
        lines.append(f"  - {folder.name}  ({title(folder)}): {report['to_grade']} הגשות")
    lines += ["", f"בכל תיקיית מטלה יש קובץ {paths.README} עם הפרטים."]
    return "\n".join(lines) + "\n"


def assignment_guide(assignment_dir: Path) -> str:
    info = paths.read_info(assignment_dir)
    report = status.status(assignment_dir)
    heading = info.get("title") or info.get("name", assignment_dir.name)
    lines = [heading, "=" * len(heading), f"קורס: {info.get('course', assignment_dir.parent.name)}"]
    if info.get("due"):
        lines.append(f"מועד הגשה: {info['due'][:16].replace('T', ' ')}")
    for question in info.get("questions") or []:
        lines.append(f"שאלות: {question['sheet']}, {', '.join(str(n) for n in question['numbers'])}")
    lines.append(f"מספר המטלה במודל: {info.get('id')}")
    grades = "עוד אין" if report["grades_rows"] is None else f"{report['grades_rows']} שורות"
    lines += [
        "",
        "מה יש כאן:",
        f"  {paths.TO_GRADE}",
        f"      {report['to_grade']} הגשות, כל אחת במספר משלה (0001.pdf ...). מכאן בודקים.",
        "      0023-2.pdf = קובץ שני של אותו סטודנט.",
        f"  {paths.MARKED}",
        "      העבודה של כל סטודנט עם הערות הבודק עליה, באותו מספר (0023.pdf). עד 1-2 MB לקובץ.",
        f"  {paths.UPLOAD}",
        "      נוצר אוטומטית: מה שעולה בחזרה למודל, עם הוראות העלאה.",
        f"  {paths.INFO}",
        "      פרטי המטלה: שאלות, כללי הגשה, ציון מקסימלי, מחוון.",
        f"  {paths.GRADES}",
        "      הבדיקה כותבת לכאן: number,grade,feedback - שורה לכל הגשה.",
        f"  {paths.KEY}",
        "      איזה מספר שייך לאיזה סטודנט. לא פותחים בזמן בדיקה.",
        f"  {paths.DOWNLOAD_PREFIX} <תאריך>.zip",
        "      הקובץ כמו שהורד ממודל. גיבוי, לא צריך לפתוח.",
        "",
        "מצב נוכחי:",
        f"  עבודות לבדיקה: {report['to_grade']}",
        f"  ציונים: {grades}",
        f"  עבודות בדוקות: {report['marked']}",
    ]
    if info.get("notes"):
        lines += ["", f"הערה: {info['notes']}"]
    return "\n".join(lines) + "\n"


# Short notes inside the folders that start empty, so they're there (and clear) from day one
SUBFOLDER_NOTES = {
    paths.MARKED: "כאן שמים את העבודות אחרי הבדיקה: העבודה של הסטודנט עם ההערות עליה,\n"
                  "באותו מספר כמו ב\"" + paths.TO_GRADE + "\" (למשל 0023.pdf). עד 1-2 MB לקובץ.\n",
    paths.UPLOAD: "התיקייה מתמלאת אוטומטית כשמכינים העלאה למודל.\n"
                  "ההוראות יופיעו כאן בקובץ \"Upload steps.txt\", ומה שכבר הועלה למודל\n"
                  "ביומן \"Upload log.csv\" (מספרים בלבד, בלי שמות).\n",
}


def write_guides(data_dir: Path) -> list[Path]:
    # Every course folder, including one whose assignments haven't been downloaded yet
    courses: dict[str, list[Path]] = {p.name: [] for p in sorted(data_dir.iterdir()) if p.is_dir()} \
        if data_dir.is_dir() else {}
    for folder in paths.assignment_dirs():
        courses.setdefault(folder.parent.name, []).append(folder)

    written = []
    for course, assignments in courses.items():
        for folder in assignments:
            for subfolder, note in SUBFOLDER_NOTES.items():
                (folder / subfolder).mkdir(exist_ok=True)
                (folder / subfolder / paths.README).write_text(note, encoding="utf-8-sig")
            written.append(folder / paths.README)
            written[-1].write_text(assignment_guide(folder), encoding="utf-8-sig")
        written.append(data_dir / course / paths.README)
        written[-1].write_text(course_guide(course, assignments), encoding="utf-8-sig")
    written.append(data_dir / paths.README)
    written[-1].write_text(top_guide(courses), encoding="utf-8-sig")
    return written
