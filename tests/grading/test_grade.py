"""בדיקות לשלב הבדיקה (grade.py), עם Claude מדומה בלבד. מריצים: python -m pytest

הכל קורה בתיקייה זמנית (tmp_path). התיקייה האמיתית ב-OneDrive לא נקראת ולא משתנה.
"""
from __future__ import annotations

import csv
import http.client
import json
import random
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import quote

import pymupdf
import pytest

from moodle import claude_driver, paths
from dashboard import actions, folder_view
from grading import grade as grading
from tests.sample_files import homework_pdf

COURSE, HW = "Linear Algebra", "Assignment 0 - Sets and Complex Numbers"
NAMES = {"1001": "נועה כהן", "1002": "איתי לוי", "1003": "מאיה מזרחי"}
LABELS = ["דף קבוצות 11", "דף קבוצות 12", "דף מספרים מרוכבים 6", "דף מספרים מרוכבים 7", "דף מספרים מרוכבים 8"]
_real_claude_ask = grading.claude_ask


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    """אף בדיקה לא מדברת עם Claude באמת. בדיקה שצריכה את Claude מקבלת גרסה מדומה."""
    def refuse():
        raise AssertionError("בבדיקות משתמשים רק ב-Claude מדומה")
    monkeypatch.setattr(grading, "claude_ask", refuse)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # וגם לא Claude Code שמחובר במחשב הזה
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": False, "message": "fake"})


@pytest.fixture
def root(tmp_path, monkeypatch):
    """עותק מוקטן של Exercise Checking System עם שלוש הגשות ממוספרות, כמו ש-moodle ingest משאיר."""
    course_folder = tmp_path / "נדב מאיר - YallaLinearit"
    r = course_folder / "Exercise Checking System"
    a = folder_view.Assignment(r / COURSE / HW)
    for sub in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD):
        (a.dir / sub).mkdir(parents=True)
    save_details(a, {"id": "3438636", "course": COURSE, "course_id": "67024", "name": HW,
                     "questions": [{"sheet": "דף קבוצות", "numbers": [11, 12]}, {"sheet": "דף מספרים מרוכבים", "numbers": [6, 7, 8]}],
                     "submission_rules": ["כתב יד, קובץ PDF אחד"], "max_grade": None, "rubric": None,
                     "title": "הגשה 0 - קבוצות ומרוכבים", "course_title": "אלגברה לינארית להנדסה"})
    rows = []
    for i, pid in enumerate(NAMES, start=1):
        n = f"{i:04d}"
        (a.submissions / f"{n}.pdf").write_bytes(homework_pdf(NAMES[pid], HW))
        rows.append({"number": n, "anon_file": f"{n}.pdf", "participant_id": pid,
                     "original_folder": f"{NAMES[pid]}_{pid}_assignsubmission_file", "original_file": "hw.pdf"})
    with (a.dir / paths.KEY).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["number", "anon_file", "participant_id", "original_folder", "original_file"])
        w.writeheader()
        w.writerows(rows)
    monkeypatch.setenv("ASSIGNMENT_CHECKER_ROOT", str(course_folder))
    return r


def asg(root) -> folder_view.Assignment:
    return folder_view.Assignment(root / COURSE / HW)


def save_details(a: folder_view.Assignment, d: dict) -> None:
    (a.dir / paths.INFO).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def answer(points=(20, 15, 20, 20, 10), feedback="עבודה טובה. בשאלה 12 חסר נימוק.", marks=None, review=""):
    return json.dumps({
        "questions": [{"label": l, "points": p, "comment": "חסר נימוק" if p < 20 else "נכון"} for l, p in zip(LABELS, points)],
        "feedback": feedback,
        "annotations": marks if marks is not None else [{"page": 1, "x0": 100, "y0": 100, "x1": 900, "y1": 160, "text": "חסר נימוק"}],
        "needs_review": bool(review), "review_reason": review,
    }, ensure_ascii=False)


class FakeClaude:
    """במקום Claude: שומר כל בקשה ומחזיר תשובה קבועה (או לפי מספר העמודים)."""
    def __init__(self, reply=None):
        self.requests: list[dict] = []
        self.reply = reply or (lambda req: answer())
        self.lock = threading.Lock()

    def __call__(self, req: dict) -> str:
        with self.lock:
            self.requests.append(req)
        return self.reply(req)


def text(page) -> str:
    """הטקסט בעמוד, עם רווחים רגילים בשורה אחת (PyMuPDF מחזיר רווחים קשיחים ושבירות שורה)."""
    return " ".join(page.get_text().replace("\xa0", " ").split())


def read_csv(path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------- מה נשלח ל-Claude ----------
def test_request_has_only_the_pages_no_names_and_no_key(root):
    fake = FakeClaude()
    grading.grade_assignment(asg(root).dir, ["0001"], ask=fake)
    (req,) = fake.requests
    # התמונות עצמן בצד: ב-base64 יכול להופיע במקרה כל רצף של ספרות
    text_only = [b for b in req["messages"][0]["content"] if b["type"] != "image"]
    raw = json.dumps({**req, "messages": text_only}, ensure_ascii=False)
    # בלי שמות, בלי מספרי משתתפים ובלי שום דבר מטבלת המפתח
    assert not any(name in raw for name in NAMES.values())
    assert not any(pid in raw for pid in NAMES) and paths.KEY not in raw and "assignsubmission" not in raw
    content = req["messages"][0]["content"]
    with pymupdf.open(asg(root).submissions / "0001.pdf") as doc:
        assert sum(b["type"] == "image" for b in content) == doc.page_count
    assert not any(b["type"] == "document" for b in content)  # אין פתרון רשמי בתיקייה
    # מה שמשותף לכל ההגשות נשמר במטמון, והשאלות כתובות בו לפי הסדר עם הניקוד
    shared = next(b for b in content if b.get("cache_control"))
    assert "1. דף קבוצות 11 (20 נקודות)" in shared["text"] and "כתב יד, קובץ PDF אחד" in shared["text"]
    assert req["model"] == grading.DEFAULT_MODEL and req["output_config"]["effort"] == "high"
    assert req["output_config"]["format"]["type"] == "json_schema" and req["fallbacks"] == "default"
    assert "thinking" not in req and "temperature" not in req


def test_rubric_and_solution_are_sent(root):
    a = asg(root)
    d = a.details()
    d["rubric"] = {"questions": [{"label": "קבוצות", "points": 40, "criteria": "הכלה דו-כיוונית"},
                                 {"label": "מרוכבים", "points": 60}], "notes": "לא מורידים על חישוב"}
    d["grading_instructions"] = "להקפיד על נימוקים"
    save_details(a, d)
    (a.dir / grading.SOLUTION).write_bytes(homework_pdf("פתרון", HW, pages=1))
    ctx = grading.load_context(a.dir, instructions="הנחיה מהאתר")
    req = grading.build_request(ctx, [], "claude-haiku-5-5")
    content = req["messages"][0]["content"]
    assert content[0]["type"] == "document" and content[0]["source"]["media_type"] == "application/pdf"
    text = content[1]["text"]
    assert "1. קבוצות (40 נקודות): הכלה דו-כיוונית" in text and "2. מרוכבים (60 נקודות)" in text
    assert "לא מורידים על חישוב" in text and "להקפיד על נימוקים" in text and "הנחיה מהאתר" in text
    assert "fallbacks" not in req  # ל-Haiku אין fallback
    assert "document" not in json.dumps(grading.build_request(grading.load_context(a.dir, send_solution=False), []))


# ---------- התשובה ----------
def test_parse_answer_clamps_and_computes_the_grade(root):
    ctx = grading.load_context(asg(root).dir)
    text = json.dumps({
        "questions": [{"label": l, "points": p, "comment": ""} for l, p in zip(LABELS, (25, 15.3, -4, "x"))],  # רק 4 שאלות
        "feedback": "יפה",
        "annotations": [
            {"page": 1, "x0": 900, "y0": 50, "x1": 100, "y1": 20, "text": "הפוך"},  # מלבן הפוך מתוקן
            {"page": 9, "x0": 0, "y0": 0, "x1": 10, "y1": 10, "text": "עמוד שלא קיים"},
            {"page": 1, "x0": 5, "y0": 5, "x1": 5, "y1": 90, "text": "קו בלי רוחב"},
        ],
        "needs_review": False, "review_reason": "",
    }, ensure_ascii=False)
    g = grading.parse_answer(text, ctx, pages=2)
    assert g.points == [20, 15.5, 0, 0, 0]  # עד הניקוד המרבי, בחצאי נקודות
    assert g.grade == 36
    assert [(m.x0, m.y0, m.x1, m.y1) for m in g.marks] == [(100, 20, 900, 50)]
    assert "4 שאלות במקום 5" in g.review
    with pytest.raises(grading.GradingError):
        grading.parse_answer("not json", ctx, 1)


def test_names_are_removed_even_if_claude_copies_them(root):
    fake = FakeClaude(lambda req: answer(feedback="כל הכבוד נועה כהן, עבודה מסודרת. כהן נועה, שימו לב לשאלה 12.",
                                         marks=[{"page": 1, "x0": 10, "y0": 10, "x1": 500, "y1": 60, "text": "נועה כהן: חסר נימוק"}]))
    grading.grade_assignment(asg(root).dir, ["0001"], ask=fake)
    row = grading.read_grades(asg(root).dir)["0001"]
    assert "נועה" not in row["feedback"] and "כהן" not in row["feedback"]
    assert row["feedback"].startswith("כל הכבוד, עבודה מסודרת.")
    with pymupdf.open(asg(root).dir / paths.MARKED / "0001.pdf") as doc:
        assert "נועה" not in doc[0].get_text()  # עמוד הסיכום
        # בעמוד של הסטודנט השם כתוב בעבודה עצמה (ונשאר), אבל ההערה האדומה בלי השם
        assert "חסר נימוק" in text(doc[1]) and text(doc[1]).count("נועה") == 1


# ---------- הפלט ----------
def test_grading_writes_grades_csv_and_marked_pdfs(root):
    a = asg(root)
    fake = FakeClaude()
    rep = grading.grade_assignment(a.dir, ask=fake, parallel=3)
    assert rep.graded == ["0001", "0002", "0003"] and not rep.failed and len(fake.requests) == 3

    rows = read_csv(a.dir / grading.GRADES)
    assert list(rows[0])[:3] == ["number", "grade", "feedback"]  # בדיוק מה ש-upload.py קורא
    assert (a.dir / grading.GRADES).read_bytes().startswith(b"\xef\xbb\xbf")
    assert [(r["number"], r["grade"], r["points"]) for r in rows] == [(n, "85", "20;15;20;20;10") for n in ("0001", "0002", "0003")]
    assert rows[0]["approved"] == "" and rows[0]["review"] == ""

    out = a.dir / paths.MARKED / "0001.pdf"
    assert out.stat().st_size <= grading.MAX_BYTES
    with pymupdf.open(a.submissions / "0001.pdf") as src, pymupdf.open(out) as doc:
        assert doc.page_count == src.page_count + 1  # עמוד סיכום בהתחלה
        assert "ציון: 85 מתוך 100" in text(doc[0])
        red = [d for d in doc[1].get_drawings() if d.get("color") and d["color"][0] > 0.8 and d["color"][1] < 0.1]
        assert red, "לא צויר מלבן אדום"
        r = red[0]["rect"]
        w, h = doc[1].rect.width, doc[1].rect.height
        assert abs(r.x0 - 0.1 * w) < 2 and abs(r.y0 - 0.1 * h) < 2 and abs(r.x1 - 0.9 * w) < 2 and abs(r.y1 - 0.16 * h) < 2
    assert rep.summary() == "נבדקו 3 מתוך 3"


def test_several_files_of_one_student_are_graded_together(root):
    """moodle ingest שומר קובץ שני של סטודנט בשם 0002-2 (גם תמונה), ואת זה אי אפשר לבדוק: 0002-3.docx."""
    a = asg(root)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 400), False)
    pix.clear_with(230)
    (a.submissions / "0002-2.jpg").write_bytes(pix.tobytes("jpeg"))
    (a.submissions / "0002-3.docx").write_bytes(b"PK not graded")
    fake = FakeClaude()
    rep = grading.grade_assignment(a.dir, ["0002"], ask=fake)
    assert rep.graded == ["0002"] and rep.review == ["0002"]
    with pymupdf.open(a.submissions / "0002.pdf") as first:
        pages = first.page_count + 1
    assert sum(b["type"] == "image" for b in fake.requests[0]["messages"][0]["content"]) == pages
    with pymupdf.open(a.dir / paths.MARKED / "0002.pdf") as marked:
        assert marked.page_count == pages + 1
    assert "0002-3.docx" in grading.read_grades(a.dir)["0002"]["review"]
    assert not (a.dir / paths.MARKED / "0002-2.pdf").exists()  # עבודה מסומנת אחת לכל מספר


def test_approved_rows_are_kept_and_not_regraded(root):
    a = asg(root)
    grading.write_grades(a.dir, {
        "0002": {"number": "0002", "grade": "70", "feedback": "אושר ידנית", "approved": "כן", "extra": "של המרצה"},
        "0003": {"number": "3", "grade": "40", "feedback": "ישן", "approved": ""},
    })
    fake = FakeClaude()
    rep = grading.grade_assignment(a.dir, ["0002", "3"], ask=fake)
    assert rep.skipped == ["0002"] and rep.graded == ["0003"] and len(fake.requests) == 1
    rows = grading.read_grades(a.dir)
    assert rows["0002"]["grade"] == "70" and rows["0002"]["feedback"] == "אושר ידנית" and rows["0002"]["extra"] == "של המרצה"
    assert rows["0003"]["grade"] == "85"
    assert not (a.dir / paths.MARKED / "0002.pdf").exists()


def test_pending_skips_graded_and_extra_marked_files(root):
    a = asg(root)
    (a.dir / paths.MARKED / "0001-2.pdf").write_bytes(b"%PDF marked by hand")
    grading.write_grades(a.dir, {"0002": {"number": "0002", "grade": "90", "feedback": ""}})
    assert grading.pending(a.dir) == ["0003"]
    assert a.graded_numbers() == {"0001"}


def test_one_failure_does_not_stop_the_rest(root):
    calls = []

    def ask(req):
        calls.append(1)
        if len(calls) == 2:
            raise grading.GradingError("Claude סירב לבדוק את העבודה הזו. צריך לבדוק אותה ידנית.")
        return answer(review="כתב יד לא קריא בעמוד 2")
    rep = grading.grade_assignment(asg(root).dir, ask=ask, parallel=1)
    assert len(rep.graded) == 2 and len(rep.failed) == 1 and rep.review == rep.graded
    assert "סירב" in next(iter(rep.failed.values()))
    assert all(r["review"] == "כתב יד לא קריא בעמוד 2" for r in grading.read_grades(asg(root).dir).values())


def test_big_scans_are_shrunk_to_the_size_limit():
    w, h = 1700, 2200
    rnd = random.Random(1)
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, bytes(rnd.getrandbits(8) for _ in range(w * h * 3)), False)
    jpg = pix.tobytes("jpeg", jpg_quality=95)
    doc = pymupdf.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_image(page.rect, stream=jpg)
    pdf = doc.tobytes()
    assert len(pdf) > 2 * grading.MAX_BYTES
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 100)])
    g = grading.Graded([80], [""], 80, "יפה", [grading.Mark(2, 100, 100, 400, 200, "כאן")])
    out = grading.mark_pdf(pdf, g, ctx)
    assert len(out) <= grading.MAX_BYTES
    with pymupdf.open(stream=out, filetype="pdf") as marked:
        assert marked.page_count == 3


def test_rotated_page_is_marked_where_it_is_seen():
    doc = pymupdf.open(stream=homework_pdf("x", HW, pages=1), filetype="pdf")
    doc[0].set_rotation(90)
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 100)])
    g = grading.Graded([100], [""], 100, "", [grading.Mark(1, 100, 100, 300, 200, "")])
    with pymupdf.open(stream=grading.mark_pdf(doc.tobytes(), g, ctx), filetype="pdf") as out:
        page = out[1]
        pix = page.get_pixmap(dpi=36)
        # מלבן אדום ליד הפינה השמאלית העליונה של העמוד כפי שהוא מוצג
        x, y = int(0.1 * pix.width), int(0.15 * pix.height)
        reds = [(i, j) for i in range(pix.width) for j in range(pix.height)
                if (lambda c: c[0] > 150 and c[1] < 90 and c[2] < 90)(pix.pixel(i, j))]
        assert reds and min(abs(i - x) for i, _ in reds) <= 3


# ---------- בלי מפתח ----------
def test_no_key_gives_a_clear_message(root, monkeypatch):
    monkeypatch.setattr(grading, "claude_ask", _real_claude_ask)
    with pytest.raises(grading.NoApiKey) as e:
        grading.grade_assignment(asg(root).dir)
    assert "ANTHROPIC_API_KEY" in str(e.value) and ".env" in str(e.value)
    assert not (asg(root).dir / grading.GRADES).exists()


# ---------- האתר ----------
def test_state_reads_grades_and_marked_files(root):
    a = asg(root)
    grading.write_grades(a.dir, {"0001": {"number": "0001", "grade": "85", "feedback": "יפה", "points": "20;15;20;20;10",
                                          "approved": "כן", "review": ""},
                                 "0002": {"number": "0002", "grade": "72.5", "feedback": "", "review": "כתב יד לא קריא"}})
    (a.dir / paths.MARKED / "0001.pdf").write_bytes(b"%PDF")
    (a.dir / paths.MARKED / "0001-2.pdf").write_bytes(b"%PDF")
    (a.dir / paths.MARKED / "0003-2.pdf").write_bytes(b"%PDF")
    st = actions.state(root)
    (A,) = st["assignments"]
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
    subs = {s["id"]: s for s in state["assignments"][0]["subs"]}
    assert subs["0001"]["status"] == "graded" and subs["0001"]["score"] == 85 and subs["0003"]["status"] == "pulled"
    assert state["claude"] is True and state["assignments"][0]["gradedAt"]

    st, out = call(server, "POST", "/api/grade", {"course": COURSE, "assignment": HW, "ids": ["../x"]})
    assert st == 400
    st, out = call(server, "POST", "/api/grade", {"course": COURSE, "assignment": "../../x"})
    assert st == 404


# ---------- Grading notes, טעויות נפוצות ובדיקה ידנית ----------
RUBRIC = {"questions": [{"label": l, "points": 20, "deductions": [{"text": "חסר נימוק", "points": 5}, "רק הערה"] if i == 1 else []}
                        for i, l in enumerate(LABELS)]}


def detailed(points=(20, 15, 20, 20, 10), review="", kind="", unsure=(), mistakes=None):
    """תשובה של Claude עם סוגי הטעויות, שאלות לא ודאיות וסוג הבעיה."""
    mistakes = mistakes or {1: ["חסר נימוק", "חסר נימוק."], 4: ["תחום לא נכון"]}
    return json.dumps({
        "questions": [{"label": l, "points": p, "comment": "", "mistakes": mistakes.get(i, []), "unsure": i in unsure}
                      for i, (l, p) in enumerate(zip(LABELS, points))],
        "feedback": "יפה", "annotations": [{"page": 1, "x0": 100, "y0": 100, "x1": 900, "y1": 160, "text": "חסר נימוק"}],
        "needs_review": bool(review), "review_reason": review, "review_kind": kind,
    }, ensure_ascii=False)


def test_rubric_deductions_reach_claude(root):
    a = asg(root)
    save_details(a, {**a.details(), "rubric": RUBRIC})
    ctx = grading.load_context(a.dir)
    assert ctx.questions[1].deductions == [{"text": "חסר נימוק", "points": 5}, {"text": "רק הערה", "points": 0}]
    prompt = grading.context_text(ctx)
    assert '"חסר נימוק" (מורידים 5)' in prompt and '"רק הערה"' in prompt
    assert "review_kind" in grading.SYSTEM and "בדיקה ידנית" in grading.SYSTEM
    assert grading.SCHEMA["properties"]["review_kind"]["enum"] == ["", *grading.REVIEW_KINDS]


def test_answer_keeps_mistakes_unsure_and_the_kind_of_problem(root):
    ctx = grading.load_context(asg(root).dir)
    g = grading.parse_answer(detailed(review="שאלה 12, עמוד 1: לא קריא", kind="unreadable", unsure=(1,)), ctx, 1)
    assert g.mistakes[1] == ["חסר נימוק"] and g.mistakes[4] == ["תחום לא נכון"] and g.mistakes[0] == []
    assert g.unsure == [False, True, False, False, False] and g.review_kind == "unreadable"
    assert grading.parse_answer(detailed(review="משהו", kind="weird"), ctx, 1).review_kind == "other"
    assert grading.parse_answer(detailed(kind="unreadable"), ctx, 1).review_kind == ""  # בלי סיבה אין בדיקה ידנית
    assert grading.parse_answer(answer(), ctx, 1).mistakes == [[]] * 5  # תשובה בלי השדות החדשים עדיין נקראת


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
    out = grading.save_review(a.dir, "1", [20, 14.7, 20, 99, 0], ["", "חסר נימוק.", "", "", "השאלה לא נמצאה"],
                              "עבודה טובה.", by="dana (PC)", mistakes=[[], ["חסר נימוק"], [], [], []])
    assert out == {"number": "0001", "grade": 75}  # 14.7 → 14.5, 99 → 20 (הניקוד המרבי)
    row = grading.read_grades(a.dir)["0001"]
    assert row["points"] == "20;14.5;20;20;0" and row["grade"] == "75" and row["feedback"] == "עבודה טובה."
    assert row["approved"].startswith("dana (PC) ") and row["review"] == "לא בטוח" and grading.is_approved(row)
    note = grading.read_notes(a.dir, "0001")
    assert note["reviewed"]["by"] == "dana (PC)" and note["mistakes"][4] == [] and note["marks"]  # הסימונים של Claude נשארים
    with pymupdf.open(a.dir / paths.MARKED / "0001.pdf") as doc, pymupdf.open(a.submissions / "0001.pdf") as src:
        assert doc.page_count == src.page_count + 1 and "ציון: 75 מתוך 100" in text(doc[0])
        assert "השאלה לא נמצאה" in text(doc[0]) and "נועה" not in text(doc[0])
    # מאושרת: הבדיקה האוטומטית לא דורסת אותה
    assert grading.grade_assignment(a.dir, ["0001"], ask=lambda req: detailed()).skipped == ["0001"]
    subs = {s["id"]: s for s in actions.state(root)["assignments"][0]["subs"]}
    assert subs["0001"]["approved"] and subs["0001"]["reviewedBy"] == "dana (PC)" and subs["0001"]["score"] == 75


def test_save_review_of_work_graded_before_notes_keeps_its_marks(root):
    """עבודה שנבדקה לפני שהיו Grading notes: מחליפים רק את עמוד הסיכום, והסימונים שב-PDF נשארים."""
    a = asg(root)
    grading.grade_assignment(a.dir, ["0002"], ask=lambda req: detailed())
    grading.notes_path(a.dir, "0002").unlink()
    with pymupdf.open(a.dir / paths.MARKED / "0002.pdf") as doc:
        pages, marked_page = doc.page_count, len(doc[1].get_drawings())
    grading.save_review(a.dir, "0002", [20] * 5, [], "", by="x")
    with pymupdf.open(a.dir / paths.MARKED / "0002.pdf") as doc:
        assert doc.page_count == pages and "ציון: 100 מתוך 100" in text(doc[0]) and len(doc[1].get_drawings()) == marked_page


def test_save_review_refuses_what_it_cannot_match(root):
    a = asg(root)
    with pytest.raises(grading.GradingError):
        grading.save_review(a.dir, "0009", [20] * 5, [], "", by="x")  # אין הגשה כזו
    with pytest.raises(grading.GradingError):
        grading.save_review(a.dir, "0001", [20] * 4, [], "", by="x")  # ניקוד לא לכל השאלות
    assert not (a.dir / grading.GRADES).exists()


def test_server_review_and_downloads(root, server):
    a = asg(root)
    st, out = call(server, "POST", "/api/review", {"course": COURSE, "assignment": HW, "number": "0003",
                                                     "points": [20, 20, 20, 20, 10], "comments": [], "feedback": "יפה"})
    assert st == 200 and out == {"number": "0003", "grade": 90}
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
    for path in (paths.KEY, f"{paths.MARKED}/0003-2.jpg", f"{paths.NOTES}/0003.json"):
        assert get(rel + path)[0] == 404  # רק הגשות ועבודות מסומנות יוצאות. לא המפתח ולא שום דבר אחר
