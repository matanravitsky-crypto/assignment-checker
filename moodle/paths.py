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
# Every grade next to the Moodle participant id it belongs to (moodle/moodle_table.py): derived from the grades and the
# key, rebuilt on every grading, edit and upload. The upload fills Moodle's worksheet from it
MOODLE_TABLE = "Grades for Moodle.csv"
# Moodle's grading worksheet, downloaded with every pull (moodle/moodle_table.py, save_worksheet), WITHOUT the columns
# that identify a person (name, email, ID number...): only Moodle's participant identifier and the grading columns.
# Filled from Grades for Moodle.csv on every grading and edit, so it always holds the grades as they are now
MOODLE_WORKSHEET = "Moodle grading worksheet.csv"
# The activity log (activity_log/): who did what and when, e.g. every grade edit with its reason. A folder in the
# assignment folder with one "<who>.jsonl" per writer, so OneDrive never merges two versions of a file
ACTIVITY_LOG = "Activity log"
# Suspected copying: pairs of numbers whose files, PDF metadata or page images match, and what each file looked like
# (hashes only: no names, no metadata values). Written by copying/check.py, read by the site's "העתקות" page
COPYING = "Copying check.json"
README = "README.txt"
# The lecturer's or TA's grading material, in the assignment folder: rubric, solutions, accepted methods (.md/.txt).
# Grading sends all of it to Claude. "פדגוגי" is the name the team gave it; "Pedagogy" works too.
PEDAGOGY = ("Pedagogy", "פדגוגי")
# The lecturer's official grading key (המכוון), uploaded from the site's grading step. In the assignment folder:
# "Official key/" holds the file as given (PDF, image, Word or text) and "Official key.txt" the text sent to Claude
# (pasted, or read out of a Word file). The points per question go in Assignment details.json, "official_key_points".
# When there is a key, grading follows it before any other rubric. A replaced key moves to "Earlier official keys/<date>/"
OFFICIAL_KEY = "Official key"
# What the rubric-builder skill (.claude/skills/rubric-builder) writes into the pedagogy folder, and the site reads
RUBRIC_MD = "Rubric.md"                       # the grading bot's rubric
RUBRIC_PDF = "Rubric.pdf"                     # the same rubric for people
RUBRIC_NOTES = "Working notes"                # the committee's folder: rubric.json, findings, the agents' reports
RUBRIC_LOG = "Rubric PDF changelog.md"        # in RUBRIC_NOTES: every round of remarks, and the approval
OFFICIAL_KEY_TEXT = "Official key.txt"
OFFICIAL_KEY_OLD = "Earlier official keys"
# A pull never deletes or overwrites a submission: a file that a newer download replaces (a resubmission, or a
# second file that is gone) moves here first, "Earlier versions/<date>/0001.pdf". The key before every change goes
# to "Key history" (not next to the key: a "Key - number to student*.csv" there counts as an OneDrive conflict copy)
EARLIER = "Earlier versions"
KEY_HISTORY = "Key history"
DOWNLOAD_PREFIX = "Moodle download"
# Every Moodle download is kept, as Moodle gave it, on the computer that pulled only (it has the students' names, and
# 2-3 GB per pull would fill OneDrive): <ASSIGNMENT_WORK>/Backup - Moodle downloads/<course>/<assignment>/
BACKUP = "Backup - Moodle downloads"
# In the assignment folder: one row per pull (when, who, how many), so every computer sees when it was pulled
PULL_LOG = "Pull log.csv"
# The shared folder is the course's OneDrive folder ("YallaLinearit", or "<owner> - YallaLinearit" as OneDrive names
# it). in_shared_folder says whether a folder is inside it; since 2026-10-29 a local copy may pull too (the pull
# owner's key is the one key), so nothing refuses a pull by it any more
SHARED_COURSE_FOLDER = "YallaLinearit"
# The statistics database (stats/): in the data folder, next to the courses. One JSON per assignment, by slot
# ("Statistics/<course>/Assignment N.json"), derived from the grades and notes and recomputed whenever they change,
# plus one CSV of every assignment and question. Numbers only
STATISTICS = "Statistics"
STATS_FILE = "Assignment {}.json"
STATS_EXPORT = "All assignments.csv"
PULL_LOCK = "Pull in progress.txt"      # in the assignment folder while a pull runs (see lock.py)
UPLOAD_LOCK = "Upload in progress.txt"  # in the assignment folder while an upload to Moodle runs
# The last pull's check, in the assignment folder: nothing lost, missed, doubled or changed (pull_check.py)
PULL_CHECK = "Pull check.json"
# In "3 - Ready to upload to Moodle" (upload.py, upload_log.py, send.py, send_grades.py)
UPLOAD_STEPS = "Upload steps.txt"                        # the steps and a checklist for an upload by hand
UPLOAD_LOG = "Upload log.csv"                            # what went up, per number (numbers only)
UPLOAD_BATCH = "Upload batch.json"                       # the current batch: each ZIP and file with its sha256
GRADES_WORKSHEET = "Grades for Moodle worksheet.csv"     # Moodle's worksheet filled by "Prepare return"
GRADES_RUN_FILE = "Grades for Moodle - this upload.csv"  # the worksheet one grades upload sends
GRADES_UPLOAD_LOG = "Grades upload log.csv"              # which grades went up
# In the data folder: one line per Claude Code grading run, tokens and cost only (grading/claude_cli.py, dashboard/usage.py)
USAGE_LOG = "Grading usage.jsonl"
# The folders' default names (data_dir, work_dir), and the system folder's name inside the synced course folder
DATA_FOLDER = "Exercise Checking System"
WORK_FOLDER = "Moodle originals"


def data_dir() -> Path:
    return Path(os.environ.get("ASSIGNMENT_DATA", Path.home() / DATA_FOLDER))


def work_dir() -> Path:
    return Path(os.environ.get("ASSIGNMENT_WORK", Path.home() / WORK_FOLDER))


def downloads_dir() -> Path:
    """Where Chrome saves what it downloads from Moodle (ZIPs, parts, the grading worksheet)."""
    return Path(os.environ.get("DOWNLOADS_DIR") or Path.home() / "Downloads")


def assignment_dirs() -> list[Path]:
    """Every <course>/<assignment> folder that has its details file."""
    return sorted(p.parent for p in data_dir().glob(f"*/*/{INFO}"))


def read_info(assignment_dir: Path) -> dict:
    with open(assignment_dir / INFO, encoding="utf-8") as f:
        return json.load(f)


class TwoFolders(ValueError):
    """Two assignment folders carry the same Moodle id (a copied folder): a pull or upload could go to the wrong one."""


def read_info_or_none(assignment_dir: Path) -> dict | None:
    """The details, or None when the file is unreadable (a broken file is datastore doctor's to report, not a crash here)."""
    try:
        d = read_info(assignment_dir)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def find_assignment(assignment_id: str) -> Path | None:
    found = [f for f in assignment_dirs() if str((read_info_or_none(f) or {}).get("id")) == str(assignment_id)]
    if len(found) > 1:
        raise TwoFolders(f"Moodle id {assignment_id} is in {len(found)} assignment folders: "
                         + ", ".join(str(f.relative_to(data_dir())) for f in found))
    return found[0] if found else None


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
    # Split on both separators so a Windows path is read the same way on any OS (CI runs on Linux)
    parts = [p for p in re.split(r"[\\/]", str(Path(path).resolve())) if p][:-1]  # the folder itself is not its own parent
    return any(p == name or p.endswith(f" - {name}") or p.startswith(f"{name} - ") for p in parts)


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
