"""Build a fictional "Exercise Checking System" folder, to try the website without real student data.

    python -m tests.make_demo_root data/demo-root

Then run the dashboard on it. It never touches Moodle (MOODLE_DRIVER=simulate):

    ASSIGNMENT_CHECKER_ROOT=data/demo-root MOODLE_DRIVER=simulate python -m dashboard serve --no-open

The folder has one course with one assignment (Moodle id 3438636): 24 numbered submissions, a key with
fictional names from tests/sample_files.NAMES, a rubric with known mistakes, and two marked files (0001 approved,
0002 not yet), ready to upload. Each marked file is padded to about 5 MB (--pad-mb) so they land in two ZIPs, which
lets you see the progress, the stop and the resume. 0003-0020 have grades and Grading notes (made-up mistakes, so the
dashboard has statistics), four of them flagged for manual review, and 0022's grading "failed". Everything is made up;
`data/` is git-ignored.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import sys
from pathlib import Path

from moodle import paths
from tests.sample_files import NAMES, homework_pdf

COURSE = "Linear Algebra"
ASSIGNMENT = "Assignment 0 - Sets and Complex Numbers"
MARKER = "Demo root.txt"  # written into every demo folder: only a folder that has it is ever wiped
MOODLE_ID = "3438636"
TITLE = "הגשה 0 - קבוצות ומרוכבים"
SUBMISSIONS = 24
MARKED = {  # number -> (grade, points, feedback, approved)
    "0001": ("100", "20;20;20;20;20", "עבודה מצוינת, כל השלבים ברורים.", "1"),
    "0002": ("70", "20;20;10;10;10", "בשאלה 3 חסר נימוק בצעד האחרון.", ""),
}
# The rubric: 20 points a question, and the mistakes the lecturer expects (the site's ready-made comments)
RUBRIC = [
    ("דף קבוצות 11", [("חסר נימוק להכלה ההפוכה", 5), ("בלבול בין שייכות להכלה", 4)]),
    ("דף קבוצות 12", [("שימוש שגוי בחוקי דה מורגן", 6), ("לא הוכח לכל x", 4)]),
    ("דף מספרים מרוכבים 6", [("טעות בחישוב הארגומנט", 4), ("שכחו את הצמוד", 5)]),
    ("דף מספרים מרוכבים 7", [("לא נמצאו כל השורשים", 8), ("טעות בנוסחת דה מואבר", 5)]),
    ("דף מספרים מרוכבים 8", [("חסר שרטוט במישור המרוכב", 3), ("תחום לא נכון", 5)]),
]
GRADED = range(3, 21)  # 0003-0020: graded, with Grading notes, no marked file
REVIEW = {  # number -> (review_kind, reason, the question Claude is unsure of)
    "0005": ("unreadable", "שאלה 12, עמוד 1: השורה האחרונה של ההוכחה לא קריאה, נתתי ניקוד בלי לראות אותה.", 1),
    "0009": ("uncertain", "שאלה 7: הסטודנט פתר בדרך גאומטרית שלא בטוח שהיא מלאה. כדאי לבדוק את המעבר בעמוד 1.", 3),
    "0013": ("missing", "שאלה 8 לא נמצאה בהגשה. ייתכן שחסר עמוד.", 4),
    "0017": ("format", "ההגשה לא לפי סדר השאלות: שאלה 6 מופיעה בסוף.", 2),
}
FAILED = {"0022": "Claude עמוס כרגע (מגבלת קצב). כדאי לנסות שוב בעוד כמה דקות."}


def build(root: Path, pad_mb: float = 5.0) -> Path:
    """Create the demo folder at `root` (replacing an earlier demo there) and return the assignment folder."""
    if root.exists():
        if any(root.iterdir()):
            if not (root / MARKER).is_file():  # never wipe a folder this script did not make
                raise SystemExit(f"{root} exists and is not an earlier demo folder (no {MARKER}). Pick an empty or new folder.")
            shutil.rmtree(root)
    assignment = root / COURSE / ASSIGNMENT
    root.mkdir(parents=True, exist_ok=True)
    (root / MARKER).write_text("A fictional demo folder made by tests/make_demo_root.py. Safe to delete.\n", encoding="utf-8")
    for sub in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD):
        (assignment / sub).mkdir(parents=True)

    (assignment / paths.INFO).write_text(json.dumps({
        "id": MOODLE_ID, "course": COURSE, "course_id": "67024", "name": ASSIGNMENT,
        "due": "2026-10-26T23:59:00+02:00",
        "questions": [{"sheet": "דף קבוצות", "numbers": [11, 12]}, {"sheet": "דף מספרים מרוכבים", "numbers": [6, 7, 8]}],
        "title": TITLE, "course_title": "אלגברה לינארית להנדסה", "notes": "תיקיית הדגמה: הכול בדוי",
        "max_grade": 100,
        "rubric": {"questions": [{"label": label, "points": 20, "deductions": [{"text": t, "points": p} for t, p in ds]}
                                 for label, ds in RUBRIC]},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = []
    for i in range(1, SUBMISSIONS + 1):
        number, pid, name = f"{i:04d}", str(1000 + i), NAMES[(i - 1) % len(NAMES)]
        (assignment / paths.TO_GRADE / f"{number}.pdf").write_bytes(homework_pdf(name, TITLE, pages=1))
        rows.append({"number": number, "anon_file": f"{number}.pdf", "participant_id": pid,
                     "original_folder": f"{name}_{pid}_assignsubmission_file", "original_file": "hw.pdf"})
    with (assignment / paths.KEY).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["number", "anon_file", "participant_id", "original_folder", "original_file"])
        writer.writeheader()
        writer.writerows(rows)

    # The marked files are written after the submissions: a submission newer than its marked file counts as resubmitted
    for number in MARKED:
        pdf = homework_pdf(NAMES[int(number) - 1], TITLE, pages=1) + b"\n%" + os.urandom(int(pad_mb * 1_000_000))
        (assignment / paths.MARKED / f"{number}.pdf").write_bytes(pdf)  # random padding: it doesn't compress

    grades = {number: [grade, feedback, points, approved, ""] for number, (grade, points, feedback, approved) in MARKED.items()}
    notes = assignment / paths.NOTES
    notes.mkdir()
    rnd = random.Random(7)
    for i in GRADED:
        number = f"{i:04d}"
        kind, reason, unsure_q = REVIEW.get(number, ("", "", -1))
        points, comments, mistakes = [], [], []
        for _, known in RUBRIC:
            made = [m for m in known if rnd.random() < 0.28]
            points.append(max(20 - sum(p for _, p in made), 0))
            mistakes.append([t for t, _ in made])
            comments.append(". ".join(t for t, _ in made) if made else "נכון ומנומק.")
        grade = sum(points)
        marks = [{"page": 1, "x0": 120, "y0": 200 + 90 * q, "x1": 860, "y1": 250 + 90 * q, "text": ms[0]}
                 for q, ms in enumerate(mistakes) if ms]
        (notes / f"{number}.json").write_text(json.dumps({
            "points": points, "comments": comments, "mistakes": mistakes, "unsure": [q == unsure_q for q in range(len(RUBRIC))],
            "review": reason, "review_kind": kind, "marks": marks, "model": "demo", "graded_at": "2026-10-22T21:00:00",
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        found = [m for ms in mistakes for m in ms]
        feedback = "עבודה טובה." + (" כדאי לשים לב: " + "; ".join(found) + "." if found else "")
        grades[number] = [str(grade), feedback, ";".join(map(str, points)), "1" if not reason and i % 3 == 0 else "", reason]
    for number, why in FAILED.items():
        (notes / f"{number}.json").write_text(json.dumps({"error": why, "failed_at": "2026-10-22T21:05:00"}, ensure_ascii=False),
                                              encoding="utf-8")

    with (assignment / paths.GRADES).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["number", "grade", "feedback", "points", "approved", "review"])
        for number in sorted(grades):
            writer.writerow([number, *grades[number]])
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
