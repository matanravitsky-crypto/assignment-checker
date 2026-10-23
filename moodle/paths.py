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
          Grades.csv                                 number,grade,feedback (older grades, approvals by hand)
          Grades by <name>.csv                       each grader's own grades (see grades.py)
          Who grades what/<name>.json                the numbers each grader took (see claims.py)
          Grading notes/              0001.json ...  per-question comments, mistakes, marks, why a person should look
          Key - number to student.csv                the key: number -> Moodle participant
          Moodle download <date>.zip                 the ZIP exactly as Moodle gave it
          README.txt

The extracted ZIP stays on the downloader's computer only, in the same
course/assignment layout under the work folder (ASSIGNMENT_WORK): students'
file names there break OneDrive sync, and it can be rebuilt from the ZIP.
"""

import json
import os
import re
from pathlib import Path

TO_GRADE = "1 - Submissions to grade"
MARKED = "2 - Graded with comments"
UPLOAD = "3 - Ready to upload to Moodle"
INFO = "Assignment details.json"
GRADES = "Grades.csv"
GRADES_BY = "Grades by {}.csv"           # one per grader, so two graders never write the same file (grades.py)
CLAIMS = "Who grades what"               # folder: one "<name>.json" per grader, the numbers they took (claims.py)
TASKS = "Who does what"                  # in the COURSE folder: who took the pull or the return of each assignment (claims.py)
# What the grader said about each submission, per number (0001.json): per-question comments and mistakes, the marks
# on the pages, and why it needs a person. Numbers only, never names. The site's manual review reads it
NOTES = "Grading notes"
KEY = "Key - number to student.csv"
README = "README.txt"
# The lecturer's or TA's grading material, in the assignment folder: rubric, solutions, accepted methods (.md/.txt).
# Grading sends all of it to Claude. "פדגוגי" is the name the team gave it; "Pedagogy" works too.
PEDAGOGY = ("Pedagogy", "פדגוגי")
DOWNLOAD_PREFIX = "Moodle download"
# Every Moodle download is kept, as Moodle gave it, on the computer that pulled only (it has the students' names, and
# 2-3 GB per pull would fill OneDrive): <ASSIGNMENT_WORK>/Backup - Moodle downloads/<course>/<assignment>/
BACKUP = "Backup - Moodle downloads"
# In the assignment folder: one row per pull (when, who, how many), so every computer sees when it was pulled
PULL_LOG = "Pull log.csv"
# The shared folder is the course's OneDrive folder ("YallaLinearit", or "<owner> - YallaLinearit" as OneDrive names
# it): pulls write the one key there. A copy outside it (a local folder) must not pull: its key would not see the
# numbers another computer gave, and two students would get one number
SHARED_COURSE_FOLDER = "YallaLinearit"
PULL_LOCK = "Pull in progress.txt"      # in the assignment folder while a pull runs (see lock.py)
UPLOAD_LOCK = "Upload in progress.txt"  # in the assignment folder while an upload to Moodle runs


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


def backup_dir(assignment_dir: Path) -> Path:
    """Where this computer keeps the assignment's Moodle downloads (never in OneDrive)."""
    return work_dir() / BACKUP / assignment_dir.relative_to(data_dir())


def in_shared_folder(path: Path) -> bool:
    """Is this folder inside the course's synced OneDrive folder, where the one key of every assignment lives?"""
    name = SHARED_COURSE_FOLDER
    return any(p.name == name or p.name.endswith(f" - {name}") or p.name.startswith(f"{name} - ")
               for p in Path(path).resolve().parents)


def original_dir(assignment_dir: Path) -> Path:
    """The extracted ZIP for an assignment, on this computer only."""
    return work_dir() / assignment_dir.relative_to(data_dir())


def files_by_number(folder: Path, pattern: str = "*") -> dict[str, list[Path]]:
    """Files named 0001 or 0001-2 (an extra file of the same submission), grouped by number, in order.

    The same as grading.grade.files_by_number: moodle/ can't import grading/, which loads PyMuPDF.
    """
    out: dict[str, list[tuple[int, Path]]] = {}
    for p in folder.glob(pattern) if folder.is_dir() else []:
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", p.stem)
        if p.is_file() and m:
            out.setdefault(m.group(1), []).append((int(m.group(2) or 1), p))
    return {n: [p for _, p in sorted(files)] for n, files in sorted(out.items())}
