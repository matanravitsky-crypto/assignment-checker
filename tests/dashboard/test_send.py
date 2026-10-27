"""Tests for the dashboard's upload to Moodle: prepare, start, follow, stop, and what the site shows after it.

Drivers here are fakes (`FakeDriver` or small classes): nothing starts `claude` or touches Moodle.
"""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

from dashboard import actions
from moodle import claude_driver, lock, paths, upload_log
from moodle.send import UPLOAD_LOCK, UploadResult, prepare_batch
from tests.fakes import FakeDriver
from tests.dashboard.helpers import BODY, COURSE, HDR, HW, MID, NAMES, call, hw, mark


def a_dir(root):
    return root / COURSE / HW


def wait_idle(timeout=5.0):
    end = time.time() + timeout
    while actions.send_status()["running"] and time.time() < end:
        time.sleep(0.01)
    return actions.send_status()


def statuses(root):
    return [s["status"] for s in hw(actions.state(root))["subs"]]


class GateDriver:
    """Waits inside the first upload until the test lets it go, and says every ZIP went through."""

    def __init__(self):
        self.inside = threading.Event()
        self.release = threading.Event()

    def upload_zip(self, info, zip_path, expected, dry_run, sha256=None):
        self.inside.set()
        self.release.wait(5)
        return UploadResult("imported", rows=expected, imported=expected)


class StopsAfterFirst:
    """Presses "stop" in the site while the first ZIP uploads."""

    def upload_zip(self, info, zip_path, expected, dry_run, sha256=None):
        actions.stop_send()
        return UploadResult("imported", rows=expected, imported=expected)


class Exploding:
    def upload_zip(self, info, zip_path, expected, dry_run, sha256=None):
        raise OSError("disk gone")


# ---------- prepare and start ----------
def test_prepare_then_start_marks_students_returned(root):
    mark(root, "0001", "0002")
    rep = actions.prepare_send(root, COURSE, HW)
    assert rep["students"] == 2 and "2 סטודנטים" in rep["summary"]
    assert rep["summary"] == 'מטלה "הגשה 0 - קבוצות ומרוכבים" (מודל 3438636): 2 קבצים של 2 סטודנטים, ב-1 קובצי ZIP.'
    actions.start_send(root, COURSE, HW, rep["id"], driver=FakeDriver(), wait=True)
    subs = hw(actions.state(root))["subs"]
    assert [s["status"] for s in subs] == ["returned", "returned", "pulled"]


def test_prepare_blocked_becomes_a_user_error(root):
    mark(root, "0001")
    (a_dir(root) / paths.UPLOAD / "Upload log-DESKTOP-X.csv").write_text("number\n", encoding="utf-8")
    with pytest.raises(actions.UserError) as e:
        actions.prepare_send(root, COURSE, HW)
    assert "עותק כפול של יומן ההעלאה" in str(e.value)


def test_prepare_with_a_number_missing_from_the_key_is_a_user_error(root):
    mark(root, "0009")
    with pytest.raises(actions.UserError) as e:
        actions.prepare_send(root, COURSE, HW)
    assert "0009" in str(e.value)


def test_prepare_is_refused_while_an_upload_runs(root):
    mark(root, "0001")
    lock_file = a_dir(root) / UPLOAD_LOCK
    lock_file.write_text("uri (URI-LAPTOP)", encoding="utf-8")
    with pytest.raises(actions.UserError) as e:
        actions.prepare_send(root, COURSE, HW)
    assert str(e.value) == "uri (URI-LAPTOP) מעלה את המטלה הזו עכשיו. אפשר להכין העלאה חדשה כשהיא תסתיים."
    old = time.time() - (lock.LOCK_MINUTES + 1) * 60  # a stuck lock does not block
    os.utime(lock_file, (old, old))
    assert actions.prepare_send(root, COURSE, HW)["students"] == 1


def test_start_with_stale_batch_is_refused(root, server):
    mark(root, "0001")
    old = call(server, "POST", "/api/upload/prepare", BODY, HDR)[1]["id"]
    call(server, "POST", "/api/upload/prepare", BODY, HDR)
    st, rep = call(server, "POST", "/api/upload/start", {**BODY, "batchId": old}, HDR)
    assert st == 409 and "השתנו" in rep["error"]
    assert rep["error"] == "הקבצים השתנו מאז ההכנה. צריך ללחוץ שוב על 'העלה למודל'."


def test_start_with_a_stale_batch_raises_value_error(root):
    mark(root, "0001")
    old = actions.prepare_send(root, COURSE, HW)["id"]
    actions.prepare_send(root, COURSE, HW)
    with pytest.raises(ValueError, match="stale"):
        actions.start_send(root, COURSE, HW, old, driver=FakeDriver(), wait=True)
    assert not actions.send_status()["running"]


def test_needs_login_shows_in_status(root):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    actions.start_send(root, COURSE, HW, rep["id"], driver=FakeDriver([UploadResult("needs_login")]), wait=True)
    assert actions.send_status()["stopped"] == "needs_login"


def test_state_and_status_have_no_names(root):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    actions.start_send(root, COURSE, HW, rep["id"], driver=FakeDriver(), wait=True)
    text = json.dumps([actions.state(root), actions.send_status(), rep], ensure_ascii=False)
    assert not any(name in text for name in NAMES.values())


# ---------- one job at a time, and the job never stays "running" ----------
def test_only_one_upload_runs_at_a_time(root):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    gate = GateDriver()
    actions.start_send(root, COURSE, HW, rep["id"], driver=gate)
    assert gate.inside.wait(5)
    status = actions.send_status()
    assert (status["running"], status["batch_id"], status["current"]) == (True, rep["id"], "Graded - part 01.zip")
    with pytest.raises(RuntimeError, match="העלאה אחרת כבר רצה."):
        actions.start_send(root, COURSE, HW, rep["id"], driver=FakeDriver())
    gate.release.set()
    done = wait_idle()
    assert (done["running"], done["stopped"], done["done"], done["total"]) == (False, None, 1, 1)
    assert done["finished_at"] and done["current"] == ""


def test_prepare_is_refused_while_this_process_uploads_even_before_the_lock_file_exists(root):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    gate = GateDriver()
    actions.start_send(root, COURSE, HW, rep["id"], driver=gate)
    assert gate.inside.wait(5)
    with pytest.raises(actions.UserError, match="מעלה את המטלה הזו עכשיו"):
        actions.prepare_send(root, COURSE, HW)
    gate.release.set()
    wait_idle()


def test_a_crashing_driver_ends_the_job_with_a_hebrew_error(root):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    actions.start_send(root, COURSE, HW, rep["id"], driver=Exploding(), wait=True)
    s = actions.send_status()
    assert (s["running"], s["stopped"]) == (False, "error")
    assert s["message"].startswith("ההעלאה נכשלה") and "disk gone" in s["message"]
    assert s["finished_at"]
    assert not (a_dir(root) / UPLOAD_LOCK).exists()


def test_a_crash_before_the_run_also_ends_the_job(root, monkeypatch):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)

    def boom(*a, **k):
        raise RuntimeError("no way")
    monkeypatch.setattr(actions.moodle_send, "run_batch", boom)
    actions.start_send(root, COURSE, HW, rep["id"], driver=FakeDriver(), wait=True)
    s = actions.send_status()
    assert (s["running"], s["stopped"]) == (False, "error") and "no way" in s["message"]


# ---------- stop, and progress after a resume ----------
def two_zip_batch(root):
    mark(root, "0001", "0002")
    return prepare_batch(a_dir(root), max_bytes=30)  # each marked file (20 bytes) in a ZIP of its own


def test_stop_ends_after_the_zip_in_progress_and_a_new_start_resumes(root):
    batch = two_zip_batch(root)
    assert len(batch.zips) == 2
    actions.start_send(root, COURSE, HW, batch.id, driver=StopsAfterFirst(), wait=True)
    s = actions.send_status()
    assert (s["stopped"], s["done"], s["total"], s["running"]) == ("user", 1, 2, False)
    assert statuses(root) == ["returned", "graded", "pulled"]  # 0002 is marked, but not uploaded yet
    drv = FakeDriver()
    actions.start_send(root, COURSE, HW, batch.id, driver=drv, wait=True)
    s = actions.send_status()
    assert drv.calls == ["Graded - part 02.zip"]  # the first ZIP is skipped on resume
    assert (s["stopped"], s["done"], s["total"]) == (None, 2, 2)
    assert statuses(root) == ["returned", "returned", "pulled"]


def test_progress_after_a_resume_counts_the_skipped_zips(root):
    batch = two_zip_batch(root)
    actions.start_send(root, COURSE, HW, batch.id, driver=StopsAfterFirst(), wait=True)
    gate = GateDriver()
    actions.start_send(root, COURSE, HW, batch.id, driver=gate)
    assert gate.inside.wait(5)
    assert actions.send_status()["done"] == 1  # one is done before the second even starts
    gate.release.set()
    assert wait_idle()["done"] == 2


def test_stop_without_a_job_is_harmless(root):
    assert actions.stop_send()["running"] is False


def test_dry_run_is_shown_in_status_and_logs_nothing(root):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    actions.start_send(root, COURSE, HW, rep["id"], driver=FakeDriver(), dry_run=True, wait=True)
    s = actions.send_status()
    assert s["dry_run"] is True and s["stopped"] is None
    assert upload_log.read_log(a_dir(root)) == []


# ---------- which driver ----------
def test_default_driver_is_claude_in_chrome(root, monkeypatch):
    seen = []

    class FakeChrome:
        def check(self, info):
            return {"chrome": True, "moodle": True, "message": "ok", "answered": True}

        def upload_zip(self, info, zip_path, expected, dry_run, sha256=None):
            seen.append(zip_path.name)
            return UploadResult("imported", rows=expected, imported=expected)
    monkeypatch.setattr(claude_driver, "ClaudeChromeDriver", FakeChrome)
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    actions.start_send(root, COURSE, HW, rep["id"], wait=True)
    assert seen == ["Graded - part 01.zip"]


def test_an_upload_needs_the_chrome_extension_and_moodle(root, monkeypatch):
    monkeypatch.setattr(claude_driver.ClaudeChromeDriver, "answer",
                        {"chrome": True, "moodle": False, "message": "login page", "answered": True})
    driver = FakeDriver()
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    with pytest.raises(actions.UserError, match="כרום לא מחובר למודל"):
        actions.start_send(root, COURSE, HW, rep["id"], driver=driver, wait=True)
    assert driver.calls == [] and actions.send_status()["running"] is False


def test_server_upload_start_says_what_is_not_connected(root, server, monkeypatch):
    mark(root, "0001")
    st, rep = call(server, "POST", "/api/upload/prepare", BODY, HDR)
    monkeypatch.setattr(claude_driver.ClaudeChromeDriver, "answer",
                        {"chrome": False, "moodle": False, "message": "no extension", "answered": False})
    st, err = call(server, "POST", "/api/upload/start", {**BODY, "batchId": rep["id"]}, HDR)
    assert st == 422 and "התוסף של Claude בכרום לא מחובר" in err["error"]


# ---------- state() ----------
def test_state_shows_when_it_was_returned_and_what_changed_after(root):
    mark(root, "0001", "0002")
    rep = actions.prepare_send(root, COURSE, HW)
    assert hw(actions.state(root))["returnedAt"] is None
    actions.start_send(root, COURSE, HW, rep["id"], driver=FakeDriver(), wait=True)
    last = max(r["uploaded_at"] for r in upload_log.read_log(a_dir(root)))
    assert hw(actions.state(root))["returnedAt"] == last
    (a_dir(root) / paths.MARKED / "0001.pdf").write_bytes(b"%PDF-1.4 changed after the upload")  # the grader edited it
    assert statuses(root) == ["graded", "returned", "pulled"]


def test_uploaded_txt_no_longer_decides_returned(root):
    mark(root, "0001")
    (a_dir(root) / paths.UPLOAD / "Uploaded.txt").write_text("Graded - part 01.zip 1", encoding="utf-8")
    assert statuses(root) == ["graded", "pulled", "pulled"]


def test_state_does_not_reread_unchanged_files(root, monkeypatch):
    mark(root, "0001", "0002")
    rep = actions.prepare_send(root, COURSE, HW)
    actions.start_send(root, COURSE, HW, rep["id"], driver=FakeDriver(), wait=True)
    reads = []
    real = upload_log.file_hash
    monkeypatch.setattr(upload_log, "file_hash", lambda p: reads.append(p.name) or real(p))
    assert statuses(root) == ["returned", "returned", "pulled"]
    assert sorted(reads) == ["0001.pdf", "0002.pdf"]
    reads.clear()
    assert statuses(root) == ["returned", "returned", "pulled"]
    assert reads == []  # same path, size and mtime: not hashed again
    marked = a_dir(root) / paths.MARKED / "0001.pdf"
    marked.write_bytes(b"%PDF-1.4 other content")  # a different file with the same name
    assert statuses(root) == ["graded", "returned", "pulled"]
    assert reads == ["0001.pdf"]


def test_state_warns_about_a_log_conflict_and_an_upload_in_progress(root):
    folder = a_dir(root)
    (folder / paths.UPLOAD / "Upload log-DESKTOP-X.csv").write_text("number\n", encoding="utf-8")
    (folder / UPLOAD_LOCK).write_text("uri (URI-LAPTOP)", encoding="utf-8")
    warnings = hw(actions.state(root))["warnings"]
    assert "עותק כפול של יומן ההעלאה: Upload log-DESKTOP-X.csv" in warnings
    assert "העלאה בתהליך: uri (URI-LAPTOP)" in warnings


def test_state_has_the_sending_status(root):
    assert actions.state(root)["sending"] == actions.send_status()
    assert actions.state(root)["sending"]["running"] is False


# ---------- Moodle and Claude status ----------
def test_moodle_status_is_cached_for_a_minute(monkeypatch):
    calls = []
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: calls.append(1) or {"logged_in": True, "message": "ok"})
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    assert actions.moodle_status()["logged_in"] is True
    now[0] += 59
    actions.moodle_status()
    assert len(calls) == 1
    now[0] += 2
    actions.moodle_status()
    assert len(calls) == 2


def test_check_moodle_asks_the_driver_with_the_assignment_details(root, monkeypatch):
    seen = []

    class FakeChrome:
        def check(self, info):
            seen.append(info["id"])
            return {"chrome": True, "moodle": True, "message": "ok"}
    monkeypatch.setattr(claude_driver, "ClaudeChromeDriver", FakeChrome)
    assert actions.check_moodle(root, COURSE, HW) == {"chrome": True, "moodle": True, "message": "ok"}
    assert seen == [MID]
    with pytest.raises(FileNotFoundError):
        actions.check_moodle(root, COURSE, "../../Recordings")


# ---------- the local server ----------
def test_server_upload_flow(root, server, monkeypatch):
    monkeypatch.setattr(actions, "_make_driver", lambda: FakeDriver())
    mark(root, "0001", "0002")
    st, rep = call(server, "POST", "/api/upload/prepare", BODY, HDR)
    assert st == 200 and rep["students"] == 2 and "2 סטודנטים" in rep["summary"]
    st, job = call(server, "POST", "/api/upload/start", {**BODY, "batchId": rep["id"]}, HDR)
    assert st == 202 and job["batch_id"] == rep["id"]
    wait_idle()
    st, job = call(server, "GET", "/api/upload")
    assert st == 200 and job["running"] is False and job["done"] == 1 and job["stopped"] is None
    st, state = call(server, "GET", "/api/state")
    assert [s["status"] for s in hw(state)["subs"]] == ["returned", "returned", "pulled"]
    assert state["sending"]["done"] == 1
    st, stopped = call(server, "POST", "/api/upload/stop", {}, HDR)
    assert st == 200 and stopped["running"] is False


def test_server_start_while_running_is_a_conflict(root, server, monkeypatch):
    mark(root, "0001")
    rep = call(server, "POST", "/api/upload/prepare", BODY, HDR)[1]
    gate = GateDriver()
    monkeypatch.setattr(actions, "_make_driver", lambda: gate)
    assert call(server, "POST", "/api/upload/start", {**BODY, "batchId": rep["id"]}, HDR)[0] == 202
    assert gate.inside.wait(5)
    st, err = call(server, "POST", "/api/upload/start", {**BODY, "batchId": rep["id"]}, HDR)
    assert st == 409 and err["error"] == "העלאה אחרת כבר רצה."
    st, err = call(server, "POST", "/api/upload/prepare", BODY, HDR)
    assert st == 422 and "מעלה את המטלה הזו עכשיו" in err["error"]
    gate.release.set()
    wait_idle()


def test_server_upload_errors(root, server):
    assert call(server, "POST", "/api/upload/prepare", {"course": COURSE}, HDR)[0] == 400
    assert call(server, "POST", "/api/upload/start", BODY, HDR)[0] == 400  # no batchId
    assert call(server, "POST", "/api/upload/prepare", {"course": COURSE, "assignment": "nope"}, HDR)[0] == 404
    mark(root, "0009")
    st, err = call(server, "POST", "/api/upload/prepare", BODY, HDR)
    assert st == 422 and "0009" in err["error"]


def test_server_upload_posts_need_the_header_and_a_local_origin(root, server):
    for path in ("/api/upload/prepare", "/api/upload/start", "/api/upload/stop", "/api/moodle/check"):
        assert call(server, "POST", path, {**BODY, "batchId": "x"})[0] == 403
        assert call(server, "POST", path, {**BODY, "batchId": "x"}, {**HDR, "Origin": "https://evil.example"})[0] == 403


def test_server_moodle_status_check_and_health(root, server, monkeypatch):
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": True, "message": "Claude Code מחובר."})

    class FakeChrome:
        def check(self, info):
            return {"chrome": True, "moodle": False, "message": "אין התחברות"}
    monkeypatch.setattr(claude_driver, "ClaudeChromeDriver", FakeChrome)
    assert call(server, "GET", "/api/moodle")[1] == {"logged_in": True, "message": "Claude Code מחובר."}
    assert call(server, "GET", "/api/health")[1]["moodle"] is True
    st, rep = call(server, "POST", "/api/moodle/check", BODY, HDR)
    assert st == 200 and rep == {"chrome": True, "moodle": False, "message": "אין התחברות"}
    assert call(server, "POST", "/api/moodle/check", {"course": COURSE}, HDR)[0] == 400
    assert call(server, "POST", "/api/moodle/check", {**BODY, "assignment": "nope"}, HDR)[0] == 404


def test_return_endpoint_still_works(root, server, monkeypatch):
    monkeypatch.setattr("moodle.upload.find_worksheet", lambda *a, **k: None)
    mark(root, "0001")
    (a_dir(root) / paths.GRADES).write_text("number,grade,feedback\n0001,90,ok\n", encoding="utf-8")
    st, rep = call(server, "POST", "/api/return", BODY, HDR)
    assert st == 200 and rep["report"]["results"] == 1


def test_lock_text_with_a_pid_is_shown_without_it(root):
    mark(root, "0001")
    (a_dir(root) / UPLOAD_LOCK).write_text("uri (URI-LAPTOP) pid=4242", encoding="utf-8")
    with pytest.raises(actions.UserError) as e:
        actions.prepare_send(root, COURSE, HW)
    assert str(e.value) == "uri (URI-LAPTOP) מעלה את המטלה הזו עכשיו. אפשר להכין העלאה חדשה כשהיא תסתיים."
    assert "העלאה בתהליך: uri (URI-LAPTOP)" in hw(actions.state(root))["warnings"]


def test_prepare_refuses_while_the_key_has_a_conflict_copy(root):
    mark(root, "0001")
    (a_dir(root) / "Key - number to student-DESKTOP-ABC.csv").write_text("number\n", encoding="utf-8")
    with pytest.raises(actions.UserError) as e:
        actions.prepare_send(root, COURSE, HW)
    assert "עותק כפול של טבלת המפתח" in str(e.value)
    assert upload_log.read_batch(a_dir(root)) is None



def test_prepare_return_is_refused_while_an_upload_runs(root):
    mark(root, "0001")
    lock_file = a_dir(root) / UPLOAD_LOCK
    lock_file.write_text("uri (URI-LAPTOP) pid=4242", encoding="utf-8")
    with pytest.raises(actions.UserError) as e:
        actions.prepare_return(root, COURSE, HW)
    assert str(e.value) == "uri (URI-LAPTOP) מעלה את המטלה הזו עכשיו. אפשר להכין החזרה כשההעלאה תסתיים."
    assert not list((a_dir(root) / paths.UPLOAD).glob("*.zip"))


def test_prepare_return_is_refused_while_this_dashboard_uploads(root):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    gate = GateDriver()
    actions.start_send(root, COURSE, HW, rep["id"], driver=gate)
    try:
        assert gate.inside.wait(5)
        with pytest.raises(actions.UserError):
            actions.prepare_return(root, COURSE, HW)
    finally:
        gate.release.set()
        wait_idle()
