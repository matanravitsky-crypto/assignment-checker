"""Grades for Moodle.csv when grading runs without the dashboard (`python -m grading`, the exercise-grader skill).

grading does not import moodle_table (it would take the return to Moodle with it: upload, anonymize, pull_check), so
only the dashboard connects it (web_server.connect_stores). Without it the table in the Drive can be older than the
grades. That never sends an old grade to Moodle: the upload builds the table again before it fills Moodle's worksheet
(moodle/upload.py), and the grades upload reads the merged grades themselves (moodle/send_grades.py), never the table.
"""
from __future__ import annotations

import csv

from grading import __main__ as grading_cli, grade as grading, grade_edit
from moodle import moodle_table, paths, send_grades
from moodle.upload import GRADES_FOR_MOODLE, prepare_upload
from tests.grading.test_grade_edit import FULL, graded
from tests.grading.test_grade import no_real_claude, root  # noqa: F401  (fixtures)


def table(a) -> dict[str, dict]:
    return {r["number"]: r for r in moodle_table.read(a.dir)}


def test_a_table_left_behind_by_grading_alone_never_sends_an_old_grade(root, tmp_path):
    grade_edit.connect_moodle_table(moodle_table.build)  # graded in the dashboard first: the table says 85
    try:
        a = graded(root)
    finally:
        grade_edit.connect_moodle_table(None)
    assert table(a)["0001"]["grade"] == "85"
    # then an edit with nothing connected (grading alone): the grade is 100, the table in the Drive still says 85
    grading.save_review(a.dir, "0001", FULL, [], "", by="dana (PC)", reason="ערעור")
    assert grading.read_grades(a.dir)["0001"]["grade"] == "100" and table(a)["0001"]["grade"] == "85"

    # the grades upload takes the grades themselves
    assert send_grades.pending(a.dir, returned={"0001"})["0001"]["grade"] == "100"
    # "Prepare return" builds the table again before it fills Moodle's worksheet
    sheet = tmp_path / "worksheet.csv"
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([["מזהה", "שם מלא", "ציון", "ציון מירבי", "הערות למשוב"],
                                 ["משתתף 1001", "x", "", "100", ""], ["משתתף 1002", "y", "", "100", ""]])
    rep = prepare_upload(a.dir, sheet)
    assert rep["grades_filled"] == 1
    with open(a.dir / paths.UPLOAD / GRADES_FOR_MOODLE, encoding="utf-8-sig") as f:
        filled = {r[0]: r for r in csv.reader(f)}
    assert filled["משתתף 1001"][2] == "100" and filled["משתתף 1002"][2] == ""
    assert table(a)["0001"]["grade"] == "100"


def test_python_m_grading_says_the_table_was_not_built(root, monkeypatch, capsys):
    a = graded(root)
    rep = grading.GradeReport(total=1, graded=["0002"])
    monkeypatch.setattr(grading, "grade_assignment", lambda *args, **kw: rep)
    assert grading_cli.main(["3438636", "--ids", "0002"]) == 0
    out = capsys.readouterr().out
    assert paths.MOODLE_TABLE in out and "python -m moodle table 3438636" in out
    assert not (a.dir / paths.MOODLE_TABLE).exists()
