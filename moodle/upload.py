"""Build what goes back to Moodle from results kept by number.

Inputs in <assignment>/:
    results.csv   columns: number, grade, feedback (feedback may be empty)
    marked/       marked files named by number: 0001.pdf, 0001-2.pdf, ...
    the grading worksheet, downloaded from Moodle (Actions > Download grading
    worksheet; needs "Offline grading worksheet" on in the assignment settings)

Outputs in <assignment>/upload/:
    grades.csv    the worksheet with grades and feedback filled in
                  -> Moodle: Actions > Upload grading worksheet
    feedback-1.zip, feedback-2.zip, ...
                  one folder per student, named as in Moodle's download,
                  each ZIP under 10 MB
                  -> Moodle: Actions > Upload multiple feedback files in a zip

Nothing here talks to Moodle: uploading is a separate, approved step.
"""

import csv
import re
import zipfile
from pathlib import Path

from moodle import anonymize

# The worksheet's headers follow the Moodle language the user downloaded it in
GRADE_HEADERS = {"Grade", "ציון"}
FEEDBACK_HEADERS = {"Feedback comments", "הערות למשוב", "משוב"}

# Claude in Chrome's file upload takes up to 10 MB per call; leave some room
MAX_ZIP_BYTES = 9_000_000


def find_worksheet(assignment_id: str, downloads: Path | None = None) -> Path | None:
    """Return the newest grading worksheet for this assignment in Downloads, if any."""
    downloads = downloads or Path.home() / "Downloads"
    sheets = [p for p in downloads.glob("*.csv") if p.stem.endswith(f"-{assignment_id}")]
    return max(sheets, key=lambda p: p.stat().st_mtime) if sheets else None


def read_results(assignment_dir: Path) -> dict[str, dict]:
    with open(assignment_dir / "results.csv", encoding="utf-8-sig") as f:
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

    Claude in Chrome uploads at most 10 MB at a time, so the files are split
    into feedback-1.zip, feedback-2.zip, ... each under max_bytes. Moodle adds
    each upload to the earlier ones. Files too big for any ZIP are returned by
    name to be uploaded by hand.
    """
    for old in upload.glob("feedback-*.zip"):
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
            raise ValueError(f"{file.name}: number {match.group(1)} is not in mapping.csv")
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
        out = upload / f"feedback-{index + 1}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            for file, arcname in files:
                archive.write(file, arcname)
        zips.append(out)
    return zips, too_big


def prepare_upload(assignment_dir: Path, worksheet: Path | None = None) -> dict:
    mapping = anonymize.read_mapping(assignment_dir)
    results = read_results(assignment_dir)
    upload = assignment_dir / "upload"
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
        report["grades_filled"] = fill_worksheet(worksheet, upload / "grades.csv", results, mapping)
    marked = assignment_dir / "marked"
    if marked.is_dir():
        report["feedback_zips"], report["too_big"] = build_feedback_zips(marked, upload, mapping)
    return report
