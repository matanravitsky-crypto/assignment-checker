"""The check after every prepared return (moodle/return_check.py): the ZIPs on the disk, read again, against the key,
the marked files and the filled worksheet. One wrong file or grade, and nothing is ready to upload."""
import csv
import json
import os
import time
import zipfile

import pytest

from moodle import paths, return_check, send
from moodle.send import BatchBlocked, prepare_batch
from moodle.upload import GRADES_FOR_MOODLE, INSTRUCTIONS_FILE
from moodle.upload_log import BATCH_FILE, batch_folder, read_batch

# Fictional names
STUDENTS = [("0001", "100", "נועה כהן"), ("0002", "200", "איתי לוי"), ("0003", "300", "מאיה מזרחי")]
FOLDER = "{name}_{participant}_assignsubmission_file"


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([header, *rows])


@pytest.fixture
def assignment(tmp_path):
    a = tmp_path / "Course" / "Assignment 1"
    for folder in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD):
        (a / folder).mkdir(parents=True)
    (a / paths.INFO).write_text(json.dumps({"id": "555", "title": "הגשה 1", "max_grade": 100}, ensure_ascii=False),
                                encoding="utf-8")
    write_csv(a / paths.KEY, ["number", "anon_file", "participant_id", "original_folder", "original_file"],
              [(n, f"{n}.pdf", p, FOLDER.format(name=name, participant=p), "work.pdf") for n, p, name in STUDENTS])
    now = time.time()
    for n, _, _ in STUDENTS:
        (a / paths.TO_GRADE / f"{n}.pdf").write_bytes(b"submission " + n.encode())
        os.utime(a / paths.TO_GRADE / f"{n}.pdf", (now - 120, now - 120))
        (a / paths.MARKED / f"{n}.pdf").write_bytes(b"marked " + n.encode())
        os.utime(a / paths.MARKED / f"{n}.pdf", (now - 60, now - 60))
    write_csv(a / paths.GRADES, ["number", "grade", "feedback", "approved"],
              [("0001", "90", "", "yes"), ("0002", "80", "", "yes"), ("0003", "70", "", "yes")])
    return a


def worksheet(path, grades_by_pid):
    write_csv(path, ["מזהה", "שם מלא", "ציון", "ציון מירבי", "הערות למשוב"],
              [[f"משתתף {pid}", "x", g, "100", ""] for pid, g in grades_by_pid.items()])


def test_a_good_batch_passes_and_leaves_a_report(assignment, tmp_path):
    sheet = tmp_path / "ציונים-c-הגשה 1-555.csv"
    worksheet(sheet, {"100": "", "200": "", "300": ""})
    s = prepare_batch(assignment, max_bytes=10_000_000, worksheet=sheet)
    assert s.verified["ok"] and s.verified["students"] == 3 and s.verified["files"] == 3
    assert s.verified["grades_matched"] == 3 and s.verified["worksheet"] is True
    report = return_check.read(assignment)
    assert report["batch"] == s.id and report["zips"][0]["files"] == 3
    text = (assignment / paths.RETURN_REPORT).read_text(encoding="utf-8-sig")
    assert "3 סטודנטים" in text and "עבר" in text and "נועה" not in text
    steps = (assignment / paths.UPLOAD / INSTRUCTIONS_FILE).read_text(encoding="utf-8-sig")
    assert "אומת" in steps and paths.RETURN_REPORT in steps


def _swap_in_zip(zip_path, a, b):
    """Rewrite the ZIP with the files of folders a and b exchanged: the wrong file for each of the two students."""
    with zipfile.ZipFile(zip_path) as z:
        items = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
    swapped = {}
    for name, data in items.items():
        folder, _, file = name.rpartition("/")
        other = b if folder == a else a if folder == b else folder
        swapped[f"{other}/{file}"] = data
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in swapped.items():
            z.writestr(name, data)


def test_a_file_in_another_students_folder_fails(assignment):
    s = prepare_batch(assignment, max_bytes=10_000_000)
    batch = read_batch(assignment)
    zip_path = batch_folder(assignment, batch) / "Graded - part 01.zip"
    _swap_in_zip(zip_path, FOLDER.format(name="נועה כהן", participant="100"), FOLDER.format(name="איתי לוי", participant="200"))
    with pytest.raises(return_check.ReturnCheckFailed, match="not the marked file"):
        return_check.check(assignment, batch, 10_000_000)
    assert s.verified["ok"]  # the check at prepare time passed: the swap came after


def test_a_participant_with_two_numbers_fails(assignment):
    prepare_batch(assignment, max_bytes=10_000_000)
    batch = read_batch(assignment)
    rows = list(csv.DictReader(open(assignment / paths.KEY, encoding="utf-8-sig")))
    rows[2]["participant_id"] = "100"  # 0003 now claims 0001's participant
    write_csv(assignment / paths.KEY, list(rows[0].keys()), [list(r.values()) for r in rows])
    with pytest.raises(return_check.ReturnCheckFailed, match="has 2 numbers"):
        return_check.check(assignment, batch, 10_000_000)


def test_a_wrong_grade_in_the_worksheet_fails(assignment):
    prepare_batch(assignment, max_bytes=10_000_000)
    batch = read_batch(assignment)
    worksheet(assignment / paths.UPLOAD / GRADES_FOR_MOODLE, {"100": "90", "200": "70", "300": "70"})  # 0002 is 80
    with pytest.raises(return_check.ReturnCheckFailed, match="0002: the grade"):
        return_check.check(assignment, batch, 10_000_000)
    worksheet(assignment / paths.UPLOAD / GRADES_FOR_MOODLE, {"100": "90", "200": "", "300": "70"})  # blank is allowed
    rep = return_check.check(assignment, batch, 10_000_000)
    assert (rep["grades_matched"], rep["grades_blank"]) == (2, 1)


def test_a_missing_or_doubled_file_fails(assignment):
    prepare_batch(assignment, max_bytes=10_000_000)
    batch = read_batch(assignment)
    zip_path = batch_folder(assignment, batch) / "Graded - part 01.zip"
    with zipfile.ZipFile(zip_path) as z:
        items = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
    first = sorted(items)[0]
    with zipfile.ZipFile(zip_path, "w") as z:  # one file gone
        for name, data in items.items():
            if name != first:
                z.writestr(name, data)
    with pytest.raises(return_check.ReturnCheckFailed, match="holds 2 files"):
        return_check.check(assignment, batch, 10_000_000)


def test_a_failed_check_leaves_nothing_ready(assignment, monkeypatch):
    def refuse(*a, **k):
        raise return_check.ReturnCheckFailed("boom")
    monkeypatch.setattr(send.return_check, "check", refuse)
    with pytest.raises(BatchBlocked, match="boom"):
        prepare_batch(assignment, max_bytes=10_000_000)
    upload = assignment / paths.UPLOAD
    assert not (upload / BATCH_FILE).exists()
    assert not list(upload.rglob("*.zip"))
    assert not (assignment / paths.RETURN_CHECK).exists()


def test_the_steps_give_the_moodle_pages_and_a_shortcut_next_to_the_zips(assignment, tmp_path):
    sheet = tmp_path / "ציונים-c-הגשה 1-555.csv"
    worksheet(sheet, {"100": "", "200": "", "300": ""})
    prepare_batch(assignment, max_bytes=10_000_000, worksheet=sheet)
    steps = (assignment / paths.UPLOAD / INSTRUCTIONS_FILE).read_text(encoding="utf-8-sig")
    assert paths.MOODLE_UPLOAD_ZIP_PAGE.format(id="555") in steps
    assert paths.MOODLE_UPLOAD_GRADES_PAGE.format(id="555") in steps
    assert "גוררים" in steps
    folder = batch_folder(assignment, read_batch(assignment))
    shortcut = (folder / paths.UPLOAD_SHORTCUT).read_text(encoding="ascii")
    assert shortcut.startswith("[InternetShortcut]") and "pluginaction=uploadzip" in shortcut and "id=555" in shortcut
    assert "pluginaction=uploadgrades" in (assignment / paths.UPLOAD / paths.GRADES_SHORTCUT).read_text(encoding="ascii")


def test_a_worksheet_without_a_feedback_column_gets_grades_only(assignment, tmp_path):
    """"Feedback comments" off in the assignment: Moodle's worksheet has no feedback column. The grades still go in."""
    sheet = tmp_path / "ציונים-c-הגשה 1-555.csv"
    write_csv(sheet, ["מזהה", "שם מלא", "ציון", "ציון מירבי"], [[f"משתתף {p}", "x", "", "100"] for p in ("100", "200", "300")])
    s = prepare_batch(assignment, max_bytes=10_000_000, worksheet=sheet)
    assert s.grades_filled == 3 and s.verified["grades_matched"] == 3
    rows = {r[0]: r for r in csv.reader((assignment / paths.UPLOAD / GRADES_FOR_MOODLE).read_text(encoding="utf-8-sig").splitlines())}
    assert rows["משתתף 200"][2] == "80"


def test_under_the_submission_policy_the_worksheet_carries_the_course_grade_and_the_check_passes(assignment, tmp_path):
    # LA Assignment 0 (2026-11-18): Moodle gets course_grade, not the rubric's grade. The check reads the worksheet
    # against the grade that goes to Moodle; against the rubric's grade it would refuse every such batch
    info = json.loads((assignment / paths.INFO).read_text(encoding="utf-8"))
    (assignment / paths.INFO).write_text(json.dumps({**info, "moodle_grade": {"basis": "submission"}}, ensure_ascii=False),
                                         encoding="utf-8")
    write_csv(assignment / paths.GRADES, ["number", "grade", "feedback", "approved", "course_grade"],
              [("0001", "90", "", "yes", "100"), ("0002", "80", "", "yes", "95"), ("0003", "70", "", "yes", "60")])
    sheet = tmp_path / "ציונים-c-הגשה 1-555.csv"
    worksheet(sheet, {"100": "", "200": "", "300": ""})
    s = prepare_batch(assignment, max_bytes=10_000_000, worksheet=sheet)
    assert s.verified["ok"] and s.verified["grades_matched"] == 3
    with open(assignment / paths.UPLOAD / GRADES_FOR_MOODLE, encoding="utf-8-sig", newline="") as f:
        filled = {row[0]: row[2] for row in list(csv.reader(f))[1:]}
    assert filled == {"משתתף 100": "100", "משתתף 200": "95", "משתתף 300": "60"}
