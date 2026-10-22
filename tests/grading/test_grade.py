"""בדיקות לשלב הבדיקה (grade.py), עם Claude מדומה בלבד. מריצים: python -m pytest

הכל קורה בתיקייה זמנית (tmp_path). התיקייה האמיתית ב-OneDrive לא נקראת ולא משתנה.
"""
from __future__ import annotations

import base64
import csv
import http.client
import json
import os
import random
import threading
import time
from http.server import ThreadingHTTPServer

import pymupdf
import pytest

from moodle import claude_driver, paths
from dashboard import actions, folder_view
from grading import grade as grading, notes
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


def test_pedagogy_folder_is_sent_with_its_points(root):
    a = asg(root)
    ped = a.dir / "פדגוגי"
    ped.mkdir()
    (ped / "Solutions.md").write_text("# פתרון\nקבוצות 11א: כן", encoding="utf-8")
    (ped / "Rubric.md").write_text(
        "| שאלה | נקודות | סעיפים |\n|---|---|---|\n| קבוצות 11 | 20 | א 3 |\n| **קבוצות 12** | **24** | |\n"
        "| מרוכבים 6 | 12 | |\n| מרוכבים 7 | 20 | |\n| מרוכבים 8 | 24 | |\n| **סה\"כ** | **100** | |\n"
        "| \"לא\" בלבד | 2 |\n", encoding="utf-8")
    (ped / paths.README).write_text("לא נשלח", encoding="utf-8")
    (ped / "notes.pdf").write_bytes(b"not text")
    ctx = grading.load_context(a.dir)
    assert [(q.label, q.points) for q in ctx.questions] == list(zip(LABELS, (20, 24, 12, 20, 24)))
    text = grading.context_text(ctx)
    # המחוון קודם, אחריו שאר הקבצים; README ו-PDF לא נשלחים
    assert text.index("--- Rubric.md ---") < text.index("--- Solutions.md ---")
    assert "קבוצות 11א: כן" in text and "לא נשלח" not in text and "notes.pdf" not in text


def test_points_in_details_win_over_the_pedagogy_folder(root):
    a = asg(root)
    d = a.details()
    d["rubric"] = {"questions": [{"label": "הכל", "points": 100}]}
    save_details(a, d)
    (a.dir / "Pedagogy").mkdir()
    (a.dir / "Pedagogy" / "Rubric.txt").write_text("| הכל | 50 |\nמורידים על סימון", encoding="utf-8")
    ctx = grading.load_context(a.dir)
    assert [(q.label, q.points) for q in ctx.questions] == [("הכל", 100)]
    assert "מורידים על סימון" in grading.context_text(ctx)


def test_no_pedagogy_folder_splits_points_evenly(root):
    ctx = grading.load_context(asg(root).dir)
    assert [q.points for q in ctx.questions] == [20] * 5 and "חומר הבדיקה" not in ctx.rubric_text


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
        # הרוחב בדיוק כמו ש-Claude נתן. לגובה המלבן מתקרב לשורת הכתב שלו (notes.snap_box), עד חצי מגובהו
        assert abs(r.x0 - 0.1 * w) < 2 and abs(r.x1 - 0.9 * w) < 2
        reach = 0.06 * h * notes.SNAP_REACH
        assert 0.1 * h - reach - 4 <= r.y0 < r.y1 <= 0.16 * h + reach + 4 and r.y0 < 0.16 * h and r.y1 > 0.1 * h
    assert rep.summary() == "נבדקו 3 מתוך 3"
    # כל חמישית נכתבה לקובץ משלה, ובסוף, כשאף אחת לא נבדקת, הכל אוחד ל-Grades.csv
    assert not list(a.dir.glob("Grades - part *.csv")) and not list(a.dir.glob("Grading part *"))


# ---------- כמה מחשבים בו זמנית ----------
def other_computer_holds(a, part: int) -> None:
    (a.dir / paths.GRADING_LOCK.format(part)).write_text("noa (OTHER-PC) pid=1", encoding="utf-8")


def test_submissions_split_into_fifths_by_number():
    from moodle import grades
    assert [grades.part_of(n) for n in ("0001", "0002", "0005", "0006", "0481")] == [1, 2, 5, 1, 1]


def test_a_fifth_another_computer_is_grading_is_skipped(root):
    a = asg(root)
    other_computer_holds(a, 2)
    fake = FakeClaude()
    rep = grading.grade_assignment(a.dir, ask=fake)
    # 0002 בחמישית 2: לא נבדקה כאן ולא נשלחה ל-Claude
    assert rep.graded == ["0001", "0003"] and rep.busy == {2: "noa (OTHER-PC)"} and len(fake.requests) == 2
    assert "חמישית 2" in rep.notes[0] and "noa (OTHER-PC)" in rep.notes[0] and rep.total == 2
    # כל חמישית בקובץ משלה. אין איחוד ל-Grades.csv כל עוד חמישית 2 נבדקת במחשב האחר
    assert not (a.dir / grading.GRADES).exists()
    assert [r["number"] for r in read_csv(a.dir / "Grades - part 1.csv")] == ["0001"]
    assert [r["number"] for r in read_csv(a.dir / "Grades - part 3.csv")] == ["0003"]
    assert set(grading.read_grades(a.dir)) == {"0001", "0003"}
    # המנעולים שלי שוחררו, ושל המחשב האחר נשאר
    assert [p.name for p in a.dir.glob("Grading part *")] == ["Grading part 2 in progress.txt"]

    # המחשב האחר סיים (כתב את הקובץ שלו ושחרר): הריצה הבאה לא בודקת שוב, ומאחדת הכל
    (a.dir / "Grades - part 2.csv").write_text("number,grade,feedback\r\n0002,70,x\r\n", encoding="utf-8-sig")
    (a.dir / paths.GRADING_LOCK.format(2)).unlink()
    rep = grading.grade_assignment(a.dir, ask=fake)
    assert rep.graded == [] and len(fake.requests) == 2
    assert [(r["number"], r["grade"]) for r in read_csv(a.dir / grading.GRADES)] == [("0001", "85"), ("0002", "70"), ("0003", "85")]
    assert not list(a.dir.glob("Grades - part *.csv"))


def test_a_stuck_lock_does_not_block_forever(root):
    a = asg(root)
    other_computer_holds(a, 2)
    old = time.time() - 31 * 60
    os.utime(a.dir / paths.GRADING_LOCK.format(2), (old, old))
    rep = grading.grade_assignment(a.dir, ask=FakeClaude())
    assert rep.graded == ["0001", "0002", "0003"] and not rep.busy


def test_approved_rows_are_kept_when_fifths_are_merged(root):
    a = asg(root)
    (a.dir / grading.GRADES).write_text("number,grade,feedback,approved\r\n0001,90,טוב,כן\r\n", encoding="utf-8-sig")
    (a.dir / "Grades - part 1.csv").write_text("number,grade,feedback,approved\r\n0001,40,x,\r\n", encoding="utf-8-sig")
    (a.dir / "Grades - part 2.csv").write_text("number,grade,feedback,approved\r\n0002,70,y,\r\n", encoding="utf-8-sig")
    assert {n: r["grade"] for n, r in grading.read_grades(a.dir).items()} == {"0001": "90", "0002": "70"}
    from moodle import upload
    assert {n: r["grade"] for n, r in upload.read_results(a.dir).items()} == {"0001": "90", "0002": "70"}
    assert grading.merge_parts(a.dir)
    assert [(r["number"], r["grade"]) for r in read_csv(a.dir / grading.GRADES)] == [("0001", "90"), ("0002", "70")]


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


def test_math_in_a_hebrew_note_stays_left_to_right():
    lre, pdf = "‪", "‬"
    assert grading._ltr_math("כתבו את הקבוצה: A∩B=A={(1+2t,1-t)|t∈R}") == f"כתבו את הקבוצה: {lre}A∩B=A={{(1+2t,1-t)|t∈R}}{pdf}"
    # פסיק בסוף הנוסחה שייך למשפט העברי
    assert grading._ltr_math("מתקבל t_A=4t_A, לא 2t_A.") == f"מתקבל {lre}t_A=4t_A{pdf}, לא {lre}2t_A{pdf}."
    assert grading._ltr_math("חסר נימוק") == "חסר נימוק"


def test_images_have_rulers_in_thousandths_around_the_page():
    from grading import render
    doc = pymupdf.open()
    doc.new_page(width=600, height=800)
    framed, page = render.with_rulers(doc[0])
    m = render.RULER_MARGIN * 800
    assert page.rect.width == pytest.approx(600 + 2 * m) and page.rect.height == pytest.approx(800 + 2 * m)
    labels = {w[4] for w in page.get_text("words")}
    assert {"0", "100", "500", "1000"} <= labels
    img = render.render_page(doc[0], 1100)
    assert max(img.width, img.height) == 1100
    assert max(render.render_page(doc[0], 1100, rulers=False).height, 0) == 1100


def test_note_goes_to_the_nearest_empty_spot_with_an_arrow():
    # עמוד עם "כתב" שחור בכל החצי השמאלי, וטעות מסומנת בתוכו: ההערה נכתבת בחצי הימני הריק, עם חץ
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    ink = pymupdf.Rect(20, 20, 300, 780)
    page.draw_rect(ink, color=(0, 0, 0), fill=(0, 0, 0))
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 100)])
    g = grading.Graded([98], [""], 98, "", [grading.Mark(1, 300, 450, 480, 500, "לא נכון עבור t=0", 2)])
    with pymupdf.open(stream=grading.mark_pdf(doc.tobytes(), g, ctx), filetype="pdf") as out:
        marked = out[1]
        assert marked.rect == page.rect  # בלי שוליים: אותו עמוד
        words = marked.get_text("words")
        note = [w for w in words if w[4] in ("ירדו", "נכון", "2")]
        assert {w[4] for w in note} == {"ירדו", "נכון", "2"}
        assert all(pymupdf.Rect(w[:4]).x0 >= ink.x1 for w in note)  # לא על הכתב
        box = pymupdf.Rect(0.3 * 600, 0.45 * 800, 0.48 * 600, 0.5 * 800)
        assert all(not pymupdf.Rect(w[:4]).intersects(box) for w in note)  # ולא על המלבן
        assert min(abs(pymupdf.Rect(w[:4]).y0 - box.y0) for w in note) < 80  # קרוב לטעות
        lines = [d for d in marked.get_drawings() if d.get("color") and d["color"][0] > 0.8 and d["color"][1] < 0.1
                 and any(item[0] == "l" for item in d["items"])]
        assert len(lines) >= 3  # החץ: קו וראש של שני קווים


def test_points_off_is_read_from_the_answer(root):
    ctx = grading.load_context(asg(root).dir)
    marks = [{"page": 1, "x0": 100, "y0": 100, "x1": 900, "y1": 160, "text": "חסר", "points_off": 2.3}]
    g = grading.parse_answer(answer(marks=marks), ctx, pages=1)
    assert [(m.text, m.points_off) for m in g.marks] == [("חסר", 2.5)]


def _sides(req) -> list[int]:
    """הצד הארוך של כל תמונה בבקשה."""
    out = []
    for b in req["messages"][0]["content"]:
        if b["type"] == "image":
            pix = pymupdf.Pixmap(base64.b64decode(b["source"]["data"]))
            out.append(max(pix.width, pix.height))
    return out


def test_small_pages_first_then_full_size_then_one_by_one(root):
    pdf = (asg(root).submissions / "0001.pdf").read_bytes()
    ctx = grading.load_context(asg(root).dir)

    def reply(unreadable_times):
        calls = iter(range(10))
        return lambda req: json.dumps({**json.loads(answer()), "unreadable": next(calls) < unreadable_times})

    # Claude קרא בגודל הקטן: בקשה אחת, כל העמודים בבת אחת
    fake = FakeClaude(reply(0))
    g, _ = grading.grade_one(pdf, ctx, fake)
    assert len(fake.requests) == 1 and set(_sides(fake.requests[0])) == {1100}
    assert "_one_by_one" not in fake.requests[0] and not g.review

    # לא הצליח פעמיים: גודל מלא, ואז גודל מלא עמוד אחרי עמוד
    fake = FakeClaude(reply(2))
    g, _ = grading.grade_one(pdf, ctx, fake)
    assert [set(_sides(r)) for r in fake.requests] == [{1100}, {1568}, {1568}]
    assert [r.get("_one_by_one", False) for r in fake.requests] == [False, False, True] and not g.review

    # לא הצליח אף פעם: נשאר התשובה האחרונה, ומסומן לבדיקה ידנית
    fake = FakeClaude(reply(3))
    g, _ = grading.grade_one(pdf, ctx, fake)
    assert len(fake.requests) == 3 and "גם בגודל המלא" in g.review


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


def test_the_decisions_skill_reaches_claude():
    """The rules of .claude/skills/decisions are sent with every submission, and they decide what a person sees."""
    rules = grading.decision_rules()
    assert rules.startswith("קשיחות והחלטות") and "needs_review=true רק כשאי אפשר לבדוק בכלל" in rules
    assert grading.SYSTEM.endswith(rules)
    assert "<!--" not in grading.SYSTEM
