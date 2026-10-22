import random

import pymupdf

from grading import placement


def _page_with_ink(doc: pymupdf.Document, blocks: list[pymupdf.Rect]) -> pymupdf.Page:
    page = doc.new_page(width=600, height=800)
    for r in blocks:
        page.draw_rect(r, color=(0, 0, 0), fill=(0, 0, 0))
    return page


def _place(page: pymupdf.Page, box: pymupdf.Rect, size=(150, 30)):
    free = placement.FreeSpace(page)
    box = free.snap(box)
    free.occupy(box)
    note, line = free.place(box, *size)
    return free, box, note, line


def _touches_ink(page: pymupdf.Page, line: list[pymupdf.Point]) -> bool:
    """האם הקו עובר על פיקסל כהה כלשהו בעמוד המקורי (בדיקה ב-144 dpi, עם רוחב הקו)."""
    pix = page.get_pixmap(dpi=144, colorspace=pymupdf.csGRAY)
    z = 2
    for a, b in zip(line, line[1:]):
        for p in placement._samples(a, b, 0.5):
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    x, y = int(p.x * z) + dx, int(p.y * z) + dy
                    if 0 <= x < pix.width and 0 <= y < pix.height and pix.pixel(x, y)[0] < 200:
                        return True
    return False


def test_note_goes_to_empty_space_not_on_writing():
    doc = pymupdf.open()
    ink = pymupdf.Rect(20, 20, 420, 400)
    page = _page_with_ink(doc, [ink])
    _, box, note, _ = _place(page, pymupdf.Rect(100, 100, 300, 140))
    assert not note.intersects(ink)
    assert not note.intersects(box)


def test_note_next_to_box_when_there_is_room_needs_no_line():
    doc = pymupdf.open()
    page = _page_with_ink(doc, [])
    _, box, note, line = _place(page, pymupdf.Rect(200, 300, 400, 340))
    assert line is None
    assert not note.intersects(box)


def test_line_bends_around_writing_and_never_touches_ink():
    # הקופסה סגורה מכל הצדדים חוץ מפתח צר למטה משמאל: הקו חייב להתכופף כדי לצאת
    doc = pymupdf.open()
    walls = [pymupdf.Rect(0, 0, 600, 420),            # כתב מעל ומסביב
             pymupdf.Rect(0, 420, 40, 800),            # שוליים שמאליים כתובים
             pymupdf.Rect(80, 420, 600, 560)]          # כתב מתחת, חוץ מהפתח 40..80
    page = _page_with_ink(doc, walls)
    # הקופסה יושבת בתוך הכתב, צמודה לפתח
    _, box, note, line = _place(page, pymupdf.Rect(30, 400, 120, 430))
    assert line is not None and len(line) >= 3
    assert not any(note.intersects(w) for w in walls)
    assert not _touches_ink(page, line[1:-1] if len(line) > 2 else line)


def test_line_on_scribbled_page_never_touches_ink():
    random.seed(3)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for y in range(40, 800, 22):
        x = 30
        while x < random.randint(300, 420):
            w = random.randint(10, 40)
            page.draw_line((x, y), (x + w, y + random.randint(-6, 6)), width=2)
            x += w + 8
    _, box, note, line = _place(page, pymupdf.Rect(60, 400, 250, 440), (210, 40))
    if line:
        assert not _touches_ink(page, line[1:-1])


def test_two_notes_do_not_overlap():
    doc = pymupdf.open()
    page = _page_with_ink(doc, [pymupdf.Rect(0, 0, 600, 300)])
    free, box, first, _ = _place(page, pymupdf.Rect(100, 200, 300, 260))
    free.occupy(first)
    second, _ = free.place(box, 150, 30)
    assert not first.intersects(second)


def test_no_clean_way_out_gives_note_without_line():
    doc = pymupdf.open()
    ring = [pymupdf.Rect(80, 80, 320, 100), pymupdf.Rect(80, 200, 320, 220),
            pymupdf.Rect(80, 80, 100, 220), pymupdf.Rect(300, 80, 320, 220)]
    page = _page_with_ink(doc, ring)
    _, box, note, line = _place(page, pymupdf.Rect(130, 130, 270, 170))
    assert line is None


def test_note_size_grows_with_text():
    assert placement.note_size("קצר")[1] < placement.note_size("ארוך " * 40)[1]
