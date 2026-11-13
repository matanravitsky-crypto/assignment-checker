"""Editing a grade: one function, a required reason, every place updated, and the log says who, when, from, to and why."""
from __future__ import annotations

import pymupdf
import pytest

import activity_log
from grading import grade as grading, grade_edit
from moodle import grades, paths
from tests.grading.test_grade import answer, asg, no_real_claude, root, text  # noqa: F401 (fixtures)

FULL = [20] * 5


def graded(root, n="0001", **kw):
    a = asg(root)
    grading.grade_assignment(a.dir, [n], ask=lambda req: answer(**kw))
    return a


def summary(a, n="0001") -> str:
    with pymupdf.open(a.dir / paths.MARKED / f"{n}.pdf") as doc:
        return text(doc[0])


def test_editing_an_existing_grade_needs_a_reason_and_changes_nothing_without_one(root):
    a = graded(root)
    before = grading.read_grades(a.dir)["0001"]["grade"]
    for reason in ("", "   "):
        with pytest.raises(grade_edit.ReasonRequired):
            grading.save_review(a.dir, "0001", FULL, [], "", by="dana (PC)", reason=reason)
    assert grading.read_grades(a.dir)["0001"]["grade"] == before == "85"
    assert activity_log.read(a.dir, "grade_edit") == []


def test_an_edit_updates_the_pdf_the_grades_file_and_the_log(root):
    a = graded(root)
    out = grading.save_review(a.dir, "0001", FULL, [], "יפה מאוד", by="dana (PC)", reason="ערעור: הנימוק בשאלה 12 נמצא בעמוד 2")
    assert out == {"number": "0001", "grade": 100, "from": "85", "updated": ["marked_pdf", "notes", "grades_csv"]}
    # 2. עמוד הסיכום ב-PDF המסומן
    assert "100 מתוך 100" in summary(a)
    # 3. Grades by <name>.csv של מי שערך, ומשם (הקריאה המאוחדת) הציון עולה למודל
    mine = grades.read_file(grades.own_file(a.dir))["0001"]
    assert mine["grade"] == "100" and mine["approved"].startswith("dana (PC) ") and mine["points"] == "20;20;20;20;20"
    assert grading.read_grades(a.dir)["0001"]["grade"] == "100"
    # היומן: מי, מתי, מאיזה ציון לאיזה ולמה
    (e,) = activity_log.read(a.dir, "grade_edit")  # the grading run itself logs grade_set events now
    assert (e["action"], e["by"], e["number"], e["from"], e["to"], e["kind"]) == ("grade_edit", "dana (PC)", "0001", "85", "100", "edit")
    assert e["reason"] == "ערעור: הנימוק בשאלה 12 נמצא בעמוד 2" and e["at"]
    assert e["points_from"] == "20;15;20;20;10" and e["points_to"] == "20;20;20;20;20"
    assert e["updated"] == ["marked_pdf", "notes", "grades_csv"]  # database, moodle_table, stats_db: only when connected
    assert grade_edit.history(a.dir, "1") == [e]


def test_a_second_edit_logs_from_the_edited_grade(root):
    a = graded(root)
    grading.save_review(a.dir, "0001", FULL, [], "", by="dana (PC)", reason="ערעור")
    grading.save_review(a.dir, "0001", [20, 20, 20, 20, 0], [], "", by="ori (LAPTOP)", reason="טעות שלי בעריכה")
    assert [(e["from"], e["to"], e["by"]) for e in grade_edit.history(a.dir, "0001")] == [
        ("85", "100", "dana (PC)"), ("100", "80", "ori (LAPTOP)")]
    assert grading.read_grades(a.dir)["0001"]["grade"] == "80" and "80 מתוך 100" in summary(a)


def test_approving_from_the_review_queue_needs_no_reason_but_is_logged(root):
    a = graded(root, review="לא בטוח בשאלה 12")
    grading.save_review(a.dir, "0001", FULL, [], "", by="dana (PC)")
    (e,) = grade_edit.history(a.dir, "0001")
    assert (e["kind"], e["from"], e["to"], e["reason"]) == ("review", "85", "100", "")
    # אחרי האישור זו כבר עריכה: צריך סיבה
    with pytest.raises(grade_edit.ReasonRequired):
        grading.save_review(a.dir, "0001", FULL, [], "", by="dana (PC)")


def test_a_first_grade_for_work_that_failed_needs_no_reason(root):
    a = asg(root)
    grading.save_review(a.dir, "0002", FULL, [], "", by="x")
    (e,) = grade_edit.history(a.dir, "0002")
    assert (e["kind"], e["from"], e["to"]) == ("first", None, "100")


def test_the_reason_never_keeps_a_student_name(root):
    a = graded(root)
    grading.save_review(a.dir, "0001", FULL, [], "", by="x", reason="נועה כהן ערערה")
    assert "נועה" not in grade_edit.history(a.dir, "0001")[0]["reason"]


def test_a_new_place_to_update_is_one_more_target(root):
    """מקום חדש לעדכן בו ציון = יעד חדש ברשימה. הפונקציה לא משתנה."""
    a = graded(root)
    seen = []

    class Sheet:
        name, label = "sheet", "גיליון"

        def enabled(self):
            return True

        def apply(self, edit):
            seen.append((edit.number, edit.old_grade, edit.new_grade, edit.reason, edit.by))

    out = grade_edit.edit_grade(a.dir, "0001", FULL, [], "", by="x", reason="ערעור",
                                targets=[*grade_edit.TARGETS, Sheet()])
    assert seen == [("0001", "85", "100", "ערעור", "x")] and out["updated"][-1] == "sheet"


def test_the_database_is_off_until_connected_and_then_updated_first(root):
    a = graded(root)
    (db,) = [t for t in grade_edit.TARGETS if isinstance(t, grade_edit.DatabaseTarget)]
    assert not db.enabled() and grade_edit.TARGETS[0] is db

    class Store:
        def __init__(self):
            self.saved = []

        def save_grade(self, edit):
            self.saved.append((edit.number, edit.new_grade, edit.reason))

    store = Store()
    grade_edit.connect_database(store)
    try:
        out = grading.save_review(a.dir, "0001", FULL, [], "", by="x", reason="ערעור")
    finally:
        grade_edit.connect_database(None)
    assert store.saved == [("0001", "100", "ערעור")] and out["updated"][0] == "database"
    assert not db.enabled()


def test_a_failing_place_stops_says_what_was_updated_and_is_logged(root):
    a = graded(root)

    class Broken:
        name, label = "broken", "מקום שבור"

        def enabled(self):
            return True

        def apply(self, edit):
            raise OSError("OneDrive נעל את הקובץ")

    pdf, csv_ = grade_edit.MarkedPdfTarget(), grade_edit.GradesCsvTarget()
    with pytest.raises(grade_edit.EditIncomplete) as e:
        grade_edit.edit_grade(a.dir, "0001", FULL, [], "", by="x", reason="ערעור", targets=[pdf, Broken(), csv_])
    assert e.value.updated == ["marked_pdf"] and e.value.failed == "broken"
    assert "מקום שבור" in str(e.value) and "עמוד הסיכום" in str(e.value)
    assert grading.read_grades(a.dir)["0001"]["grade"] == "85"  # הקובץ שאחרי השבור לא עודכן
    (entry,) = grade_edit.history(a.dir, "0001")
    assert entry["action"] == "grade_edit_failed" and entry["failed"] == "broken" and "OneDrive" in entry["error"]


def test_anyone_may_edit_a_work_that_someone_else_graded_and_approved(root, monkeypatch):
    """פתוח לכולם (מתן, 2026-11-07): כל אחד בצוות עורך כל עבודה, גם כשמישהו אחר לקח אותה, בדק ואישר."""
    a = asg(root)
    monkeypatch.setenv("GRADER_NAME", "דנה")
    grading.grade_assignment(a.dir, ["0001"], ask=lambda req: answer())
    grading.save_review(a.dir, "0001", [20, 15, 20, 20, 15], [], "", by="dana (PC1)", reason="תיקון")
    monkeypatch.setenv("GRADER_NAME", "אורי")
    out = grading.save_review(a.dir, "0001", FULL, [], "", by="ori (LAPTOP)", reason="ערעור")
    assert out["from"] == "90" and out["grade"] == 100
    assert grades.read_file(grades.own_file(a.dir, "דנה"))["0001"]["grade"] == "90"  # הקובץ של דנה לא נגעו בו
    assert grading.read_grades(a.dir)["0001"]["grade"] == "100"  # והציון שעולה למודל הוא של העריכה האחרונה
    assert "100 מתוך 100" in summary(a)


class Table:
    """Stands in for moodle_table.build: grading never imports moodle_table, the system connects it (connect_moodle_table)."""

    def __init__(self, fail: str = ""):
        self.built, self.fail = [], fail

    def __call__(self, assignment_dir):
        if self.fail:
            raise OSError(self.fail)
        self.built.append((assignment_dir, grading.read_grades(assignment_dir).get("0001", {}).get("grade")))


@pytest.fixture
def table():
    t = Table()
    grade_edit.connect_moodle_table(t)
    yield t
    grade_edit.connect_moodle_table(None)


def test_the_moodle_table_is_off_until_connected(root):
    """grading alone (the exercise-grader skill, `python -m grading`) does not build Grades for Moodle.csv: every upload
    builds it again before it fills Moodle's worksheet (tests/integration/test_moodle_table_after_grading.py)."""
    (t,) = [t for t in grade_edit.TARGETS if isinstance(t, grade_edit.MoodleTableTarget)]
    assert not t.enabled() and grade_edit.moodle_table_builder() is None
    a = graded(root)
    assert not (a.dir / paths.MOODLE_TABLE).exists()
    out = grading.save_review(a.dir, "0001", FULL, [], "", by="x", reason="ערעור")
    assert "moodle_table" not in out["updated"] and not (a.dir / paths.MOODLE_TABLE).exists()


def test_once_connected_the_moodle_table_is_built_after_a_run_and_after_each_edit(root, table):
    a = graded(root)
    assert table.built == [(a.dir, "85")]  # at the end of the grading run
    out = grading.save_review(a.dir, "0001", FULL, [], "", by="dana (PC)", reason="ערעור")
    # after the grades file: the table is built from the edited grade, and before the statistics
    assert out["updated"] == ["marked_pdf", "notes", "grades_csv", "moodle_table"]
    assert table.built[-1] == (a.dir, "100")
    names = [t.name for t in grade_edit.TARGETS]
    assert names.index("grades_csv") < names.index("moodle_table") < names.index("stats_db")


def test_a_connected_moodle_table_is_not_optional_an_edit_that_misses_it_fails(root):
    """A stale table would send the old grade to Moodle: unlike the statistics, a failure stops the edit and says so."""
    a = graded(root)
    grade_edit.connect_moodle_table(Table(fail="OneDrive נעל את הקובץ"))
    try:
        with pytest.raises(grade_edit.EditIncomplete) as e:
            grading.save_review(a.dir, "0001", FULL, [], "", by="x", reason="ערעור")
        # a grading run is not stopped by it: the table is derived, and the upload builds it again
        rep = grading.grade_assignment(a.dir, ["0001", "0003"], ask=lambda req: answer())
    finally:
        grade_edit.connect_moodle_table(None)
    assert e.value.failed == "moodle_table" and e.value.updated == ["marked_pdf", "notes", "grades_csv"]
    assert "Grades for Moodle.csv" in str(e.value) and "אפשר לשמור שוב" in str(e.value)
    (entry,) = grade_edit.history(a.dir, "0001")
    assert entry["action"] == "grade_edit_failed" and entry["failed"] == "moodle_table"
    assert rep.graded == ["0003"]
