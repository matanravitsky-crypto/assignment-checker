"""הסנכרון לוואן דרייב (dashboard/sync.py ו-/api/sync/ ב-web_server): מה השרת המקומי נותן לסקריפט בלשונית של הוואן דרייב."""
from __future__ import annotations

import http.client
import json

import pytest

from dashboard import sync
from moodle import paths

from tests.dashboard.helpers import COURSE, HW

SHAREPOINT = "https://bgu365-my.sharepoint.com"


@pytest.fixture
def data(root, monkeypatch):
    """תיקיית הנתונים שממנה מעלים: אותה תיקייה כמו של האתר בבדיקות, עם מנעול וקובץ זמני שלא עולים."""
    monkeypatch.setenv("ASSIGNMENT_DATA", str(root))
    a = root / COURSE / HW
    (a / paths.PULL_LOCK).write_text("noa (PC) pid=1", encoding="utf-8")
    (a / "Grades.csv.tmp").write_text("half written", encoding="utf-8")
    (root.parent / "outside.txt").write_text("not in the data folder", encoding="utf-8")
    return root


def get(port, path, origin=None, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request(method, path, headers={"Host": f"localhost:{port}", **({"Origin": origin} if origin else {})})
    r = conn.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_lists_every_course_file_but_locks_and_temp_files(data):
    assert COURSE in sync.courses()
    files = {f["path"]: f for f in sync.list_files(COURSE)}
    assert f"{HW}/{paths.TO_GRADE}/0001.pdf" in files and f"{HW}/{paths.KEY}" in files
    assert not any(p.endswith((paths.PULL_LOCK, ".tmp")) for p in files)
    # ZIP לעולם לא עולה: ה-ZIP של מודל שבתיקיית המטלה (conftest) ו-ZIP להחזרה למודל
    (data / COURSE / HW / paths.UPLOAD / "Graded - part 01.zip").write_bytes(b"PK")
    files = {f["path"] for f in sync.list_files(COURSE)}
    assert not any(p.lower().endswith(".zip") for p in files)
    with pytest.raises(FileNotFoundError):
        sync.read_file(COURSE, f"{HW}/{paths.UPLOAD}/Graded - part 01.zip")
    files = {f["path"]: f for f in sync.list_files(COURSE)}
    f = files[f"{HW}/{paths.TO_GRADE}/0001.pdf"]
    assert f["size"] == (data / COURSE / f["path"]).stat().st_size and f["mtime"] > 1_600_000_000_000


def test_only_files_inside_a_course_folder_are_read(data):
    assert sync.read_file(COURSE, f"{HW}/{paths.TO_GRADE}/0001.pdf").startswith(b"%PDF")
    for course, rel in ((COURSE, "../outside.txt"), (COURSE, "../../outside.txt"), ("..", "outside.txt"),
                        (COURSE, f"{HW}/{paths.PULL_LOCK}"), ("No such course", "x")):
        with pytest.raises(FileNotFoundError):
            sync.read_file(course, rel)


def test_server_gives_the_lists_and_files_to_the_lecturers_onedrive_only(data, server):
    status, headers, body = get(server, "/api/sync/courses", SHAREPOINT)
    assert status == 200 and headers.get("Access-Control-Allow-Origin") == SHAREPOINT and COURSE in json.loads(body)["courses"]
    status, headers, body = get(server, "/api/sync/script.js", SHAREPOINT)
    assert status == 200 and b"__ecsSyncAll" in body and headers.get("Access-Control-Allow-Origin") == SHAREPOINT
    status, headers, body = get(server, f"/api/sync/list?course={COURSE.replace(' ', '%20')}", SHAREPOINT)
    assert status == 200 and len(json.loads(body)["files"]) > 3
    path = f"{HW}/{paths.TO_GRADE}/0001.pdf".replace(" ", "%20")
    status, headers, body = get(server, f"/api/sync/file?course={COURSE.replace(' ', '%20')}&path={path}", SHAREPOINT)
    assert status == 200 and body.startswith(b"%PDF")
    # Chrome שואל לפני שאתר פונה לשרת במחשב (preflight): רק הוואן דרייב, ורק לקריאה
    status, headers, _ = get(server, "/api/sync/list", SHAREPOINT, method="OPTIONS")
    assert status == 204 and headers.get("Access-Control-Allow-Private-Network") == "true"
    assert headers.get("Access-Control-Allow-Methods") == "GET, POST"  # POST: put/state, הכיוון השני


def test_other_sites_and_other_addresses_get_no_access(data, server):
    # אתר אחר: השרת עונה (הוא במחשב), אבל בלי CORS הדפדפן לא נותן לאתר לקרוא את התשובה
    status, headers, _ = get(server, "/api/sync/courses", "https://evil.example")
    assert "Access-Control-Allow-Origin" not in headers
    status, _, _ = get(server, "/api/sync/list", "https://evil.example", method="OPTIONS")
    assert status == 403
    # הוואן דרייב לא מקבל CORS לשאר השרת (מצב, ציונים, פעולות)
    status, headers, _ = get(server, "/api/state", SHAREPOINT)
    assert "Access-Control-Allow-Origin" not in headers
    status, _, _ = get(server, "/api/state", SHAREPOINT, method="OPTIONS")
    assert status == 403
    status, _, _ = get(server, "/api/sync/file?course=Linear%20Algebra&path=../outside.txt", SHAREPOINT)
    assert status == 404


def test_top_level_files_sync_without_the_courses(data):
    """הקבצים שבתיקייה הראשית (README, "Pull only on this computer.txt") עולים בלי לעבור על הקורסים."""
    (data / "Pull only on this computer.txt").write_text("ori34 (OriLaptop)", encoding="utf-8")
    top = {f["path"] for f in sync.list_files("")}
    assert "Pull only on this computer.txt" in top and not any("/" in p for p in top) and COURSE not in top
    assert sync.read_file("", "Pull only on this computer.txt") == b"ori34 (OriLaptop)"
    for rel in (f"{COURSE}/{HW}/{paths.KEY}", "../outside.txt"):
        with pytest.raises(FileNotFoundError):
            sync.read_file("", rel)


# ---------- הכיוון השני: מהוואן דרייב למחשב (2026-11-20, בשביל Mac) ----------
@pytest.fixture
def local_copy(tmp_path, monkeypatch):
    """תיקיית נתונים מקומית, כמו ב-Mac שלא יכול לסנכרן באפליקציית OneDrive: עוד לא קיימת."""
    folder = tmp_path / "home" / paths.DATA_FOLDER
    monkeypatch.setenv("ASSIGNMENT_DATA", str(folder))
    monkeypatch.setenv("ASSIGNMENT_WORK", str(tmp_path / "home" / paths.WORK_FOLDER))
    return folder


T = 1_793_740_000_000


def test_a_file_from_onedrive_is_written_with_its_onedrive_time(local_copy):
    rel = f"{HW}/{paths.TO_GRADE}/0001.pdf"
    out = sync.write_file(COURSE, rel, b"%PDF-1", T, "none")
    target = local_copy / COURSE / rel
    assert target.read_bytes() == b"%PDF-1" and out == {"path": rel, "size": 6, "mtime": T}
    assert abs(target.stat().st_mtime * 1000 - T) < 1000
    assert {f["path"] for f in sync.list_files(COURSE)} == {rel}
    # a newer version replaces it only when the computer still has what the script saw
    assert sync.write_file(COURSE, rel, b"%PDF-22", T + 5000, f"6:{T}")["size"] == 7
    assert sync.write_file("", "README.txt", b"hi", T, "none")["size"] == 2


def test_a_file_that_changed_here_since_the_comparison_is_never_overwritten(local_copy):
    rel = f"{HW}/Grades by נועה.csv"
    sync.write_file(COURSE, rel, b"number,grade\n", T, "none")
    (local_copy / COURSE / rel).write_bytes(b"number,grade\n0001,90\n")  # graded here meanwhile
    for expect in (f"13:{T}", "none"):
        with pytest.raises(sync.Refused):
            sync.write_file(COURSE, rel, b"from onedrive", T + 9000, expect)
    assert (local_copy / COURSE / rel).read_bytes() == b"number,grade\n0001,90\n"
    with pytest.raises(sync.Refused):  # deleted here since the comparison: not written back
        sync.write_file(COURSE, f"{HW}/gone.csv", b"x", T, "5:1")


def test_only_plain_paths_inside_a_course_folder(local_copy):
    for course, rel in ((COURSE, "../x.txt"), ("..", "x.txt"), (COURSE, f"{HW}/../../x.txt"), (".claude", "settings.json"),
                        (COURSE, ".claude/settings.json"), (COURSE, f"{HW}/.git/config"), ("", "Linear Algebra/x.txt"),
                        (COURSE, f"{HW}/Pull in progress.txt"), (COURSE, f"{HW}/Moodle download.zip"),
                        (COURSE, "C:/x.txt"), (COURSE, "a\\b.txt"), (COURSE, "a\nb.txt"), ("a/b", "x.txt"), (COURSE, "")):
        with pytest.raises(sync.Refused):
            sync.write_file(course, rel, b"x", T, "none")
    assert not (local_copy.parent / "x.txt").exists()


def test_nothing_comes_down_while_this_computer_pulls_or_grades_the_assignment(local_copy):
    a = local_copy / COURSE / HW
    a.mkdir(parents=True)
    (a / "Grading part 2 in progress.txt").write_text("noa", encoding="utf-8")
    with pytest.raises(sync.Refused, match="Grading part 2"):
        sync.write_file(COURSE, f"{HW}/{paths.KEY}", b"number\n", T, "none")
    assert sync.write_file(COURSE, f"Assignment 1/{paths.KEY}", b"number\n", T, "none")["size"] == 7


def test_a_folder_onedrive_syncs_itself_takes_nothing_from_the_browser(data):
    assert sync.writable() is not None
    with pytest.raises(sync.Refused, match="OneDrive"):
        sync.write_file(COURSE, f"{HW}/new.pdf", b"x", T, "none")


def test_the_sync_state_is_kept_on_this_computer_only(local_copy):
    assert sync.read_state(COURSE) == {}
    assert sync.record_state(COURSE, {"a.pdf": {"local": [1, T], "remote": [1, T + 1]}, "bad": {"local": "x"}}) == 1
    assert sync.record_state(COURSE, {"b.pdf": {"local": [2, T], "remote": [2, T]}}) == 1
    assert set(sync.read_state(COURSE)) == {"a.pdf", "b.pdf"}
    state = local_copy.parent / paths.WORK_FOLDER / sync.STATE_FOLDER
    assert state.is_dir() and not local_copy.exists()  # never inside the data folder that goes to OneDrive


def post(port, path, body: bytes, origin=SHAREPOINT, header=True):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    headers = {"Host": f"localhost:{port}", "Origin": origin, "Content-Type": "application/octet-stream"}
    if header:
        headers["X-Assignment-Checker"] = "1"
    conn.request("POST", path, body=body, headers=headers)
    r = conn.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_the_onedrive_tab_writes_through_the_server(server, local_copy):
    from urllib.parse import quote
    rel = f"{HW}/{paths.TO_GRADE}/0002.pdf"
    url = f"/api/sync/put?course={quote(COURSE)}&path={quote(rel)}&mtime={T}&expect=none"
    status, headers, body = post(server, url, b"%PDF-2")
    assert status == 200 and json.loads(body)["size"] == 6 and headers.get("Access-Control-Allow-Origin") == SHAREPOINT
    assert (local_copy / COURSE / rel).read_bytes() == b"%PDF-2"
    status, _, body = post(server, url, b"%PDF-3")  # "none", but it exists now
    assert status == 409 and "השתנה" in json.loads(body)["error"]
    status, _, body = post(server, f"/api/sync/state?course={quote(COURSE)}",
                           json.dumps({rel: {"local": [6, T], "remote": [6, T]}}).encode())
    assert status == 200 and json.loads(body)["recorded"] == 1
    status, _, body = get(server, f"/api/sync/list?course={quote(COURSE)}", SHAREPOINT)
    listed = json.loads(body)
    assert listed["writable"] is True and rel in listed["state"] and [f["path"] for f in listed["files"]] == [rel]
    # another site, or the OneDrive tab without our header: nothing is written
    for origin, header in (("https://evil.example", True), (SHAREPOINT, False)):
        status, _, _ = post(server, url.replace("0002", "0003"), b"x", origin, header)
        assert status == 403
    assert not (local_copy / COURSE / HW / paths.TO_GRADE / "0003.pdf").exists()


def test_a_mac_with_no_data_folder_yet_lists_nothing(server, local_copy):
    status, _, body = get(server, "/api/sync/courses", SHAREPOINT)
    assert status == 200 and json.loads(body)["courses"] == []
    status, _, body = get(server, "/api/sync/list?course=Linear%20Algebra", SHAREPOINT)
    assert status == 200 and json.loads(body)["files"] == []
