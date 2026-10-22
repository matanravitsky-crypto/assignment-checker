import os
import time
from datetime import datetime

import pytest

from moodle import paths
from moodle.lock import me
from moodle.send import UPLOAD_LOCK, SimulatedDriver, UploadResult, prepare_batch, run_batch
from moodle.upload_log import batch_folder, read_batch, read_log, record_zip, write_batch
from test_send_prepare import STUDENTS, assignment  # noqa: F401  (assignment: the fixture, used by `batch` below)

PART_1, PART_2 = "Graded - part 01.zip", "Graded - part 02.zip"


@pytest.fixture
def batch(assignment):
    """The prepared assignment, with each of its 2 marked files (11 bytes) in a ZIP of its own."""
    return assignment, prepare_batch(assignment, max_bytes=20)


class RecordingDriver:
    """Keeps exactly what run_batch hands to the driver."""

    def __init__(self):
        self.calls = []
        self.hashes = []

    def upload_zip(self, info, zip_path, expected, dry_run, sha256=None):
        self.calls.append((info, zip_path, expected, dry_run))
        self.hashes.append(sha256)
        return UploadResult("imported", rows=expected, imported=expected)


# ---------- the simulated driver ----------
def test_simulated_driver_returns_its_list_in_order_then_imports_everything(tmp_path):
    results = [UploadResult("needs_login", message="x")]
    d = SimulatedDriver(results)
    assert d.upload_zip({}, tmp_path / "a.zip", 3, False).status == "needs_login"
    assert d.upload_zip({}, tmp_path / "b.zip", 3, False) == UploadResult("imported", rows=3, imported=3)
    assert d.upload_zip({}, tmp_path / "c.zip", 3, True) == UploadResult("dry_run_ok", rows=3)
    assert d.calls == ["a.zip", "b.zip", "c.zip"]
    assert len(results) == 1  # the caller's list is left alone


def test_simulated_driver_waits_for_its_delay(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)
    SimulatedDriver(delay=0.5).upload_zip({}, tmp_path / "a.zip", 1, False)
    SimulatedDriver().upload_zip({}, tmp_path / "a.zip", 1, False)
    assert slept == [0.5]


# ---------- the loop ----------
def test_all_zips_upload_and_get_recorded(batch):
    a, s = batch
    d = SimulatedDriver()
    r = run_batch(a, s.id, d)
    assert (r.stopped, r.done_zips, len(d.calls)) == (None, [PART_1, PART_2], 2)
    assert not (a / UPLOAD_LOCK).exists()
    assert (r.total_zips, r.recorded) == (2, 2)
    assert sorted(row["file"] for row in read_log(a)) == ["0001.pdf", "0002.pdf"]
    assert {row["by"] for row in read_log(a)} == {me()}
    assert r.message == "הסתיים: 2 מתוך 2 קבצי ZIP הועלו, 2 קבצים נרשמו ביומן."


def test_resume_skips_zips_already_recorded(batch):
    a, s = batch
    r = run_batch(a, s.id, SimulatedDriver([UploadResult("imported", 1, 1), UploadResult("needs_login")]))
    assert r.stopped == "needs_login" and r.done_zips == [PART_1]
    d = SimulatedDriver()
    resumed = run_batch(a, s.id, d)
    assert resumed.stopped is None and d.calls == [PART_2]
    assert (resumed.done_zips, resumed.recorded) == ([PART_1, PART_2], 1)  # done_zips: the whole batch so far; recorded: this run


def test_nothing_to_upload_when_every_zip_is_already_recorded(batch):
    a, s = batch
    run_batch(a, s.id, SimulatedDriver())
    d = SimulatedDriver()
    r = run_batch(a, s.id, d, dry_run=True)
    assert (r.stopped, r.done_zips, r.recorded, d.calls) == (None, [PART_1, PART_2], 0, [])
    assert r.message == "אין מה להעלות: כל קבצי ה-ZIP כבר הועלו."


def test_a_zip_whose_file_changed_since_its_last_upload_is_not_skipped(batch):
    a, s = batch
    run_batch(a, s.id, SimulatedDriver())
    (a / paths.MARKED / "0001.pdf").write_bytes(b"marked again")
    again = prepare_batch(a, max_bytes=20)
    d = SimulatedDriver()
    assert run_batch(a, again.id, d).stopped is None and d.calls == [PART_1]
    assert [row["file"] for row in read_log(a)].count("0001.pdf") == 2


def test_count_mismatch_stops_without_recording(batch):
    a, s = batch
    r = run_batch(a, s.id, SimulatedDriver([UploadResult("imported", rows=1, imported=0)]))
    assert r.stopped == "error" and read_log(a) == []
    assert not (a / UPLOAD_LOCK).exists()


@pytest.mark.parametrize("result", [
    UploadResult("imported", rows=2, imported=1),             # Moodle's list has more rows than the ZIP has files
    UploadResult("imported", rows=1, imported=2),             # imported more than the files in the ZIP
    UploadResult("imported", rows=1),                         # no import count at all
    UploadResult("imported", imported=1),                     # no row count at all
    UploadResult("imported", rows=1, imported=1, skipped=1),  # imported + skipped over the ZIP's files
])
def test_imported_with_numbers_that_do_not_add_up_is_an_error(batch, result):
    a, s = batch
    r = run_batch(a, s.id, SimulatedDriver([result]))
    assert (r.stopped, r.done_zips, read_log(a)) == ("error", [], [])
    assert r.message.startswith(f"{PART_1}: ")


def test_a_driver_without_a_message_still_gets_the_numbers_in_the_report(batch):
    a, s = batch
    r = run_batch(a, s.id, SimulatedDriver([UploadResult("imported", rows=1, imported=0)]))
    assert r.message == f"{PART_1}: קבצים צפויים: 1, קבצים ש-Moodle עיבד: 1, יובאו: 0, דולגו: 0"


def test_identical_files_skipped_by_moodle_count_as_done(batch):
    a, s = batch
    r = run_batch(a, s.id, SimulatedDriver([UploadResult("imported", 1, 0, skipped=1)]))
    assert (r.stopped, r.done_zips, len(read_log(a))) == (None, [PART_1, PART_2], 2)


@pytest.mark.parametrize("status", ["needs_login", "mismatch", "error"])
def test_a_stop_status_from_the_driver_stops_with_that_status_and_its_message(batch, status):
    a, s = batch
    r = run_batch(a, s.id, SimulatedDriver([UploadResult("imported", 1, 1), UploadResult(status, message="הודעה")]))
    assert (r.stopped, r.done_zips, r.recorded, r.message) == (status, [PART_1], 1, f"{PART_2}: הודעה")
    assert [row["file"] for row in read_log(a)] == ["0001.pdf"]  # the first ZIP stays recorded, the second is not


def test_a_result_the_loop_does_not_know_stops_as_an_error(batch):
    a, s = batch
    r = run_batch(a, s.id, SimulatedDriver([UploadResult("dry_run_ok", rows=1)]))  # a real run that only checked
    assert (r.stopped, read_log(a)) == ("error", [])


def test_stale_batch_and_foreign_lock_are_refused(batch):
    a, s = batch
    stale = run_batch(a, "old-id", SimulatedDriver())
    assert stale.stopped == "stale" and stale.message == "הקבצים השתנו מאז ההכנה. צריך להכין שוב."
    assert not (a / UPLOAD_LOCK).exists()  # a refused run leaves no lock behind
    (a / UPLOAD_LOCK).write_text("other (PC2)", encoding="utf-8")
    assert run_batch(a, s.id, SimulatedDriver()).stopped == "locked"


def test_no_batch_at_all_is_stale(assignment):
    assert run_batch(assignment, "any", SimulatedDriver()).stopped == "stale"


def test_the_lock_message_says_who_and_since_when_and_the_other_lock_stays(batch):
    a, s = batch
    lock = a / UPLOAD_LOCK
    lock.write_text("other (PC2)", encoding="utf-8")
    since = time.time() - 300
    os.utime(lock, (since, since))
    d = SimulatedDriver()
    r = run_batch(a, s.id, d)
    assert r.message == f"other (PC2) מעלה את המטלה הזו עכשיו (מ-{datetime.fromtimestamp(since):%H:%M})."
    assert (r.total_zips, r.done_zips, d.calls) == (2, [], [])
    assert lock.read_text(encoding="utf-8") == "other (PC2)"  # not taken over, not deleted


def test_an_old_lock_of_someone_else_is_taken_over_and_released(batch):
    a, s = batch
    lock = a / UPLOAD_LOCK
    lock.write_text("other (PC2)", encoding="utf-8")
    old = time.time() - 31 * 60
    os.utime(lock, (old, old))
    assert run_batch(a, s.id, SimulatedDriver()).stopped is None
    assert not lock.exists()


def test_stop_request_stops_before_the_next_zip(batch):
    a, s = batch
    calls = iter([False, True])
    d = SimulatedDriver()
    r = run_batch(a, s.id, d, should_stop=lambda: next(calls))
    assert r.done_zips == [PART_1] and (r.stopped, d.calls) == ("user", [PART_1])
    assert r.message == "נעצר לבקשתך אחרי 1 מתוך 2 קבצי ZIP."
    assert not (a / UPLOAD_LOCK).exists()


def test_stop_request_before_the_first_zip_uploads_nothing(batch):
    a, s = batch
    d = SimulatedDriver()
    r = run_batch(a, s.id, d, should_stop=lambda: True)
    assert (r.stopped, r.done_zips, d.calls, read_log(a)) == ("user", [], [], [])


def test_dry_run_checks_first_zip_only_and_records_nothing(batch):
    a, s = batch
    d = SimulatedDriver()
    r = run_batch(a, s.id, d, dry_run=True)
    assert r.stopped is None and len(d.calls) == 1 and read_log(a) == []
    assert (r.done_zips, r.recorded) == ([], 0)
    assert r.message == "בדיקה יבשה עברה: הדף והקובץ נבדקו (1 קבצים ב-ZIP), שום דבר לא יובא"
    assert not (a / UPLOAD_LOCK).exists()


def test_dry_run_takes_the_first_zip_that_is_still_to_upload(batch):
    a, s = batch
    record_zip(a, PART_1, by="me (PC)")
    d = SimulatedDriver()
    r = run_batch(a, s.id, d, dry_run=True)
    assert (r.stopped, d.calls, r.done_zips) == (None, [PART_2], [PART_1])


@pytest.mark.parametrize("result, stopped", [
    (UploadResult("dry_run_ok", rows=5), "error"),               # the list is not the size of the ZIP
    (UploadResult("mismatch", rows=5, message="הודעה"), "mismatch"),
    (UploadResult("imported", rows=1, imported=1), "error"),     # a dry run must never import
])
def test_dry_run_that_does_not_check_out_stops_with_nothing_recorded(batch, result, stopped):
    a, s = batch
    r = run_batch(a, s.id, SimulatedDriver([result]), dry_run=True)
    assert (r.stopped, read_log(a)) == (stopped, [])
    assert r.message.startswith(f"{PART_1}: ")


def test_progress_is_reported_after_each_zip_with_the_lock_fresh(batch):
    a, s = batch
    lock = a / UPLOAD_LOCK
    progress = []

    class SlowDriver(SimulatedDriver):
        def upload_zip(self, *args, **kwargs):
            old = time.time() - 20 * 60
            os.utime(lock, (old, old))  # a ZIP that took long: the lock has not been touched for 20 minutes
            return super().upload_zip(*args, **kwargs)

    def on_progress(index, total, name):
        progress.append((index, total, name, time.time() - lock.stat().st_mtime < 60))

    run_batch(a, s.id, SlowDriver(), on_progress=on_progress)
    assert progress == [(1, 2, PART_1, True), (2, 2, PART_2, True)]


def test_progress_is_not_reported_for_a_zip_that_stopped_the_run(batch):
    a, s = batch
    progress = []
    run_batch(a, s.id, SimulatedDriver([UploadResult("imported", 1, 1), UploadResult("error")]),
              on_progress=lambda *args: progress.append(args))
    assert progress == [(1, 2, PART_1)]


def test_a_batch_prepared_again_during_the_run_stops_it_before_the_next_zip(batch):
    a, s = batch
    d = SimulatedDriver()
    r = run_batch(a, s.id, d, on_progress=lambda *_: write_batch(a, {**read_batch(a), "id": "prepared-again"}))
    assert (r.stopped, r.done_zips, d.calls) == ("stale", [PART_1], [PART_1])
    assert r.message == "הקבצים השתנו מאז ההכנה. צריך להכין שוב."


def test_a_batch_prepared_again_while_a_zip_uploads_is_not_recorded(batch):
    a, s = batch

    class PreparedAgainDuringUpload(SimulatedDriver):
        def upload_zip(self, *args, **kwargs):
            result = super().upload_zip(*args, **kwargs)  # Moodle imported the ZIP built from the old files...
            write_batch(a, {**read_batch(a), "id": "prepared-again"})  # ...and meanwhile someone prepared again
            return result

    d = PreparedAgainDuringUpload()
    r = run_batch(a, s.id, d)
    assert (r.stopped, r.done_zips, r.recorded, d.calls) == ("stale", [], 0, [PART_1])
    assert r.message == "הקבצים השתנו מאז ההכנה. צריך להכין שוב."
    assert read_log(a) == [] and not (a / UPLOAD_LOCK).exists()


def test_the_driver_gets_the_details_the_zip_path_and_the_expected_count(assignment):
    (assignment / paths.MARKED / "0002-2.pdf").write_bytes(b"second marked file")
    s = prepare_batch(assignment)  # one ZIP with 3 files
    d = RecordingDriver()
    run_batch(assignment, s.id, d, dry_run=True)
    [(info, zip_path, expected, dry_run)] = d.calls
    batch = read_batch(assignment)
    assert (info["id"], zip_path, expected, dry_run) == ("555", batch_folder(assignment, batch) / PART_1, 3, True)
    assert d.hashes == [batch["zips"][0]["sha256"]]  # the driver gets the hash to check its copy against


def test_the_lock_is_released_when_the_driver_blows_up(batch):
    a, s = batch

    class Broken(SimulatedDriver):
        def upload_zip(self, *args, **kwargs):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        run_batch(a, s.id, Broken())
    assert not (a / UPLOAD_LOCK).exists()


def test_reports_have_numbers_and_no_student_names(batch):
    a, s = batch
    reports = [run_batch(a, s.id, SimulatedDriver([UploadResult("imported", 1, 0)])),
               run_batch(a, s.id, SimulatedDriver(), dry_run=True),
               run_batch(a, s.id, SimulatedDriver()),
               run_batch(a, "old-id", SimulatedDriver())]
    messages = " ".join(r.message for r in reports)
    log = (a / paths.UPLOAD / "Upload log.csv").read_text(encoding="utf-8-sig")
    assert not any(name in messages or name in log or p in messages for _, p, name in STUDENTS)


# ---------- the ZIP is checked by its hash, not only by its name ----------
def zip_path(a, name):
    return batch_folder(a, read_batch(a)) / name


def test_a_zip_changed_after_the_yes_is_not_uploaded(batch):
    a, s = batch
    zip_path(a, PART_1).write_bytes(b"another ZIP with the same name")
    d = SimulatedDriver()
    r = run_batch(a, s.id, d)
    assert (r.stopped, d.calls, read_log(a)) == ("stale", [], [])
    assert r.message.startswith(f"{PART_1}: ")
    assert not (a / UPLOAD_LOCK).exists()


def test_a_missing_zip_is_not_uploaded(batch):
    a, s = batch
    zip_path(a, PART_2).unlink()
    d = SimulatedDriver()
    r = run_batch(a, s.id, d)
    assert (r.stopped, d.calls, r.done_zips) == ("stale", [PART_1], [PART_1])


def test_a_zip_that_changes_while_it_uploads_is_not_recorded(batch):
    a, s = batch

    class ChangesTheZip(SimulatedDriver):
        def upload_zip(self, info, path, *args, **kwargs):
            result = super().upload_zip(info, path, *args, **kwargs)
            path.write_bytes(b"changed during the upload")
            return result

    d = ChangesTheZip()
    r = run_batch(a, s.id, d)
    assert (r.stopped, r.done_zips, r.recorded, d.calls, read_log(a)) == ("stale", [], 0, [PART_1], [])
    assert "ייתכן שמודל כבר ייבא" in r.message


def test_a_batch_list_from_before_zip_hashes_is_stale(batch):
    a, s = batch
    old = read_batch(a)
    write_batch(a, {**old, "zips": [{k: v for k, v in z.items() if k != "sha256"} for z in old["zips"]]})
    d = SimulatedDriver()
    assert (run_batch(a, s.id, d).stopped, d.calls) == ("stale", [])
    write_batch(a, {k: v for k, v in old.items() if k != "folder"})
    assert (run_batch(a, s.id, d).stopped, d.calls) == ("stale", [])
