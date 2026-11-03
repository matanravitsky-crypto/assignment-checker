"""The site's "סנכרון" button (POST /api/refresh): it reads the shared folder again, everything, and says whether
OneDrive itself keeps that folder in sync on this computer (dashboard/onedrive_check.py)."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

import pytest

from dashboard import actions, folder_view, onedrive_check
from dashboard.onedrive_check import needs_signin as real_needs_signin, status as real_status
from moodle import paths

from tests.dashboard.helpers import COURSE, HDR, HW, NAMES, call, hw, write_key


def counts(state):
    a = hw(state)
    return {"pulled": len(a["subs"]), "graded": sum(s["status"] in ("graded", "returned") for s in a["subs"])}


def test_refresh_shows_what_onedrive_brought_since_the_page_loaded(root, server):
    _, rep = call(server, "POST", "/api/refresh", {}, HDR)
    assert counts(rep["state"]) == {"pulled": 3, "graded": 0}

    # OneDrive brings what another computer did: a pull of one more student, and a grade with its marked PDF
    a_dir = root / COURSE / HW
    (a_dir / paths.TO_GRADE / "0004.pdf").write_bytes(b"%PDF-1.4 new")
    with (a_dir / paths.KEY).open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    write_key(a_dir, rows + [{"number": "0004", "anon_file": "0004.pdf", "participant_id": "2000",
                              "original_folder": f"{NAMES['2000']}_2000_assignsubmission_file", "original_file": "hw.pdf"}])
    (a_dir / paths.MARKED / "0001.pdf").write_bytes(b"%PDF-1.4 marked")
    (a_dir / paths.GRADES_BY.format("אורי")).write_text(
        "number,grade,feedback,graded_at,graded_by\r\n0001,90,טוב,2026-11-03T12:00:00,אורי\r\n", encoding="utf-8")

    st, rep = call(server, "POST", "/api/refresh", {}, HDR)
    assert st == 200
    assert counts(rep["state"]) == {"pulled": 4, "graded": 1}
    # the signature it returns is the one the site polls, so the next poll doesn't load everything again
    assert rep["sig"] == call(server, "GET", "/api/changes")[1]["sig"]
    assert rep["at"] and rep["onedrive"]["running"] is True and rep["onedrive"]["signin"] is False


def test_refresh_reads_notes_again_even_when_size_and_time_did_not_change(root):
    a_dir = root / COURSE / HW
    (a_dir / paths.NOTES).mkdir()
    note = a_dir / paths.NOTES / "0001.json"
    note.write_text(json.dumps({"comments": ["aaaa"]}), encoding="utf-8")
    first = next(s for s in hw(actions.state(root))["subs"] if s["id"] == "0001")["comments"]
    st = note.stat()
    note.write_text(json.dumps({"comments": ["bbbb"]}), encoding="utf-8")  # same size
    os.utime(note, ns=(st.st_atime_ns, st.st_mtime_ns))                    # and the time OneDrive kept
    cached = next(s for s in hw(actions.state(root))["subs"] if s["id"] == "0001")["comments"]
    fresh = next(s for s in hw(actions.refresh(root)["state"])["subs"] if s["id"] == "0001")["comments"]
    assert (first, cached, fresh) == (["aaaa"], ["aaaa"], ["bbbb"])


def test_refresh_passes_on_what_is_wrong_with_onedrive(root, server, monkeypatch):
    monkeypatch.setattr(onedrive_check, "status", lambda root, folders: {
        "synced": True, "running": False, "started": True, "signin": True, "pending": 2,
        "pendingFiles": [f"{COURSE}/{HW}/1 - Submissions to grade/0004.pdf"]})
    st, rep = call(server, "POST", "/api/refresh", {}, HDR)
    assert st == 200
    assert rep["onedrive"]["signin"] is True and rep["onedrive"]["started"] is True and rep["onedrive"]["pending"] == 2


def test_refresh_needs_the_sites_header(root, server):
    assert call(server, "POST", "/api/refresh", {})[0] == 403


def test_refresh_says_how_to_reconnect_when_the_folder_cannot_be_read(root, server, monkeypatch):
    def unreadable(_root):
        raise OSError(362, "The cloud file provider is not running")
    monkeypatch.setattr(folder_view, "courses", unreadable)
    st, rep = call(server, "POST", "/api/refresh", {}, HDR)
    assert st == 503
    assert "The cloud file provider is not running" in rep["error"] and "חיבור OneDrive BGU" in rep["error"]


# ---------- onedrive_check.status ----------

class FakeCloud:
    def __init__(self, synced=True, not_uploaded=()):
        self._synced, self.not_uploaded = synced, set(not_uploaded)

    def synced(self, folder):
        return self._synced

    def in_sync(self, file):
        return file.name not in self.not_uploaded


def dirs(root):
    return actions._watched_dirs(root)


def test_status_counts_files_onedrive_has_not_uploaded_yet(root, monkeypatch):
    monkeypatch.setattr(onedrive_check, "_cloud_files", lambda: FakeCloud(not_uploaded={"0002.pdf", "0002-2.pdf"}))
    od = real_status(root, dirs(root))
    assert od["synced"] is True and od["pending"] == 2
    assert sorted(od["pendingFiles"]) == [f"{COURSE}/{HW}/{paths.TO_GRADE}/0002-2.pdf", f"{COURSE}/{HW}/{paths.TO_GRADE}/0002.pdf"]


def test_status_starts_onedrive_when_it_is_not_running(root, monkeypatch):
    started = []
    monkeypatch.setattr(onedrive_check, "_cloud_files", lambda: FakeCloud())
    monkeypatch.setattr(onedrive_check, "running", lambda: False)
    monkeypatch.setattr(onedrive_check, "start", lambda: started.append(1) or True)
    assert real_status(root, dirs(root))["started"] is True and started == [1]
    assert real_status(root, dirs(root), start_if_stopped=False)["started"] is False and started == [1]


def test_status_of_a_local_copy_checks_nothing_else(root, monkeypatch):
    monkeypatch.setattr(onedrive_check, "_cloud_files", lambda: FakeCloud(synced=False))
    monkeypatch.setattr(onedrive_check, "running", lambda: pytest.fail("a local copy has nothing to do with OneDrive"))
    assert real_status(root, dirs(root)) == {"synced": False, "running": None, "started": False, "signin": None,
                                             "pending": None, "pendingFiles": []}


@pytest.mark.parametrize("out, code, expected", [
    ("Event[0]:\n  Description: Error: 0xCAA2000C ... AADSTS50076: Due to a configuration change made by your administrator", 0, True),
    ("Event[0]:\n  Description: Error: 0xCAA70004 The server or proxy was not found.", 0, False),
    ("", 0, False),
    ("Failed to read", 15, None),
])
def test_needs_signin_looks_for_the_mfa_error_in_the_aad_log(monkeypatch, out, code, expected):
    seen = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(onedrive_check, "_run", lambda args, timeout=15: seen.append(args) or subprocess.CompletedProcess(args, code, out, ""))
    assert real_needs_signin() is expected
    assert seen[0][:3] == ["wevtutil", "qe", onedrive_check.AAD_LOG]
    assert f"timediff(@SystemTime) <= {onedrive_check.SIGNIN_MINUTES * 60_000}" in seen[0][3]


@pytest.mark.skipif(sys.platform != "win32", reason="the Cloud Files API is Windows only")
def test_a_temp_folder_is_not_a_onedrive_folder(tmp_path):
    cloud = onedrive_check._CloudFiles()
    (tmp_path / "x.txt").write_text("x")
    assert cloud.synced(tmp_path) is False
    assert cloud.in_sync(tmp_path / "missing.txt") is None
