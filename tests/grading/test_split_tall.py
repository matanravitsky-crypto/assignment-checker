"""A page much taller than wide (a whole work as one long photo) is cut into about-A4 pages on blank rows."""
import pymupdf

from grading import grade


def _doc(pages):
    doc = pymupdf.open()
    for w, h, lines in pages:
        p = doc.new_page(width=w, height=h)
        for y in lines:
            p.draw_rect(pymupdf.Rect(20, y, w - 20, y + 14), color=(0, 0, 0), fill=(0, 0, 0))
    return doc


def _sizes(data):
    with pymupdf.open(stream=data) as d:
        return [(round(p.rect.width), round(p.rect.height)) for p in d]


def test_normal_pages_untouched(tmp_path):
    f = tmp_path / "a.pdf"
    _doc([(595, 842, [100, 300]), (842, 595, [100])]).save(f)
    data, skipped = grade.submission_pdf([f])
    assert skipped == []
    assert _sizes(data) == [(595, 842), (842, 595)]


def test_tall_page_becomes_a4_like_pages_and_keeps_order(tmp_path):
    f = tmp_path / "a.pdf"
    lines = list(range(40, 4000, 40))  # a line every 40 pt, gaps of 26 pt between them
    _doc([(595, 842, [100]), (800, 4000, lines), (595, 842, [100])]).save(f)
    sizes = _sizes(grade.submission_pdf([f])[0])
    assert sizes[0] == (595, 842) and sizes[-1] == (595, 842)
    middle = sizes[1:-1]
    assert len(middle) == 4  # 4000/800 = 5 → ceil(5/1.45) = 4
    assert all(w == 800 for w, _ in middle)
    assert abs(sum(h for _, h in middle) - 4000) <= 2  # nothing lost, nothing doubled
    assert all(h / w <= grade.TALL_RATIO for w, h in middle)


def test_cut_falls_on_a_blank_row():
    ink = [1.0] * 100
    for y in (46, 47):  # the only blank rows near the middle
        ink[y] = 0.0
    assert grade.tall_cuts(ink, 2) == [0.47]  # the blank row nearest the middle


def test_cut_stays_near_even_when_no_blank_row():
    cuts = grade.tall_cuts([0.5] * 300, 3)
    assert [round(c, 2) for c in cuts] == [0.33, 0.67]
