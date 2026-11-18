"""The check after every return is prepared (send.prepare_batch): no student gets another student's file or grade.

The one way a wrong file can reach a student is through the key table (number -> Moodle participant id), and the
ZIPs are built from it. So this does not trust the code that packed them: it reads the ZIPs that were just written,
the key, the marked files and the filled worksheet again from the disk, and compares, by number and participant id
only (never a name):
- every folder in a ZIP names a participant id that the key gives exactly one number, and the folder is exactly the
  one the key has for that number (Moodle matches the student by it);
- the feedback file inside it has exactly the bytes of that number's marked file ("2 - Graded with comments");
- the grade in the filled worksheet ("Grades for Moodle worksheet.csv", when one was filled) for that participant is
  that number's merged grade;
- no number and no file twice across the ZIPs, nothing the batch lists is missing, every ZIP holds exactly the files
  the batch lists for it, and every ZIP is under Moodle's limit.
One failure raises ReturnCheckFailed, and prepare_batch then removes the batch: nothing is "ready to upload".
The result goes to "Return check.json" (numbers) and "Return check.txt" (Hebrew) in the assignment folder.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

from moodle import anonymize, grades, paths, upload, upload_log

CHECK_FILE = paths.RETURN_CHECK
REPORT_FILE = paths.RETURN_REPORT
FEEDBACK = "feedback"  # the name inside the ZIP (Moodle skips a file identical to the submission, upload.plan_parts)


class ReturnCheckFailed(Exception):
    """A file or a grade could reach the wrong student: the batch must not be uploaded."""


def _key(assignment_dir: Path) -> tuple[dict[str, str], dict[str, set[str]], dict[str, str]]:
    """(number -> participant id, participant id -> numbers, number -> original folder), read from the key itself."""
    number_pid: dict[str, str] = {}
    pid_numbers: dict[str, set[str]] = {}
    folders: dict[str, str] = {}
    with open(assignment_dir / paths.KEY, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            n, pid = row["number"], row["participant_id"]
            number_pid.setdefault(n, pid)
            pid_numbers.setdefault(pid, set()).add(n)
            folders.setdefault(n, row["original_folder"])
    return number_pid, pid_numbers, folders


def _num(text: str | None) -> float | None:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def _worksheet_grades(path: Path) -> dict[str, str] | None:
    """participant id -> the grade cell of the filled worksheet, or None when there is no worksheet."""
    if not path.exists():
        return None
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return None
    grade_col = upload.find_column(rows[0], upload.GRADE_HEADERS)
    out = {}
    for row in rows[1:]:
        if row and row[0].strip():
            out[upload.participant_from_identifier(row[0])] = row[grade_col] if grade_col < len(row) else ""
    return out


def check(assignment_dir: Path, batch: dict, max_bytes: int) -> dict:
    """Verify the batch's ZIPs on the disk. Returns the report (numbers only); raises ReturnCheckFailed."""
    folder = upload_log.batch_folder(assignment_dir, batch)
    if folder is None or not folder.is_dir():
        raise ReturnCheckFailed("the batch's folder is missing")
    number_pid, pid_numbers, key_folders = _key(assignment_dir)
    merged = grades.to_moodle(assignment_dir, grades.read(assignment_dir))  # the grade Moodle gets (course policy)
    worksheet = _worksheet_grades(assignment_dir / paths.UPLOAD / paths.GRADES_WORKSHEET)
    marked_dir = assignment_dir / paths.MARKED

    seen: set[tuple[str, str]] = set()
    expected: set[tuple[str, str]] = set()
    zips_out, grades_matched, grades_blank = [], 0, 0
    numbers_checked: set[str] = set()
    for z in batch.get("zips", []):
        path = folder / z["name"]
        listed = {(f["number"], f["file"]) for f in z.get("files", [])}
        expected |= listed
        if not path.is_file():
            raise ReturnCheckFailed(f"{z['name']}: the ZIP is missing")
        size = path.stat().st_size
        with zipfile.ZipFile(path) as archive:
            entries = [i for i in archive.infolist() if not i.is_dir()]
            if len(entries) != len(listed):
                raise ReturnCheckFailed(f"{z['name']}: holds {len(entries)} files, the batch lists {len(listed)}")
            # The limit is on the files' own bytes, as plan_parts split them (the ZIP adds a few bytes per file; the
            # default limit keeps 20 MB under Moodle's)
            inside = sum(i.file_size for i in entries)
            if inside > max_bytes:
                raise ReturnCheckFailed(f"{z['name']}: {inside / 1_000_000:.1f} MB of files is over the limit of {max_bytes / 1_000_000:.0f} MB")
            for info in entries:
                folder_name, _, file_name = info.filename.replace("\\", "/").rpartition("/")
                if not folder_name or "/" in folder_name:
                    raise ReturnCheckFailed(f"{z['name']}: a file is not in a student's folder")
                try:
                    pid = anonymize.parse_folder(folder_name)
                except ValueError:
                    raise ReturnCheckFailed(f"{z['name']}: a folder without a participant id") from None
                numbers = pid_numbers.get(pid, set())
                if len(numbers) != 1:
                    raise ReturnCheckFailed(f"participant {pid} has {len(numbers)} numbers in the key")
                number = next(iter(numbers))
                if key_folders.get(number) != folder_name:
                    raise ReturnCheckFailed(f"number {number}: the folder in the ZIP is not the one the key has")
                if not file_name.startswith(FEEDBACK):
                    raise ReturnCheckFailed(f"number {number}: a file that is not a feedback file ({file_name})")
                marked_name = number + file_name[len(FEEDBACK):]
                marked = marked_dir / marked_name
                if not marked.is_file():
                    raise ReturnCheckFailed(f"number {number}: no marked file {marked_name}")
                if hashlib.sha256(archive.read(info)).hexdigest() != upload_log.file_hash(marked):
                    raise ReturnCheckFailed(f"number {number}: the file in the ZIP is not the marked file {marked_name}")
                if (number, marked_name) in seen:
                    raise ReturnCheckFailed(f"number {number}: {marked_name} is in the ZIPs twice")
                if (number, marked_name) not in listed:
                    raise ReturnCheckFailed(f"number {number}: {marked_name} is in {z['name']} but not in its list")
                seen.add((number, marked_name))
                if worksheet is not None and number not in numbers_checked:
                    cell = worksheet.get(pid, "")
                    ours = _num((merged.get(number) or {}).get("grade"))
                    if cell.strip():
                        if ours is None or _num(cell) != ours:
                            raise ReturnCheckFailed(f"number {number}: the grade in the worksheet is not this number's grade")
                        grades_matched += 1
                    else:
                        grades_blank += 1
                numbers_checked.add(number)
        zips_out.append({"name": z["name"], "files": len(entries), "mb": round(size / 1_000_000, 1)})
    if expected - seen:
        raise ReturnCheckFailed(f"{len(expected - seen)} files the batch lists are not in the ZIPs")
    return {"ok": True, "batch": batch.get("id"), "zips": zips_out, "students": len(numbers_checked),
            "files": len(seen), "grades_matched": grades_matched, "grades_blank": grades_blank,
            "worksheet": worksheet is not None, "limit_mb": max_bytes // 1_000_000}


def report_text(report: dict) -> str:
    """The same, in Hebrew, for the person who uploads."""
    lines = [f"אימות ההחזרה: {report.get('checked_at', '')}", "=" * 20,
             f"{report['students']} סטודנטים, {report['files']} קבצים, {len(report['zips'])} ZIP (עד {report['limit_mb']} MB כל אחד)."]
    for z in report["zips"]:
        lines.append(f"  {z['name']}: {z['files']} קבצים, {z['mb']} MB")
    lines += ["",
              "נבדק מחדש מהדיסק, לכל קובץ בכל ZIP:",
              "  התיקייה ב-ZIP היא בדיוק התיקייה שטבלת המפתח נותנת למספר הזה, ולמזהה המשתתף שבה יש מספר אחד בלבד.",
              "  הקובץ זהה בייט לבייט לעבודה המסומנת של אותו מספר ב-\"" + paths.MARKED + "\".",
              "  אף מספר ואף קובץ לא פעמיים, שום דבר מהרשימה לא חסר, וכל ZIP מתחת לגבול."]
    if report.get("worksheet"):
        lines.append(f"  הציון בגיליון של מודל: {report['grades_matched']} ציונים זהים לציון של המספר שלהם"
                     + (f", {report['grades_blank']} סטודנטים בלי ציון בגיליון" if report.get("grades_blank") else "") + ".")
    else:
        lines.append("  גיליון ציונים לא מולא בהכנה הזו (אין גיליון של מודל ב-Downloads), ולכן הציונים לא נבדקו.")
    lines += ["", "תוצאה: עבר. אפשר להעלות לפי Upload steps.txt. הפירוט במספרים: " + CHECK_FILE]
    return "\n".join(lines) + "\n"


def write(assignment_dir: Path, report: dict) -> None:
    report = {"checked_at": datetime.now().isoformat(timespec="seconds"), **report}
    tmp = assignment_dir / (CHECK_FILE + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, assignment_dir / CHECK_FILE)
    (assignment_dir / REPORT_FILE).write_text(report_text(report), encoding="utf-8-sig")


def read(assignment_dir: Path) -> dict | None:
    try:
        return json.loads((assignment_dir / CHECK_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
