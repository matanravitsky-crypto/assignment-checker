"""Number Moodle submissions 0001..N so grading never sees student names.

Input: a "Download all submissions" ZIP extracted (one folder per student) into
    <data>/submissions/<assignment id>/original/
Output, next to it:
    anon/0001.pdf, anon/0002.pdf, ...   the files the grader gets
    mapping.csv                         number -> Moodle participant id and
                                        original folder; it stays private and
                                        is used to rebuild names for the upload

The data folder defaults to ~/assignment-data, outside the repo and OneDrive.
Set ASSIGNMENT_DATA to use another one.

Usage: python prepare_submissions.py <assignment id>
"""

import csv
import os
import re
import shutil
import sys
from pathlib import Path

# Moodle names each folder "<full name>_<participant id>_assignsubmission_file"
FOLDER_PATTERN = re.compile(r"^(?P<name>.+)_(?P<participant>\d+)_assignsubmission_file_?$")


def data_dir() -> Path:
    return Path(os.environ.get("ASSIGNMENT_DATA", Path.home() / "assignment-data"))


def parse_folder(folder_name: str) -> str:
    """Return the Moodle participant id from a submission folder name."""
    match = FOLDER_PATTERN.match(folder_name)
    if not match:
        raise ValueError(f"Not a Moodle submission folder: {folder_name!r}")
    return match.group("participant")


def prepare(assignment_dir: Path) -> list[dict]:
    original = assignment_dir / "original"
    anon = assignment_dir / "anon"
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

    with open(assignment_dir / "mapping.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["number"])
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python prepare_submissions.py <assignment id>")
    assignment_dir = data_dir() / "submissions" / sys.argv[1]
    rows = prepare(assignment_dir)
    students = len({row["number"] for row in rows})
    print(f"{students} submissions, {len(rows)} files -> {assignment_dir / 'anon'}")


if __name__ == "__main__":
    main()
