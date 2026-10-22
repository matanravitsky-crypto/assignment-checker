"""בדיקות למערכת, על עותק מוקטן של המבנה של הצוות. מריצים: python -m pytest"""
from __future__ import annotations

import csv
import http.client
import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote

import pytest

from pipeline import config, service, team
from pipeline.demo import homework_pdf
from pipeline.moodle_zip import read_zip
from pipeline.pull import single_pdf
from pipeline.types import Submission, SubmittedFile

COURSE, HW = "Linear Algebra", "Assignment 0 - Sets and Complex Numbers"
NAMES = {"1001": "נועה כהן", "1002": "איתי לוי", "1003": "מאיה מזרחי", "2000": "יונתן פרץ", "2001": "שירה ביטון"}


def make_zip(entries: dict[str, bytes], utf8: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            cls = zipfile.ZipInfo if utf8 else _NoUtf8Flag
            zf.writestr(cls(name, date_time=(2026, 10, 20, 12, 0, 0)), data)
    return buf.getvalue()


class _NoUtf8Flag(zipfile.ZipInfo):
    """ZIP ישן: השם נשמר בבתים של UTF-8, אבל בלי הסימון שאומר שזה UTF-8."""
    def _encodeFilenameFlags(self):
        return self.filename.encode("utf-8"), self.flag_bits & ~0x800


def entry(pid: str, fname: str = "hw.pdf") -> str:
    return f"{NAMES[pid]}_{pid}_assignsubmission_file/{fname}"


@pytest.fixture
def root(tmp_path, monkeypatch):
    """עותק מוקטן של YallaLinearit/Exercise Checking System, כמו שאורי בנה."""
    course_folder = tmp_path / "BGU" / "נדב מאיר - YallaLinearit"
    (course_folder / "Recordings").mkdir(parents=True)
    r = course_folder / "Exercise Checking System"
    (r / "Discrete Mathematics").mkdir(parents=True)
    (r / "README.txt").write_text("כללים של הצוות", encoding="utf-8-sig")
    a = team.Assignment(r / COURSE / HW)
    for sub in (team.SUBMISSIONS, team.GRADED, team.READY):
        (a.dir / sub).mkdir(parents=True)
    a.save_details({"id": "3438636", "course": COURSE, "course_id": "67024", "name": HW,
                    "due": "2026-10-26T23:59:00+02:00",
                    "questions": [{"sheet": "דף קבוצות", "numbers": [11, 12]}, {"sheet": "דף מספרים מרוכבים", "numbers": [6, 7, 8]}],
                    "title": "הגשה 0 - קבוצות ומרוכבים", "course_title": "אלגברה לינארית להנדסה"})
    rows = []
    for i, pid in enumerate(("1001", "1002", "1003"), start=1):
        n = f"{i:04d}"
        (a.submissions / f"{n}.pdf").write_bytes(homework_pdf(NAMES[pid], HW))
        rows.append({"number": n, "anon_file": f"{n}.pdf", "participant_id": pid,
                     "original_folder": f"{NAMES[pid]}_{pid}_assignsubmission_file", "original_file": "hw.pdf"})
    a.save_key(rows)
    monkeypatch.setenv("ASSIGNMENT_CHECKER_ROOT", str(course_folder))
    monkeypatch.delenv("MOODLE_TOKEN", raising=False)
    return r


def asg(root) -> team.Assignment:
    return team.Assignment(root / COURSE / HW)


def key(root) -> list[dict]:
    with (asg(root).dir / team.KEY).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------- איתור התיקייה ----------
def test_find_root_goes_into_the_team_folder(root):
    assert config.find_root() == root


def test_find_root_after_sync_button(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSIGNMENT_CHECKER_ROOT", raising=False)
    monkeypatch.setattr(config, "onedrive_roots", lambda: [])
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: tmp_path))
    system = tmp_path / "BGU" / "נדב מאיר - YallaLinearit" / "Exercise Checking System"
    system.mkdir(parents=True)
    assert config.find_root() == system


def test_course_folder_without_team_folder_is_not_used(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSIGNMENT_CHECKER_ROOT", raising=False)
    monkeypatch.setattr(config, "onedrive_roots", lambda: [])
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / "BGU" / "נדב מאיר - YallaLinearit" / "Recordings").mkdir(parents=True)
    with pytest.raises(config.FolderNotFound) as e:
        config.find_root()
    assert "Exercise Checking System" in str(e.value)
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    with pytest.raises(config.FolderNotFound) as e:
        config.find_root()
    assert "Sync" in str(e.value)


# ---------- ZIP של מודל ----------
def test_read_zip_folders_flat_and_wrapper(tmp_path):
    pdf = homework_pdf("x", HW)
    z = tmp_path / "x.zip"
    z.write_bytes(make_zip({
        "נועה כהן_111_assignsubmission_file/hw.pdf": pdf,
        "איתי לוי_222_assignsubmission_file_hw.pdf": pdf,
        "COURSE-HW1-9/מאיה מזרחי_333_assignsubmission_file/part 1.pdf": pdf,
        "מאיה מזרחי_333_assignsubmission_onlinetext/onlinetext.html": b"<p>hi</p>",
    }))
    with zipfile.ZipFile(z) as zf:
        subs = {s.moodle_id: s for s in read_zip(zf)}
        assert subs["111"].files[0].content()[:4] == b"%PDF"
    assert set(subs) == {"111", "222", "333"}
    assert subs["111"].folder == "נועה כהן_111_assignsubmission_file"
    assert subs["222"].folder == "איתי לוי_222_assignsubmission_file"
    assert sorted(f.name for f in subs["333"].files) == ["onlinetext.html", "part 1.pdf"]


def test_read_zip_hebrew_names_without_utf8_flag(tmp_path):
    z = tmp_path / "old.zip"
    z.write_bytes(make_zip({"שירה ביטון_444_assignsubmission_file_hw.pdf": b"%PDF"}, utf8=False))
    with zipfile.ZipFile(z) as zf:
        (s,) = read_zip(zf)
    assert s.name == "שירה ביטון"


# ---------- איחוד ל-PDF אחד ----------
def test_single_pdf_merges_pdfs_and_scanned_pages():
    import pymupdf
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 60), False)
    pix.clear_with(200)
    sub = Submission("1", "x", [SubmittedFile("b.png", pix.tobytes("png")), SubmittedFile("a.pdf", homework_pdf("x", HW, pages=2))])
    data, issues = single_pdf(sub)
    with pymupdf.open(stream=data, filetype="pdf") as d:
        assert d.page_count == 3
    assert not issues
    empty, issues = single_pdf(Submission("2", "y", [SubmittedFile("hw.pdf", b"")]))
    assert empty is None and "ריק" in issues[0]


# ---------- משיכה ----------
def test_pull_keeps_numbers_numbers_new_students_and_hides_names(root):
    a = asg(root)
    old_0002 = (a.submissions / "0002.pdf").read_bytes()
    (a.dir / team.GRADED / "0003.pdf").write_bytes(b"%PDF graded")
    a.inbox.mkdir()
    (a.inbox / "LA-Assignment 0-3438636.zip").write_bytes(make_zip({
        entry("1002"): old_0002,                                   # לא השתנה
        entry("1003"): homework_pdf(NAMES["1003"], HW, pages=3),   # הוגש מחדש אחרי בדיקה
        entry("2000"): homework_pdf(NAMES["2000"], HW),            # סטודנט חדש
        entry("2001"): b"",                                         # קובץ ריק
    }))
    rep = service.pull(root, COURSE, HW)

    r = rep.result
    assert (r.total, r.new, r.updated, r.same, len(r.problems)) == (4, 1, 1, 1, 1)
    rows = {row["participant_id"]: row for row in key(root)}
    assert rows["1002"]["number"] == "0002" and rows["1003"]["number"] == "0003"
    assert rows["2000"]["number"] == "0004" and rows["2000"]["anon_file"] == "0004.pdf"
    assert rows["2000"]["original_folder"] == f"{NAMES['2000']}_2000_assignsubmission_file"
    assert "2001" not in rows  # קובץ ריק לא מקבל מספר
    assert list(key(root)[0].keys())[:5] == team.KEY_COLUMNS
    assert (a.dir / team.KEY).read_bytes().startswith(b"\xef\xbb\xbf")  # BOM, כמו בקובץ של אורי
    assert any("0003 הוגשה מחדש" in n for n in rep.notes)
    assert "משתתף 2001" in r.problems[0]

    # שמות מופיעים רק בטבלת המפתח
    assert sorted(p.name for p in a.submissions.iterdir()) == ["0001.pdf", "0002.pdf", "0003.pdf", "0004.pdf"]
    log = (a.dir / team.LOG).read_text(encoding="utf-8")
    assert not any(name in log for name in NAMES.values())
    assert not list(a.inbox.glob("*.zip")) and len(list((a.inbox / team.INBOX_DONE).glob("*.zip"))) == 1
    readme = (root / COURSE / "README.txt").read_text(encoding="utf-8-sig")
    assert f"{HW}  (הגשה 0 - קבוצות ומרוכבים): 4 הגשות" in readme
    assert (root / "README.txt").read_text(encoding="utf-8-sig") == "כללים של הצוות"  # לא נוגעים


def test_second_pull_of_same_zip_changes_nothing(root):
    a = asg(root)
    data = make_zip({entry("2000"): homework_pdf(NAMES["2000"], HW)})
    a.inbox.mkdir()
    (a.inbox / "a.zip").write_bytes(data)
    service.pull(root, COURSE, HW)
    (a.inbox / "b.zip").write_bytes(data)
    rep = service.pull(root, COURSE, HW)
    assert rep.result.same == 1 and rep.result.new == 0
    assert len(key(root)) == 4


def test_late_submission_is_noted(root):
    a = asg(root)
    d = a.details()
    d["due"] = "2026-10-20T10:00:00+03:00"
    a.save_details(d)
    a.inbox.mkdir()
    (a.inbox / "a.zip").write_bytes(make_zip({entry("2000"): homework_pdf(NAMES["2000"], HW)}))
    rep = service.pull(root, COURSE, HW)
    assert any("0004 הוגשה באיחור" in n for n in rep.notes)


def test_zips_outside_the_download_folder_are_not_touched(root):
    # ההורדה המקורית של אורי יושבת בתיקיית המטלה: לא קוראים אותה ולא מזיזים אותה
    a = asg(root)
    original = a.dir / "Moodle download 2026-10-21 16-28.zip"
    original.write_bytes(make_zip({entry("2000"): homework_pdf(NAMES["2000"], HW)}))
    (root / COURSE / "stray.zip").write_bytes(b"not even a zip")
    rep = service.pull(root, COURSE, HW)
    assert rep.result.total == 0 and len(key(root)) == 3
    assert original.exists() and (root / COURSE / "stray.zip").exists()


def test_no_sources_explains_what_to_do(root):
    rep = service.pull(root, COURSE, HW)
    assert rep.result.total == 0 and any(team.INBOX in n for n in rep.notes)


def test_unknown_assignment_is_refused(root):
    with pytest.raises(FileNotFoundError):
        service.pull(root, COURSE, "../../Recordings")


# ---------- מודל עם טוקן ----------
class FakeMoodle(BaseHTTPRequestHandler):
    pdf = b""

    def log_message(self, *a):
        pass

    def do_POST(self):
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
        assert form["wstoken"] == "tok"
        fn = form["wsfunction"]
        base = f"http://127.0.0.1:{self.server.server_port}/webservice/pluginfile.php"
        if fn == "mod_assign_get_assignments":
            assert form["courseids[0]"] == "67024"
            out = {"courses": [{"id": 67024, "assignments": [
                {"id": 901, "cmid": 3438636, "name": "הגשה 0 - קבוצות ומרוכבים", "duedate": 1792540740},
                {"id": 902, "cmid": 3438700, "name": "הגשה 1 - מטריצות", "duedate": 0}]}]}
        elif fn == "mod_assign_get_submissions":
            assert form["assignmentids[0]"] == "901"
            out = {"assignments": [{"assignmentid": 901, "submissions": [
                {"userid": 2000, "status": "submitted", "timemodified": 1792500000, "plugins": [
                    {"type": "file", "fileareas": [{"area": "submission_files", "files": [{"filename": "hw.pdf", "fileurl": f"{base}/1/hw.pdf"}]}]}]},
                {"userid": 2001, "status": "new", "timemodified": 0, "plugins": []},
            ]}]}
        elif fn == "core_user_get_users_by_field":
            out = [{"id": 2000, "fullname": NAMES["2000"], "email": "x@post.bgu.ac.il", "idnumber": "123456789"}]
        else:
            out = {"exception": "x", "message": "unknown"}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(out).encode())

    def do_GET(self):
        assert "token=tok" in self.path
        self.send_response(200)
        self.end_headers()
        self.wfile.write(FakeMoodle.pdf)


def test_pull_from_moodle_with_token(root, monkeypatch):
    FakeMoodle.pdf = homework_pdf(NAMES["2000"], HW)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeMoodle)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("MOODLE_URL", f"http://127.0.0.1:{srv.server_port}")
        monkeypatch.setenv("MOODLE_TOKEN", "tok")
        rep = service.pull(root, COURSE, HW)
        assert "מודל" in rep.source and rep.result.new == 1
        assert {r["participant_id"]: r["number"] for r in key(root)}["2000"] == "0004"
        new = team.Assignment(root / COURSE / "הגשה 1 - מטריצות")
        assert new.details()["id"] == "3438700"  # מטלה חדשה במודל קיבלה תיקייה לבד
    finally:
        srv.shutdown()


# ---------- השרת המקומי ----------
@pytest.fixture
def server(root):
    from pipeline.server import Handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_port
    srv.shutdown()


def call(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    h = {"Host": f"localhost:{port}", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    if data:
        h["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=h)
    r = conn.getresponse()
    raw = r.read()
    return r.status, (json.loads(raw) if r.getheader("Content-Type", "").startswith("application/json") else raw)


def test_server_state_shows_numbers_not_names(root, server):
    (asg(root).dir / team.GRADED / "0001.pdf").write_bytes(b"%PDF")
    st, state = call(server, "GET", "/api/state")
    assert st == 200
    assert [c["name"] for c in state["courses"]] == ["אלגברה לינארית להנדסה"]  # קורס בלי מטלות לא מוצג
    (a,) = state["assignments"]
    assert a["title"] == "הגשה 0 - קבוצות ומרוכבים" and a["questions"] == 5 and a["pulledAt"]
    assert [s["name"] for s in a["subs"]] == ["הגשה 0001", "הגשה 0002", "הגשה 0003"]
    assert {s["id"]: s["status"] for s in a["subs"]}["0001"] == "graded"
    raw = json.dumps(state, ensure_ascii=False)
    assert not any(name in raw for name in NAMES.values())


def test_server_pull_and_file(root, server):
    asg(root).inbox.mkdir()
    (asg(root).inbox / "a.zip").write_bytes(make_zip({entry("2000"): homework_pdf(NAMES["2000"], HW)}))
    st, rep = call(server, "POST", "/api/pull", {"course": COURSE, "assignment": HW}, {"X-Assignment-Checker": "1"})
    assert st == 200 and rep["result"]["new"] == 1
    _, state = call(server, "GET", "/api/state")
    f = state["assignments"][0]["subs"][-1]["files"][0]
    st, data = call(server, "GET", f"/api/file?path={quote(f['path'])}")
    assert st == 200 and data[:4] == b"%PDF"
    st, index = call(server, "GET", "/")
    assert st == 200 and b"<html" in index


def test_server_refuses_foreign_requests(root, server):
    body = {"course": COURSE, "assignment": HW}
    assert call(server, "POST", "/api/pull", body)[0] == 403
    assert call(server, "POST", "/api/pull", body, {"X-Assignment-Checker": "1", "Origin": "https://evil.example"})[0] == 403
    assert call(server, "GET", "/api/state", headers={"Host": "evil.example"})[0] == 403
    assert call(server, "GET", "/api/file?path=../../Recordings")[0] == 404
    assert call(server, "GET", f"/api/file?path={quote(COURSE + '/' + HW + '/' + team.KEY)}")[0] == 404  # טבלת המפתח לא נשלחת לאתר
