"""בדיקות לשלב הבדיקה (grade.py), עם Claude מדומה בלבד. מריצים: python -m pytest

הכל קורה בתיקייה זמנית (tmp_path). התיקייה האמיתית ב-OneDrive לא נקראת ולא משתנה.
"""
from __future__ import annotations

import csv
import json
import random
import threading
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import pytest

from moodle import claims, claude_code, grades, paths
from grading import grade as grading
from tests.sample_files import homework_pdf

COURSE, HW = "Linear Algebra", "Assignment 0 - Sets and Complex Numbers"
NAMES = {"1001": "נועה כהן", "1002": "איתי לוי", "1003": "מאיה מזרחי"}
LABELS = ["דף קבוצות 11", "דף קבוצות 12", "דף מספרים מרוכבים 6", "דף מספרים מרוכבים 7", "דף מספרים מרוכבים 8"]
_real_claude_ask = grading.claude_ask
# המחוון של מטלת הבדיקות: 20 נקודות לכל שאלה. בלי מחוון אין ציונים בכלל
RUBRIC = {"questions": [{"label": l, "points": 20, "deductions": [{"text": "חסר נימוק", "points": 5}, "רק הערה"] if i == 1 else []}
                        for i, l in enumerate(LABELS)]}


@dataclass
class Assignment:
    """An assignment folder, as these tests use it (the site's dashboard/folder_view.Assignment is the same, for the site:
    the grading tests don't need the dashboard)."""
    dir: Path

    @property
    def submissions(self) -> Path:
        return self.dir / paths.TO_GRADE

    def details(self) -> dict:
        f = self.dir / paths.INFO
        return json.loads(f.read_text(encoding="utf-8-sig")) if f.exists() else {}


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    """אף בדיקה לא מדברת עם Claude באמת. בדיקה שצריכה את Claude מקבלת גרסה מדומה."""
    def refuse():
        raise AssertionError("בבדיקות משתמשים רק ב-Claude מדומה")
    monkeypatch.setattr(grading, "claude_ask", refuse)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # וגם לא Claude Code שמחובר במחשב הזה (grading מוצא אותו דרך הליבה, moodle/claude_code.py)
    monkeypatch.setattr(claude_code, "auth_status", lambda *a, **k: {"logged_in": False, "message": "fake"})


@pytest.fixture
def root(tmp_path, monkeypatch):
    """עותק מוקטן של Exercise Checking System עם שלוש הגשות ממוספרות, כמו ש-moodle ingest משאיר."""
    course_folder = tmp_path / "נדב מאיר - YallaLinearit"
    r = course_folder / "Exercise Checking System"
    a = Assignment(r / COURSE / HW)
    for sub in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD):
        (a.dir / sub).mkdir(parents=True)
    save_details(a, {"id": "3438636", "course": COURSE, "course_id": "67024", "name": HW,
                     "questions": [{"sheet": "דף קבוצות", "numbers": [11, 12]}, {"sheet": "דף מספרים מרוכבים", "numbers": [6, 7, 8]}],
                     "submission_rules": ["כתב יד, קובץ PDF אחד"], "max_grade": None, "rubric": RUBRIC,
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
    monkeypatch.setenv("GRADER_NAME", "בודק א")
    return r


def asg(root) -> Assignment:
    return Assignment(root / COURSE / HW)


def save_details(a: Assignment, d: dict) -> None:
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
        "questions": [{"label": l, "points": p, "comment": "משהו"} for l, p in zip(LABELS, (25, 15.3, -4, "x", 0))],
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
    assert g.lost == ["עמוד 9 (אין עמוד כזה): עמוד שלא קיים"]  # לא נזרקת: תגיע לעמוד הסיכום
    assert "25 מתוך 20" in g.review and "שאלות במקום" not in g.review
    with pytest.raises(grading.GradingError):
        grading.parse_answer("not json", ctx, 1)


def test_answers_are_matched_by_label_and_a_partial_answer_is_refused(root):
    # באג אמיתי (2026-11-11): Claude החזיר 15 שאלות מ-21 בעבודה של 24 עמודים. השידוך לפי מקום ברשימה נתן 0
    # לשש שאלות נכונות, 5 מתוך 2 לשאלה שהניקוד של שכנתה זלג אליה, ו-"placeholder" בעמוד הסיכום של הסטודנט
    ctx = grading.load_context(asg(root).dir)

    def reply(questions, feedback="יפה", annotations=()):
        return json.dumps({"questions": questions, "feedback": feedback, "annotations": list(annotations),
                           "needs_review": False, "review_reason": ""}, ensure_ascii=False)

    def q(label, points, comment="נכון"):
        return {"label": label, "points": points, "comment": comment}

    # הפוך בסדר: הניקוד הולך לפי התווית
    g = grading.parse_answer(reply([q(l, p) for l, p in zip(reversed(LABELS), (1, 2, 3, 4, 5))]), ctx, 1)
    assert g.points == [5, 4, 3, 2, 1]
    # תווית עם רווחים אחרים עדיין מזוהה; באותו מספר שאלות תווית זרה הולכת לפי הסדר
    g = grading.parse_answer(reply([q(" ".join(LABELS[0]), 7)] + [q(l, 20) for l in LABELS[1:]]), ctx, 1)
    assert g.points[0] == 7
    g = grading.parse_answer(reply([q("משהו אחר", 7)] + [q(l, 20) for l in LABELS[1:]]), ctx, 1)
    assert g.points[0] == 7
    # חסרות שאלות: הבדיקה נכשלת, לא 0 בשקט
    with pytest.raises(grading.GradingError, match="4 שאלות במקום 5"):
        grading.parse_answer(reply([q(l, 20) for l in LABELS[:4]]), ctx, 1)
    with pytest.raises(grading.GradingError, match="placeholder"):
        grading.parse_answer(reply([q(l, 20) for l in LABELS[:4]] + [q(LABELS[4], 0, "placeholder")]), ctx, 1)
    with pytest.raises(grading.GradingError, match="placeholder"):
        grading.parse_answer(reply([q(l, 20) for l in LABELS], feedback="Placeholder"), ctx, 1)
    with pytest.raises(grading.GradingError, match="0 בלי הערה"):
        grading.parse_answer(reply([q(l, 20) for l in LABELS[:4]] + [q(LABELS[4], 0, "")]), ctx, 1)
    # 0 עם הערה הוא תשובה לגיטימית (שאלה שלא נמצאה)
    g = grading.parse_answer(reply([q(l, 20) for l in LABELS[:4]] + [q(LABELS[4], 0, "לא נמצאה")]), ctx, 1)
    assert g.points[4] == 0


def test_a_note_on_a_page_that_does_not_exist_reaches_the_summary_page(root):
    ctx = grading.load_context(asg(root).dir)
    g = grading.parse_answer(answer(marks=[{"page": 7, "x0": 0, "y0": 0, "x1": 10, "y1": 10, "text": "הערה בעמוד 7"}]), ctx, 2)
    assert g.marks == [] and g.lost == ["עמוד 7 (אין עמוד כזה): הערה בעמוד 7"]
    with pymupdf.open(stream=grading.mark_pdf(homework_pdf("x", "t"), g, ctx), filetype="pdf") as out:
        assert "הערה בעמוד 7" in text(out[0])


def test_a_note_that_cannot_be_written_goes_to_the_summary(monkeypatch):
    # באג אמיתי (2026-11-11): insert_htmlbox נכשל על מלבן ריק, _write בלע את השגיאה, והסטודנט ראה תיבה בלי הסבר
    doc, page = _scan_page((100, 200, 300, 230))
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 100)])
    g = grading.Graded([90], [""], 90, "", [grading.Mark(1, 168, 237, 504, 273, "הערה שלא נכנסת")])
    real = pymupdf.Page.insert_htmlbox

    def failing(self, rect, html, **kw):
        if "הערה שלא נכנסת" in html and "ציון:" not in html:  # ההערה על הדף, לא עמוד הסיכום
            raise OverflowError("int too large to convert to float")
        return real(self, rect, html, **kw)
    monkeypatch.setattr(pymupdf.Page, "insert_htmlbox", failing)
    with pymupdf.open(stream=grading.mark_pdf(doc.tobytes(), g, ctx), filetype="pdf") as out:
        assert "הערה שלא נכנסת" in text(out[0]) and "עמוד 1" in text(out[0])
    assert len(g.marks) == 1  # המלבן עצמו כן צויר


def test_places_come_from_the_answer_and_are_kept_in_the_notes(root):
    ctx = grading.load_context(asg(root).dir)
    data = json.loads(answer())
    for i, q in enumerate(data["questions"]):
        q.update({"page": 1 if i < 2 else 0, "x0": 700, "y0": 100 + 200 * i, "x1": 900, "y1": 130 + 200 * i})
    g = grading.parse_answer(json.dumps(data, ensure_ascii=False), ctx, 1)
    assert [(p.page, p.text) for p in g.places] == [(1, LABELS[0]), (1, LABELS[1])] + [(0, l) for l in LABELS[2:]]
    assert grading.parse_answer(answer(), ctx, 1).places[0].page == 0  # תשובה בלי מקום עדיין נקראת
    notes = grading.graded_notes(g, "m")
    assert [p["page"] for p in notes["places"]] == [1, 1, 0, 0, 0] and notes["places"][0]["text"] == LABELS[0]


def _strokes(page, color):
    return [d for d in page.get_drawings() if d.get("color") and all(abs(a - b) < 0.05 for a, b in zip(d["color"], color))]


def test_check_cross_or_half_is_drawn_where_each_answer_starts():
    doc, page = _scan_page((100, 200, 300, 230))
    ctx = grading.Context("מטלה", "קורס", [grading.Question(f"שאלה {i}", 10) for i in range(1, 5)])
    places = [grading.Mark(1, 700, 100, 760, 130, "שאלה 1"), grading.Mark(1, 700, 300, 760, 330, "שאלה 2"),
              grading.Mark(1, 700, 500, 760, 530, "שאלה 3"), grading.Mark(0, 0, 0, 0, 0, "שאלה 4")]
    g = grading.Graded([10, 0, 6.5, 10], [""] * 4, 66, "", [], places=places)
    with pymupdf.open(stream=grading.mark_pdf(doc.tobytes(), g, ctx), filetype="pdf") as out:
        page = out[1]
        green, red, orange = (_strokes(page, c) for c in (grading.GREEN, grading.RED, grading.ORANGE))
    # כל סימן בעיגול לבן עם מסגרת בצבע שלו: ✓ = עיגול + קו · ✗ = עיגול + שני קווים · ✓✗ = אליפסה + קו + שני קווים
    assert len(green) == 2 and len(red) == 3 and len(orange) == 4
    circles = [d for d in green + red + orange if d.get("fill") == (1.0, 1.0, 1.0)]
    assert len(circles) == 3
    # העיגול של שאלה 1 מימין למלבן שלה, בגובה שלו, וגדול מספיק כדי לבלוט
    r = next(d["rect"] for d in green if d.get("fill"))
    assert r.x0 >= 760 / 1000 * 595 and abs((r.y0 + r.y1) / 2 - 115 / 1000 * 842) < 20 and r.height >= 20
    # ✓✗ רחב יותר מ-✓
    assert next(d["rect"] for d in orange if d.get("fill")).width > r.width * 1.5
    assert grading.check_kind(10, 10) == "check" and grading.check_kind(0, 10) == "cross" and grading.check_kind(3, 10) == "half"


def test_a_badge_sits_on_free_paper_next_to_the_label_not_on_the_writing():
    # 2026-11-12: מימין למספר הסעיף בלבד, העיגול ישב על "A=" שהסטודנט כתב אחרי "(ב)"
    doc, page = _scan_page((130, 300, 560, 330))   # "(ב) A = ..." : התווית בשמאל, והכתב ממשיך ימינה
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 10)])
    g = grading.Graded([10], [""], 100, "", [], places=[grading.Mark(1, 210, 352, 290, 395, "שאלה 1")])
    ink = grading.Ink(page)  # לפני שהעיגול מצויר (אחרי, הוא עצמו נספר כדיו)
    (badge,) = grading._place_checks(doc, g, ctx)[1]
    assert ink.density(badge.x0 / 595 * 1000, badge.y0 / 842 * 1000, badge.x1 / 595 * 1000, badge.y1 / 842 * 1000) < 0.02
    assert abs((badge.y0 + badge.y1) / 2 - 315) < 45 or badge.x1 < 130  # עדיין ליד התווית


def test_badges_do_not_pile_up_and_notes_go_around_them():
    doc, page = _scan_page((100, 100, 500, 130))
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 10), grading.Question("שאלה 2", 10)])
    places = [grading.Mark(1, 700, 118, 800, 150, "שאלה 1"), grading.Mark(1, 700, 125, 800, 157, "שאלה 2")]  # כמעט באותו מקום
    marks = [grading.Mark(1, 170, 118, 840, 156, "הערה שלא עולה על הסימן")]
    g = grading.Graded([10, 0], ["", ""], 50, "", marks, places=places)
    taken = grading._place_checks(doc, g, ctx)
    a, b = taken[1]
    assert not a.intersects(b)
    grading._place_marks(doc, g, grading._archive(), taken)
    note = next(b for b in page.get_text("blocks") if "הערה" in b[4])
    assert not pymupdf.Rect(note[:4]).intersects(a) and not pymupdf.Rect(note[:4]).intersects(b)


def test_math_in_a_note_reads_left_to_right():
    # MuPDF הפך את "3-i" בסוף משפט ל-"i-3": כל ביטוי עטוף ב-LRE...PDF, מקף אחרי אות עברית נשאר בחוץ
    assert grading._ltr("4-4i+2i+2 = 6-2i, לא 6+2i; הקבוע 3-i") == \
        "\u202a4-4i+2i+2 = 6-2i\u202c, לא \u202a6+2i\u202c; הקבוע \u202a3-i\u202c"
    assert grading._ltr("חסר להראות ש-(2,2)∉A") == "חסר להראות ש-\u202a(2,2)∉A\u202c"
    assert grading._ltr("הקבוע -2+i") == "הקבוע \u202a-2+i\u202c"
    assert grading._ltr("בלי נוסחה בכלל") == "בלי נוסחה בכלל"
    assert "\u202a" not in grading._html("{(0,0)}", math=False)


def test_a_note_far_from_its_box_gets_a_line_to_it():
    doc, page = _scan_page((60, 300, 560, 360))   # שורה כתובה ברוחב כל העמוד
    for y in range(240, 300, 3):                  # וגם מעליה ומתחתיה
        page.draw_line((60, y), (560, y), color=(0, 0, 0.3), width=1.2)
    for y in range(360, 420, 3):
        page.draw_line((60, y), (560, y), color=(0, 0, 0.3), width=1.2)
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 100)])
    g = grading.Graded([90], [""], 90, "", [grading.Mark(1, 300, 360, 700, 425, "הערה בשוליים")])
    with pymupdf.open(stream=grading.mark_pdf(doc.tobytes(), g, ctx), filetype="pdf") as out:
        lines = [d for d in out[1].get_drawings() if d.get("color") and d["color"][0] > 0.8 and d["color"][1] < 0.1
                 and len(d["items"]) == 1 and d["items"][0][0] == "l"]
        assert "הערה בשוליים" in text(out[1])
    assert lines  # ההערה לא ליד המלבן (הכול כתוב סביבו), אז קו מוביל אליו


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
def test_grading_writes_grades_csv_and_marked_pdfs(root, monkeypatch):
    monkeypatch.setattr(grading, "refine_box", lambda ink, box: box)  # כאן בודקים מיקום, לא הצמדה לכתב
    a = asg(root)
    fake = FakeClaude()
    rep = grading.grade_assignment(a.dir, ask=fake, parallel=3)
    assert rep.graded == ["0001", "0002", "0003"] and not rep.failed and len(fake.requests) == 3

    mine = a.dir / "Grades by בודק א.csv"  # הבדיקה כותבת לקובץ של הבודק, לא ל-Grades.csv המשותף
    assert not (a.dir / grading.GRADES).exists()
    rows = read_csv(mine)
    assert list(rows[0])[:3] == ["number", "grade", "feedback"]  # בדיוק מה ש-upload.py קורא
    assert mine.read_bytes().startswith(b"\xef\xbb\xbf")
    assert [(r["number"], r["grade"], r["points"]) for r in rows] == [(n, "85", "20;15;20;20;10") for n in ("0001", "0002", "0003")]
    assert rows[0]["approved"] == "" and rows[0]["review"] == "" and rows[0]["graded_by"] == "בודק א" and rows[0]["graded_at"]
    assert set(claims.read_all(a.dir)) == {"0001", "0002", "0003"}  # ומה שנבדק נרשם על שם הבודק

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


def test_a_claim_that_syncs_in_mid_run_stops_that_submission(root):
    """שניים לקחו את 0003 לפני ש-OneDrive סנכרן. הסימון שלה (מוקדם יותר) מגיע באמצע הבדיקה שלי: אני מוותר עליה."""
    a = asg(root)

    def first(req):
        claims._write(a.dir, "בודקת ב", {"0003": "2000-01-01T00:00:00"})  # OneDrive הביא את הקובץ שלה
        return answer()
    fake = FakeClaude(first)
    progress = {}
    rep = grading.grade_assignment(a.dir, ["0001", "0002", "0003"], ask=fake, parallel=1, on_progress=progress.__setitem__)
    assert rep.graded == ["0001", "0002"] and len(fake.requests) == 2 and progress["0003"] == "taken"
    assert claims.read_all(a.dir)["0003"]["who"] == "בודקת ב"
    assert rep.summary() == "נבדקו 2 מתוך 2" and any("0003" in note for note in rep.notes)


def test_two_graders_split_the_work_without_sharing_a_file(root):
    """שני בודקים בשני מחשבים: כל אחד כותב רק לקבצים שלו, ומה שהשני לקח לא נבדק."""
    a = asg(root)
    claims.take(a.dir, ["0002"], who="בודקת ב")
    fake = FakeClaude()
    progress = {}
    rep = grading.grade_assignment(a.dir, ask=fake, on_progress=progress.__setitem__)
    assert rep.graded == ["0001", "0003"] and len(fake.requests) == 2 and progress["0002"] == "taken"
    assert any("0002" in note for note in rep.notes)
    assert rep.summary() == "נבדקו 2 מתוך 2"

    rep = grading.grade_assignment(a.dir, ["0002"], ask=FakeClaude(lambda req: answer(points=(10, 10, 10, 10, 10))),
                                   who="בודקת ב")
    assert rep.graded == ["0002"]
    assert [p.name for p in grades.files(a.dir)] == ["Grades by בודק א.csv", "Grades by בודקת ב.csv"]
    rows = grading.read_grades(a.dir)
    assert {n: r["grade"] for n, r in rows.items()} == {"0001": "85", "0002": "50", "0003": "85"}
    assert rows["0002"]["graded_by"] == "בודקת ב"
    assert grading.pending(a.dir) == []


def test_merged_grades_prefer_approved_then_newest(root):
    a = asg(root)
    grading.write_grades(a.dir, {"0001": {"number": "0001", "grade": "60", "approved": "כן"},
                                 "0002": {"number": "0002", "grade": "61"}})
    grades.write_file(grades.own_file(a.dir, "א"), {
        "0001": {"number": "0001", "grade": "90", "graded_at": "2026-10-23T10:00:00"},
        "0002": {"number": "0002", "grade": "70", "graded_at": "2026-10-23T10:00:00"},
        "0003": {"number": "0003", "grade": "71", "graded_at": "2026-10-23T11:00:00"}})
    grades.write_file(grades.own_file(a.dir, "ב"), {
        "0003": {"number": "0003", "grade": "72", "graded_at": "2026-10-23T09:00:00"}})
    rows = grading.read_grades(a.dir)
    # מאושרת גוברת, אחריה הבדיקה האחרונה, ושורה בלי זמן (Grades.csv הישן) מפסידה לשורה עם זמן
    assert {n: r["grade"] for n, r in rows.items()} == {"0001": "60", "0002": "70", "0003": "71"}


def test_pending_skips_graded_and_extra_marked_files(root):
    a = asg(root)
    (a.dir / paths.MARKED / "0001-2.pdf").write_bytes(b"%PDF marked by hand")
    grading.write_grades(a.dir, {"0002": {"number": "0002", "grade": "90", "feedback": ""}})
    assert grading.pending(a.dir) == ["0003"]
    assert set(grading.marked_files(a.dir)) == {"0001"}  # 0001-2.pdf belongs to 0001


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


def test_rotated_page_is_marked_where_it_is_seen(monkeypatch):
    monkeypatch.setattr(grading, "refine_box", lambda ink, box: box)
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


# ---------- Grading notes, טעויות נפוצות ובדיקה ידנית ----------


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


def test_save_review_of_work_graded_before_notes_keeps_its_marks(root):
    """עבודה שנבדקה לפני שהיו Grading notes: מחליפים רק את עמוד הסיכום, והסימונים שב-PDF נשארים."""
    a = asg(root)
    grading.grade_assignment(a.dir, ["0002"], ask=lambda req: detailed())
    grading.notes_path(a.dir, "0002").unlink()
    with pymupdf.open(a.dir / paths.MARKED / "0002.pdf") as doc:
        pages, marked_page = doc.page_count, len(doc[1].get_drawings())
    grading.save_review(a.dir, "0002", [20] * 5, [], "", by="x", reason="ערעור התקבל")
    with pymupdf.open(a.dir / paths.MARKED / "0002.pdf") as doc:
        assert doc.page_count == pages and "ציון: 100 מתוך 100" in text(doc[0]) and len(doc[1].get_drawings()) == marked_page


def test_save_review_refuses_what_it_cannot_match(root):
    a = asg(root)
    with pytest.raises(grading.GradingError):
        grading.save_review(a.dir, "0009", [20] * 5, [], "", by="x")  # אין הגשה כזו
    with pytest.raises(grading.GradingError):
        grading.save_review(a.dir, "0001", [20] * 4, [], "", by="x")  # ניקוד לא לכל השאלות
    assert not (a.dir / grading.GRADES).exists()


# ---------- ניקוד רק לפי המחוון ----------


def test_a_question_without_points_in_the_rubric_blocks_grading(root):
    a = asg(root)
    rubric = json.loads(json.dumps(RUBRIC))
    rubric["questions"][4]["points"] = None
    save_details(a, {**a.details(), "rubric": rubric})
    with pytest.raises(grading.NoRubric) as e:
        grading.grade_assignment(a.dir, ["0001"], ask=FakeClaude())
    assert LABELS[4] in str(e.value)


def test_points_above_the_rubric_are_never_kept(root):
    a = asg(root)
    ctx = grading.load_context(a.dir)
    g = grading.parse_answer(detailed(points=(20, 20, 20, 20, 23)), ctx, 1)
    assert g.points[4] == 20 and "יותר מהמחוון" in g.review and f"{LABELS[4]}: 23 מתוך 20" in g.review
    with pytest.raises(grading.GradingError) as e:
        grading.save_review(a.dir, "0001", [20, 20, 20, 20, 24], [], "", by="x")
    assert f"{LABELS[4]}: 24 מתוך 20" in str(e.value) and not (a.dir / grading.GRADES).exists()


def test_the_rubric_points_come_from_the_pedagogy_folder(root):
    """בלי rubric ב-Assignment details.json הניקוד נלקח מטבלת המחוון שבתיקייה "פדגוגי", כמו שהצוות כותב אותו."""
    a = asg(root)
    save_details(a, {**a.details(), "rubric": None})
    folder = a.dir / "פדגוגי"
    folder.mkdir()
    (folder / "Rubric.md").write_text("# מחוון\n\n| שאלה | נק' | סעיפים |\n|---|---|---|\n| קבוצות 11 | 20 | א 3 |\n"
                                      "| קבוצות 12 | 24 | |\n| **מרוכבים 6** | 12 | |\n| מרוכבים 7 | 20 | |\n| מרוכבים 8 | 24 | |\n",
                                      encoding="utf-8")
    (folder / "Rubric v1.md").write_text("| קבוצות 11 | 99 |\n", encoding="utf-8")  # גרסה ישנה: לא נקראת
    ctx = grading.load_context(a.dir)
    assert [q.points for q in ctx.questions] == [20, 24, 12, 20, 24] and not ctx.no_rubric
    assert "Rubric.md" in ctx.rubric_text and "99" not in ctx.rubric_text
    (folder / "Rubric.md").write_text("| קבוצות 11 | 20 |\n", encoding="utf-8")
    assert "אין ניקוד" in grading.load_context(a.dir).no_rubric  # שאלה בלי ניקוד: עדיין אין ציונים


def test_stop_leaves_the_rest_waiting_and_what_was_sent_is_saved(root):
    a = asg(root)
    stop = threading.Event()

    def ask(req):
        stop.set()  # the button is pressed while the first submission is with Claude
        return answer()
    rep = grading.grade_assignment(a.dir, ask=ask, parallel=1, stop=stop)
    assert len(rep.graded) == 1 and len(rep.stopped) == 2 and not rep.failed
    assert rep.stop_reason == "עצרת את הבדיקה" and "נעצרה: 2 לא נבדקו" in rep.summary()
    assert sorted(grading.pending(a.dir)) == rep.stopped  # still waiting: the next "Grade" takes them
    assert all("error" not in grading.read_notes(a.dir, n) for n in rep.stopped)


def _scan_page(ink_rect=(100, 100, 300, 140)):
    """עמוד לבן עם פס "כתב יד" כהה אחד, ב-ink_rect (נקודות)."""
    doc = pymupdf.open()
    page = doc.new_page()
    for y in range(int(ink_rect[1]), int(ink_rect[3]), 3):
        page.draw_line((ink_rect[0], y), (ink_rect[2], y), color=(0, 0, 0.3), width=1.2)
    return doc, page


def test_box_on_empty_paper_snaps_to_the_nearby_writing():
    doc, page = _scan_page((100, 400, 300, 440))
    ink = grading.Ink(page)
    # Claude סימן מקום ריק מעל הכתב: המלבן מוצמד לכתב עצמו
    x0, y0, x1, y1 = grading.refine_box(ink, (150, 300, 600, 360))
    assert abs(x0 / 1000 * 595 - 100) < 15 and abs(x1 / 1000 * 595 - 300) < 15
    assert abs(y0 / 1000 * 842 - 400) < 15 and abs(y1 / 1000 * 842 - 440) < 15
    # מלבן גדול שמקיף את הכתב מתהדק אליו
    big = grading.refine_box(ink, (0, 0, 1000, 1000))
    assert big[2] - big[0] < 400 and big[3] - big[1] < 100


def test_mark_with_no_writing_anywhere_is_dropped_and_its_note_goes_to_the_summary():
    doc, page = _scan_page((100, 20, 400, 60))
    ink = grading.Ink(page)
    assert grading.refine_box(ink, (700, 800, 900, 900)) is None
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 100)])
    g = grading.Graded([100], [""], 100, "", [grading.Mark(1, 700, 800, 900, 900, "הערה אבודה")])
    with pymupdf.open(stream=grading.mark_pdf(doc.tobytes(), g, ctx), filetype="pdf") as out:
        assert "הערה אבודה" in text(out[0])
        assert not [d for d in out[1].get_drawings() if d.get("color") and d["color"][0] > 0.8 and d["color"][1] < 0.1]
    assert g.marks == []


def test_note_goes_to_free_paper_not_over_the_writing():
    doc, page = _scan_page((100, 100, 500, 140))
    for y in range(160, 200, 3):  # עוד שורה כתובה ישר מתחת
        page.draw_line((100, y), (500, y), color=(0, 0, 0.3), width=1.2)
    ink = grading.Ink(page)
    box = pymupdf.Rect(100, 100, 500, 140)
    note = grading._note_rect(box, page.rect, "חסר נימוק להכלה", 11, ink)
    assert note.y1 <= box.y0  # מתחת יש כתב, אז ההערה מעל
    norm = (note.x0 / 595 * 1000, note.y0 / 842 * 1000, note.x1 / 595 * 1000, note.y1 / 842 * 1000)
    assert ink.density(*norm) < 0.25


def test_every_note_on_a_page_is_written_not_only_the_first():
    # באג אמיתי (2026-11-07): ההערה השנייה בעמוד לא נכתבה. _note_rect חישב חפיפה עם r.intersect(t),
    # שמשנה את r עצמו, אז המקום שנבחר להערה התכווץ או התהפך והכתיבה נכשלה בשקט
    doc, page = _scan_page((100, 200, 300, 230))
    for y in range(380, 410, 3):  # שורה כתובה שנייה, רחוקה מהראשונה
        page.draw_line((100, y), (350, y), color=(0, 0, 0.3), width=1.2)
    for y in range(560, 590, 3):  # ושלישית
        page.draw_line((100, y), (320, y), color=(0, 0, 0.3), width=1.2)
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 100)])
    notes = ["הערה ראשונה", "הערה שנייה", "הערה שלישית"]
    g = grading.Graded([90], [""], 90, "", [
        grading.Mark(1, 168, 237, 504, 273, notes[0]),
        grading.Mark(1, 168, 451, 588, 487, notes[1]),
        grading.Mark(1, 168, 665, 538, 701, notes[2]),
    ])
    with pymupdf.open(stream=grading.mark_pdf(doc.tobytes(), g, ctx), filetype="pdf") as out:
        written = text(out[1])
    assert len(g.marks) == 3
    assert all(n in written for n in notes)


def test_shrinking_does_not_blacken_pages_with_several_images():
    # באג אמיתי: rewrite_images שיבש תמונה שנייה בעמוד (פס שחור במקום השאלה)
    rnd = random.Random(3)
    big = pymupdf.Pixmap(pymupdf.csRGB, 1700, 2200, bytes(rnd.getrandbits(8) for _ in range(1700 * 2200 * 3)), False).tobytes("jpeg", jpg_quality=95)
    strip = pymupdf.Pixmap(pymupdf.csRGB, 600, 100, bytes([240]) * (600 * 100 * 3), False).tobytes("png")
    doc = pymupdf.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_image(page.rect, stream=big)
        page.insert_image(pymupdf.Rect(50, 50, 500, 130), stream=strip)
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 100)])
    g = grading.Graded([100], [""], 100, "", [])
    out = grading.mark_pdf(doc.tobytes(), g, ctx, max_bytes=300_000)
    assert len(out) <= 300_000
    with pymupdf.open(stream=out, filetype="pdf") as marked:
        assert marked.page_count == 3


def test_model_images_carry_a_numbered_grid_but_files_do_not():
    from grading.render import render_pdf
    pdf = homework_pdf("x", "t", pages=1)
    plain, gridded = render_pdf(pdf)[0], render_pdf(pdf, grid=True)[0]
    assert (plain.width, plain.height) == (gridded.width, gridded.height) and plain.data != gridded.data
    pix = pymupdf.Pixmap(gridded.data)
    # קו הרשת ב-x=500 צבוע כתום באמצע העמוד
    assert any(pix.pixel(pix.width // 2, y)[2] < 200 for y in range(pix.height // 2, pix.height // 2 + 40))
    # ומספר העמוד ("page 1") כתוב בכתום בראש התמונה, באמצע, כדי שהמודל לא ייקח אותו משם הקובץ
    top = [(x, y) for y in range(2, int(pix.height * 0.03)) for x in range(int(pix.width * 0.4), int(pix.width * 0.6), 2)
           if pix.pixel(x, y)[2] < 120 and pix.pixel(x, y)[0] > 200]
    assert len(top) > 20
    assert not [(x, y) for y in range(2, int(pix.height * 0.03)) for x in range(int(pix.width * 0.4), int(pix.width * 0.6), 2)
                if pymupdf.Pixmap(plain.data).pixel(x, y)[2] < 120]
