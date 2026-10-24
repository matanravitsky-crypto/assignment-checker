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
    assert headers.get("Access-Control-Allow-Methods") == "GET"


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
