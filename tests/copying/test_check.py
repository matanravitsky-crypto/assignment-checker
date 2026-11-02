"""copying/check.py: חשד להעתקה בלי טוקנים. סריקות בדויות: קווים אקראיים כמו כתב יד, צולמו ל-JPEG."""
from __future__ import annotations

import json
import random

import pymupdf
import pytest

from copying import check
from moodle import paths


def scan(seed: int, quality: int = 80, dpi: int = 100) -> bytes:
    """תמונה של עמוד "בכתב יד": שורות של קווים אקראיים. אותו seed = אותו עמוד."""
    rnd = random.Random(seed)
    doc = pymupdf.open()
    page = doc.new_page()
    for row in range(rnd.randint(8, 20)):
        y = 60 + row * 35
        x = rnd.uniform(40, 120)
        while x < rnd.uniform(380, 550):
            page.draw_line((x, y + rnd.uniform(-8, 8)), (x + rnd.uniform(4, 18), y + rnd.uniform(-8, 8)), width=1.5)
            x += rnd.uniform(4, 18)
    if rnd.random() < .5:
        page.draw_rect(pymupdf.Rect(300, 600, 300 + rnd.uniform(50, 200), 650 + rnd.uniform(0, 120)), width=2)
    data = page.get_pixmap(dpi=dpi).tobytes("jpeg", jpg_quality=quality)
    doc.close()
    return data


def pdf_of(*images: bytes, author: str = "", created: str = "") -> bytes:
    doc = pymupdf.open()
    for img in images:
        page = doc.new_page()
        page.insert_image(page.rect, stream=img)
    doc.set_metadata({"author": author, "creationDate": created})
    data = doc.tobytes()
    doc.close()
    return data


def blank() -> bytes:
    doc = pymupdf.open()
    data = doc.new_page().get_pixmap(dpi=60).tobytes("jpeg")
    doc.close()
    return data


@pytest.fixture
def assignment(tmp_path):
    d = tmp_path / "Linear Algebra" / "Assignment 0"
    (d / paths.TO_GRADE).mkdir(parents=True)
    return d


def put(d, name: str, data: bytes) -> None:
    (d / paths.TO_GRADE / name).write_bytes(data)


def pairs(rep) -> dict[tuple[str, str], set[str]]:
    return {(p["a"], p["b"]): {r["kind"] for r in p["reasons"]} for p in rep.pairs}


def test_same_file_same_scan_and_unrelated(assignment):
    original = pdf_of(scan(1), scan(2))
    put(assignment, "0001.pdf", original)
    put(assignment, "0002.pdf", original)                                   # אותו קובץ בדיוק
    put(assignment, "0003.pdf", pdf_of(scan(1, quality=50, dpi=90), scan(2, quality=45, dpi=80)))  # אותן סריקות, דחוסות מחדש
    put(assignment, "0004.pdf", pdf_of(scan(3), scan(4)))                   # עבודה אחרת
    rep = check.check_assignment(assignment)
    found = pairs(rep)
    assert found[("0001", "0002")] >= {"file", "doc_id", "page"}
    assert found[("0001", "0003")] == {"page"} and found[("0002", "0003")] == {"page"}
    assert not any("0004" in pair for pair in found)
    pages = next(r["pages"] for p in rep.pairs if (p["a"], p["b"]) == ("0001", "0003") for r in p["reasons"])
    assert [(a, b) for a, b, _ in pages] == [(1, 1), (2, 2)]
    assert all(p["level"] == "strong" for p in rep.pairs)


def test_many_different_scans_never_match(assignment):
    for i in range(30):
        put(assignment, f"{i + 1:04d}.pdf", pdf_of(scan(100 + i)))
    assert check.check_assignment(assignment).pairs == []


def test_page_numbers_run_across_files_of_a_number(assignment):
    put(assignment, "0001.pdf", pdf_of(scan(1)))
    put(assignment, "0001-2.jpg", scan(5))       # עמוד 2 של 0001
    put(assignment, "0001-3.jpg", scan(6))       # עמוד 3 של 0001
    put(assignment, "0002.pdf", pdf_of(scan(5, quality=60), scan(6, quality=60)))
    rep = check.check_assignment(assignment)
    (pair,) = rep.pairs
    assert [(a, b) for a, b, _ in pair["reasons"][0]["pages"]] == [(2, 1), (3, 2)]


def test_a_page_many_have_is_listed_apart_and_blank_pages_ignored(assignment):
    sheet = scan(999)
    n = check.COMMON_PAGE + 2
    for i in range(n):
        put(assignment, f"{i + 1:04d}.pdf", pdf_of(sheet, blank(), scan(200 + i)))
    rep = check.check_assignment(assignment)
    assert rep.pairs == []
    (group,) = rep.repeated  # דף השאלות: לא זוגות, אלא קבוצה אחת שאדם מסתכל עליה
    assert group["numbers"] == n and group["kind"] == "page"
    assert group["pages"] == [[f"{i + 1:04d}", 1] for i in range(n)]


# הגופן המובנה helv בלי עברית, אז התשובות בדויות באנגלית
ANSWER = ("Let x be in A and in B union C. Then x is in A, and x is in B or in C. If x is in B then x is in "
          "A intersect B, otherwise x is in A intersect C. So x is in the union of both intersections, and "
          "the other inclusion is similar: every element of the union is in A and in B or C.")
THIRD = ("Complex numbers: write each number in the form a plus bi, find the modulus and the argument, "
         "solve the equations below over the complex numbers, and draw the set of points in the plane "
         "that satisfy each condition. Show every step of the computation and explain each answer.")
OTHER = ("We use a truth table. Every element has eight options for membership in the three sets, and in "
         "each one both sides get the same value. For example if the element is in A and C but not in B, "
         "both sides are true. Going over all rows shows the sets are equal for any three sets.")


def typed(name: str, answer: str) -> bytes:
    """עמוד מוקלד מאותה תבנית: כותרת, השאלה, שם הסטודנט והתשובה."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((60, 60), "Assignment 0, question 11: prove that A∩(B∪C) = (A∩B)∪(A∩C)")
    page.insert_text((60, 80), name)
    page.insert_textbox(pymupdf.Rect(60, 100, 540, 400), answer, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return data


def test_typed_pages_compare_by_text_not_by_look(assignment):
    put(assignment, "0001.pdf", typed("Student One", ANSWER))
    put(assignment, "0002.pdf", typed("Someone Else", ANSWER))   # אותה תשובה, שם אחר
    put(assignment, "0003.pdf", typed("Third Student", OTHER))   # אותה תבנית, תשובה אחרת: נראה דומה, לא העתקה
    rep = check.check_assignment(assignment)
    assert pairs(rep) == {("0001", "0002"): {"text"}}
    (reason,) = rep.pairs[0]["reasons"]
    assert reason["pages"][0][:2] == [1, 1] and reason["pages"][0][2] >= 80


def test_rare_metadata_is_weak_and_common_metadata_ignored(assignment):
    put(assignment, "0001.pdf", pdf_of(scan(1), author="Someone", created="D:20261020103000+02'00'"))
    put(assignment, "0002.pdf", pdf_of(scan(2), author="Someone"))
    for i in range(3, 3 + check.COMMON_META + 1):  # כולם עם אותו מחבר: ברירת מחדל של תוכנה
        put(assignment, f"{i:04d}.pdf", pdf_of(scan(i + 10), author="Microsoft Office User"))
    rep = check.check_assignment(assignment)
    assert pairs(rep) == {("0001", "0002"): {"author"}}
    assert rep.pairs[0]["level"] == "weak"


def test_report_has_no_metadata_values_and_reuses_cache(assignment, monkeypatch):
    put(assignment, "0001.pdf", pdf_of(scan(1), author="נועה כהן"))
    put(assignment, "0002.pdf", pdf_of(scan(1), author="נועה כהן"))
    rep = check.check_assignment(assignment)
    assert rep.read == 2
    text = check.report_path(assignment).read_text(encoding="utf-8")
    assert "נועה" not in text and "Student" not in text
    saved = json.loads(text)
    assert saved["pairs"] == rep.pairs and set(saved["files"]) == {"0001.pdf", "0002.pdf"}
    assert not check.is_stale(assignment)

    # הרצה שנייה: אף קובץ לא נקרא מחדש
    monkeypatch.setattr(check, "fingerprint", lambda p: pytest.fail(f"read {p.name} again"))
    assert check.check_assignment(assignment).read == 0

    put(assignment, "0003.pdf", pdf_of(scan(3)))
    assert check.is_stale(assignment)


def test_unreadable_and_other_files(assignment):
    put(assignment, "0001.pdf", b"not a pdf")
    put(assignment, "0002.pdf", b"not a pdf")
    put(assignment, "0003.docx", b"same bytes")
    put(assignment, "0004.docx", b"same bytes")
    found = pairs(check.check_assignment(assignment))
    assert found == {("0001", "0002"): {"file"}, ("0003", "0004"): {"file"}}


def cover(seed: int = 0) -> bytes:
    """כריכה של אפליקציית מחברות: צבע אחיד, מלבנים בהירים וקו לשם. בלי כתב יד."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(page.rect, color=None, fill=(0.68, 0.62, 0.53))
    page.draw_rect(pymupdf.Rect(0, 0, 25, page.rect.height), color=None, fill=(0.78, 0.74, 0.67))
    page.draw_line((60, 300), (540, 300), color=(0.58, 0.54, 0.47), width=1)
    for y in (700, 720, 740):
        page.draw_line((400, y), (520, y), color=(0.58, 0.54, 0.47), width=1)
    data = page.get_pixmap(dpi=90 + seed).tobytes("jpeg", jpg_quality=80)
    doc.close()
    return data


def grid() -> bytes:
    """דף משבצות כמעט ריק."""
    doc = pymupdf.open()
    page = doc.new_page()
    for x in range(40, 560, 14):
        page.draw_line((x, 40), (x, 800), color=(0.85, 0.87, 0.92), width=0.4)
    for y in range(40, 800, 14):
        page.draw_line((40, y), (560, y), color=(0.85, 0.87, 0.92), width=0.4)
    data = page.get_pixmap(dpi=90).tobytes("jpeg", jpg_quality=80)
    doc.close()
    return data


def test_covers_and_empty_pages_are_not_copying(assignment):
    # אותה כריכה ואותו דף משבצות ריק אצל שלושה, עם עבודה שונה: לא העתקה
    for i in range(3):
        put(assignment, f"{i + 1:04d}.pdf", pdf_of(cover(i), scan(300 + i), grid()))
    assert check.check_assignment(assignment).pairs == []
    pages = json.loads(check.report_path(assignment).read_text(encoding="utf-8"))["files"]["0001.pdf"]["pages"]
    assert pages[0]["i"] < check.MIN_INK <= pages[1]["i"] and pages[2]["i"] < check.MIN_INK


def test_two_photos_of_the_same_kind_of_page_are_not_the_same_photo(assignment):
    # עבודות שונות שנראות דומה מרחוק (אותו מבנה של שורות) רחוקות יותר מ-MAX_DISTANCE
    for i in range(12):
        put(assignment, f"{i + 1:04d}.pdf", pdf_of(scan(500 + i, quality=60)))
    assert check.check_assignment(assignment).pairs == []


def test_one_shared_scanned_page_is_not_enough(assignment):
    # עמוד אחד זהה עם כתיבה (נניח שאלה שצולמה מחבר) לא מספיק: כך גם כריכה עם כותרת. צריך שניים
    put(assignment, "0001.pdf", pdf_of(scan(1), scan(2)))
    put(assignment, "0002.pdf", pdf_of(scan(1, quality=55), scan(3)))
    assert check.check_assignment(assignment).pairs == []


def test_a_typed_page_three_submissions_share_is_course_material(assignment):
    # עמוד מחוברת השאלות ששלושה צירפו: לא זוגות, אלא עמוד שחוזר. שניים עם אותו פתרון מוקלד: כן זוג
    for n, name in (("0001", "One"), ("0002", "Two"), ("0003", "Three")):
        put(assignment, f"{n}.pdf", typed(name, ANSWER))
    put(assignment, "0004.pdf", typed("Four", OTHER))
    put(assignment, "0005.pdf", typed("Five", OTHER))
    put(assignment, "0003-2.pdf", typed("Three", THIRD))  # עמוד אחר מאותה חוברת, ששניים מהשלושה צירפו
    put(assignment, "0002-2.pdf", typed("Two", THIRD))
    rep = check.check_assignment(assignment)
    assert pairs(rep) == {("0004", "0005"): {"text"}}
    (group,) = rep.repeated
    assert group["kind"] == "text" and group["numbers"] == 3


QUESTION = ("Prove that for every three sets A, B and C the intersection of A with the union of B and C equals "
            "the union of the intersection of A and B with the intersection of A and C, and explain each step.")


def material(assignment, text: str) -> None:
    """דף תרגילים של הקורס, ב-"<קורס>/Course material/Sheets"."""
    folder = assignment.parent / paths.COURSE_MATERIAL / "Sheets"
    folder.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(60, 60, 540, 600), text, fontname="helv")
    doc.save(folder / "Sheet 1 - Sets.pdf")
    doc.close()


def test_a_booklet_page_two_students_inserted_is_course_material(assignment):
    # העמוד מהחוברת כמו שהוא, עם הכותרת שלו (typed מוסיף כותרת של שאלה 11)
    material(assignment, "Assignment 0, question 11: prove that A∩(B∪C) = (A∩B)∪(A∩C) " + THIRD + " " + QUESTION)
    put(assignment, "0001.pdf", typed("One", THIRD))
    put(assignment, "0002.pdf", typed("Two", THIRD))
    rep = check.check_assignment(assignment)
    assert rep.pairs == [] and rep.repeated == []
    assert rep.material == {"pages": 2, "files": 1}


def test_quoting_the_question_is_not_copying_but_the_same_answer_still_is(assignment):
    material(assignment, QUESTION)
    put(assignment, "0001.pdf", typed("One", QUESTION + " " + ANSWER))
    put(assignment, "0002.pdf", typed("Two", QUESTION + " " + OTHER))
    put(assignment, "0003.pdf", typed("Three", QUESTION + " " + ANSWER))
    rep = check.check_assignment(assignment)
    assert pairs(rep) == {("0001", "0003"): {"text"}}
    assert rep.material["pages"] == 0
