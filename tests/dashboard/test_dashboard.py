"""בדיקות לאתר המחובר: איתור התיקייה, המצב לאתר, והחיבור לשלבים של moodle/.

את moodle/ עצמו בודקות הבדיקות של אורי (test_*.py בשורש הריפו).
מריצים: python -m pytest
"""
from __future__ import annotations

import json
import zipfile
from urllib.parse import quote

import pytest

from moodle import paths
from dashboard import actions, folder_view, shared_folder
from tests.sample_files import homework_pdf

from tests.dashboard.conftest import FakeDownloader
from tests.dashboard.helpers import COURSE, HW, MID, NAMES, call, write_key


# ---------- איתור התיקייה ----------
def test_find_root_goes_into_the_team_folder(root):
    assert shared_folder.find_root() == root


def test_find_root_after_sync_button(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSIGNMENT_CHECKER_ROOT", raising=False)
    monkeypatch.setattr(shared_folder, "onedrive_roots", lambda: [])
    monkeypatch.setattr(shared_folder.Path, "home", staticmethod(lambda: tmp_path))
    system = tmp_path / "BGU" / "נדב מאיר - YallaLinearit" / "Exercise Checking System"
    system.mkdir(parents=True)
    assert shared_folder.find_root() == system


def test_course_folder_without_team_folder_is_not_used(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSIGNMENT_CHECKER_ROOT", raising=False)
    monkeypatch.setattr(shared_folder, "onedrive_roots", lambda: [])
    monkeypatch.setattr(shared_folder.Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / "BGU" / "נדב מאיר - YallaLinearit" / "Recordings").mkdir(parents=True)
    with pytest.raises(shared_folder.FolderNotFound) as e:
        shared_folder.find_root()
    assert "Exercise Checking System" in str(e.value)


# ---------- המצב לאתר ----------
def test_state_groups_files_by_number_and_hides_names(root):
    a_dir = root / COURSE / HW
    (a_dir / paths.MARKED / "0001.pdf").write_bytes(b"%PDF")
    with (a_dir / paths.GRADES).open("w", encoding="utf-8", newline="") as fh:
        fh.write("number,grade,feedback\n0003,87,עבודה טובה\n")
    st = actions.state(root)
    assert [c["name"] for c in st["courses"]] == ["אלגברה לינארית להנדסה"]  # קורס בלי מטלות לא מוצג
    (a,) = st["assignments"]
    assert a["title"] == "הגשה 0 - קבוצות ומרוכבים" and a["questions"] == 5 and a["moodleId"] == MID
    assert a["pulledAt"].startswith("2026-10-21T16:28")  # מתוך שם ה-ZIP ששמור בתיקייה
    subs = {s["id"]: s for s in a["subs"]}
    assert list(subs) == ["0001", "0002", "0003"]
    assert [f["name"] for f in subs["0002"]["files"]] == ["0002.pdf", "0002-2.pdf"]
    assert subs["0001"]["status"] == "graded"  # יש עבודה מסומנת
    assert subs["0003"]["status"] == "graded" and subs["0003"]["score"] == 87 and subs["0003"]["feedback"] == "עבודה טובה"
    assert subs["0002"]["status"] == "pulled"
    raw = json.dumps(st, ensure_ascii=False)
    assert not any(name in raw for name in NAMES.values())


# ---------- משיכה: moodle ingest ----------
def test_pull_runs_ingest_with_the_assignment_id(root, monkeypatch):
    seen = {}

    def fake_ingest(assignment_id, zip_path=None, course=None, name=None):
        seen["id"], seen["data"] = assignment_id, paths.data_dir()
        a_dir = paths.find_assignment(assignment_id)
        rows = folder_view.Assignment(a_dir).key_rows()
        (a_dir / paths.TO_GRADE / "0004.pdf").write_bytes(homework_pdf(NAMES["2000"], HW))
        rows.append({"number": "0004", "anon_file": "0004.pdf", "participant_id": "2000",
                     "original_folder": f"{NAMES['2000']}_2000_assignsubmission_file", "original_file": "hw.pdf"})
        write_key(a_dir, rows)
        return rows

    monkeypatch.setattr("moodle.ingest.ingest", fake_ingest)
    rep = actions.pull(root, COURSE, HW)
    assert seen == {"id": MID, "data": root}
    assert rep["result"] == {"total": 4, "new": 1, "files": 5}
    assert "1 חדשות" in rep["summary"]


@pytest.mark.parametrize("error, expect", [
    (FileNotFoundError("7-Zip is not installed (winget install 7zip.7zip)"), "7-Zip לא מותקן"),
    (FileNotFoundError(f"No ZIP ending in -{MID}.zip in Downloads"), "תיקיית ההורדות"),
])
def test_pull_errors_are_explained_in_hebrew(root, monkeypatch, error, expect):
    def broken(*args, **kwargs):
        raise error
    monkeypatch.setattr("moodle.ingest.ingest", broken)
    with pytest.raises(actions.UserError) as e:
        actions.pull(root, COURSE, HW)
    assert expect in str(e.value)


# ---------- החזרה: moodle upload ----------
def test_return_runs_upload_and_builds_feedback(root, monkeypatch):
    monkeypatch.setattr("moodle.upload.find_worksheet", lambda *a, **k: None)
    a_dir = root / COURSE / HW
    (a_dir / paths.MARKED / "0001.pdf").write_bytes(homework_pdf("x", HW))
    with (a_dir / paths.GRADES).open("w", encoding="utf-8", newline="") as fh:
        fh.write("number,grade,feedback\n0001,90,יפה\n")
    rep = actions.prepare_return(root, COURSE, HW)
    assert rep["report"]["results"] == 1 and rep["report"]["submissions"] == 3
    assert any("עוד אין ציון ל-2" in n for n in rep["notes"])
    assert any("גיליון ציונים" in n for n in rep["notes"])
    zips = list((a_dir / paths.UPLOAD).glob("*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as zf:
        assert any(n.startswith(f"{NAMES['1001']}_1001_") for n in zf.namelist())  # השם רק בתוך ה-ZIP למודל


def test_unknown_assignment_is_refused(root):
    with pytest.raises(FileNotFoundError):
        actions.pull(root, COURSE, "../../Recordings")



def test_server_pull_error_and_files(root, server, monkeypatch):
    def no_zip(*a, **k):
        raise FileNotFoundError(f"No ZIP ending in -{MID}.zip in Downloads")
    monkeypatch.setattr("moodle.ingest.ingest", no_zip)
    st, rep = call(server, "POST", "/api/pull", {"course": COURSE, "assignment": HW}, {"X-Assignment-Checker": "1"})
    assert st == 422 and "תיקיית ההורדות" in rep["error"]
    _, state = call(server, "GET", "/api/state")
    f = state["assignments"][0]["subs"][0]["files"][0]
    st, data = call(server, "GET", f"/api/file?path={quote(f['path'])}")
    assert st == 200 and data[:4] == b"%PDF"
    st, index = call(server, "GET", "/")
    assert st == 200 and b"<html" in index


def test_server_refuses_foreign_requests(root, server):
    body = {"course": COURSE, "assignment": HW}
    assert call(server, "POST", "/api/pull", body)[0] == 403
    assert call(server, "POST", "/api/return", body, {"X-Assignment-Checker": "1", "Origin": "https://evil.example"})[0] == 403
    assert call(server, "GET", "/api/state", headers={"Host": "evil.example"})[0] == 403
    assert call(server, "GET", "/api/file?path=../../Recordings")[0] == 404
    assert call(server, "GET", f"/api/file?path={quote(COURSE + '/' + HW + '/' + paths.KEY)}")[0] == 404  # טבלת המפתח לא נשלחת לאתר



SITE = "https://bodek-hacham.vercel.app"


def _raw(port, method, path, headers):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request(method, path, headers={"Host": f"127.0.0.1:{port}", **headers})
    r = conn.getresponse()
    r.read()
    return r.status, {k.lower(): v for k, v in r.getheaders()}


def test_public_site_can_connect_and_others_cannot(root, server):
    """האתר הציבורי (Vercel) מתחבר לשרת שבמחשב: preflight, קריאת תשובות ופעולות. אתר אחר לא."""
    st, h = _raw(server, "OPTIONS", "/api/state", {"Origin": SITE, "Access-Control-Request-Method": "GET",
                                                   "Access-Control-Request-Private-Network": "true"})
    assert st == 204 and h["access-control-allow-origin"] == SITE and h["access-control-allow-private-network"] == "true"
    assert "X-Assignment-Checker" in h["access-control-allow-headers"]
    st, h = _raw(server, "GET", "/api/health", {"Origin": SITE})
    assert st == 200 and h["access-control-allow-origin"] == SITE
    assert call(server, "POST", "/api/open", {"course": COURSE, "assignment": "nope"},
                {"X-Assignment-Checker": "1", "Origin": SITE})[0] == 404  # עבר את בדיקת המקור
    for evil in ("https://evil.example", "https://bodek-hacham-git-x.vercel.app", "https://bodek-hacham.vercel.app.evil.example"):
        assert _raw(server, "OPTIONS", "/api/state", {"Origin": evil})[0] == 403
        assert "access-control-allow-origin" not in _raw(server, "GET", "/api/health", {"Origin": evil})[1]
        assert call(server, "POST", "/api/pull", {"course": COURSE, "assignment": HW},
                    {"X-Assignment-Checker": "1", "Origin": evil})[0] == 403


def test_activity_log_comes_from_the_folder(root):
    """היומן באתר: רק מה שבאמת קרה. משיכות (ה-ZIP-ים שנשמרו), Grades.csv, והעלאות מיומן ההעלאה."""
    a_dir = root / COURSE / HW
    assert [(x["kind"], x["at"]) for x in actions.state(root)["assignments"][0]["log"]] == [("pull", "2026-10-21T16:28")]
    with (a_dir / paths.GRADES).open("w", encoding="utf-8", newline="") as fh:
        fh.write("number,grade,feedback\n0001,90,טוב\n0002,,\n")
    with (a_dir / paths.UPLOAD / "Upload log.csv").open("w", encoding="utf-8", newline="") as fh:
        fh.write("number,file,sha256,zip,uploaded_at,by\n"
                 "0001,0001.pdf,a,Graded - part 01.zip,2026-10-22T10:00:05,matan (PC)\n"
                 "0003,0003.pdf,b,Graded - part 01.zip,2026-10-22T10:00:09,matan (PC)\n")
    log = {x["kind"]: x for x in actions.state(root)["assignments"][0]["log"]}
    assert log["grade"]["text"] == "Grades.csv עודכן: 1 ציונים"
    assert log["return"]["text"] == "הועלו למודל 2 עבודות מסומנות (Graded - part 01.zip)"
    assert log["return"]["actor"] == "matan (PC)" and log["return"]["at"] == "2026-10-22T10:00"
    assert "נועה" not in json.dumps(log, ensure_ascii=False)

# ---------- כל אחד יכול למשוך: נעילה והתנגשויות ----------
def _ok_ingest(assignment_id, *a, **k):
    return folder_view.Assignment(paths.find_assignment(assignment_id)).key_rows()


def test_pull_waits_for_someone_elses_pull(root, monkeypatch):
    import os, time
    monkeypatch.setattr("moodle.ingest.ingest", _ok_ingest)
    lock = root / COURSE / HW / actions.LOCK_FILE
    lock.write_text("uri (URI-LAPTOP)", encoding="utf-8")
    with pytest.raises(actions.UserError) as e:
        actions.pull(root, COURSE, HW)
    assert "uri (URI-LAPTOP) מושך" in str(e.value)
    assert actions.state(root)["assignments"][0]["warnings"] == ["משיכה בתהליך: uri (URI-LAPTOP)"]
    old = time.time() - 31 * 60  # נעילה ישנה (משיכה שנתקעה) לא חוסמת
    os.utime(lock, (old, old))
    actions.pull(root, COURSE, HW)
    assert not lock.exists()  # הנעילה משתחררת בסוף


def test_lock_is_released_when_pull_fails(root, monkeypatch):
    def no_zip(*a, **k):
        raise FileNotFoundError(f"No ZIP ending in -{MID}.zip in Downloads")
    monkeypatch.setattr("moodle.ingest.ingest", no_zip)
    with pytest.raises(actions.UserError):
        actions.pull(root, COURSE, HW)
    assert not (root / COURSE / HW / actions.LOCK_FILE).exists()


def test_onedrive_conflict_copy_blocks_pull(root, monkeypatch):
    monkeypatch.setattr("moodle.ingest.ingest", _ok_ingest)
    a_dir = root / COURSE / HW
    (a_dir / "Key - number to student-DESKTOP-ABC.csv").write_text("number\n", encoding="utf-8")
    with pytest.raises(actions.UserError) as e:
        actions.pull(root, COURSE, HW)
    assert "עותק כפול" in str(e.value)
    assert actions.state(root)["assignments"][0]["warnings"] == ["עותק כפול של טבלת המפתח: Key - number to student-DESKTOP-ABC.csv"]


# ---------- משיכה: ההורדה ממודל דרך Claude בכרום ----------
def _record_ingest(seen):
    def ingest(assignment_id, zip_path=None, *a, **k):
        seen.append(zip_path)
        return _ok_ingest(assignment_id)
    return ingest


def test_pull_downloads_from_moodle_when_no_zip_is_waiting(root, monkeypatch):
    from moodle import ingest
    seen, fake = [], FakeDownloader(ingest.downloads_dir())
    monkeypatch.setattr(actions, "_make_downloader", lambda: fake)
    monkeypatch.setattr("moodle.ingest.ingest", _record_ingest(seen))
    actions.pull(root, COURSE, HW)
    assert fake.calls == [MID]
    assert [p.name for p in seen] == [f"214193210120271-x-{MID}.zip"]


def test_pull_takes_a_zip_that_was_downloaded_by_hand(root, monkeypatch):
    from moodle import ingest
    by_hand = ingest.downloads_dir() / f"קורס-הגשה 0-{MID}.zip"
    by_hand.write_bytes(b"zip")
    seen, fake = [], FakeDownloader(ingest.downloads_dir())
    monkeypatch.setattr(actions, "_make_downloader", lambda: fake)
    monkeypatch.setattr("moodle.ingest.ingest", _record_ingest(seen))
    actions.pull(root, COURSE, HW)
    assert seen == [by_hand] and fake.calls == []  # לא מורידים שוב


def test_pull_explains_a_download_that_did_not_start(root, monkeypatch):
    from moodle import ingest
    fake = FakeDownloader(ingest.downloads_dir(), {"status": "needs_login", "message": "Moodle מבקש התחברות."})
    monkeypatch.setattr(actions, "_make_downloader", lambda: fake)
    monkeypatch.setattr("moodle.ingest.ingest", lambda *a, **k: pytest.fail("nothing to ingest"))
    with pytest.raises(actions.UserError, match="מבקש התחברות"):
        actions.pull(root, COURSE, HW)
    assert not (root / COURSE / HW / actions.LOCK_FILE).exists()


def test_pull_waits_for_chrome_to_finish_and_explains_a_stuck_download(root, monkeypatch):
    from moodle import ingest

    class NothingArrives:
        def download(self, info):
            return {"status": "started", "message": "ok"}

    monkeypatch.setattr(actions, "_make_downloader", NothingArrives)
    def no_start(*a, **k):
        raise TimeoutError("The download did not start in Chrome")
    monkeypatch.setattr(ingest, "wait_for_download", no_start)
    with pytest.raises(actions.UserError, match="שאל איפה לשמור"):
        actions.pull(root, COURSE, HW)


def test_pull_does_not_download_while_an_upload_uses_chrome(root, monkeypatch):
    monkeypatch.setattr(actions._send, "running", True)
    with pytest.raises(actions.UserError, match="העלאה"):
        actions.pull(root, COURSE, HW)
