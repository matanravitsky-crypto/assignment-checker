"""Number Moodle submissions 0001..N so grading never sees student names.

Reads the extracted ZIP (one folder per student, as Moodle's "Download all
submissions" gives them) and writes into the assignment folder:
    1 - עבודות לבדיקה/0001.pdf ...      the files the grader gets
    טבלת מפתח - מספר לסטודנט.csv        number -> Moodle participant id and
                                        original folder; used to rebuild
                                        Moodle's names for the upload
"""

import csv
import re
import shutil
from pathlib import Path

from moodle import paths

# Moodle names each folder "<full name>_<participant id>_assignsubmission_file"
FOLDER_PATTERN = re.compile(r"^(?P<name>.+)_(?P<participant>\d+)_assignsubmission_file_?$")

MAPPING_FIELDS = ["number", "anon_file", "participant_id", "original_folder", "original_file"]


def parse_folder(folder_name: str) -> str:
    """Return the Moodle participant id from a submission folder name."""
    match = FOLDER_PATTERN.match(folder_name)
    if not match:
        raise ValueError(f"Not a Moodle submission folder: {folder_name!r}")
    return match.group("participant")


def prepare(original: Path, assignment_dir: Path) -> list[dict]:
    anon = assignment_dir / paths.TO_GRADE
    if anon.exists():
        shutil.rmtree(anon)
    anon.mkdir()

    # Sort by participant id so the numbers are the same on every run
    folders = sorted(
        (f for f in original.iterdir() if f.is_dir()),
        key=lambda f: int(parse_folder(f.name)),
    )

    rows = []
    for number, folder in enumerate(folders, start=1):
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        for index, file in enumerate(files):
            # A second file from the same student becomes 0001-2.pdf
            suffix = "" if index == 0 else f"-{index + 1}"
            anon_name = f"{number:04d}{suffix}{file.suffix.lower()}"
            shutil.copy2(file, anon / anon_name)
            rows.append({
                "number": f"{number:04d}",
                "anon_file": anon_name,
                "participant_id": parse_folder(folder.name),
                "original_folder": folder.name,
                "original_file": str(file.relative_to(folder)),
            })

    with open(assignment_dir / paths.KEY, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=MAPPING_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def read_mapping(assignment_dir: Path) -> dict[str, dict]:
    """Return the key as {number: first row for that number}."""
    with open(assignment_dir / paths.KEY, encoding="utf-8-sig") as f:
        mapping = {}
        for row in csv.DictReader(f):
            mapping.setdefault(row["number"], row)
        return mapping
