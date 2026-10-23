"""בדיקות לאתר המחובר: איתור התיקייה, המצב לאתר, והחיבור לשלבים של moodle/.

את moodle/ עצמו בודקות הבדיקות של אורי (test_*.py בשורש הריפו).
מריצים: python -m pytest
"""
from __future__ import annotations

import json
import subprocess
import zipfile
from urllib.parse import quote

import pytest

from moodle import paths
from dashboard import actions, folder_view, shared_folder
from tests.sample_files import homework_pdf

from tests.dashboard.conftest import FakeDownloader
from tests.dashboard.helpers import COURSE, HDR, HW, MID, NAMES, call, hw, write_key

_REAL_POPEN = subprocess.Popen  # before the fixture blocks every process


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
    assert [c["name"] for c in st["courses"]] == ["מתמטיקה בדידה", "אלגברה לינארית להנדסה"]
    a = next(x for x in st["assignments"] if x["folder"] == HW)
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


def test_every_course_has_ten_assignments(root):
    """עשר הגשות בכל קורס, גם בקורס שעוד אין בו אף מטלה. מה שעוד לא נמשך הוא מקום ריק בלי מזהה מודל."""
    st = actions.state(root)
    by_course = {c["folder"]: [a for a in st["assignments"] if a["courseId"] == c["id"]] for c in st["courses"]}
    assert {k: len(v) for k, v in by_course.items()} == {"Discrete Mathematics": 10, COURSE: 10}
    assert [a["title"] for a in by_course["Discrete Mathematics"]] == [f"הגשה {n}" for n in range(10)]
    la = by_course[COURSE]
    assert la[0]["folder"] == HW and la[0]["moodleId"] == MID and not la[0].get("empty")
    assert la[3] == {**la[3], "folder": "Assignment 3", "title": "הגשה 3", "moodleId": None, "subs": [], "empty": True}
    assert len({a["id"] for a in st["assignments"]}) == 20


def test_first_pull_of_an_empty_slot_saves_the_moodle_id(root, monkeypatch):
    seen = {}

    def fake_ingest(assignment_id, zip_path=None, course=None, name=None, **_):
        seen["id"], seen["dir"] = assignment_id, paths.find_assignment(assignment_id)
        return []

    monkeypatch.setattr("moodle.ingest.ingest", fake_ingest)
    actions.pull(root, "Discrete Mathematics", "Assignment 2", moodle_id="3500001")
    a_dir = root / "Discrete Mathematics" / "Assignment 2"
    assert seen == {"id": "3500001", "dir": a_dir}
    info = json.loads((a_dir / paths.INFO).read_text(encoding="utf-8"))
    assert info == {"id": "3500001", "course": "Discrete Mathematics", "name": "Assignment 2", "title": "x"}  # הכותרת משם ה-ZIP
    dm = [a for a in actions.state(root)["assignments"] if a["courseFolder"] == "Discrete Mathematics"]
    assert len(dm) == 10 and dm[2]["moodleId"] == "3500001" and not dm[2].get("empty")
    actions.pull(root, "Discrete Mathematics", "Assignment 2", moodle_id="3500001")  # שוב עם אותו מזהה: בסדר


@pytest.mark.parametrize("course, assignment, mid, expect", [
    ("Discrete Mathematics", "Assignment 2", "abc", "המספר שאחרי id="),
    ("Discrete Mathematics", "Assignment 2", MID, "כבר שייך"),  # המזהה של הגשה 0 באלגברה
    (COURSE, "Assignment 0", "3500001", "כבר יש תיקייה"),
])
def test_empty_slot_pull_is_refused(root, course, assignment, mid, expect):
    with pytest.raises(actions.UserError) as e:
        actions.pull(root, course, assignment, moodle_id=mid)
    assert expect in str(e.value)


@pytest.mark.parametrize("course, assignment", [
    ("Discrete Mathematics", "Assignment 10"), ("Discrete Mathematics", "../x"), ("Physics", "Assignment 1"),
    ("Discrete Mathematics", "Assignment 1 - Logic"),
])
def test_empty_slot_pull_takes_only_the_ten_slots(root, course, assignment):
    with pytest.raises(FileNotFoundError):
        actions.pull(root, course, assignment, moodle_id="3500001")
    assert not (root / course / assignment).exists()


def test_server_passes_the_moodle_id_of_a_new_slot(root, server, monkeypatch):
    monkeypatch.setattr("moodle.ingest.ingest", lambda *a, **k: [])
    st, rep = call(server, "POST", "/api/pull", {"course": "Discrete Mathematics", "assignment": "Assignment 1",
                                                 "moodleId": "3500002"}, HDR)
    assert st == 200, rep
    assert paths.read_info(root / "Discrete Mathematics" / "Assignment 1")["id"] == "3500002"


# ---------- משיכה: moodle ingest ----------
def test_pull_runs_ingest_with_the_assignment_id(root, monkeypatch):
    seen = {}

    def fake_ingest(assignment_id, zip_path=None, course=None, name=None, **_):
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


def test_pull_time_left_follows_the_pace_of_the_phase():
    assert actions._eta("parts", 1, 15, 0, 0) == 14 * actions.PART_S  # no pace yet: about PART_S a part
    assert actions._eta("parts", 5, 15, 40, 4) == 100  # 4 parts in 40 s → 10 more in 100 s
    assert actions._eta("extract", 50, 100, 30, 50) == 30
    assert actions._eta("extract", 0, 100, 0, 0) is None  # nothing to go by
    assert actions._eta("parts", 3, 0, 20, 2) is None  # total not known
    assert actions._eta("number", 10, 10, 5, 10) == 0


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
    f = hw(state)["subs"][0]["files"][0]
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
    assert [(x["kind"], x["at"]) for x in hw(actions.state(root))["log"]] == [("pull", "2026-10-21T16:28")]
    with (a_dir / paths.GRADES).open("w", encoding="utf-8", newline="") as fh:
        fh.write("number,grade,feedback\n0001,90,טוב\n0002,,\n")
    with (a_dir / paths.UPLOAD / "Upload log.csv").open("w", encoding="utf-8", newline="") as fh:
        fh.write("number,file,sha256,zip,uploaded_at,by\n"
                 "0001,0001.pdf,a,Graded - part 01.zip,2026-10-22T10:00:05,matan (PC)\n"
                 "0003,0003.pdf,b,Graded - part 01.zip,2026-10-22T10:00:09,matan (PC)\n")
    log = {x["kind"]: x for x in hw(actions.state(root))["log"]}
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
    assert hw(actions.state(root))["warnings"] == ["משיכה בתהליך: uri (URI-LAPTOP)"]
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
    assert hw(actions.state(root))["warnings"] == ["עותק כפול של טבלת המפתח: Key - number to student-DESKTOP-ABC.csv"]


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


def test_pull_progress_for_the_site(root, server, monkeypatch):
    """GET /api/pull: how far the pull got, while the POST still runs. The ZIP's size is guessed from the last download."""
    from moodle import ingest
    seen = []

    def ingest_with_progress(assignment_id, zip_path=None, *a, on_progress=None, **k):
        on_progress("check", 40, 100)
        seen.append(call(server, "GET", "/api/pull")[1])
        on_progress("number", 1, 3)
        seen.append(call(server, "GET", "/api/pull")[1])
        return _ok_ingest(assignment_id)

    monkeypatch.setattr(actions, "_make_downloader", lambda: FakeDownloader(ingest.downloads_dir()))
    monkeypatch.setattr("moodle.ingest.ingest", ingest_with_progress)
    st, rep = call(server, "POST", "/api/pull", {"course": COURSE, "assignment": HW}, HDR)
    assert st == 200, rep
    assert [(x["running"], x["phase"], x["done"], x["total"], x["downloaded"]) for x in seen] == [
        (True, "check", 40, 100, True), (True, "number", 1, 3, True)]
    end = call(server, "GET", "/api/pull")[1]
    assert end["running"] is False and end["summary"] == rep["summary"] and not end["error"]
    assert actions._expected_zip_size(folder_view.Assignment(root / COURSE / HW)) > 0  # ה-ZIP הקודם שבתיקייה


def test_pull_progress_keeps_the_error(root, monkeypatch):
    monkeypatch.setattr("moodle.ingest.ingest", lambda *a, **k: (_ for _ in ()).throw(ValueError("The ZIP is incomplete")))
    with pytest.raises(actions.UserError):
        actions.pull(root, COURSE, HW)
    status = actions.pull_status()
    assert status["running"] is False and "לא שלם" in status["error"] and "7-Zip לא מותקן" not in status["error"]


def test_pull_takes_a_zip_that_was_downloaded_by_hand(root, monkeypatch):
    from moodle import ingest
    by_hand = ingest.downloads_dir() / f"קורס-הגשה 0-{MID}.zip"
    by_hand.write_bytes(b"zip")
    seen, fake = [], FakeDownloader(ingest.downloads_dir())
    monkeypatch.setattr(actions, "_make_downloader", lambda: fake)
    monkeypatch.setattr("moodle.ingest.ingest", _record_ingest(seen))
    actions.pull(root, COURSE, HW)
    assert seen == [by_hand] and fake.calls == []  # לא מורידים שוב


def test_pull_refuses_an_empty_key_before_opening_chrome(root, monkeypatch):
    """טבלת מפתח ריקה כשכבר יש הגשות: משיכה הייתה נותנת לכולם מספרים חדשים. עוצרים לפני כרום, בלי לגעת בתיקייה."""
    from moodle import ingest
    (root / COURSE / HW / paths.KEY).write_text("", encoding="utf-8")
    fake = FakeDownloader(ingest.downloads_dir())
    monkeypatch.setattr(actions, "_make_downloader", lambda: fake)
    with pytest.raises(actions.UserError, match="טבלת המפתח של המטלה הזו ריקה או פגומה"):
        actions.pull(root, COURSE, HW)
    assert fake.calls == [] and not (root / COURSE / HW / actions.LOCK_FILE).exists()


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


def test_health_answers_at_once_while_claude_is_checked_in_the_background(root, server, monkeypatch):
    """`claude auth status` לוקח במחשב של אורי עד 13 שניות. /api/health לא מחכה לו: עונה מיד עם checking,
    והבדיקה רצה ברקע. כשהיא נגמרת, השאלה הבאה מקבלת את התשובה."""
    import threading
    import time
    from moodle import claude_driver
    gate = threading.Event()

    def slow_status(*a, **k):
        gate.wait(10)
        return {"logged_in": True, "message": "Claude Code מחובר."}
    monkeypatch.setattr(claude_driver, "auth_status", slow_status)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    started = time.monotonic()
    st, h = call(server, "GET", "/api/health")
    assert st == 200 and time.monotonic() - started < 2
    assert h["ok"] and h["root"] and h["checking"] is True and h["claude"] is False
    gate.set()
    for _ in range(100):
        h = call(server, "GET", "/api/health")[1]
        if not h["checking"]:
            break
        time.sleep(0.05)
    assert h["checking"] is False and h["claude"] is True and h["moodle"] is True and h["claudeVia"] == "code"


class PartsDownloader:
    """Moodle in parts (moodle/download_parts.js): a ZIP per part in Downloads, and the list of the parts last."""

    def __init__(self, downloads, students_per_part):
        self.downloads, self.students_per_part = downloads, students_per_part

    def download(self, info):
        stem, n = f"214193210120271-הגשה 0-{info['id']}", len(self.students_per_part)
        files = []
        for i, students in enumerate(self.students_per_part, 1):
            name = f"{stem} part {i:03} of {n:03}.zip"
            with zipfile.ZipFile(self.downloads / name, "w") as z:
                for pid in students:
                    z.writestr(f"{NAMES[pid]}_{pid}_assignsubmission_file/hw.pdf", homework_pdf(NAMES[pid], HW))
            files.append({"name": name, "size": (self.downloads / name).stat().st_size})
        listed = {"users": sum(map(len, self.students_per_part)), "parts": n, "empty": [], "failed": [], "files": files}
        (self.downloads / f"{stem}.json").write_text(json.dumps(listed), encoding="utf-8")
        return {"status": "started", "message": "ok", "users": listed["users"], "parts": n}


def test_pull_in_parts_keeps_every_number_and_adds_the_new_student(root, monkeypatch, tmp_path):
    """Moodle cuts one big ZIP (2026-10-23), so the pull downloads in parts: all of them land in one originals folder."""
    from moodle import ingest
    monkeypatch.setenv("ASSIGNMENT_WORK", str(tmp_path / "Moodle originals"))  # never the real extracted folder
    try:
        ingest.seven_zip()
    except FileNotFoundError:
        pytest.skip("7-Zip is not installed")
    seven = ingest.seven_zip()
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, *a, **k: _REAL_POPEN(cmd, *a, **k) if cmd[0] == seven
                        else pytest.fail("a test started a real process"))
    monkeypatch.setattr(actions, "_make_downloader",
                        lambda: PartsDownloader(ingest.downloads_dir(), [["1001", "2000"], ["1002", "1003"]]))
    rep = actions.pull(root, COURSE, HW)
    assert rep["result"]["total"] == 4 and rep["result"]["new"] == 1
    key = {r["participant_id"]: r["number"] for r in folder_view.Assignment(root / COURSE / HW).key_rows()}
    assert key["1001"] == "0001" and key["1002"] == "0002" and key["1003"] == "0003" and key["2000"] == "0004"
    kept = [p for p in (root / COURSE / HW).iterdir() if p.is_dir() and p.name.startswith(paths.DOWNLOAD_PREFIX)]
    assert len(kept) == 1 and sorted(p.name for p in kept[0].iterdir()) == ["part 001.zip", "part 002.zip", "parts.json"]
    assert list(ingest.downloads_dir().iterdir()) == []  # every part was taken
    assert actions.pull_status()["phase"] == "number"
    assert len(list((tmp_path / "Moodle originals" / COURSE / HW).iterdir())) == 4


def test_a_pull_in_parts_tells_how_many_came_without_a_file(tmp_path):
    listed = tmp_path / f"x-{MID}.json"
    listed.write_text(json.dumps({"empty": 2, "files": [{"asked": 38, "students": 36}, {"asked": 38, "students": 38}]}),
                      encoding="utf-8")
    assert actions._without_file(listed) == 4
    assert actions._without_file(tmp_path / f"x-{MID}.zip") == 0  # one ZIP of all: nothing to compare with


def test_only_one_download_from_moodle_at_a_time_on_this_computer(root, monkeypatch):
    """Two pulls at once in one Chrome each clicked Moodle's folders option on 2026-10-23."""
    import os
    from moodle import lock as moodle_lock
    held = actions._work_dir() / actions.CHROME_PULL_LOCK  # another dashboard on this computer is downloading
    held.write_text(moodle_lock.my_text().replace(f"pid={os.getpid()}", "pid=1"), encoding="utf-8")
    monkeypatch.setattr(moodle_lock, "pid_alive", lambda pid: True)
    fake = FakeDownloader(actions.moodle_ingest.downloads_dir())
    monkeypatch.setattr(actions, "_make_downloader", lambda: fake)
    with pytest.raises(actions.UserError, match="משיכה אחת בכל פעם"):
        actions.pull(root, COURSE, HW)
    assert fake.calls == []  # Chrome was never asked
    held.unlink()
    assert "tmp" in str(actions._work_dir()).lower() or "pytest" in str(actions._work_dir()).lower()


def test_a_pull_without_folders_is_explained_in_hebrew(root, monkeypatch):
    def flat(*a, **k):
        raise ValueError("The download is incomplete or broken (not in a folder per student: 76 files)")
    monkeypatch.setattr("moodle.ingest.ingest", flat)
    with pytest.raises(actions.UserError, match="בלי תיקייה לכל סטודנט"):
        actions.pull(root, COURSE, HW)


def test_the_site_dates_every_kind_of_kept_download(root):
    """ingest keeps every download as "Moodle download <stamp>" (a ZIP, or a folder of parts); the site shows when."""
    from moodle import ingest, status
    a = actions.find_assignment(root, COURSE, HW)
    for p in a.dir.glob(f"{paths.DOWNLOAD_PREFIX} *"):
        p.unlink()
    (a.dir / f"{paths.DOWNLOAD_PREFIX} 2026-10-22 09-30.zip").write_bytes(b"old name, to the minute")
    stamp = ingest._free_stamp(a.dir)  # what ingest names the next one
    (a.dir / f"{paths.DOWNLOAD_PREFIX} {stamp}").mkdir()  # in parts
    again = ingest._free_stamp(a.dir)
    assert again == f"{stamp} (2)"
    (a.dir / f"{paths.DOWNLOAD_PREFIX} {again}.zip").write_bytes(b"same second")
    (a.dir / f"{paths.DOWNLOAD_PREFIX} 2026-10-23 08-00-00 (incomplete).zip").write_bytes(b"not a kept download")
    times = actions._downloads(a)
    assert len(times) == 3 and times[0] == "2026-10-22T09:30" and times == sorted(times)
    assert actions._last_download(a) == times[-1] != "2026-10-22T09:30"
    assert len(status.status(a.dir)["downloads"]) == 4  # moodle status lists the folder of parts too
