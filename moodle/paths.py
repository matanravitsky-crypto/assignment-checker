"""Where student data lives, and what every folder and file is called.

The shared folder (the lecturer's OneDrive) has a folder per course and, in it,
a folder per assignment, with plain English names that say what each one is
(the README files inside explain them in Hebrew):

    Exercise Checking System/                    data folder (ASSIGNMENT_DATA)
      Linear Algebra/                              course
        Assignment 0 - Sets and Complex Numbers/   assignment
          1 - Submissions to grade/   0001.pdf ...   numbered submissions, for grading
          2 - Graded with comments/   0001.pdf ...   marked by the grader
          3 - Ready to upload to Moodle/             built for the upload to Moodle
          Assignment details.json                    Moodle id, questions, rules, rubric
          Grades.csv                                 number,grade,feedback (from grading)
          Key - number to student.csv                the key: number -> Moodle participant
          Moodle download <date>.zip                 the ZIP exactly as Moodle gave it
          README.txt

The extracted ZIP stays on the downloader's computer only, in the same
course/assignment layout under the work folder (ASSIGNMENT_WORK): students'
file names there break OneDrive sync, and it can be rebuilt from the ZIP.
"""

import json
import os
from pathlib import Path

TO_GRADE = "1 - Submissions to grade"
MARKED = "2 - Graded with comments"
UPLOAD = "3 - Ready to upload to Moodle"
INFO = "Assignment details.json"
GRADES = "Grades.csv"
KEY = "Key - number to student.csv"
README = "README.txt"
DOWNLOAD_PREFIX = "Moodle download"


def data_dir() -> Path:
    return Path(os.environ.get("ASSIGNMENT_DATA", Path.home() / "Exercise Checking System"))


def work_dir() -> Path:
    return Path(os.environ.get("ASSIGNMENT_WORK", Path.home() / "Moodle originals"))


def assignment_dirs() -> list[Path]:
    """Every <course>/<assignment> folder that has its details file."""
    return sorted(p.parent for p in data_dir().glob(f"*/*/{INFO}"))


def read_info(assignment_dir: Path) -> dict:
    with open(assignment_dir / INFO, encoding="utf-8") as f:
        return json.load(f)


def find_assignment(assignment_id: str) -> Path | None:
    for folder in assignment_dirs():
        if str(read_info(folder).get("id")) == str(assignment_id):
            return folder
    return None


def assignment_dir(assignment_id: str) -> Path:
    found = find_assignment(assignment_id)
    if found is None:
        raise FileNotFoundError(f"No assignment with Moodle id {assignment_id} under {data_dir()}")
    return found


def original_dir(assignment_dir: Path) -> Path:
    """The extracted ZIP for an assignment, on this computer only."""
    return work_dir() / assignment_dir.relative_to(data_dir())
