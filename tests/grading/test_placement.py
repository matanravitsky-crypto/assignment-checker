import pymupdf

from grading import placement


def _page_with_ink(doc: pymupdf.Document, blocks: list[pymupdf.Rect]) -> pymupdf.Page:
    page = doc.new_page(width=600, height=800)
    for r in blocks:
        page.draw_rect(r, color=(0, 0, 0), fill=(0, 0, 0))
    return page


def test_note_goes_to_empty_space_not_on_writing():
    doc = pymupdf.open()
    # כתב על כל החצי העליון, חוץ מהשוליים הימניים
    ink = pymupdf.Rect(20, 20, 420, 400)
    page = _page_with_ink(doc, [ink])
    free = placement.FreeSpace(page)
    box = pymupdf.Rect(100, 100, 300, 140)
    free.occupy(box)
    note = free.place(box, 150, 30)
    assert not note.intersects(ink)
    assert not note.intersects(box)


def test_note_next_to_box_when_there_is_room_needs_no_arrow():
    doc = pymupdf.open()
    page = _page_with_ink(doc, [])
    free = placement.FreeSpace(page)
    box = pymupdf.Rect(200, 300, 400, 340)
    note = free.place(box, 150, 30)
    assert placement.arrow(note, box) is None


def test_far_note_gets_arrow_to_box():
    note, box = pymupdf.Rect(450, 50, 590, 80), pymupdf.Rect(100, 500, 200, 540)
    a, b = placement.arrow(note, box)
    assert (note + (-1, -1, 1, 1)).contains(a) and (box + (-1, -1, 1, 1)).contains(b)


def test_two_notes_do_not_overlap():
    doc = pymupdf.open()
    page = _page_with_ink(doc, [pymupdf.Rect(0, 0, 600, 300)])
    free = placement.FreeSpace(page)
    box = pymupdf.Rect(100, 200, 300, 260)
    first = free.place(box, 150, 30)
    free.occupy(first)
    second = free.place(box, 150, 30)
    assert not first.intersects(second)


def test_note_size_grows_with_text():
    assert placement.note_size("קצר")[1] < placement.note_size("ארוך " * 40)[1]
