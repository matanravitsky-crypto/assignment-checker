"""The zoom pass (grading/locate.py): crops around each rough box, a tight box back, mapped to the page."""
from __future__ import annotations

import json

import pymupdf
import pytest

from grading import grade as grading, locate


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    monkeypatch.setattr(grading, "claude_ask", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Claude מדומה בלבד")))


def scan() -> bytes:
    """A page with three "lines of handwriting" at 20%, 40% and 60% of its height."""
    doc = pymupdf.open()
    page = doc.new_page()  # 595 x 842
    for top in (168, 336, 505):
        for y in range(top, top + 25, 3):
            page.draw_line((100, y), (420, y), color=(0, 0, 0.3), width=1.2)
    return doc.tobytes()


def test_a_crop_is_a_close_up_around_the_rough_box_with_its_own_grid():
    mark = grading.Mark(1, 150, 390, 700, 650, "רחב מדי")  # rough: 3 lines
    (c,) = locate.crops(scan(), [mark])
    x0, y0, x1, y1 = c.area
    assert x0 < 150 and x1 > 700 and y0 < 390 and y1 > 650  # the rough box and some room around it
    pix = pymupdf.Pixmap(c.png)
    assert max(pix.width, pix.height) <= locate.SIDE
    # a close-up: the page part is shown larger than in the grading image (1568 px for the whole page)
    assert pix.height / ((y1 - y0) / 1000) > 1568 * 1.2


def test_a_small_box_still_gets_room_for_a_line_above_and_below():
    (c,) = locate.crops(scan(), [grading.Mark(1, 200, 400, 260, 410, "קטן")])
    assert c.area[3] - c.area[1] >= locate.MIN_H - 1 and c.area[2] - c.area[0] >= locate.MIN_W - 1


def test_small_writing_gets_a_closer_crop_than_big_writing():
    (small,) = locate.crops(scan(), [grading.Mark(1, 400, 400, 520, 415, "כתב קטן")])
    (big,) = locate.crops(scan(), [grading.Mark(1, 300, 380, 700, 440, "כתב גדול")])
    assert small.area[3] - small.area[1] < big.area[3] - big.area[1]


def test_the_tight_box_is_mapped_back_to_the_page_and_a_miss_keeps_the_rough_one():
    marks = [grading.Mark(1, 150, 390, 700, 650, "רחב"), grading.Mark(1, 150, 180, 700, 240, "לא נמצא")]
    items = locate.crops(scan(), marks)
    a = items[0].area
    answer = json.dumps({"boxes": [{"i": 1, "found": True, "x0": 100, "y0": 400, "x1": 500, "y1": 500},
                                   {"i": 2, "found": False, "x0": 0, "y0": 0, "x1": 0, "y1": 0}]})
    out, moved = locate.apply(answer, items, marks, grading.Mark)
    assert moved == 1 and out[1] is marks[1]
    m = out[0]
    assert m.text == "רחב" and m.page == 1
    assert abs(m.x0 - (a[0] + 0.1 * (a[2] - a[0]))) < 0.01 and abs(m.y1 - (a[1] + 0.5 * (a[3] - a[1]))) < 0.01
    assert locate.apply("not json", items, marks, grading.Mark) == (marks, 0)


def test_the_request_carries_every_crop_with_its_note_and_asks_for_the_schema():
    marks = [grading.Mark(1, 150, 390, 700, 650, "הערה אחת"), grading.Mark(1, 150, 180, 700, 240, "הערה שתיים")]
    req = locate.build_request(locate.crops(scan(), marks), marks, "claude-sonnet-5-5")
    texts = [b["text"] for b in req["messages"][0]["content"] if b["type"] == "text"]
    assert any("חיתוך 1" in t and "הערה אחת" in t for t in texts) and any("חיתוך 2" in t and "הערה שתיים" in t for t in texts)
    assert sum(b["type"] == "image" for b in req["messages"][0]["content"]) == 2
    assert req["output_config"]["format"]["schema"] == locate.SCHEMA and req["file_prefix"] == "crop"
    assert req["model"] == "claude-sonnet-5-5" and req["system"] == locate.SYSTEM


def test_grading_moves_the_boxes_and_a_failing_zoom_pass_changes_nothing():
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 10)])
    answer = json.dumps({"questions": [{"label": "שאלה 1", "points": 8, "comment": "טעות"}], "feedback": "",
                         "annotations": [{"page": 1, "x0": 150, "y0": 390, "x1": 700, "y1": 650, "text": "רחב"}],
                         "needs_review": False, "review_reason": ""})
    seen = []

    def zoom(req):
        seen.append(req)
        return json.dumps({"boxes": [{"i": 1, "found": True, "x0": 100, "y0": 400, "x1": 500, "y1": 500}]})

    g, _ = grading.grade_one(scan(), ctx, lambda req: answer, crop=False, locate_ask=zoom)
    assert len(seen) == 1 and g.marks[0].y1 - g.marks[0].y0 < 120  # was 260

    def broken(req):
        raise grading.GradingError("נפל")
    g, _ = grading.grade_one(scan(), ctx, lambda req: answer, crop=False, locate_ask=broken)
    assert g.marks and g.marks[0].y1 - g.marks[0].y0 > 200  # the rough box stays (snapped to ink as before)
    g, _ = grading.grade_one(scan(), ctx, lambda req: answer, crop=False)  # no zoom pass at all
    assert g.marks


def test_grading_with_a_given_ask_never_starts_the_zoom_pass(monkeypatch):
    # tests and the dashboard's fakes pass `ask`; only a real run (ask=None) builds the zoom pass
    called = []
    monkeypatch.setattr(locate, "relocate", lambda *a, **k: called.append(1) or a[1])
    ctx = grading.Context("מטלה", "קורס", [grading.Question("שאלה 1", 10)])
    answer = json.dumps({"questions": [{"label": "שאלה 1", "points": 8, "comment": "טעות"}], "feedback": "",
                         "annotations": [{"page": 1, "x0": 150, "y0": 390, "x1": 700, "y1": 650, "text": "x"}],
                         "needs_review": False, "review_reason": ""})
    grading.grade_one(scan(), ctx, lambda req: answer, crop=False)
    assert not called


def test_the_zoom_pass_can_be_turned_off(monkeypatch):
    from moodle import settings
    monkeypatch.setattr(settings, "get", lambda k, d=None: "off" if k == "LOCATE" else d)
    assert not locate.enabled()
    monkeypatch.setattr(settings, "get", lambda k, d=None: d)
    assert locate.enabled() and locate.model() == locate.DEFAULT_MODEL
