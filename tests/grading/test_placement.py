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


def test_draw_returns_what_happened_to_each_mark():
    doc = pymupdf.open()
    page = _page_with_ink(doc, [pymupdf.Rect(0, 0, 600, 300)])
    written = []
    result = placement.draw(page, [(pymupdf.Rect(100, 320, 300, 360), "טעות"), (pymupdf.Rect(100, 500, 300, 540), "")],
                            lambda p, r, t: written.append((r, t)))
    assert result[1] is None and len(written) == 1
    assert result[0] in (True, False)
    assert any(d["color"] and d["color"][0] > 0.8 for d in page.get_drawings())


def test_command_line_marks_a_pdf_and_prints_one_line(tmp_path, capsys):
    import json
    doc = pymupdf.open()
    _page_with_ink(doc, [pymupdf.Rect(20, 20, 420, 400)])
    doc.save(tmp_path / "in.pdf")
    (tmp_path / "marks.json").write_text(json.dumps(
        {"marks": [{"page": 1, "x0": 200, "y0": 150, "x1": 500, "y1": 200, "text": "חסר נימוק"}]}), encoding="utf-8")
    assert placement.main([str(tmp_path / "in.pdf"), str(tmp_path / "marks.json"), str(tmp_path / "out.pdf")]) == 0
    out = capsys.readouterr().out
    assert len(out.strip().splitlines()) == 1 and out.startswith("1 סימונים")
    with pymupdf.open(tmp_path / "out.pdf") as marked:
        assert "חסר נימוק" in marked[0].get_text().replace(" ", " ")


def test_command_line_refuses_a_page_that_does_not_exist(tmp_path):
    import json
    doc = pymupdf.open()
    doc.new_page()
    doc.save(tmp_path / "in.pdf")
    (tmp_path / "m.json").write_text(json.dumps([{"page": 3, "x0": 0, "y0": 0, "x1": 10, "y1": 10, "text": "x"}]))
    assert placement.main([str(tmp_path / "in.pdf"), str(tmp_path / "m.json"), str(tmp_path / "o.pdf")]) == 2
