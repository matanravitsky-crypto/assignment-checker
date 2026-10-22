"""Build what goes back to Moodle from results kept by number.

Inputs in the assignment folder:
    Grades.csv                        columns: number, grade, feedback (feedback may be empty)
    2 - Graded with comments/         marked files named by number: 0001.pdf, 0001-2.pdf, ...
    the grading worksheet, downloaded from Moodle (Actions > Download grading
    worksheet; needs "Offline grading worksheet" on in the assignment settings)

Outputs in "3 - Ready to upload to Moodle/":
    Grades for Moodle worksheet.csv   the worksheet with grades and feedback filled in
                                      -> Moodle: Actions > Upload grading worksheet
    Graded - part 01.zip ...          one folder per student, named as in Moodle's
                                      download, each ZIP under the upload limit
                                      -> Moodle: Actions > Upload multiple feedback files in a zip
    Upload steps.txt                  step-by-step in Hebrew for whoever uploads (TA or lecturer)

Nothing here talks to Moodle: a person uploads, and confirms Moodle's list
of which file goes to which student before it imports.
"""

import csv
import re
import zipfile
from pathlib import Path

from moodle import anonymize, paths

# The worksheet's headers follow the Moodle language the user downloaded it in
GRADE_HEADERS = {"Grade", "ציון"}
FEEDBACK_HEADERS = {"Feedback comments", "הערות למשוב", "משוב"}

# BGU Moodle takes up to 31 MB per upload on the feedback ZIP page; leave some room
MAX_ZIP_BYTES = 30_000_000
# When Claude uploads through Claude in Chrome, each file can be at most 10 MB
CLAUDE_MAX_ZIP_BYTES = 9_000_000

INSTRUCTIONS_FILE = "Upload steps.txt"
GRADES_FOR_MOODLE = "Grades for Moodle worksheet.csv"
ZIP_PREFIX = "Graded - part"


def find_worksheet(assignment_id: str, downloads: Path | None = None) -> Path | None:
    """Return the newest grading worksheet for this assignment in Downloads, if any."""
    downloads = downloads or Path.home() / "Downloads"
    sheets = [p for p in downloads.glob("*.csv") if p.stem.endswith(f"-{assignment_id}")]
    return max(sheets, key=lambda p: p.stat().st_mtime) if sheets else None


def read_results(assignment_dir: Path) -> dict[str, dict]:
    with open(assignment_dir / paths.GRADES, encoding="utf-8-sig") as f:
        return {f"{int(row['number']):04d}": row for row in csv.DictReader(f)}


def participant_from_identifier(identifier: str) -> str:
    """'Participant 13464355' or 'משתתף 13464355' -> '13464355'."""
    match = re.search(r"(\d+)\s*$", identifier.strip())
    if not match:
        raise ValueError(f"No participant id in worksheet identifier {identifier!r}")
    return match.group(1)


def find_column(header: list[str], names: set[str]) -> int:
    for index, name in enumerate(header):
        if name.strip() in names:
            return index
    raise ValueError(f"Worksheet has none of {sorted(names)}; its columns are {header}")


def fill_worksheet(worksheet: Path, out: Path, results: dict, mapping: dict) -> int:
    """Write the worksheet with grades filled in. Returns how many rows were filled."""
    by_participant = {mapping[n]["participant_id"]: r for n, r in results.items() if n in mapping}

    with open(worksheet, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    grade_col = find_column(header, GRADE_HEADERS)
    feedback_col = find_column(header, FEEDBACK_HEADERS)

    filled = 0
    for row in body:
        result = by_participant.get(participant_from_identifier(row[0]))
        if result is None:
            continue
        row[grade_col] = result["grade"]
        row[feedback_col] = result.get("feedback", "")
        filled += 1

    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([header, *body])
    return filled


def build_feedback_zips(
    marked: Path, upload: Path, mapping: dict, max_bytes: int = MAX_ZIP_BYTES
) -> tuple[list[Path], list[str]]:
    """Zip marked files under each student's original Moodle folder name.

    Moodle limits each upload, so the files are split into numbered parts
    ("Graded - part 01.zip", ...), each under max_bytes. Moodle adds each
    upload to the earlier ones. Files bigger than max_bytes on their own can't
    go through Moodle at all; they are returned by name to be saved smaller.
    """
    for old in upload.glob(f"{ZIP_PREFIX} *.zip"):
        old.unlink()

    parts: list[list[tuple[Path, str]]] = [[]]
    too_big = []
    size = 0
    for file in sorted(marked.iterdir()):
        match = re.match(r"^(\d{4})(-\d+)?$", file.stem)
        if not file.is_file() or not match:
            continue
        row = mapping.get(match.group(1))
        if row is None:
            raise ValueError(f"{file.name}: number {match.group(1)} is not in the key table")
        file_size = file.stat().st_size
        if file_size > max_bytes:
            too_big.append(file.name)
            continue
        if parts[-1] and size + file_size > max_bytes:
            parts.append([])
            size = 0
        # Moodle skips files identical to the submission, so give them a new name
        name = f"feedback{match.group(2) or ''}{file.suffix.lower()}"
        parts[-1].append((file, f"{row['original_folder']}/{name}"))
        size += file_size

    zips = []
    for index, files in enumerate(p for p in parts if p):
        out = upload / f"{ZIP_PREFIX} {index + 1:02d}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            for file, arcname in files:
                archive.write(file, arcname)
        zips.append(out)
    return zips, too_big


def write_instructions(out: Path, report: dict, max_bytes: int) -> None:
    """Plain Hebrew steps for whoever uploads, with this run's numbers."""
    zips = report["feedback_zips"]
    limit_mb = max_bytes // 1_000_000
    lines = [
        "העלאת הבדיקות למודל",
        "=" * 20,
        "",
        f"הגשות: {report['submissions']}. ציונים: {report['results']}. קבצי ZIP של עבודות בדוקות: {len(zips)}.",
        "",
        "שלב 1: עבודות בדוקות עם הערות",
        "במודל, במטלה: הגשות ← פעולות ← \"העלאת מספר קובצי משוב כקובץ 7Zip אחד\".",
        f"מעלים כל קובץ בנפרד, לפי הסדר (מודל מקבל עד {limit_mb} MB בכל העלאה):",
    ]
    lines += [f"  [ ] {z.name}  ({z.stat().st_size / 1_000_000:.1f} MB)" for z in zips]
    lines += [
        "אחרי כל העלאה מודל מציג רשימה: איזה קובץ הולך לאיזה סטודנט.",
        "בודקים שמספר השורות תואם, ולוחצים אישור. כל העלאה מוסיפה לקודמות ולא מוחקת אותן.",
        "",
    ]
    if report["too_big"]:
        lines += [
            f"לא נכנסו ({len(report['too_big'])}), כי כל אחד מהם גדול מ-{limit_mb} MB:",
            "  " + ", ".join(report["too_big"]),
            "צריך לשמור אותם מחדש בגודל קטן יותר ולהריץ שוב את ההכנה.",
            "",
        ]
    lines.append("שלב 2: ציונים")
    if report["grades_filled"] is None:
        lines.append("עוד לא מוכן: צריך להוריד ממודל את גיליון הציונים (Offline grading worksheet) ולהריץ שוב את ההכנה.")
    else:
        lines += [
            f"\"{GRADES_FOR_MOODLE}\" מוכן ({report['grades_filled']} ציונים).",
            f"במודל: הגשות ← פעולות ← \"העלאת גיליון ציונים\" ← בוחרים \"{GRADES_FOR_MOODLE}\" ← בודקים את התצוגה המקדימה ← אישור.",
        ]
    if report["missing_results"]:
        lines += ["", f"שימו לב: {len(report['missing_results'])} הגשות עוד בלי ציון: {', '.join(report['missing_results'][:30])}"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def prepare_upload(assignment_dir: Path, worksheet: Path | None = None, max_bytes: int = MAX_ZIP_BYTES) -> dict:
    mapping = anonymize.read_mapping(assignment_dir)
    results = read_results(assignment_dir)
    upload = assignment_dir / paths.UPLOAD
    upload.mkdir(exist_ok=True)

    report = {
        "submissions": len(mapping),
        "results": len(results),
        "missing_results": sorted(set(mapping) - set(results)),
        "unknown_numbers": sorted(set(results) - set(mapping)),
        "grades_filled": None,
        "feedback_zips": [],
        "too_big": [],
    }
    if worksheet:
        report["grades_filled"] = fill_worksheet(worksheet, upload / GRADES_FOR_MOODLE, results, mapping)
    marked = assignment_dir / paths.MARKED
    if marked.is_dir():
        report["feedback_zips"], report["too_big"] = build_feedback_zips(marked, upload, mapping, max_bytes)
    write_instructions(upload / INSTRUCTIONS_FILE, report, max_bytes)
    return report
