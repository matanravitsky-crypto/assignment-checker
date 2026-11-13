"""הבדיקה (grading/) כפי שהאתר רואה אותה: המצב שהדשבורד בונה ממה שהבדיקה כתבה, וכפתורי הבדיקה בשרת.

הועבר מ-tests/grading/test_grade.py ב-2026-11-12: הבדיקות של grading לבד לא תלויות בדשבורד (tests/test_modularity.py),
ומה שבודק את שניהם יחד נמצא כאן. no_real_claude (autouse) מיובא, אז גם כאן אף בדיקה לא מדברת עם Claude באמת.
"""
from __future__ import annotations

import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import quote

import pymupdf
import pytest

from dashboard import actions
from grading import grade as grading
from moodle import paths
from tests.dashboard.helpers import hw
from tests.grading.test_grade import (COURSE, HW, NAMES, FakeClaude, _real_claude_ask, answer, asg, detailed,  # noqa: F401
                                      no_real_claude, root, save_details, text)


def test_state_reads_grades_and_marked_files(root):
    a = asg(root)
    grading.write_grades(a.dir, {"0001": {"number": "0001", "grade": "85", "feedback": "יפה", "points": "20;15;20;20;10",
                                          "approved": "כן", "review": ""},
                                 "0002": {"number": "0002", "grade": "72.5", "feedback": "", "review": "כתב יד לא קריא"}})
    (a.dir / paths.MARKED / "0001.pdf").write_bytes(b"%PDF")
    (a.dir / paths.MARKED / "0001-2.pdf").write_bytes(b"%PDF")
    (a.dir / paths.MARKED / "0003-2.pdf").write_bytes(b"%PDF")
    st = actions.state(root)
    A = hw(st)
    subs = {s["id"]: s for s in A["subs"]}
    assert subs["0001"]["status"] == "graded" and subs["0001"]["score"] == 85 and subs["0001"]["approved"] is True
    assert subs["0001"]["q"] == [20, 15, 20, 20, 10] and subs["0001"]["feedback"] == "יפה"
    assert [f["name"] for f in subs["0001"]["files"] if f.get("marked")] == ["0001.pdf", "0001-2.pdf"]
    assert subs["0002"]["status"] == "graded" and subs["0002"]["score"] == 72.5 and subs["0002"]["review"] == "כתב יד לא קריא"
    assert subs["0003"]["status"] == "graded" and subs["0003"]["score"] is None  # סומן ידנית, בלי שורה ב-Grades.csv
    assert [q["points"] for q in A["rubric"]] == [20] * 5 and A["maxGrade"] == 100
    assert st["claude"] is False
    assert not any(name in json.dumps(st, ensure_ascii=False) for name in NAMES.values())


@pytest.fixture
def server(root):
    from dashboard.web_server import Handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_port
    srv.shutdown()


def call(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    h = {"Host": f"localhost:{port}", "X-Assignment-Checker": "1"}
    data = json.dumps(body).encode() if body is not None else None
    if data:
        h["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=h)
    r = conn.getresponse()
    return r.status, json.loads(r.read())


def test_server_without_key_explains(root, server, monkeypatch):
    monkeypatch.setattr(grading, "claude_ask", _real_claude_ask)
    st, out = call(server, "POST", "/api/grade", {"course": COURSE, "assignment": HW})
    assert st == 400 and out["noKey"] and "ANTHROPIC_API_KEY" in out["error"]


def test_server_grades_in_the_background(root, server, monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr(grading, "claude_ask", lambda: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    st, job = call(server, "POST", "/api/grade", {"course": COURSE, "assignment": HW, "ids": ["0001", "0002"],
                                                  "model": "claude-sonnet-5-5", "parallel": 2, "instructions": "בקפדנות"})
    assert st == 202 and job["total"] == 2
    for _ in range(200):
        _, job = call(server, "GET", "/api/grade")
        if not job["running"]:
            break
        time.sleep(0.05)
    assert not job["running"] and job["summary"].startswith("נבדקו 2 מתוך 2") and set(job["done"]) == {"0001", "0002"}
    assert {r["model"] for r in fake.requests} == {"claude-sonnet-5-5"}
    assert "בקפדנות" in json.dumps(fake.requests[0], ensure_ascii=False)
    _, state = call(server, "GET", "/api/state")
    subs = {s["id"]: s for s in hw(state)["subs"]}
    assert subs["0001"]["status"] == "graded" and subs["0001"]["score"] == 85 and subs["0003"]["status"] == "pulled"
    assert state["claude"] is True and hw(state)["gradedAt"]

    st, out = call(server, "POST", "/api/grade", {"course": COURSE, "assignment": HW, "ids": ["../x"]})
    assert st == 400
    st, out = call(server, "POST", "/api/grade", {"course": COURSE, "assignment": "../../x"})
    assert st == 404


def test_grading_writes_notes_and_a_failure_reaches_the_review_queue(root):
    a = asg(root)
    calls = []

    def ask(req):
        calls.append(1)
        if len(calls) == 2:
            raise grading.GradingError("Claude עמוס כרגע")
        return detailed(review="שאלה 8 לא נמצאה", kind="missing", unsure=(4,))
    rep = grading.grade_assignment(a.dir, ask=ask, parallel=1)
    (bad,) = rep.failed
    good = rep.graded[0]
    note = grading.read_notes(a.dir, good)
    assert note["mistakes"][1] == ["חסר נימוק"] and note["unsure"][4] and note["review_kind"] == "missing"
    assert note["marks"][0]["text"] == "חסר נימוק" and note["points"] == [20, 15, 20, 20, 10]
    assert grading.read_notes(a.dir, bad)["error"] == "Claude עמוס כרגע"
    subs = {s["id"]: s for s in actions.state(root)["assignments"][0]["subs"]}
    assert subs[good]["reviewKind"] == "missing" and subs[good]["unsure"][4] and subs[good]["mistakes"][4] == ["תחום לא נכון"]
    assert subs[bad]["reviewKind"] == "failed" and subs[bad]["failed"] == "Claude עמוס כרגע" and subs[bad]["status"] == "pulled"
    # בדיקה חוזרת שהצליחה מוחקת את הכישלון
    grading.grade_assignment(a.dir, [bad], ask=lambda req: detailed())
    assert "error" not in grading.read_notes(a.dir, bad)


def test_save_review_approves_with_who_and_rewrites_the_summary_page(root):
    a = asg(root)
    grading.grade_assignment(a.dir, ["0001"], ask=lambda req: detailed(review="לא בטוח", kind="uncertain"))
    out = grading.save_review(a.dir, "1", [20, 14.7, 20, 20, 0], ["", "חסר נימוק.", "", "", "השאלה לא נמצאה"],
                              "עבודה טובה.", by="dana (PC)", mistakes=[[], ["חסר נימוק"], [], [], []])
    assert (out["number"], out["grade"], out["from"]) == ("0001", 75, "85")  # 14.7 → 14.5
    row = grading.read_grades(a.dir)["0001"]
    assert row["points"] == "20;14.5;20;20;0" and row["grade"] == "75" and row["feedback"] == "עבודה טובה."
    assert row["approved"].startswith("dana (PC) ") and row["review"] == "לא בטוח" and grading.is_approved(row)
    note = grading.read_notes(a.dir, "0001")
    assert note["reviewed"]["by"] == "dana (PC)" and note["mistakes"][4] == [] and note["marks"]  # הסימונים של Claude נשארים
    assert note["model"] and note["effort"] == "high" and note["via"] == ""  # ask מבחוץ: לא ידוע איך רץ
    with pymupdf.open(a.dir / paths.MARKED / "0001.pdf") as doc, pymupdf.open(a.submissions / "0001.pdf") as src:
        assert doc.page_count == src.page_count + 1 and "75 מתוך 100" in text(doc[0])
        assert "השאלה לא נמצאה" in text(doc[0]) and "נועה" not in text(doc[0])
    # מאושרת: הבדיקה האוטומטית לא דורסת אותה
    assert grading.grade_assignment(a.dir, ["0001"], ask=lambda req: detailed()).skipped == ["0001"]
    subs = {s["id"]: s for s in actions.state(root)["assignments"][0]["subs"]}
    assert subs["0001"]["approved"] and subs["0001"]["reviewedBy"] == "dana (PC)" and subs["0001"]["score"] == 75


def test_server_review_and_downloads(root, server):
    a = asg(root)
    st, out = call(server, "POST", "/api/review", {"course": COURSE, "assignment": HW, "number": "0003",
                                                     "points": [20, 20, 20, 20, 10], "comments": [], "feedback": "יפה"})
    assert st == 200 and (out["number"], out["grade"], out["from"]) == ("0003", 90, None)
    assert grading.read_grades(a.dir)["0003"]["approved"]
    for bad in ({"number": "../1", "points": [20] * 5}, {"number": "0003", "points": ["20"] * 5}, {"number": "0003", "points": [True] * 5}):
        st, _ = call(server, "POST", "/api/review", {"course": COURSE, "assignment": HW, **bad})
        assert st == 400
    st, out = call(server, "POST", "/api/review", {"course": COURSE, "assignment": HW, "number": "0003", "points": [1]})
    assert st == 422 and "5" in out["error"]

    def get(path, download=False):
        conn = http.client.HTTPConnection("127.0.0.1", server, timeout=30)
        conn.request("GET", "/api/file?path=" + quote(path) + ("&download=1" if download else ""), headers={"Host": f"localhost:{server}"})
        r = conn.getresponse()
        return r.status, r.getheader("Content-Disposition"), r.read()
    rel = f"{COURSE}/{HW}/"
    st, disp, data = get(rel + f"{paths.MARKED}/0003.pdf")
    assert st == 200 and disp is None and data[:4] == b"%PDF"
    st, disp, _ = get(rel + f"{paths.MARKED}/0003.pdf", download=True)
    assert st == 200 and disp == 'attachment; filename="0003 - graded.pdf"'
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False)
    (a.submissions / "0003-2.jpg").write_bytes(pix.tobytes("jpeg"))
    st, disp, _ = get(rel + f"{paths.TO_GRADE}/0003-2.jpg", download=True)
    assert st == 200 and disp == 'attachment; filename="0003-2 - submission.jpg"'
    (a.dir / paths.MARKED / "0003-2.jpg").write_bytes(pix.tobytes("jpeg"))
    # the review page shows the submission as images: every file of the number, in order, as Claude saw it
    q = f"course={quote(COURSE)}&assignment={quote(HW)}&number=0003"
    with pymupdf.open(a.submissions / "0003.pdf") as src:
        pages = src.page_count
    assert call(server, "GET", f"/api/pages?{q}") == (200, {"pages": pages + 1})
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=30)
    conn.request("GET", f"/api/page?{q}&page={pages + 1}", headers={"Host": f"localhost:{server}"})
    r = conn.getresponse()
    assert r.status == 200 and r.getheader("Content-Type") == "image/jpeg" and r.read()[:2] == b"\xff\xd8"
    for bad in (f"/api/page?{q}&page=99", f"/api/page?{q}&page=x", f"/api/page?course={quote(COURSE)}&assignment={quote(HW)}&number=../1&page=1"):
        conn = http.client.HTTPConnection("127.0.0.1", server, timeout=30)
        conn.request("GET", bad, headers={"Host": f"localhost:{server}"})
        assert conn.getresponse().status in (400, 404)
    for path in (paths.KEY, f"{paths.MARKED}/0003-2.jpg", f"{paths.NOTES}/0003.json"):
        assert get(rel + path)[0] == 404  # רק הגשות ועבודות מסומנות יוצאות. לא המפתח ולא שום דבר אחר


def test_state_shows_the_special_case_and_what_is_missing(root):
    """The grading writes "special" and "missing" to Grades.csv; the site's queue shows them."""
    a = asg(root)
    grading.write_grades(a.dir, {"0002": {"number": "0002", "grade": "80", "feedback": "", "points": "20;0;20;20;20",
                                          "review": "חסר שאלה 12. בדוק במודל אם הוגש בקובץ נפרד.",
                                          "special": "missing_question", "missing": "שאלה 12"},
                                 "0003": {"number": "0003", "grade": "90", "feedback": "", "review": "", "special": ""}})
    subs = {s["id"]: s for s in actions.state(root)["assignments"][0]["subs"]}
    assert (subs["0002"]["reviewKind"], subs["0002"]["missing"]) == ("missing_question", "שאלה 12")
    assert (subs["0003"]["reviewKind"], subs["0003"]["missing"]) == ("", "")


def test_without_a_rubric_there_are_no_grades(root, server):
    """בלי מחוון אין חלוקה שווה ואין שום חלוקה אחרת: לא בודקים, לא מאשרים, והאתר יודע למה."""
    a = asg(root)
    save_details(a, {**a.details(), "rubric": None})
    ctx = grading.load_context(a.dir)
    assert [q.points for q in ctx.questions] == [0] * 5 and "אין מחוון" in ctx.no_rubric
    fake = FakeClaude()
    with pytest.raises(grading.NoRubric):
        grading.grade_assignment(a.dir, ["0001"], ask=fake)
    assert not fake.requests and not (a.dir / grading.GRADES).exists()
    with pytest.raises(grading.NoRubric):
        grading.save_review(a.dir, "0001", [20] * 5, [], "", by="x")
    st, out = call(server, "POST", "/api/grade", {"course": COURSE, "assignment": HW})
    assert st == 422 and out["noRubric"] and "אך ורק לפי המחוון" in out["error"]
    A = hw(actions.state(root))
    assert "אין מחוון" in A["noRubric"] and [q["points"] for q in A["rubric"]] == [0] * 5


def test_a_usage_limit_stops_grading_and_fails_no_work(root):
    a = asg(root)
    calls = []

    def ask(req):
        calls.append(1)
        if len(calls) >= 2:
            raise grading.GradingError("Claude Code נכשל: You've hit your session limit · resets 2:50am")
        return detailed()
    with pytest.raises(grading.ClaudeLimit) as e:
        grading.grade_assignment(a.dir, ask=ask, parallel=1)
    assert "מגבלת השימוש" in str(e.value)
    graded = grading.read_grades(a.dir)
    assert len(graded) == 1
    assert not [n for n in ("0001", "0002", "0003") if "error" in grading.read_notes(a.dir, n)]
    # שגיאת מכסה ישנה ב-Grading notes (מריצה אחרת) לא שולחת את העבודה לבדיקה הידנית
    left = next(n for n in ("0001", "0002", "0003") if n not in graded)
    grading.write_notes(a.dir, left, {"error": "Claude Code נכשל: You've hit your session limit", "failed_at": "x"})
    subs = {s["id"]: s for s in hw(actions.state(root))["subs"]}
    assert subs[left]["failed"] == "" and subs[left]["reviewKind"] == ""


def test_server_stops_a_running_grading(root, server, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def ask(req):
        started.set()
        release.wait(10)
        return answer()
    monkeypatch.setattr(grading, "claude_ask", lambda: ask)
    st, job = call(server, "POST", "/api/grade", {"course": COURSE, "assignment": HW, "parallel": 1})
    assert st == 202 and started.wait(10)
    st, job = call(server, "POST", "/api/grade/stop", {})
    assert st == 200 and job["stopping"] and job["running"]
    release.set()
    for _ in range(200):
        _, job = call(server, "GET", "/api/grade")
        if not job["running"]:
            break
        time.sleep(0.05)
    assert not job["running"] and len(job["report"]["graded"]) == 1 and len(job["report"]["stopped"]) == 2
    _, again = call(server, "POST", "/api/grade/stop", {})
    assert again["stopping"] is False or again["running"] is False  # nothing running: stopping does nothing
