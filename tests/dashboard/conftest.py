"""Fixtures for the dashboard tests (the constants and helpers are in helpers.py)."""
from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from moodle import claude_driver, paths
from dashboard import actions
from tests.sample_files import homework_pdf

from tests.dashboard.helpers import COURSE, HW, MID, NAMES, write_key


@pytest.fixture(autouse=True)
def fresh_dashboard_state(monkeypatch):
    """Module-level state of dashboard.actions starts empty in every test, and no test can start `claude`."""
    actions._send = actions.SendJob()
    actions._stop.clear()
    actions._moodle_cache = None
    actions._hashes.clear()
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": False, "message": "fake"})


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
    return r


@pytest.fixture
def server(root):
    from dashboard.web_server import Handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_port
    srv.shutdown()
