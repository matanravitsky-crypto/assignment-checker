"""חיתוך השוליים הלבנים במדגם: רק המלבן שיש בו כתב נשלח, כדי שהשוליים לא יעלו טוקנים."""
from pathlib import Path

import pymupdf

from grading import sample


def _page_with_ink(path: Path, rect: pymupdf.Rect | None) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4
    if rect is not None:
        page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(path)
    doc.close()


def test_ink_bbox_finds_the_written_area(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    _page_with_ink(pdf, pymupdf.Rect(50, 100, 545, 600))   # כמחצית העמוד
    with pymupdf.open(pdf) as doc:
        box = sample.ink_bbox(doc[0])
    assert box is not None
    assert 30 < box.x0 <= 50 and 545 <= box.x1 < 570    # 2% שוליים סביב הכתב
    assert 75 < box.y0 <= 100 and 600 <= box.y1 < 625


def test_a_faint_page_with_little_visible_ink_is_not_cropped(tmp_path: Path) -> None:
    pdf = tmp_path / "faint.pdf"
    _page_with_ink(pdf, pymupdf.Rect(100, 200, 300, 500))   # "כתב" ב-12% מהעמוד בלבד: חשד לעיפרון חיוור
    with pymupdf.open(pdf) as doc:
        assert sample.ink_bbox(doc[0]) is None


def test_full_page_and_empty_page_are_not_cropped(tmp_path: Path) -> None:
    full = tmp_path / "full.pdf"
    _page_with_ink(full, pymupdf.Rect(5, 5, 590, 837))
    empty = tmp_path / "empty.pdf"
    _page_with_ink(empty, None)
    with pymupdf.open(full) as doc:
        assert sample.ink_bbox(doc[0]) is None
    with pymupdf.open(empty) as doc:
        assert sample.ink_bbox(doc[0]) is None


def test_crop_makes_a_smaller_image_with_the_same_long_side(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    _page_with_ink(pdf, pymupdf.Rect(50, 100, 545, 600))
    out = tmp_path / "out"
    out.mkdir()
    names, _ = sample.render_file(pdf, "0001", out, 0, max_side=600, crop=False)
    whole = pymupdf.Pixmap(str(out / names[0]))
    names, _ = sample.render_file(pdf, "0002", out, 0, max_side=600, crop=True)
    cropped = pymupdf.Pixmap(str(out / names[0]))
    assert max(whole.width, whole.height) == 600
    assert max(cropped.width, cropped.height) < 600          # חיתוך מקטין, לא מגדיל
    assert cropped.width * cropped.height < 0.75 * whole.width * whole.height
