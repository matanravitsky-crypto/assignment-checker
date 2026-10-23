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
          Copying check.json                         suspected copying between numbers (python -m copying)
          Moodle download <date>.zip                 the ZIP exactly as Moodle gave it
          Earlier versions/<date>/    0001.pdf ...   files a newer download replaced (nothing is deleted)
          Key history/                               the key as it was before each pull changed it
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
# Suspected copying: pairs of numbers whose files, PDF metadata or page images match, and what each file looked like
# (hashes only: no names, no metadata values). Written by copying/check.py, read by the site's "העתקות" page
COPYING = "Copying check.json"
README = "README.txt"
# The lecturer's or TA's grading material, in the assignment folder: rubric, solutions, accepted methods (.md/.txt).
# Grading sends all of it to Claude. "פדגוגי" is the name the team gave it; "Pedagogy" works too.
PEDAGOGY = ("Pedagogy", "פדגוגי")
# The course's own material, in the course folder: exercise sheets and booklets with their solutions (Sheets/...).
# The copying check reads it so that a page a student copied from the booklet is not a suspicion
COURSE_MATERIAL = "Course material"
# A pull never deletes or overwrites a submission: a file that a newer download replaces (a resubmission, or a
# second file that is gone) moves here first, "Earlier versions/<date>/0001.pdf". The key before every change goes
# to "Key history" (not next to the key: a "Key - number to student*.csv" there counts as an OneDrive conflict copy)
EARLIER = "Earlier versions"
KEY_HISTORY = "Key history"
DOWNLOAD_PREFIX = "Moodle download"
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


class TwoFolders(ValueError):
    """Two assignment folders carry the same Moodle id (a copied folder): a pull or upload could go to the wrong one."""


def find_assignment(assignment_id: str) -> Path | None:
    found = [f for f in assignment_dirs() if str(read_info(f).get("id")) == str(assignment_id)]
    if len(found) > 1:
        raise TwoFolders(f"Moodle id {assignment_id} is in {len(found)} assignment folders: "
                         + ", ".join(str(f.relative_to(data_dir())) for f in found))
    return found[0] if found else None


def assignment_dir(assignment_id: str) -> Path:
    found = find_assignment(assignment_id)
    if found is None:
        raise FileNotFoundError(f"No assignment with Moodle id {assignment_id} under {data_dir()}")
    return found


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
