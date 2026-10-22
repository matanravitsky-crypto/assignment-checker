import csv
import json
from datetime import datetime
import os
import time
import zipfile

import pytest

from moodle import paths
from moodle.send import BatchBlocked, prepare_batch
from moodle.upload import INSTRUCTIONS_FILE
from moodle.upload_log import BATCH_FILE, file_hash, last_hashes, read_batch, read_log, record_zip

# Fictional names (from tests.sample_files.NAMES, copied so these tests don't load PyMuPDF)
STUDENTS = [("0001", "100", "נועה כהן"), ("0002", "200", "איתי לוי"), ("0003", "300", "מאיה מזרחי")]
FOLDER = "{name}_{participant}_assignsubmission_file"


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([header, *rows])


def write_grades(a, rows):
    """rows: (number, grade, approved)."""
    write_csv(a / paths.GRADES, ["number", "grade", "feedback", "approved"], [(n, g, "", ok) for n, g, ok in rows])


@pytest.fixture
def assignment(tmp_path):
    """Key 0001-0003; submissions in TO_GRADE written first, then small marked files 0001.pdf and 0002.pdf, so marked are newer."""
    a = tmp_path / "Course" / "Assignment 1"
    for folder in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD):
        (a / folder).mkdir(parents=True)
    (a / paths.INFO).write_text(json.dumps({"id": "555", "title": "הגשה 1"}, ensure_ascii=False), encoding="utf-8")
    write_csv(a / paths.KEY, ["number", "anon_file", "participant_id", "original_folder", "original_file"],
              [(n, f"{n}.pdf", p, FOLDER.format(name=name, participant=p), "work.pdf") for n, p, name in STUDENTS])
    now = time.time()
    for n, _, _ in STUDENTS:
        (a / paths.TO_GRADE / f"{n}.pdf").write_bytes(b"submission " + n.encode())
        os.utime(a / paths.TO_GRADE / f"{n}.pdf", (now - 120, now - 120))
    for n in ("0001", "0002"):
        (a / paths.MARKED / f"{n}.pdf").write_bytes(b"marked " + n.encode())
        os.utime(a / paths.MARKED / f"{n}.pdf", (now - 60, now - 60))
    return a


def batch_numbers(a):
    return {f["number"] for z in read_batch(a)["zips"] for f in z["files"]}


def test_prepare_skips_returned_and_builds_zips_with_a_batch(assignment):
    s = prepare_batch(assignment, max_bytes=10_000_000)
    assert (s.students, s.files, [z["name"] for z in s.zips]) == (2, 2, ["Graded - part 01.zip"])
    assert read_batch(assignment)["id"] == s.id
    record_zip(assignment, "Graded - part 01.zip", by="me (PC)")
    assert prepare_batch(assignment).students == 0


def test_resubmitted_after_grading_is_held_back(assignment):
    later = time.time() + 60
    os.utime(assignment / paths.TO_GRADE / "0002.pdf", (later, later))
    s = prepare_batch(assignment)
    assert s.resubmitted == ["0002"] and s.students == 1


def test_not_approved_is_reported_but_still_uploaded(assignment):
    write_grades(assignment, [("0001", "90", "yes"), ("0002", "80", "")])
    s = prepare_batch(assignment)
    assert s.not_approved == ["0002"] and s.students == 2


def test_too_big_file_holds_back_the_whole_number(assignment):
    (assignment / paths.MARKED / "0002-2.pdf").write_bytes(b"x" * 2000)
    s = prepare_batch(assignment, max_bytes=1500)
    assert s.too_big == ["0002-2.pdf"]
    assert {f["number"] for z in read_batch(assignment)["zips"] for f in z["files"]} == {"0001"}


def test_log_conflict_copy_blocks_prepare(assignment):
    (assignment / paths.UPLOAD / "Upload log-PC2.csv").write_text("x", encoding="utf-8")
    with pytest.raises(BatchBlocked) as blocked:
        prepare_batch(assignment)
    assert "Upload log-PC2.csv" in str(blocked.value)
    assert read_batch(assignment) is None  # nothing was built


@pytest.mark.parametrize("value, approved", [
    ("yes", True), ("1", True), ("כן", True), ("TRUE", True),
    ("", False), ("0", False), ("no", False), ("False", False), ("לא", False), ("  NO ", False),
])
def test_approval_values_follow_grading_is_approved(assignment, value, approved):
    write_grades(assignment, [("0001", "90", "yes"), ("0002", "80", value)])
    assert prepare_batch(assignment).not_approved == ([] if approved else ["0002"])


def test_a_number_without_a_grade_row_is_not_approved_and_missing_grades_file_is_fine(assignment):
    assert not (assignment / paths.GRADES).exists()
    s = prepare_batch(assignment)
    assert s.not_approved == ["0001", "0002"]
    write_grades(assignment, [("0001", "90", "yes")])
    assert prepare_batch(assignment).not_approved == ["0002"]


def test_not_approved_ignores_numbers_that_are_held_back(assignment):
    later = time.time() + 60
    os.utime(assignment / paths.TO_GRADE / "0002.pdf", (later, later))
    write_grades(assignment, [("0001", "90", "yes"), ("0002", "80", "")])
    s = prepare_batch(assignment)
    assert s.resubmitted == ["0002"] and s.not_approved == []


def test_resubmission_is_judged_by_all_of_a_numbers_submission_files(assignment):
    # 0002 has a second submission file, and only that one is newer than the marked work
    with open(assignment / paths.KEY, "a", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerow(["0002", "0002-2.pdf", "200", FOLDER.format(name="איתי לוי", participant="200"), "extra.pdf"])
    (assignment / paths.TO_GRADE / "0002-2.pdf").write_bytes(b"second file")
    later = time.time() + 60
    os.utime(assignment / paths.TO_GRADE / "0002-2.pdf", (later, later))
    s = prepare_batch(assignment)
    assert s.resubmitted == ["0002"] and s.students == 1


def test_a_changed_marked_file_goes_up_again(assignment):
    prepare_batch(assignment)
    record_zip(assignment, "Graded - part 01.zip", by="me (PC)")
    (assignment / paths.MARKED / "0001.pdf").write_bytes(b"marked again")
    s = prepare_batch(assignment)
    assert (s.students, s.files) == (1, 1)
    assert batch_numbers(assignment) == {"0001"}


def test_a_marked_number_missing_from_the_key_stops_the_batch(assignment):
    (assignment / paths.MARKED / "0009.pdf").write_bytes(b"marked")
    with pytest.raises(ValueError):
        prepare_batch(assignment)


def test_batch_lists_hashes_by_number_and_the_zip_holds_the_files_under_moodle_folder_names(assignment):
    (assignment / paths.MARKED / "0002-2.pdf").write_bytes(b"second marked file")
    s = prepare_batch(assignment)
    batch = read_batch(assignment)
    assert (batch["id"], batch["assignment_id"]) == (s.id, "555")
    datetime.fromisoformat(batch["created_at"])
    assert (s.assignment_id, s.title) == ("555", "הגשה 1")
    [zip_entry] = batch["zips"]
    assert zip_entry["files"] == [
        {"number": n, "file": f, "sha256": file_hash(assignment / paths.MARKED / f)}
        for n, f in [("0001", "0001.pdf"), ("0002", "0002.pdf"), ("0002", "0002-2.pdf")]]
    assert (s.students, s.files) == (2, 3)
    assert s.zips == [{"name": "Graded - part 01.zip", "count": 3,
                       "mb": round((assignment / paths.UPLOAD / "Graded - part 01.zip").stat().st_size / 1_000_000, 1)}]
    with zipfile.ZipFile(assignment / paths.UPLOAD / "Graded - part 01.zip") as archive:
        assert sorted(archive.namelist()) == sorted([
            FOLDER.format(name="נועה כהן", participant="100") + "/feedback.pdf",
            FOLDER.format(name="איתי לוי", participant="200") + "/feedback.pdf",
            FOLDER.format(name="איתי לוי", participant="200") + "/feedback-2.pdf"])


def test_the_batch_file_has_numbers_and_no_student_names(assignment):
    prepare_batch(assignment)
    text = (assignment / paths.UPLOAD / BATCH_FILE).read_text(encoding="utf-8-sig")
    assert not any(name in text for _, _, name in STUDENTS)
    assert not any(p in text for _, p, _ in STUDENTS)


def test_each_run_makes_a_new_batch_id_and_replaces_the_old_zips(assignment):
    first = prepare_batch(assignment, max_bytes=20)  # two marked files of 11 bytes don't fit one ZIP together
    assert [z["name"] for z in first.zips] == ["Graded - part 01.zip", "Graded - part 02.zip"]
    second = prepare_batch(assignment, max_bytes=10_000_000)
    assert second.id != first.id
    assert sorted(p.name for p in (assignment / paths.UPLOAD).glob("Graded - part *.zip")) == ["Graded - part 01.zip"]
    assert read_batch(assignment)["id"] == second.id


def test_prepare_writes_the_upload_steps_with_the_record_command(assignment):
    prepare_batch(assignment)
    steps = (assignment / paths.UPLOAD / INSTRUCTIONS_FILE).read_text(encoding="utf-8-sig")
    assert "Graded - part 01.zip" in steps
    assert 'python -m moodle record 555 "<שם ה-ZIP>"' in steps


def test_prepare_does_not_write_the_log(assignment):
    prepare_batch(assignment)
    assert read_log(assignment) == [] and last_hashes(assignment) == {}
    assert not (assignment / paths.UPLOAD / "Upload log.csv").exists()
