"""הכיוון וואן דרייב → מחשב של הסנכרון (dashboard/sync.py: put_file, remove_file, snapshot, הסנכרון החי) ו-POST /api/sync/.

onedrive/sync.js בלשונית של הוואן דרייב מוריד לכאן מה שחדש בענן, מעביר ל-"Removed from OneDrive" מה שנעלם משם,
שומר מה ראה, ומדווח שהוא חי. כאן: רק לתוך תיקיית קורס, לא מנעולים, לא Key history, לא דורסים קובץ שהשתנה במחשב,
ולא כותבים במטלה שבדיקה רצה בה."""
from __future__ import annotations

import http.client
import json
import os
import time

import pytest

from dashboard import actions, sync
from moodle import paths

from tests.dashboard.helpers import COURSE, HW
from tests.dashboard.test_sync import SHAREPOINT, data, get  # noqa: F401  (data: the fixture)

CLOUD_MS = 1_793_000_000_000


def post(port, path, body, origin=SHAREPOINT, raw=False, header=True):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    h = {"Host": f"localhost:{port}", **({"Origin": origin} if origin else {}), **({"X-Assignment-Checker": "1"} if header else {})}
    payload = body if raw else json.dumps(body).encode()
    h["Content-Type"] = "application/octet-stream" if raw else "application/json"
    conn.request("POST", path, body=payload, headers=h)
    r = conn.getresponse()
    out = r.read()
    return r.status, dict(r.getheaders()), (json.loads(out) if r.getheader("Content-Type", "").startswith("application/json") else out)


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """מה הסקריפט ראה בסנכרון הקודם: מחוץ לתיקיית הנתונים, ובבדיקה בתיקייה זמנית."""
    monkeypatch.setenv("ASSIGNMENT_SYNC_STATE", str(tmp_path / "sync-state"))
    sync.reset_live()
    yield tmp_path / "sync-state"
    sync.reset_live()


@pytest.fixture
def cloud(data):
    """תיקיית הנתונים של test_sync, עם המנעול שבה ישן (תקוע): מנעול טרי היה חוסם כל כתיבה במטלה."""
    old = time.time() - 31 * 60
    os.utime(data / COURSE / HW / paths.PULL_LOCK, (old, old))
    return data


def test_put_writes_the_cloud_version_with_its_time_and_only_inside_a_course(cloud, state_dir):
    rel = f"{HW}/{paths.NOTES}/0005.json"
    r = sync.put_file(COURSE, rel, b'{"q": 1}', CLOUD_MS, None)
    f = cloud / COURSE / rel
    assert f.read_bytes() == b'{"q": 1}' and abs(f.stat().st_mtime * 1000 - CLOUD_MS) < 1000 and r["size"] == 8
    # מחוץ לקורס, מנעול, זמני, Key history, Removed from OneDrive, ZIP, תיקייה בתוך הראשית, תיקייה: לא נכתבים
    for course, bad in ((COURSE, "../outside.txt"), (COURSE, f"{HW}/../../x.txt"), ("..", "x.txt"), ("No such course", "x"),
                        (COURSE, f"{HW}/{paths.PULL_LOCK}"), (COURSE, f"{HW}/Grades.csv.tmp"),
                        (COURSE, f"{HW}/{paths.KEY_HISTORY}/old.csv"), (COURSE, f"{HW}/{sync.REMOVED}/2026-11-11 10-00-00/a.txt"),
                        (COURSE, f"{HW}/{paths.UPLOAD}/Graded - part 01.zip"), ("", f"{COURSE}/x.txt"), (COURSE, ""), (COURSE, HW)):
        with pytest.raises(FileNotFoundError):
            sync.put_file(course, bad, b"x", CLOUD_MS, None)
    assert (cloud.parent / "outside.txt").read_text(encoding="utf-8") == "not in the data folder"
    assert (cloud / COURSE / HW / paths.PULL_LOCK).read_text(encoding="utf-8") == "noa (PC) pid=1"
    # קובץ בתיקייה הראשית: כן
    sync.put_file("", "Protocol.txt", b"p", CLOUD_MS, None)
    assert (cloud / "Protocol.txt").read_bytes() == b"p"


def test_put_does_not_overwrite_a_file_that_changed_on_this_computer(cloud, state_dir):
    rel = f"{HW}/Grades by נועה.csv"
    f = cloud / COURSE / rel
    f.write_text("number,grade\n0001,90\n", encoding="utf-8")
    seen = int(f.stat().st_mtime * 1000)
    # הסקריפט ראה את הקובץ בזמן seen: אפשר לדרוס
    sync.put_file(COURSE, rel, b"number,grade\n0001,95\n", CLOUD_MS, seen)
    assert f.read_bytes() == b"number,grade\n0001,95\n"
    # הקובץ השתנה כאן בינתיים (זמן אחר ממה שהסקריפט ראה), או שהסקריפט חשב שאין קובץ: לא נדרס
    with pytest.raises(sync.Conflict):
        sync.put_file(COURSE, rel, b"other", CLOUD_MS, seen)
    with pytest.raises(sync.Conflict):
        sync.put_file(COURSE, rel, b"other", CLOUD_MS, None)
    assert f.read_bytes() == b"number,grade\n0001,95\n"


def test_an_assignment_with_a_fresh_lock_is_not_written(cloud, state_dir):
    a = cloud / COURSE / HW
    (a / "Grading part 2 in progress.txt").write_text("ori (PC) pid=7", encoding="utf-8")
    assert sync.busy_assignments(COURSE) == [HW]
    with pytest.raises(sync.Busy):
        sync.put_file(COURSE, f"{HW}/{paths.NOTES}/0001.json", b"{}", CLOUD_MS, None)
    with pytest.raises(sync.Busy):
        sync.remove_file(COURSE, f"{HW}/{paths.KEY}", int((a / paths.KEY).stat().st_mtime * 1000))
    assert (a / paths.KEY).is_file() and not (a / paths.NOTES / "0001.json").exists()
    # מנעול ישן (תקוע) לא חוסם
    old = time.time() - 31 * 60
    os.utime(a / "Grading part 2 in progress.txt", (old, old))
    assert sync.busy_assignments(COURSE) == []
    sync.put_file(COURSE, f"{HW}/{paths.NOTES}/0001.json", b"{}", CLOUD_MS, None)
    assert (a / paths.NOTES / "0001.json").is_file()


def test_a_file_gone_from_onedrive_moves_to_removed_from_onedrive_in_the_assignment(cloud, state_dir):
    a = cloud / COURSE / HW
    marked = a / paths.MARKED / "0001.pdf"
    marked.write_bytes(b"%PDF marked")
    seen = int(marked.stat().st_mtime * 1000)
    r = sync.remove_file(COURSE, f"{HW}/{paths.MARKED}/0001.pdf", seen, "2026-11-11 10-00-00")
    # (sync._long: הנתיב בבדיקה עובר את 260 התווים של Windows; בתיקיית הנתונים האמיתית הוא קצר בהרבה)
    dest = sync._long(a / sync.REMOVED / "2026-11-11 10-00-00" / paths.MARKED / "0001.pdf")
    assert not marked.exists() and dest.read_bytes() == b"%PDF marked"
    assert r["moved_to"] == f"{HW}/{sync.REMOVED}/2026-11-11 10-00-00/{paths.MARKED}/0001.pdf"
    # אותו שם שוב באותו סיבוב: לא דורס את מה שכבר בארכיון
    marked.write_bytes(b"%PDF again")
    sync.remove_file(COURSE, f"{HW}/{paths.MARKED}/0001.pdf", int(marked.stat().st_mtime * 1000), "2026-11-11 10-00-00")
    assert dest.read_bytes() == b"%PDF marked" and (dest.parent / "0001 (2).pdf").read_bytes() == b"%PDF again"
    # הארכיון לא עולה לוואן דרייב ולא יורד ממנו
    assert not any(sync.REMOVED in f["path"] for f in sync.list_files(COURSE))
    # קובץ שהשתנה במחשב מאז ההשוואה: נשאר
    marked.write_bytes(b"%PDF newer")
    with pytest.raises(sync.Conflict):
        sync.remove_file(COURSE, f"{HW}/{paths.MARKED}/0001.pdf", seen - 10 * 60 * 1000)
    assert marked.exists()
    # קובץ בתיקיית הקורס (לא בתוך מטלה): הארכיון של הקורס. stamp לא תקין: התאריך של עכשיו
    who = cloud / COURSE / paths.TASKS / "נועה.json"
    who.parent.mkdir()
    who.write_text("{}", encoding="utf-8")
    r = sync.remove_file(COURSE, f"{paths.TASKS}/נועה.json", int(who.stat().st_mtime * 1000), "../evil")
    moved = cloud / COURSE / r["moved_to"]
    assert moved.parent.parent.parent == cloud / COURSE / sync.REMOVED and moved.name == "נועה.json" and not who.exists()
    assert sync.STAMP.match(moved.parent.parent.name)
    # מנעול, Key history ומחוץ לקורס לא זזים
    (a / paths.KEY_HISTORY).mkdir()
    (a / paths.KEY_HISTORY / "k.csv").write_text("number\n", encoding="utf-8")
    for rel in (f"{HW}/{paths.PULL_LOCK}", f"{HW}/{paths.KEY_HISTORY}/k.csv", "../outside.txt"):
        with pytest.raises(FileNotFoundError):
            sync.remove_file(COURSE, rel, None)
    assert (a / paths.PULL_LOCK).is_file() and (a / paths.KEY_HISTORY / "k.csv").is_file() and (cloud.parent / "outside.txt").is_file()


def test_snapshot_is_kept_outside_the_data_folder_and_live_status_expires(cloud, state_dir, monkeypatch):
    assert sync.read_snapshot(COURSE) == {}
    sync.write_snapshot(COURSE, {f"{HW}/{paths.KEY}": {"l": 1, "ls": 2, "r": 3, "rs": 2}})
    assert sync.read_snapshot(COURSE)[f"{HW}/{paths.KEY}"]["r"] == 3
    assert (state_dir / f"{COURSE}.json").is_file() and not list(cloud.rglob(f"{COURSE}.json"))
    with pytest.raises(FileNotFoundError):
        sync.write_snapshot("No such course", {})
    with pytest.raises(ValueError):
        sync.write_snapshot(COURSE, ["not", "an", "object"])
    assert sync.live_status() == {"alive": False, "agoS": None, "report": None}
    sync.set_live({"running": True, "syncedAt": "2026-11-11T10:00:00", "conflicts": [f"{COURSE}/{HW}/Grades.csv"],
                   "summary": {"uploaded": 2}, "secret": "dropped", "failed": "not a list"})
    st = sync.live_status()
    assert st["alive"] and st["agoS"] == 0 and st["report"]["conflicts"] == [f"{COURSE}/{HW}/Grades.csv"]
    assert "secret" not in st["report"] and st["report"]["failed"] == [] and st["report"]["summary"] == {"uploaded": 2}
    # הלשונית נסגרה: בלי דיווח חדש הסנכרון החי לא רץ
    with sync._live_lock:
        sync._live["received"] -= sync.ALIVE_SECONDS + 1
    assert not sync.live_status()["alive"] and sync.live_status()["report"]["running"] is True


def test_server_takes_the_cloud_files_from_the_lecturers_onedrive_only(cloud, state_dir, server):
    course, rel = COURSE.replace(" ", "%20"), f"{HW}/{paths.NOTES}/0007.json".replace(" ", "%20")
    status, headers, body = post(server, f"/api/sync/put?course={course}&path={rel}&mtime={CLOUD_MS}", b'{"n": 7}', raw=True)
    assert status == 200 and body["size"] == 8 and headers.get("Access-Control-Allow-Origin") == SHAREPOINT
    assert (cloud / COURSE / HW / paths.NOTES / "0007.json").read_bytes() == b'{"n": 7}'
    # Chrome שואל לפני (preflight): גם POST, רק לוואן דרייב
    status, headers, _ = get(server, "/api/sync/put", SHAREPOINT, method="OPTIONS")
    assert status == 204 and "POST" in headers.get("Access-Control-Allow-Methods", "")
    # בלי הכותרת המיוחדת, מאתר אחר, או לכתובת אחרת של השרת: לא
    assert post(server, f"/api/sync/put?course={course}&path={rel}&mtime=1", b"x", raw=True, header=False)[0] == 403
    assert post(server, f"/api/sync/put?course={course}&path={rel}&mtime=1", b"x", origin="https://evil.example", raw=True)[0] == 403
    assert post(server, "/api/refresh", {})[0] == 403
    assert (cloud / COURSE / HW / paths.NOTES / "0007.json").read_bytes() == b'{"n": 7}'
    # מחוץ לקורס: 404. בלי mtime: 400. הקובץ כבר קיים והסקריפט לא ידע: 409. מנעול טרי: 423
    assert post(server, f"/api/sync/put?course={course}&path=../x.txt&mtime=1", b"x", raw=True)[0] == 404
    assert post(server, f"/api/sync/put?course={course}&path={rel}", b"x", raw=True)[0] == 400
    status, _, body = post(server, f"/api/sync/put?course={course}&path={rel}&mtime={CLOUD_MS}", b"x", raw=True)
    assert status == 409 and body["conflict"]
    (cloud / COURSE / HW / paths.UPLOAD_LOCK).write_text("noa (PC) pid=1", encoding="utf-8")
    status, _, body = post(server, f"/api/sync/put?course={course}&path={rel}&mtime={CLOUD_MS}&expect={CLOUD_MS}", b"x", raw=True)
    assert status == 423 and body["busy"]
    (cloud / COURSE / HW / paths.UPLOAD_LOCK).unlink()
    assert (cloud / COURSE / HW / paths.NOTES / "0007.json").read_bytes() == b'{"n": 7}'
    # remove, snapshot, status
    seen = int((cloud / COURSE / HW / paths.NOTES / "0007.json").stat().st_mtime * 1000)
    status, _, body = post(server, "/api/sync/remove", {"course": COURSE, "path": f"{HW}/{paths.NOTES}/0007.json", "expect": seen, "stamp": "2026-11-11 10-00-00"})
    assert status == 200 and body["moved_to"].startswith(f"{HW}/{sync.REMOVED}/2026-11-11 10-00-00/")
    assert post(server, "/api/sync/remove", {"course": COURSE, "path": f"{HW}/{paths.PULL_LOCK}", "expect": None})[0] == 404
    assert post(server, f"/api/sync/snapshot?course={course}", {"course": COURSE, "snapshot": {"a": {"l": 1}}})[0] == 200
    assert json.loads(get(server, f"/api/sync/snapshot?course={course}", SHAREPOINT)[2]) == {"course": COURSE, "snapshot": {"a": {"l": 1}}}
    assert post(server, f"/api/sync/snapshot?course={course}", {"course": COURSE, "snapshot": "no"})[0] == 400
    status, _, body = post(server, "/api/sync/status", {"running": True, "syncedAt": "2026-11-11T10:00:00", "summary": {"downloaded": 1}})
    assert status == 200 and body["alive"]
    # האתר רואה את זה בבריאות ובחתימת השינויים, ואת המטלות העסוקות ברשימה
    status, _, body = get(server, "/api/health")
    assert json.loads(body)["liveSync"]["report"]["summary"] == {"downloaded": 1}
    status, _, body = get(server, "/api/changes")
    assert json.loads(body)["liveSync"]["alive"] is True
    (cloud / COURSE / HW / paths.PULL_LOCK).write_text("noa (PC) pid=1", encoding="utf-8")
    status, _, body = get(server, f"/api/sync/list?course={course}", SHAREPOINT)
    assert json.loads(body)["busy"] == [HW]
    # הבדיקה של המחשב הזה רצה במטלה (בלי קובץ מנעול): גם אז לא נוגעים בה
    old = time.time() - 31 * 60
    os.utime(cloud / COURSE / HW / paths.PULL_LOCK, (old, old))
    assert json.loads(get(server, f"/api/sync/list?course={course}", SHAREPOINT)[2])["busy"] == []
    actions._job = actions.GradeJob(COURSE, HW, ["0001"], running=True)
    assert json.loads(get(server, f"/api/sync/list?course={course}", SHAREPOINT)[2])["busy"] == [HW]
    status, _, body = post(server, f"/api/sync/put?course={course}&path={rel}&mtime={CLOUD_MS}", b"x", raw=True)
    assert status == 423 and body["busy"]
    assert post(server, "/api/sync/remove", {"course": COURSE, "path": f"{HW}/{paths.KEY}", "expect": None})[0] == 423
    assert (cloud / COURSE / HW / paths.KEY).is_file() and not (cloud / COURSE / HW / paths.NOTES / "0007.json").exists()
