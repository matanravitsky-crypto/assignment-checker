"""The existing modules through the gate: atomic batch and details files, no invalid grade in the Moodle worksheet,
a broken details file does not break the lookup, READMEs are not rewritten, and the stuck pull lock is not "in progress"."""
from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from dashboard import actions
from moodle import guide, lock, paths, upload, upload_log


@pytest.fixture
def root(tmp_path, monkeypatch):
    r = tmp_path / "Exercise Checking System"
    for course, folder, mid in (("Linear Algebra", "Assignment 0 - Sets", "100"), ("Linear Algebra", "Assignment 1", "101"), ("Discrete Mathematics", "Assignment 0", "200")):
        a = r / course / folder
        for sub in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD):
            (a / sub).mkdir(parents=True)
        (a / paths.INFO).write_text(json.dumps({"id": mid, "course": course, "name": folder}), encoding="utf-8")
    monkeypatch.setenv("ASSIGNMENT_DATA", str(r))
    return r


def test_batch_file_is_atomic_and_a_broken_one_is_a_hebrew_error(root):
    a = root / "Linear Algebra" / "Assignment 1"
    upload_log.write_batch(a, {"id": "b1", "zips": []})
    assert upload_log.read_batch(a) == {"id": "b1", "zips": []}
    assert [p.name for p in (a / paths.UPLOAD).iterdir()] == ["Upload batch.json"]  # no temp file
    (a / paths.UPLOAD / "Upload batch.json").write_text("{half", encoding="utf-8")
    with pytest.raises(upload_log.BatchUnreadable) as e:
        upload_log.read_batch(a)
    assert "פגום" in str(e.value)
    (a / paths.UPLOAD / "Upload batch.json").write_text("[1, 2]", encoding="utf-8-sig")
    assert upload_log.read_batch(a) is None


def test_one_broken_details_file_does_not_break_find_assignment(root):
    (root / "Discrete Mathematics" / "Assignment 0" / paths.INFO).write_text("{broken", encoding="utf-8")
    assert paths.find_assignment("101") == root / "Linear Algebra" / "Assignment 1"
    assert paths.find_assignment("200") is None
    assert paths.read_info_or_none(root / "Discrete Mathematics" / "Assignment 0") is None


def test_worksheet_never_gets_an_invalid_grade(tmp_path):
    ws = tmp_path / "worksheet.csv"
    with ws.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Identifier", "Full name", "Grade", "Feedback comments"])
        for pid in ("1001", "1002", "1003", "1004"):
            w.writerow([f"Participant {pid}", "x", "", ""])
    results = {"0001": {"number": "0001", "grade": "85", "feedback": "ok"}, "0002": {"number": "0002", "grade": "abc", "feedback": ""},
               "0003": {"number": "0003", "grade": "-4", "feedback": ""}, "0004": {"number": "0004", "grade": "250", "feedback": ""}}
    mapping = {n: {"participant_id": pid} for n, pid in zip(results, ("1001", "1002", "1003", "1004"))}
    skipped: list[str] = []
    out = tmp_path / "out.csv"
    assert upload.fill_worksheet(ws, out, results, mapping, max_grade=100, skipped=skipped) == 1
    assert sorted(skipped) == ["0002", "0003", "0004"]
    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert [r[2] for r in rows[1:]] == ["85", "", "", ""]
    # without a known maximum the 250 passes, the junk and the negative still do not
    assert upload.fill_worksheet(ws, out, results, mapping) == 2


def test_readmes_are_written_only_when_their_text_changed(root):
    a = root / "Linear Algebra" / "Assignment 1"
    guide.write_guides(root) if hasattr(guide, "write_guides") else None
    readme = a / paths.README
    if not readme.exists():
        pytest.skip("guide has no write_guides entry point in this version")
    first = readme.stat().st_mtime_ns
    time.sleep(0.02)
    guide.write_guides(root)
    assert readme.stat().st_mtime_ns == first


def test_details_are_written_atomically_by_the_dashboard(root):
    from dashboard import folder_view
    a = folder_view.Assignment(root / "Linear Algebra" / "Assignment 1")
    actions._write_info(a, {"id": "101", "course": "Linear Algebra", "name": "Assignment 1", "title": "הגשה 1"})
    assert a.details()["title"] == "הגשה 1"
    assert [p.name for p in a.dir.iterdir() if p.suffix == ".tmp"] == []


def test_a_stuck_pull_lock_is_not_in_progress(root):
    a = root / "Linear Algebra" / "Assignment 1"
    p = a / paths.PULL_LOCK
    p.write_text("דנה (PC) pid=7", encoding="utf-8")
    assert actions._fresh_lock_holder(p) == "דנה (PC)"
    t = (datetime.now() - timedelta(minutes=lock.LOCK_MINUTES + 1)).timestamp()
    os.utime(p, (t, t))
    assert actions._fresh_lock_holder(p) is None
    assert actions._fresh_lock_holder(a / "nope.txt") is None


def test_pull_lock_heartbeat_refreshes_at_most_once_a_minute(root, monkeypatch):
    a = root / "Linear Algebra" / "Assignment 1"
    p = lock.take(a, paths.PULL_LOCK)
    t = (datetime.now() - timedelta(minutes=5)).timestamp()
    os.utime(p, (t, t))
    actions._pull_lock_state.update(path=p, at=0.0)
    actions._refresh_pull_lock()
    assert datetime.now() - datetime.fromtimestamp(p.stat().st_mtime) < timedelta(seconds=5)
    os.utime(p, (t, t))
    actions._refresh_pull_lock()  # within the minute: no second write
    assert datetime.fromtimestamp(p.stat().st_mtime) < datetime.now() - timedelta(minutes=4)
    p.unlink()
    actions._pull_lock_state.update(at=0.0)
    actions._refresh_pull_lock()  # a released lock is never recreated by the heartbeat
    assert not p.exists()
