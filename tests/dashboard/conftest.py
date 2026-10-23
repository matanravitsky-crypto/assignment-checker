"""Fixtures for the dashboard tests (the constants and helpers are in helpers.py)."""
from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from moodle import claude_driver, ingest, paths
from dashboard import actions
from tests.sample_files import homework_pdf

from tests.dashboard.helpers import COURSE, HW, MID, NAMES, write_key


@pytest.fixture(autouse=True)
def fresh_dashboard_state(monkeypatch, tmp_path):
    """Module-level state of dashboard.actions starts empty in every test, and no test can start `claude`."""
    actions._send = actions.SendJob()
    actions._stop.clear()
    actions._moodle_cache = None
    actions._hashes.clear()
    actions._ready_cache.clear()
    actions._checking = False
    actions._sim_login_at = None
    actions._login, actions._install = actions._Background(actions.LOGIN_MINUTES), actions._Background(actions.INSTALL_MINUTES)
    monkeypatch.delenv("MOODLE_READY", raising=False)
    # no test starts a login or an installer, whatever is installed on this computer
    monkeypatch.setattr(actions.subprocess, "Popen", lambda *a, **k: pytest.fail("a test started a real process"))
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": False, "message": "fake"})
    # no test opens Moodle or reads the real Downloads folder: "Moodle" drops the assignment's ZIP into a temp Downloads
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(ingest, "downloads_dir", lambda: downloads)
    monkeypatch.setattr(actions, "PARTS_POLL_S", 0.01)
    monkeypatch.setattr(actions, "_make_downloader", lambda: FakeDownloader(downloads))


class FakeDownloader:
    """Moodle in the tests: the parts script in Moodle's tab "downloads" the assignment's ZIPs, as Chrome would,
    and tells the local server that it finished (dashboard/pull_parts.py)."""

    def __init__(self, downloads, result=None, parts=1, finish="done"):
        self.downloads, self.result, self.parts, self.finish, self.calls = downloads, result, parts, finish, []

    def download_parts(self, info, base):
        from dashboard import pull_parts
        self.calls.append(info["id"])
        self.base = base
        if self.result:
            return self.result
        mid = info["id"]
        names = [f"214193210120271-x-{mid}{f' ({i})' if i else ''}.zip" for i in range(self.parts)]
        for name in names:
            (self.downloads / name).write_bytes(b"zip from moodle")
        pull_parts._runs[mid]["ok"].extend(names)  # what pull_parts.check records for every part that arrived whole
        if self.finish:
            error = "" if self.finish == "done" else self.finish
            pull_parts.finish(mid, "done" if self.finish == "done" else "error", str(self.parts * 50), "", str(self.parts), error)
        return {"status": "started", "message": "ok"}


@pytest.fixture
def root(tmp_path, monkeypatch):
    """עותק מוקטן של YallaLinearit/Exercise Checking System, כמו שאורי בנה."""
    course_folder = tmp_path / "BGU" / "נדב מאיר - YallaLinearit"
    (course_folder / "Recordings").mkdir(parents=True)
    r = course_folder / "Exercise Checking System"
    (r / "Discrete Mathematics").mkdir(parents=True)
    a = r / COURSE / HW
    for sub in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD):
        (a / sub).mkdir(parents=True)
    (a / paths.INFO).write_text(json.dumps({
        "id": MID, "course": COURSE, "course_id": "67024", "name": HW, "due": "2026-10-26T23:59:00+02:00",
        "questions": [{"sheet": "דף קבוצות", "numbers": [11, 12]}, {"sheet": "דף מספרים מרוכבים", "numbers": [6, 7, 8]}],
        "title": "הגשה 0 - קבוצות ומרוכבים", "course_title": "אלגברה לינארית להנדסה", "notes": "הורד ב-21/10",
    }, ensure_ascii=False), encoding="utf-8")
    rows = []
    for i, pid in enumerate(("1001", "1002", "1003"), start=1):
        n = f"{i:04d}"
        (a / paths.TO_GRADE / f"{n}.pdf").write_bytes(homework_pdf(NAMES[pid], HW))
        rows.append({"number": n, "anon_file": f"{n}.pdf", "participant_id": pid,
                     "original_folder": f"{NAMES[pid]}_{pid}_assignsubmission_file", "original_file": "hw.pdf"})
    # לסטודנט 0002 יש שני קבצים
    (a / paths.TO_GRADE / "0002-2.pdf").write_bytes(homework_pdf(NAMES["1002"], HW))
    rows.append({"number": "0002", "anon_file": "0002-2.pdf", "participant_id": "1002",
                 "original_folder": f"{NAMES['1002']}_1002_assignsubmission_file", "original_file": "part2.pdf"})
    write_key(a, rows)
    (a / "Moodle download 2026-10-21 16-28.zip").write_bytes(b"original download")
    monkeypatch.setenv("ASSIGNMENT_CHECKER_ROOT", str(course_folder))
    # The Moodle ZIP backups live in the work folder: keep the real one on this computer out of the tests
    monkeypatch.setenv("ASSIGNMENT_WORK", str(tmp_path / "work"))
    return r


@pytest.fixture
def server(root):
    from dashboard.web_server import Handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_port
    srv.shutdown()
