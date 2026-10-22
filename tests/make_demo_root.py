"""Build a fictional "Exercise Checking System" folder, to try the website without real student data.

    python -m tests.make_demo_root data/demo-root

Then run the dashboard on it. It never touches Moodle (MOODLE_DRIVER=simulate):

    ASSIGNMENT_CHECKER_ROOT=data/demo-root MOODLE_DRIVER=simulate python -m dashboard serve --no-open

The folder has one course with one assignment (Moodle id 3438636): four numbered submissions, a key with
fictional names from tests/sample_files.NAMES, and two marked files (0001 approved, 0002 not yet), ready
to upload. Each marked file is padded to about 5 MB (--pad-mb) so they land in two ZIPs, which lets you see
the progress, the stop and the resume. Everything is made up; `data/` is git-ignored.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

from moodle import paths
from tests.sample_files import NAMES, homework_pdf

COURSE = "Linear Algebra"
ASSIGNMENT = "Assignment 0 - Sets and Complex Numbers"
MOODLE_ID = "3438636"
TITLE = "הגשה 0 - קבוצות ומרוכבים"
SUBMISSIONS = 4
MARKED = {  # number -> (grade, points, feedback, approved)
    "0001": ("100", "20;20;20;20;20", "עבודה מצוינת, כל השלבים ברורים.", "1"),
    "0002": ("70", "20;20;10;10;10", "בשאלה 3 חסר נימוק בצעד האחרון.", ""),
}


def build(root: Path, pad_mb: float = 5.0) -> Path:
    """Create the demo folder at `root` (replacing an earlier demo there) and return the assignment folder."""
    if root.exists():
        if any(child.name != COURSE for child in root.iterdir()):  # never wipe a folder that isn't an earlier demo
            raise SystemExit(f"{root} exists and is not an earlier demo folder. Pick an empty or new folder.")
        shutil.rmtree(root)
    assignment = root / COURSE / ASSIGNMENT
    for sub in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD):
        (assignment / sub).mkdir(parents=True)

    (assignment / paths.INFO).write_text(json.dumps({
        "id": MOODLE_ID, "course": COURSE, "course_id": "67024", "name": ASSIGNMENT,
        "due": "2026-10-26T23:59:00+02:00",
        "questions": [{"sheet": "דף קבוצות", "numbers": [11, 12]}, {"sheet": "דף מספרים מרוכבים", "numbers": [6, 7, 8]}],
        "title": TITLE, "course_title": "אלגברה לינארית להנדסה", "notes": "תיקיית הדגמה: הכול בדוי",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = []
    for i in range(1, SUBMISSIONS + 1):
        number, pid = f"{i:04d}", str(1000 + i)
        (assignment / paths.TO_GRADE / f"{number}.pdf").write_bytes(homework_pdf(NAMES[i - 1], TITLE, pages=1))
        rows.append({"number": number, "anon_file": f"{number}.pdf", "participant_id": pid,
                     "original_folder": f"{NAMES[i - 1]}_{pid}_assignsubmission_file", "original_file": "hw.pdf"})
    with (assignment / paths.KEY).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["number", "anon_file", "participant_id", "original_folder", "original_file"])
        writer.writeheader()
        writer.writerows(rows)

    # The marked files are written after the submissions: a submission newer than its marked file counts as resubmitted
    for number in MARKED:
        pdf = homework_pdf(NAMES[int(number) - 1], TITLE, pages=1) + b"\n%" + os.urandom(int(pad_mb * 1_000_000))
        (assignment / paths.MARKED / f"{number}.pdf").write_bytes(pdf)  # random padding: it doesn't compress

    with (assignment / paths.GRADES).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["number", "grade", "feedback", "points", "approved", "review"])
        for number, (grade, points, feedback, approved) in MARKED.items():
            writer.writerow([number, grade, feedback, points, approved, ""])
    return assignment


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Build a fictional folder for the dashboard demo")
    p.add_argument("folder", type=Path, help="where to build it (an earlier demo there is replaced)")
    p.add_argument("--pad-mb", type=float, default=5.0, help="size added to each marked file (default 5), so there are two ZIPs")
    args = p.parse_args(argv)
    assignment = build(args.folder, args.pad_mb)
    print(f"Demo folder ready: {args.folder.resolve()}\nAssignment: {assignment.relative_to(args.folder)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
