"""Where student data lives, and what every folder and file is called.

The shared folder (the lecturer's OneDrive) has a folder per course and, in it,
a folder per assignment, all named in plain Hebrew so anyone opening it knows
what they're looking at:

    מערכת בדיקת תרגילים/                         data folder (ASSIGNMENT_DATA)
      אלגברה לינארית/                              course
        הגשה 0 - קבוצות ומרוכבים/                  assignment
          1 - עבודות לבדיקה/          0001.pdf ...   numbered submissions, for grading
          2 - עבודות בדוקות עם הערות/  0001.pdf ...   marked by the grader
          3 - מוכן להעלאה למודל/                     built for the upload to Moodle
          פרטי המטלה.json                            Moodle id, questions, rules, rubric
          ציונים.csv                                 number,grade,feedback (from grading)
          טבלת מפתח - מספר לסטודנט.csv               the key: number -> Moodle participant
          הורדה ממודל <date>.zip                     the ZIP exactly as Moodle gave it
          קרא אותי.txt

The extracted ZIP stays on the downloader's computer only, in the same
course/assignment layout under the work folder (ASSIGNMENT_WORK): students'
file names there break OneDrive sync, and it can be rebuilt from the ZIP.
"""

import json
import os
from pathlib import Path

TO_GRADE = "1 - עבודות לבדיקה"
MARKED = "2 - עבודות בדוקות עם הערות"
UPLOAD = "3 - מוכן להעלאה למודל"
INFO = "פרטי המטלה.json"
GRADES = "ציונים.csv"
KEY = "טבלת מפתח - מספר לסטודנט.csv"
README = "קרא אותי.txt"
DOWNLOAD_PREFIX = "הורדה ממודל"


def data_dir() -> Path:
    return Path(os.environ.get("ASSIGNMENT_DATA", Path.home() / "מערכת בדיקת תרגילים"))


def work_dir() -> Path:
    return Path(os.environ.get("ASSIGNMENT_WORK", Path.home() / "קבצים מקוריים ממודל"))


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
