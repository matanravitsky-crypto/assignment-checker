"""המשיכה בחלקים (dashboard/pull_parts.py ו-/api/pull/ ב-web_server): מה השרת המקומי עונה לסקריפט שבלשונית של מודל."""
from __future__ import annotations

import http.client
import json
import os
import time

import pytest

from dashboard import pull_parts
from moodle import ingest

MID = "3453769"
MOODLE = "https://moodle.bgu.ac.il"


@pytest.fixture
def downloads(monkeypatch):
    """תיקיית ההורדות הזמנית של הבדיקות (conftest), ו-7-Zip מדומה: ZIP שהתוכן שלו "cut" קטוע, ובכל ZIP שלם
    יש שלושה סטודנטים."""
    d = ingest.downloads_dir()

    def check_zip(p):
        if p.read_bytes() == b"cut":
            raise ValueError(f"{p.name} is incomplete")
    monkeypatch.setattr(ingest, "check_zip", check_zip)
    monkeypatch.setattr(ingest, "participants_in", lambda p: {"1", "2", "3"})
    pull_parts._runs.clear()
    return d


def since_ms():
    return (time.time() - 1) * 1000


def test_a_part_is_ok_only_after_chrome_finished_and_its_size_held(downloads):
    since = since_ms()
    pull_parts.begin(MID)
    assert pull_parts.check(MID, since, 3, downloads)["status"] == "waiting"  # עוד לא הגיע כלום
    (downloads / "Unconfirmed 1.crdownload").write_bytes(b"...")
    zip_path = downloads / f"x-{MID}.zip"
    zip_path.write_bytes(b"whole")
    assert pull_parts.check(MID, since, 3, downloads)["status"] == "waiting"  # כרום עוד מוריד
    (downloads / "Unconfirmed 1.crdownload").unlink()
    assert pull_parts.check(MID, since, 3, downloads)["status"] == "waiting"  # הגודל נמדד פעם ראשונה
    r = pull_parts.check(MID, since, 3, downloads)
    assert r == {"status": "ok", "name": zip_path.name, "participants": 3, "expected": 3}
    assert pull_parts.status(MID)["ok"] == [zip_path.name]
    # החלק הבא לא מקבל שוב את אותו ZIP
    assert pull_parts.check(MID, since, 3, downloads)["status"] == "waiting"


def test_a_cut_off_part_is_marked_broken_and_never_taken(downloads):
    since = since_ms()
    pull_parts.begin(MID)
    (downloads / f"x-{MID}.zip").write_bytes(b"cut")
    pull_parts.check(MID, since, 50, downloads)
    r = pull_parts.check(MID, since, 50, downloads)
    assert r == {"status": "broken", "name": f"{pull_parts.BROKEN_PREFIX}x-{MID}.zip"}
    assert not (downloads / f"x-{MID}.zip").exists() and (downloads / r["name"]).exists()
    assert pull_parts.status(MID)["broken"] == [r["name"]]


def test_an_old_zip_or_another_assignment_is_not_a_part(downloads):
    old = downloads / f"x-{MID}.zip"
    old.write_bytes(b"whole")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    (downloads / "x-999.zip").write_bytes(b"whole")
    pull_parts.begin(MID)
    for _ in range(3):
        assert pull_parts.check(MID, since_ms(), 3, downloads)["status"] == "waiting"


def test_finish_keeps_numbers_only(downloads):
    pull_parts.begin(MID)
    pull_parts.finish(MID, "done", "120", "121", "3", "x" * 1000)
    st = pull_parts.status(MID)
    assert st["finished"] and (st["users"], st["submitted"], st["parts"]) == (120, 121, 3) and len(st["error"]) == 300
    pull_parts.finish(MID, "error", "<b>", "", "", "")
    assert pull_parts.status(MID)["users"] is None and pull_parts.status(MID)["submitted"] is None


def get(port, path, origin=None, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request(method, path, headers={"Host": f"localhost:{port}", **({"Origin": origin} if origin else {})})
    r = conn.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_moodle_gets_the_script_and_the_part_checks_and_nothing_else(downloads, root, server):
    status, headers, body = get(server, "/api/pull/parts.js", MOODLE)
    assert status == 200 and b"__ecsParts" in body and headers.get("Access-Control-Allow-Origin") == MOODLE
    status, headers, body = get(server, f"/api/pull/zip?mid={MID}&since={since_ms()}&expect=50", MOODLE)
    assert status == 200 and json.loads(body)["status"] == "waiting" and headers.get("Access-Control-Allow-Origin") == MOODLE
    status, _, body = get(server, f"/api/pull/finish?mid={MID}&stage=done&users=2&submitted=2&parts=1&error=", MOODLE)
    assert status == 200 and pull_parts.status(MID)["finished"]
    for bad in ("/api/pull/zip?mid=1;x", "/api/pull/zip?mid=1&since=soon", "/api/pull/other?mid=1"):
        assert get(server, bad, MOODLE)[0] in (400, 404)
    # Chrome שואל לפני שאתר פונה לשרת במחשב (preflight): רק לקריאה
    status, headers, _ = get(server, "/api/pull/zip", MOODLE, method="OPTIONS")
    assert status == 204 and headers.get("Access-Control-Allow-Methods") == "GET"
    # מודל לא מקבל CORS לשאר השרת, ואתר אחר לא מקבל אותו ל-/api/pull/
    assert "Access-Control-Allow-Origin" not in get(server, "/api/state", MOODLE)[1]
    assert get(server, "/api/state", MOODLE, method="OPTIONS")[0] == 403
    assert "Access-Control-Allow-Origin" not in get(server, "/api/pull/parts.js", "https://evil.example")[1]
    assert get(server, "/api/pull/zip", "https://evil.example", method="OPTIONS")[0] == 403
