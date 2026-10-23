"""Build a fictional "Exercise Checking System" folder, to try the website without real student data.

    python -m tests.make_demo_root data/demo-root

Then run the dashboard on it. It never touches Moodle (MOODLE_DRIVER=simulate):

    ASSIGNMENT_CHECKER_ROOT=data/demo-root MOODLE_DRIVER=simulate python -m dashboard serve --no-open

The folder has one course with one assignment (Moodle id 3438636): 24 numbered submissions, a key with
fictional names from tests/sample_files.NAMES, and a rubric with known mistakes. Each submission is one page that
answers the assignment's five questions (sets and complex numbers); a mistake the "grader" found is really written
on the page, and its mark in Grading notes boxes that answer.

0001 (approved) and 0002 have marked files, ready to upload, each padded to about 5 MB (--pad-mb) so they land in
two ZIPs, which lets you see the progress, the stop and the resume. 0003-0020 have grades and Grading notes, four of
them flagged for manual review (unreadable, uncertain, missing, out of order), and 0022's grading "failed".
Everything is made up; `data/` is git-ignored.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from pathlib import Path

import pymupdf

from grading import grade as grading
from moodle import paths
from moodle.ingest import remove_tree
from tests.sample_files import NAMES

COURSE = "Linear Algebra"
ASSIGNMENT = "Assignment 0 - Sets and Complex Numbers"
MARKER = "Demo root.txt"  # written into every demo folder: only a folder that has it is ever wiped
MOODLE_ID = "3438636"
TITLE = "הגשה 0 - קבוצות ומרוכבים"
SUBMISSIONS = 24

# Each question: its label, the mistakes the lecturer expects (the site's ready-made comments), and what a student
# writes. A line is ("he", text) or ("math", text); a mistake replaces the line at its index with what was written.
QUESTIONS = [
    {"label": "דף קבוצות 11", "task": ("הוכיחו את השוויון:", "A∩(B∪C) = (A∩B)∪(A∩C)"),
     "lines": [("he", "נוכיח הכלה בשני הכיוונים."),
               ("math", "x ∈ A∩(B∪C)  ⇒  x ∈ A  and  (x ∈ B or x ∈ C)  ⇒  x ∈ (A∩B)∪(A∩C)"),
               ("math", "x ∈ (A∩B)∪(A∩C)  ⇒  x ∈ A  and  x ∈ B∪C  ⇒  x ∈ A∩(B∪C)  ∎")],
     "deductions": [("חסר נימוק להכלה ההפוכה", 5, 2, ("he", "ההכלה ההפוכה ברורה, ולכן יש שוויון.")),
                    ("בלבול בין שייכות להכלה", 4, 1, ("math", "x ⊆ A∩(B∪C)  ⇒  x ⊆ A  and  x ⊆ B∪C  ⇒  x ∈ (A∩B)∪(A∩C)"))]},
    {"label": "דף קבוצות 12", "task": ("הוכיחו את חוק דה מורגן:", "(A∪B)ᶜ = Aᶜ∩Bᶜ"),
     "lines": [("he", "לכל איבר מתקיים:"),
               ("math", "x ∈ (A∪B)ᶜ  ⇔  x ∉ A∪B  ⇔  x ∉ A  and  x ∉ B  ⇔  x ∈ Aᶜ∩Bᶜ  ∎")],
     "deductions": [("שימוש שגוי בחוקי דה מורגן", 6, 1, ("math", "(A∪B)ᶜ = Aᶜ∪Bᶜ ,  so  x ∈ Aᶜ  or  x ∈ Bᶜ")),
                    ("לא הוכח לכל x", 4, 0, ("he", "בדקנו עבור שתי דוגמאות של קבוצות וזה מתקיים."))]},
    {"label": "דף מספרים מרוכבים 6", "task": ("חשבו את הארגומנט ואת המכפלה בצמוד:", "z = 1 + i"),
     "lines": [("math", "|z| = √2 ,   arg z = π/4"),
               ("math", "z̄ = 1 − i ,   z·z̄ = 1 + 1 = 2")],
     "deductions": [("טעות בחישוב הארגומנט", 4, 0, ("math", "|z| = √2 ,   arg z = π/2")),
                    ("שכחו את הצמוד", 5, 1, ("math", "z·z̄ = (1 + i)² = 2i"))]},
    {"label": "דף מספרים מרוכבים 7", "task": ("מצאו את כל הפתרונות של המשוואה:", "z³ = 1"),
     "lines": [("math", "z = cis(2πk/3) ,   k = 0, 1, 2"),
               ("math", "z = 1 ,   −1/2 + (√3/2)i ,   −1/2 − (√3/2)i")],
     "deductions": [("לא נמצאו כל השורשים", 8, 1, ("math", "z = 1")),
                    ("טעות בנוסחת דה מואבר", 5, 0, ("math", "(cos θ + i sin θ)³ = cos θ³ + i sin θ³"))]},
    {"label": "דף מספרים מרוכבים 8", "task": ("שרטטו במישור המרוכב את התחום:", "|z − 1| ≤ 2"),
     "lines": [("math", "c = 1 ,  r = 2"), ("sketch", "1")],
     "deductions": [("חסר שרטוט במישור המרוכב", 3, 1, ("he", "")),
                    ("תחום לא נכון", 5, 0, ("math", "c = 0 ,  r = 2"))]},
]
RUBRIC = [(q["label"], [(t, p) for t, p, _, _ in q["deductions"]]) for q in QUESTIONS]

MARKED = {"0001": ([[] for _ in QUESTIONS], "1"),  # number -> (mistakes per question, approved)
          "0002": ([[], [], ["שכחו את הצמוד"], ["לא נמצאו כל השורשים"], ["תחום לא נכון"]], "")}
GRADED = range(3, 21)  # 0003-0020: graded, with Grading notes, no marked file
REVIEW = {  # number -> (review_kind, reason, the question Claude is unsure of)
    "0005": ("unreadable", "שאלה 12, עמוד 1: השורה האחרונה של ההוכחה לא קריאה, נתתי ניקוד בלי לראות אותה.", 1),
    "0009": ("uncertain", "שאלה 7: הסטודנט פתר בדרך גאומטרית במקום בנוסחת דה מואבר. לא בטוח שההסבר מספיק.", 3),
    "0013": ("missing", "שאלה 8 לא נמצאה בהגשה. ייתכן שחסר עמוד.", 4),
    "0017": ("format", "השאלות לא לפי הסדר: שאלה 6 מופיעה בסוף העמוד.", 2),
}
# The special-case columns the grading writes (grading.SPECIAL_CASES): the site shows the kind and what is missing
SPECIAL = {"0013": {"special": "missing_question", "missing": "שאלה 8 (דף מספרים מרוכבים 8)"}}
FAILED = {"0022": "Claude עמוס כרגע (מגבלת קצב). כדאי לנסות שוב בעוד כמה דקות."}

# The page: A4, a block per question, the student's "ink" in blue
W, H = 595, 842
TOP, BLOCK, LINE = 64, 152, 22
FONTS = Path("C:/Windows/Fonts")
CSS = ("@font-face {font-family: heb; src: url(arial.ttf);} @font-face {font-family: sym; src: url(seguisym.ttf);}"
       "* {font-family: heb, sym, sans-serif;}")
INK = "#1d3c8f"


def _archive():
    return pymupdf.Archive(str(FONTS)) if (FONTS / "arial.ttf").exists() else None


def _text(page, rect, text, size=13, color=INK, ltr=False, bold=False):
    html = (f'<div dir="{"ltr" if ltr else "rtl"}" style="text-align: right; color: {color}; font-size: {size}px;'
            f'{" font-weight: bold;" if bold else ""}">{text}</div>')
    page.insert_htmlbox(rect, html, css=CSS, archive=_archive())


def _thousandths(rect) -> dict:
    return {"x0": round(rect.x0 / W * 1000), "y0": round(rect.y0 / H * 1000),
            "x1": round(rect.x1 / W * 1000), "y1": round(rect.y1 / H * 1000)}


def demo_submission(number: str, mistakes: list[list[str]], order: list[int], skip: set[int], scribble: int | None,
                    geometric: int | None) -> tuple[bytes, dict[int, pymupdf.Rect]]:
    """One page with the answers to the questions in `order`, as the student wrote them. Returns the PDF and, per
    question, the rectangle around its answer (where a mark goes)."""
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    _text(page, pymupdf.Rect(40, 24, W - 40, 50), f"{TITLE} · הגשה {number}", size=11, color="#555555")
    boxes: dict[int, pymupdf.Rect] = {}
    slot = 0
    for qi in order:
        if qi in skip:
            continue
        q, top = QUESTIONS[qi], TOP + slot * BLOCK
        slot += 1
        ask, given = q["task"]
        _text(page, pymupdf.Rect(40, top, W - 40, top + 18), f"{q['label']} · {ask}", size=12, color="#222222", bold=True)
        _text(page, pymupdf.Rect(40, top + 17, W - 40, top + 35), given, size=12, color="#222222", ltr=True)
        top += 16
        lines = list(q["lines"])
        for text, _, at, wrote in q["deductions"]:
            if text in mistakes[qi]:
                lines[at] = wrote
        if geometric == qi:
            lines = [("he", "השורשים הם קודקודי משולש שווה צלעות על מעגל היחידה,"), ("he", "ואחד מהם הוא 1, ולכן השאר מתקבלים בסיבוב של 120 מעלות.")]
        y = top + 26
        for kind, text in lines:
            if kind == "sketch":
                c = pymupdf.Point(W - 150, y + 30)
                page.draw_line(pymupdf.Point(c.x - 70, c.y), pymupdf.Point(c.x + 70, c.y), color=(0.4, 0.4, 0.4), width=0.6)
                page.draw_line(pymupdf.Point(c.x - 30, c.y - 40), pymupdf.Point(c.x - 30, c.y + 40), color=(0.4, 0.4, 0.4), width=0.6)
                page.draw_circle(c, 34, color=(0.11, 0.24, 0.56), width=1.3)
                y += 64
            elif text:
                _text(page, pymupdf.Rect(60, y, W - 50, y + LINE), text, ltr=kind == "math")
                y += LINE
        boxes[qi] = pymupdf.Rect(56, top + 22, W - 46, max(y, top + 26 + LINE) + 2)
        if scribble == qi:  # the last line, scribbled over: Claude can't read it
            ly = y - LINE / 2
            for k in range(3):
                pts = [pymupdf.Point(70 + 9 * s, ly - 6 + 4 * k + (5 if s % 2 else -5)) for s in range(52)]
                page.draw_polyline(pts, color=(0.2, 0.25, 0.45), width=1.2)
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data, boxes


def build(root: Path, pad_mb: float = 5.0) -> Path:
    """Create the demo folder at `root` (replacing an earlier demo there) and return the assignment folder."""
    if root.exists():
        if any(root.iterdir()):
            if not (root / MARKER).is_file():  # never wipe a folder this script did not make
                raise SystemExit(f"{root} exists and is not an earlier demo folder (no {MARKER}). Pick an empty or new folder.")
            remove_tree(root)  # inside OneDrive the folders can be read-only
    assignment = root / COURSE / ASSIGNMENT
    root.mkdir(parents=True, exist_ok=True)
    (root / MARKER).write_text("A fictional demo folder made by tests/make_demo_root.py. Safe to delete.\n", encoding="utf-8")
    (root / "Discrete Mathematics").mkdir()  # the second course, still without assignments, like the shared folder
    for sub in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD, paths.NOTES):
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

    rnd = random.Random(7)
    plan: dict[str, list[list[str]]] = {n: m for n, (m, _) in MARKED.items()}
    for i in GRADED:
        plan[f"{i:04d}"] = [[t for t, _, _, _ in q["deductions"] if rnd.random() < 0.28] for q in QUESTIONS]

    rows, pages, boxes = [], {}, {}
    for i in range(1, SUBMISSIONS + 1):
        number, pid, name = f"{i:04d}", str(1000 + i), NAMES[(i - 1) % len(NAMES)]
        kind, _, unsure_q = REVIEW.get(number, ("", "", -1))
        order = [0, 1, 3, 4, 2] if kind == "format" else list(range(len(QUESTIONS)))
        pages[number], boxes[number] = demo_submission(
            number, plan.get(number) or [[] for _ in QUESTIONS], order, {unsure_q} if kind == "missing" else set(),
            unsure_q if kind == "unreadable" else None, unsure_q if kind == "uncertain" else None)
        (assignment / paths.TO_GRADE / f"{number}.pdf").write_bytes(pages[number])
        rows.append({"number": number, "anon_file": f"{number}.pdf", "participant_id": pid,
                     "original_folder": f"{name}_{pid}_assignsubmission_file", "original_file": "hw.pdf"})
    with (assignment / paths.KEY).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["number", "anon_file", "participant_id", "original_folder", "original_file"])
        writer.writeheader()
        writer.writerows(rows)

    ctx = grading.load_context(assignment, send_solution=False)
    grades = {}
    for number, mistakes in sorted(plan.items()):
        kind, reason, unsure_q = REVIEW.get(number, ("", "", -1))
        lost = [sum(p for t, p, _, _ in q["deductions"] if t in mistakes[qi]) for qi, q in enumerate(QUESTIONS)]
        points = [0 if kind == "missing" and qi == unsure_q else 20 - lost[qi] for qi in range(len(QUESTIONS))]
        comments = ["השאלה לא נמצאה בהגשה." if kind == "missing" and qi == unsure_q
                    else ". ".join(mistakes[qi]) + "." if mistakes[qi] else "נכון ומנומק." for qi in range(len(QUESTIONS))]
        marks = [{"page": 1, **_thousandths(boxes[number][qi]), "text": ms[0]} for qi, ms in enumerate(mistakes) if ms and qi in boxes[number]]
        if kind in ("unreadable", "uncertain"):
            marks.append({"page": 1, **_thousandths(boxes[number][unsure_q]),
                          "text": "השורה האחרונה לא קריאה" if kind == "unreadable" else "דרך גאומטרית: לבדוק שההסבר מלא"})
        g = grading.Graded(points, comments, grading.compute_grade(points, ctx), "", [grading.Mark(**m) for m in marks],
                           reason, mistakes, [qi == unsure_q for qi in range(len(QUESTIONS))], kind)
        found = [m for ms in mistakes for m in ms]
        g.feedback = "עבודה טובה." + (" כדאי לשים לב: " + "; ".join(found) + "." if found else "")
        grading.write_notes(assignment, number, {**grading.graded_notes(g, "demo"), "graded_at": "2026-10-22T21:00:00"})
        approved = MARKED[number][1] if number in MARKED else "1" if not reason and int(number) % 3 == 0 else ""
        grades[number] = {"number": number, "grade": f"{g.grade:g}", "feedback": g.feedback,
                          "points": ";".join(f"{p:g}" for p in points), "approved": approved, "review": reason,
                          **SPECIAL.get(number, {})}
        if number in MARKED:
            # Written after the submissions: a submission newer than its marked file counts as resubmitted.
            # Random padding (it doesn't compress) makes two ZIPs in the upload demo
            pdf = grading.mark_pdf(pages[number], g, ctx, max_bytes=10**9) + b"\n%" + os.urandom(int(pad_mb * 1_000_000))
            (assignment / paths.MARKED / f"{number}.pdf").write_bytes(pdf)
    for number, why in FAILED.items():
        grading.write_notes(assignment, number, {"error": why, "failed_at": "2026-10-22T21:05:00"})
    grading.write_grades(assignment, grades)
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
