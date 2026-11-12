"""Grading as a transaction: the grade row is written last, an invalid row is never written, and a failure in the
save leaves one work failed (visible to the doctor) and the rest graded."""
from __future__ import annotations

from grading import grade as grading
from datastore import doctor
from moodle import grades, paths

from tests.grading.test_grade import FakeClaude, asg, root  # noqa: F401  (fixtures of the grading tests)


def test_an_invalid_row_is_refused_and_only_that_work_fails(root, monkeypatch):
    a = asg(root)
    real = grades.update_own

    def poisoned(assignment_dir, number, row, **kw):
        if grades.number_key(number) == "0002":
            row = {**row, "grade": "abc"}  # what the schema must never let through
        return real(assignment_dir, number, row, **kw)
    monkeypatch.setattr(grades, "update_own", poisoned)
    rep = grading.grade_assignment(a.dir, ask=FakeClaude(), parallel=1)
    assert rep.graded == ["0001", "0003"] and list(rep.failed) == ["0002"] and "אינו מספר" in rep.failed["0002"]
    rows = grades.read(a.dir)
    assert set(rows) == {"0001", "0003"}  # no "abc" anywhere
    assert "abc" not in (a.dir / paths.GRADES_BY.format("בודק א")).read_text(encoding="utf-8-sig")
    # the notes and the marked PDF of 0002 exist (written before the row), the doctor says so, and the failure is recorded
    assert (a.dir / paths.MARKED / "0002.pdf").exists() and "error" in grading.read_notes(a.dir, "0002")
    codes = {(p.code, p.number) for p in doctor.check(a.dir).problems}
    assert ("marked_without_grade", "0002") in codes


def test_a_crash_in_the_save_does_not_stop_the_other_works(root, monkeypatch):
    a = asg(root)
    calls = []
    real = grades.update_own

    def flaky(assignment_dir, number, row, **kw):
        calls.append(number)
        if len(calls) == 1:
            raise OSError("disk full")
        return real(assignment_dir, number, row, **kw)
    monkeypatch.setattr(grades, "update_own", flaky)
    rep = grading.grade_assignment(a.dir, ask=FakeClaude(), parallel=1)
    assert len(rep.graded) == 2 and len(rep.failed) == 1 and "disk full" in next(iter(rep.failed.values()))
    # a second run grades the failed one again (it has a marked PDF but the row is missing, so it is pending)
    failed = next(iter(rep.failed))
    assert failed not in grades.read(a.dir)
    rep2 = grading.grade_assignment(a.dir, [failed], ask=FakeClaude(), parallel=1)
    assert rep2.graded == [failed] and failed in grades.read(a.dir)


def test_the_row_is_written_after_the_notes_and_the_pdf(root, monkeypatch):
    a = asg(root)
    order = []
    real_notes, real_update = grading.write_notes, grades.update_own
    monkeypatch.setattr(grading, "write_notes", lambda *args, **kw: (order.append("notes"), real_notes(*args, **kw))[1])
    monkeypatch.setattr(grades, "update_own", lambda *args, **kw: (order.append("row"), real_update(*args, **kw))[1])
    grading.grade_assignment(a.dir, ["0001"], ask=FakeClaude(), parallel=1)
    assert order == ["notes", "row"] and (a.dir / paths.MARKED / "0001.pdf").exists()
