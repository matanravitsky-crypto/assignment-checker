"""Cropping the white margins before a page goes to Claude: the image gets smaller, the resolution stays,
and the marks Claude returns land on the same spot of the student's full page."""
import pymupdf
import pytest

from grading import grade
from grading.render import MAX_SIDE, PageImage, render_pdf


def scan_with_margins() -> bytes:
    """A4 page with handwriting-like ink in the middle ~65% x 80%, white margins around: a typical phone scan."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for i in range(56):
        y = 90 + i * 12
        page.draw_line((80, y), (520, y + 3), color=(0, 0, 0), width=2.5)
    return doc.tobytes()


def test_cropped_page_is_smaller_but_not_magnified():
    pdf = scan_with_margins()
    full = render_pdf(pdf)[0]
    cropped = render_pdf(pdf, crop=True)[0]
    assert full.clip is None and abs(max(full.width, full.height) - MAX_SIDE) <= 1
    assert cropped.clip is not None
    assert cropped.width < full.width and cropped.height < full.height
    assert cropped.width * cropped.height < 0.7 * full.width * full.height
    x0, y0, x1, y1 = cropped.clip
    assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1


def test_marks_come_back_to_full_page_coordinates():
    img = PageImage(1, b"", 500, 500, clip=(0.2, 0.1, 0.8, 0.7))
    # the top-left corner of the crop is page (200, 100) in thousandths; the bottom-right is (800, 700)
    assert img.to_page(0, 0) == pytest.approx((200, 100))
    assert img.to_page(1000, 1000) == pytest.approx((800, 700))
    marks = grade.marks_to_page([grade.Mark(1, 500, 500, 600, 600, "x"), grade.Mark(2, 10, 10, 20, 20, "y")],
                                [img, PageImage(2, b"", 500, 500)])
    assert (marks[0].x0, marks[0].y0, marks[0].x1, marks[0].y1) == pytest.approx((500, 400, 560, 460))
    assert (marks[1].x0, marks[1].y0) == (10, 10)  # an uncropped page is left alone


def test_a_blank_page_is_not_cropped():
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    img = render_pdf(doc.tobytes(), crop=True)[0]
    assert img.clip is None
