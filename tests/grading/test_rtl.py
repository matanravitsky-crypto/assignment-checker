"""grading/rtl.py: עברית עם מתמטיקה נכתבת בסדר הנכון על ה-PDF.

MuPDF (insert_htmlbox) מתעלם מכל סימן כיוון, והסטודנטים ראו "yi-" במקום "-yi" ו-"7-=1+8" במקום "1+8=-7"
(2026-11-13/14). כאן בודקים את מה שנכתב באמת: כל אות והמקום שלה בעמוד (rawdict), משמאל לימין."""
from __future__ import annotations

import re
import time

import pymupdf
import pytest

from grading import grade as grading
from grading import rtl

LONG = "בפתיחת הסוגריים -yi הפך ל-+yi, ולכן x יצא שגוי: 1+8=-7. הזוג (1,-1) ו-{(3-i,-2-2i)} ו-A≠B."


def visual(page) -> list[str]:
    """כל שורה בעמוד כפי שהעין רואה אותה משמאל לימין: האותיות לפי x, שורה לפי קו הבסיס."""
    chars = [c for b in page.get_text("rawdict")["blocks"] for l in b.get("lines", []) for s in l["spans"] for c in s["chars"]]
    rows: dict[int, list] = {}
    for c in chars:
        rows.setdefault(round(c["origin"][1]), []).append(c)
    out = []
    for _, row in sorted(rows.items()):
        s = "".join(c["c"] for c in sorted(row, key=lambda c: c["bbox"][0]))
        out.append(" ".join(s.replace("\xad", "-").replace("\xa0", " ").split()))
    return out


def drawn(text: str, width: float = 560, size: float = 12, **kw) -> tuple[pymupdf.Document, list[str]]:
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    assert rtl.draw(page, pymupdf.Rect(600 - 20 - width, 20, 580, 380), text, size, **kw)
    return doc, visual(page)


# ---------- הקטעים ----------
def test_the_math_rule_is_the_one_grade_uses():
    assert rtl.MATH.pattern == grading._MATH.pattern


def test_segments_keep_the_edge_rules_of_grade():
    assert rtl.segments("ל-+yi") == [("ל-", False), ("+yi", True)]
    assert rtl.segments("הגשה 0 (הערה בלבד)") == [("הגשה ", False), ("0", True), (" (הערה בלבד)", False)]
    assert rtl.segments("הגשה 0 - קבוצות") == [("הגשה ", False), ("0", True), (" - קבוצות", False)]
    assert rtl.segments("נראה כ-7- ולא 7") == [("נראה כ-", False), ("-7", True), (" ולא ", False), ("7", True)]
    assert rtl.segments("4-4i+2i+2 = 6-2i, לא 6+2i") == [("4-4i+2i+2 = 6-2i", True), (", לא ", False), ("6+2i", True)]
    # סוגר בלי זוג בקצה הביטוי שייך לעברית ("(ראו 3)"), סוגריים שלמים נשארים בביטוי
    assert rtl.segments("(ראו 3)") == [("(ראו ", False), ("3", True), (")", False)]
    assert rtl.segments("הזוג (1,-1) נכון") == [("הזוג ", False), ("(1,-1)", True), (" נכון", False)]
    assert rtl.segments("הקטע [0,1) סגור") == [("הקטע ", False), ("[0,1)", True), (" סגור", False)]
    assert rtl.segments("{(0,0)}", math=False) == [("{(0,0)}", False)]


# ---------- הסדר על העמוד ----------
@pytest.mark.parametrize("text, seen", [
    ("-yi", "-yi"),
    ("ל-+yi", "+yi-ל"),
    ("1+8=-7", "1+8=-7"),
    ("(1,-1)", "(1,-1)"),
    ("הגשה 0 (הערה בלבד)", "(דבלב הרעה) 0 השגה"),
    ("הגשה 0 - קבוצות", "תוצובק - 0 השגה"),
    ("חסר להראות ש-(2,2)∉A", "(2,2)∉A-ש תוארהל רסח"),
    ("הקבוע הוא -2+i ולא 2-i", "2-i אלו -2+i אוה עובקה"),
    ("המרחב ב-ℝ² (ראו 3) נכון.", ".ןוכנ (3 ואר) ℝ²-ב בחרמה"),
    (LONG, ".A≠B-ו {(3-i,-2-2i)}-ו (1,-1) גוזה .1+8=-7 :יוגש אצי x ןכלו ,+yi-ל ךפה -yi םיירגוסה תחיתפב"),
])
def test_each_probe_is_drawn_in_the_order_a_reader_sees(text, seen):
    _, lines = drawn(text)
    assert lines == [seen]


def test_math_tokens_read_left_to_right_and_hebrew_words_right_to_left():
    _, (line,) = drawn(LONG)
    for token in ("-yi", "+yi", "1+8=-7", "(1,-1)", "{(3-i,-2-2i)}", "A≠B"):
        assert line.count(token) == 1, token
    words = [w for w in re.findall(r"[֐-׿]+", LONG)]
    at = [line.index(w[::-1]) for w in words]
    assert at == sorted(at, reverse=True)  # המילה הראשונה הכי מימין


def _ink(pix) -> list[list[int]]:
    """התמונה בגווני אפור, חתוכה למלבן שיש בו דיו."""
    rows = [[pix.pixel(x, y)[0] for x in range(pix.width)] for y in range(pix.height)]
    ys = [y for y, r in enumerate(rows) if min(r) < 160]
    xs = [x for x in range(pix.width) if min(r[x] for r in rows) < 160]
    return [r[xs[0]:xs[-1] + 1] for r in rows[ys[0]:ys[-1] + 1]]


def _diff(a, b) -> float:
    """ההפרש הממוצע לפיקסל. פיקסל אחד של הבדל בגודל (מיקום שבור) נחתך."""
    if abs(len(a) - len(b)) > 1 or abs(len(a[0]) - len(b[0])) > 1:
        return 255.0
    h, w = min(len(a), len(b)), min(len(a[0]), len(b[0]))
    return sum(abs(a[y][x] - b[y][x]) for y in range(h) for x in range(w)) / (h * w)


@pytest.mark.skipif(grading._FONT is None, reason="no Hebrew font on this computer")
@pytest.mark.parametrize("text", ["-4", "1+8=-7", "(1,-1)"])
def test_math_looks_in_the_pixels_exactly_as_written(text):
    # לא רק במה ש-get_text מחזיר: התמונה עצמה זהה לטקסט שנכתב משמאל לימין בלי שום bidi (insert_text)
    def render(draw):
        doc = pymupdf.open()
        page = doc.new_page(width=300, height=60)
        draw(page)
        return _ink(page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY))
    ours = render(lambda p: rtl.draw(p, pymupdf.Rect(10, 10, 290, 55), text, 30))

    def plain(s):
        def draw(p):
            p.insert_font(fontname="ar", fontfile=str(grading._FONT))
            p.insert_text((20, 40), s, fontname="ar", fontsize=30)
        return draw
    assert _diff(ours, render(plain(text))) < 25
    assert _diff(ours, render(plain(text[::-1]))) > 25    # הבדיקה מבחינה בין הכיוונים


# ---------- שבירת שורות ----------
def test_a_long_note_wraps_right_aligned_and_keeps_each_expression_whole():
    doc, lines = drawn(LONG, width=200)
    assert len(lines) >= 3
    joined = " ".join(lines)
    for token in ("1+8=-7", "(1,-1)", "{(3-i,-2-2i)}", "A≠B", "+yi-ל"):
        assert token in joined, token
    assert "תחיתפב" in lines[0] and "A≠B" in lines[-1]  # השורה הראשונה מתחילה במילה הראשונה
    page = doc[0]
    for b in page.get_text("dict")["blocks"]:
        for l in b["lines"]:
            assert l["bbox"][2] <= 580.5
    right: dict[int, float] = {}
    for b in page.get_text("rawdict")["blocks"]:
        for l in b["lines"]:
            for s in l["spans"]:
                for c in s["chars"]:
                    if c["c"].strip():
                        y = round(c["origin"][1])
                        right[y] = max(right.get(y, 0), c["bbox"][2])
    assert all(r > 575 for r in right.values())  # כל שורה מיושרת לימין


def test_an_expression_wider_than_the_line_breaks_at_its_spaces_and_each_part_reads_left_to_right():
    text = "התוצאה 4-4i+2i+2 = 6-2i = 6-2i+0 = 6-2i+0+0 שגויה"
    _, lines = drawn(text, width=110)
    joined = " | ".join(lines)
    for part in ("4-4i+2i+2", "6-2i", "6-2i+0", "6-2i+0+0"):
        assert part in joined
    # בתוך שורה, חלקים של אותו ביטוי נשארים משמאל לימין ובסדר המקורי (איפה השורה נשברת תלוי ברוחב הגופן:
    # Arial ב-Windows, DejaVu ב-CI), כלומר כל שורה היא רצף רציף של הביטוי
    orig = ["4-4i+2i+2", "=", "6-2i", "=", "6-2i+0", "=", "6-2i+0+0"]
    for l in lines:
        toks = [t for t in l.split() if not any("֐" <= ch <= "׿" for ch in t)]
        if toks:
            assert any(orig[i:i + len(toks)] == toks for i in range(len(orig))), l


def test_measure_matches_what_is_drawn_and_fit_gives_up_when_nothing_fits():
    h = rtl.measure(LONG, 200, 12)
    doc = pymupdf.open()
    page = doc.new_page()
    assert rtl.draw(page, pymupdf.Rect(100, 100, 300, 100 + h), LONG, 12) == pytest.approx(h)
    assert rtl.fit(LONG, pymupdf.Rect(0, 0, 200, h - 5), 12)[0] < 12        # קצת קטן יותר: מוקטן
    assert rtl.fit(LONG, pymupdf.Rect(0, 0, 30, 6), 12) is None             # לא נכנס בכלל
    note = grading._html(LONG, 12)
    assert grading._write(page, pymupdf.Rect(0, 0, 30, 6), note, None) is False  # ההערה תעבור לעמוד הסיכום


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_a_note_on_a_rotated_page_looks_like_on_an_upright_one(rotation):
    def render(rot):
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=300)
        page.set_rotation(rot)
        shown = page.rect
        rtl.draw(page, pymupdf.Rect(20, 20, shown.width - 20, 120), LONG, 12, "#d90000")
        return page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)
    up, turned = render(0), render(rotation)
    if rotation == 180:
        assert (up.width, up.height) == (turned.width, turned.height)
        diff = sum(abs(a - b) for a, b in zip(up.samples, turned.samples)) / len(up.samples)
        assert diff < 2
    # 90/270: אותו טקסט באותו גודל, בשורות לרוחב העמוד המוצג (לא לאורכו)
    ink = [(x, y) for y in range(turned.height) for x in range(turned.width) if turned.pixel(x, y)[0] < 200]
    xs, ys = [p[0] for p in ink], [p[1] for p in ink]
    assert max(xs) - min(xs) > 3 * (max(ys) - min(ys)) and min(ys) >= 18 and max(xs) <= turned.width - 18


# ---------- עמוד הסיכום ----------
def _summary(comments, feedback="", extra=None):
    ctx = grading.Context("הגשה 0 (הערה בלבד)", "אלגברה לינארית",
                          [grading.Question(f"קבוצות 11{c}", 10) for c in "אבגדה"[:len(comments)]])
    pts = [6] * len(comments)
    g = grading.Graded(pts, comments, 60, feedback, [], lost=extra or [])
    doc = pymupdf.open()
    doc.new_page()
    t = time.perf_counter()
    grading._summary_page(doc, g, ctx, None, extra)
    return doc, time.perf_counter() - t


def test_the_summary_page_shows_comments_chips_and_feedback_in_reading_order():
    doc, took = _summary([LONG, "חסר להראות ש-(2,2)∉A"], feedback=LONG, extra=["עמוד 4: הזוג (1,-1) ו-A≠B."])
    lines = visual(doc[0])
    assert "(דבלב הרעה) 0 השגה" in lines
    # שורה בטבלה, משמאל לימין: ההערה, "-4" (לא "4-"), ושם השאלה בקצה הימני
    assert any(l.startswith(".A≠B-ו") and l.endswith("-4א11 הלאש") for l in lines)
    assert any(l.endswith("(2,2)∉A-ש תוארהל רסח-4ב11 הלאש") for l in lines)
    assert any("1+8=-7" in l and "+yi-ל" in l for l in lines)
    assert any("(2,2)∉A-ש" in l for l in lines)
    assert any(".A≠B-ו (1,-1) גוזה :4 דומע" in l for l in lines)
    text = " ".join(doc[0].get_text().split())
    assert "מתוך 100" in text and "משוב" in text and "הערות נוספות" in text
    assert took < 1.0


def test_a_crowded_summary_still_fits_one_page():
    doc, _ = _summary([LONG * 3] * 5, feedback=LONG * 6, extra=[LONG] * 8)
    page = doc[0]
    bottom = max(c["bbox"][3] for b in page.get_text("rawdict")["blocks"] for l in b.get("lines", [])
                 for s in l["spans"] for c in s["chars"])
    assert bottom <= page.rect.height - 20
    assert sum("1+8=-7" in l for l in visual(page)) >= 5 + 6 + 8    # הכול נכתב, מוקטן


def test_a_note_is_balanced_with_no_word_alone_on_its_last_line():
    # 2026-11-14: "חסרה בדיקה שהנקודה (1,-1) נמצאת על" ואז "L2" לבד בשורה השנייה
    text = "חסרה בדיקה שהנקודה (1,-1) נמצאת על L2"
    greedy = rtl.layout(text, 150 / 10)
    even = rtl.balance(text, 150, 10)
    assert len(even.lines) == len(greedy.lines) == 2
    assert min(even.widths) > 0.5 * max(even.widths) and min(greedy.widths) < min(even.widths)
