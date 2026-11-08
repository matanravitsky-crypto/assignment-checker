"""stats/compute.py: the same numbers the site shows, one record per key, and nothing that identifies a student."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from moodle import grades, paths
from stats import compute as sc
import stats

COURSE, HW = "Linear Algebra", "Assignment 0 - Sets and Complex Numbers"
QUESTIONS = [{"label": "קבוצות 11", "points": 20, "deductions": [{"text": "חסר נימוק להכלה ההפוכה", "points": 5}]},
             {"label": "קבוצות 12", "points": 30, "deductions": []},
             {"label": "מרוכבים 6", "points": 50, "deductions": []}]
# the key table of the fake assignment: what must never appear in the statistics
NAMES = {"1001": "נועה כהן", "1002": "איתי לוי", "1003": "מאיה מזרחי", "1004": "יונתן פרץ", "1005": "דנה ברק", "1006": "עומר שלו"}


def strings(x) -> list[str]:
    """Every text value anywhere in the statistics (not the numbers)."""
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [t for v in x.values() for t in strings(v)]
    if isinstance(x, list):
        return [t for v in x for t in strings(v)]
    return []


def row(n, grade, points, by="אורי", at="2026-11-01T10:00:00", approved="", review="", special=""):
    return {"number": n, "grade": str(grade), "feedback": "", "points": ";".join(str(p) for p in points),
            "approved": approved, "review": review, "graded_at": at, "graded_by": by, "special": special}


def note(mistakes, unsure=(False, False, False), kind="", error=""):
    d = {"mistakes": mistakes, "unsure": list(unsure), "review_kind": kind, "comments": ["", "", ""]}
    if error:
        d["error"] = error
    return d


ROWS = {
    "0001": row("0001", 100, [20, 30, 50]),
    "0002": row("0002", 95, [15, 30, 50]),
    "0003": row("0003", 65, [15, 20, 30], by="מתן"),
    "0004": row("0004", 40, [10, 10, 20], review="לא בטוח בשאלה 2", special=""),
    "0005": row("0005", 80, [20, 30, 30], approved="אורי 2026-11-02 09:00", review="היה לא בטוח"),
    # 0006 failed: no grade row, an error in its note. 0007 submitted and not graded yet
}
NOTES = {
    "0002": note([["חסר נימוק להכלה ההפוכה"], [], []]),
    "0003": note([["חסר נימוק להכלה ההפוכה", "חסר נימוק להכלה ההפוכה"], ["בלבול בין איחוד לחיתוך"], ["טעות סימן"]]),
    "0004": note([["חסר נימוק להכלה ההפוכה", "טעות בסימון"], ["בלבול בין איחוד לחיתוך"], ["טעות סימן"]], unsure=(False, True, False), kind="uncertain"),
    "0005": note([[], [], ["טעות סימן"]]),
    "0006": note([], error="Claude refused"),
}


def compute(**over):
    args = dict(course=COURSE, folder=HW, moodle_id="3438636", title="הגשה 0", max_grade=100, questions=QUESTIONS,
                rows=ROWS, notes=NOTES, submitted=7, computed_at="2026-11-08T12:00:00", computed_by="אורי")
    args.update(over)
    return sc.compute(**args)


def test_counts_and_grade_statistics_match_the_site():
    s = compute()
    assert s["key"] == f"{COURSE}/Assignment 0" and s["slot"] == 0 and s["moodle_id"] == "3438636"
    c = s["counts"]
    assert c == {"submitted": 7, "graded": 5, "pending": 2, "approved": 1, "needs_review": 1, "failed": 1,
                 "review_kinds": {"uncertain": 1, "failed": 1}}
    g = s["grade"]
    assert g["n"] == 5 and g["mean"] == 76 and g["median"] == 80 and g["min"] == 40 and g["max"] == 100
    assert g["pass_pct"] == 80  # 4 of 5 at 60 or more
    assert g["full_marks"] == 1
    assert g["sd"] == pytest.approx(24.3, abs=0.05)  # sample standard deviation, like the site
    assert g["histogram"]["bins"][0] == {"from": 0, "to": 10} and g["histogram"]["bins"][-1] == {"from": 90, "to": 100}
    assert g["histogram"]["counts"] == [0, 0, 0, 0, 1, 0, 1, 0, 1, 2]


def test_per_question_success_and_mistakes():
    s = compute()
    q1, q2, q3 = s["per_question"]
    assert [q["key"] for q in (q1, q2, q3)] == [f"{COURSE}/Assignment 0/q{i}" for i in (1, 2, 3)]
    assert q1["graded"] == 5 and q1["mean"] == 16
    # the site's formula: the mean of each work's rounded percentage
    assert q1["success_pct"] == 80 and q3["success_pct"] == 72
    assert q1["full_marks_pct"] == 40 and q1["zero_pct"] == 0
    assert q2["unsure"] == 1
    # the rubric's deduction wins for a known mistake; the other one gets the median of what was lost (half points)
    top = q1["mistakes"][0]
    assert top["text"] == "חסר נימוק להכלה ההפוכה" and top["count"] == 3 and top["in_rubric"] and top["deduction"] == 5
    assert top["pct"] == 75  # 3 of the 4 graded works that have notes with a mistakes list (0001 has no notes)
    assert q2["mistakes"] == [{"text": "בלבול בין איחוד לחיתוך", "count": 2, "pct": 50, "in_rubric": False, "deduction": 15}]  # lost 10 and 20 → median 15
    sign = q3["mistakes"][0]
    assert sign["count"] == 3 and sign["deduction"] == 20  # losses 20, 30, 20 → median 20


def test_a_mistake_written_twice_in_one_work_counts_once():
    s = compute()
    assert s["per_question"][0]["mistakes"][0]["count"] == 3  # 0003 has it twice in its list


def test_graders_are_team_members_with_counts():
    assert compute()["graders"] == {"count": 2, "by": [{"name": "אורי", "graded": 4}, {"name": "מתן", "graded": 1}]}


def test_points_over_the_rubric_are_left_out_of_per_question():
    rows = {**ROWS, "0008": row("0008", 100, [25, 30, 50])}  # 25 of 20: graded by another split
    s = compute(rows=rows, submitted=8)
    assert s["over_rubric"] == 1 and s["per_question"][0]["graded"] == 5
    assert s["grade"]["n"] == 6  # the grade itself still counts


def test_marked_file_without_a_grade_row_counts_as_graded_and_no_rubric_gives_no_questions():
    s = compute(marked={"0009"}, questions=[])
    assert s["counts"]["graded"] == 6 and s["per_question"] == [] and s["over_rubric"] == 0


def test_empty_assignment():
    s = compute(rows={}, notes={}, submitted=0)
    assert s["counts"]["graded"] == 0 and s["grade"]["mean"] is None and s["grade"]["histogram"]["counts"] == [0] * 10
    assert s["per_question"][0]["mistakes"] == [] and s["graders"] == {"count": 0, "by": []}


def test_max_grade_other_than_100():
    rows = {"0001": row("0001", 50, [10, 15, 25]), "0002": row("0002", 20, [0, 5, 15])}
    s = compute(rows=rows, max_grade=50, questions=[{"label": "א", "points": 10}, {"label": "ב", "points": 15}, {"label": "ג", "points": 25}])
    assert s["grade"]["histogram"]["bins"][-1] == {"from": 45, "to": 50} and s["grade"]["histogram"]["counts"][-1] == 1
    assert s["grade"]["pass_pct"] == 50 and s["grade"]["full_marks"] == 1


# ---------- from a real-looking folder ----------

@pytest.fixture
def folder(tmp_path, monkeypatch):
    """A small assignment folder as the pull and the grading leave it, with a key table full of names."""
    root = tmp_path / "Exercise Checking System"
    a = root / COURSE / HW
    for sub in (paths.TO_GRADE, paths.MARKED, paths.NOTES):
        (a / sub).mkdir(parents=True)
    (a / paths.INFO).write_text(json.dumps({"id": "3438636", "course": COURSE, "name": HW, "title": "הגשה 0 - קבוצות",
                                            "max_grade": 100, "rubric": {"questions": QUESTIONS}}, ensure_ascii=False), encoding="utf-8")
    key_rows = []
    for i, (pid, name) in enumerate(NAMES.items(), start=1):
        n = f"{i:04d}"
        (a / paths.TO_GRADE / f"{n}.pdf").write_bytes(b"%PDF-1.4 fake")
        key_rows.append({"number": n, "anon_file": f"{n}.pdf", "participant_id": pid,
                         "original_folder": f"{name}_{pid}_assignsubmission_file", "original_file": f"{name}.pdf"})
    (a / paths.TO_GRADE / "0007.pdf").write_bytes(b"%PDF-1.4 fake")
    with (a / paths.KEY).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(key_rows[0]))
        w.writeheader()
        w.writerows(key_rows)
    # two graders, two files; 0005 approved by hand in Grades.csv on top of a grading row
    grades.write_file(a / paths.GRADES_BY.format("אורי"), {n: r for n, r in ROWS.items() if r["graded_by"] == "אורי"})
    grades.write_file(a / paths.GRADES_BY.format("מתן"), {n: r for n, r in ROWS.items() if r["graded_by"] == "מתן"})
    for n, d in NOTES.items():
        (a / paths.NOTES / f"{n}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (a / paths.MARKED / "0001.pdf").write_bytes(b"%PDF-1.4 marked")
    (a / paths.COPYING).write_text(json.dumps({"pairs": [{"a": "0001", "b": "0002"}], "files": {}}), encoding="utf-8")
    monkeypatch.setenv("ASSIGNMENT_DATA", str(root))
    monkeypatch.setenv("GRADER_NAME", "אורי")
    return a


def test_gather_reads_the_folder_and_compute_matches(folder):
    s = stats.compute_assignment(folder)
    assert s["counts"]["submitted"] == 7 and s["counts"]["graded"] == 5 and s["grade"]["mean"] == 76
    assert s["copying"] == {"pairs": 1} and s["computed_by"] == "אורי" and s["computed_at"]
    assert [q["points"] for q in s["per_question"]] == [20, 30, 50]
    src = s["sources"]
    assert {f["name"] for f in src["grades"]} == {paths.GRADES_BY.format("אורי"), paths.GRADES_BY.format("מתן")}
    assert src["notes"]["count"] == 5 and src["submitted"]["count"] == 7 and src["marked"]["count"] == 1


def test_a_limit_error_is_not_a_failure(folder):
    (folder / paths.NOTES / "0007.json").write_text(json.dumps({"error": "You have hit your usage limit"}), encoding="utf-8")
    s = stats.compute_assignment(folder)
    assert s["counts"]["failed"] == 1  # only 0006; 0007 just was not graded yet
    assert s["counts"]["pending"] == 2


def test_nothing_in_the_statistics_identifies_a_student(folder):
    """The whole JSON, as text: no name, participant id, original folder or file, and no submission number."""
    s = stats.compute_assignment(folder)
    text = json.dumps(s, ensure_ascii=False)
    for pid, name in NAMES.items():
        assert pid not in text and name not in text and name.split()[0] not in text
    assert "assignsubmission" not in text
    # a submission number could only leak inside a text value (a label, a mistake, a grader): none there
    assert not [t for t in strings(s) if re.search(r"\b\d{4}\b", t) and t != s["computed_at"]]
    # the fields are a closed list: a new top-level field must be added here on purpose
    assert set(stats.compute_assignment(folder)) == {
        "version", "key", "course", "slot", "folder", "moodle_id", "title", "max_grade", "computed_at", "computed_by",
        "sources", "counts", "grade", "per_question", "over_rubric", "graders", "copying"}
    assert set(stats.compute_assignment(folder)["per_question"][0]) == {
        "key", "index", "label", "points", "graded", "mean", "success_pct", "full_marks_pct", "zero_pct", "unsure", "mistakes"}
