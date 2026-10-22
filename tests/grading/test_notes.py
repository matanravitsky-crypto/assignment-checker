"""בדיקות למציאת מקום להערות (grading/notes.py), על עמודים מדומים במערכי numpy."""
import numpy as np

from grading import notes


def page(h=200, w=300):
    return np.zeros((h, w), dtype=bool)


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_note_goes_next_to_the_box_when_there_is_room():
    mask = page()
    box = (100, 80, 160, 100)
    notes.block(mask, box)
    spot = notes.find_spot(mask, box, (40, 12))
    assert spot.clear and not overlaps(spot.note, box)
    # צמוד למלבן: לא רחוק יותר מהשוליים הריקים ועוד צעד
    gap = max(box[0] - spot.note[2], spot.note[0] - box[2], box[1] - spot.note[3], spot.note[1] - box[3])
    assert gap <= notes.PAD + notes.STEP + 1


def test_note_and_arrow_avoid_the_writing():
    mask = page()
    mask[:, :150] = True        # כתב בכל החצי השמאלי
    box = (120, 90, 170, 110)   # הטעות בקצה הכתב
    notes.block(mask, box)
    spot = notes.find_spot(mask, box, (60, 20))
    assert spot.clear
    assert spot.note[0] >= 150   # ההערה בחלק הריק
    end = spot.arrow[1]
    assert box[0] <= end[0] <= box[2] and box[1] <= end[1] <= box[3]  # החץ מגיע למלבן


def test_arrow_does_not_cross_a_line_of_writing():
    mask = page()
    box = (130, 150, 170, 170)
    notes.block(mask, box)
    mask[120:124, :] = True      # שורת כתב מעל המלבן, לאורך כל העמוד
    mask[175:, :] = True         # ומתחתיו הכל כתוב
    mask[124:175, :100] = True   # ומשמאלו
    spot = notes.find_spot(mask, box, (50, 14))
    assert spot.clear
    # מעל השורה יש הרבה מקום, אבל החץ היה חוצה אותה: ההערה נשארת בפס של המלבן, בלי לגעת בו
    assert spot.note[1] >= 124 and spot.note[3] <= 175 and spot.note[0] >= 100 and not overlaps(spot.note, box)


def test_a_full_page_still_gets_the_note_where_there_is_least_ink():
    mask = np.ones((100, 100), dtype=bool)
    mask[60:80, 0:40] = False
    spot = notes.find_spot(mask, (50, 10, 60, 20), (30, 10))
    assert not spot.clear
    x0, y0, x1, y1 = spot.note
    assert 0 <= x0 and x1 <= 40 and 60 <= y0 and y1 <= 80


def test_ink_is_dark_and_notebook_grid_is_not():
    gray = np.array([[30, 120, 200, 255]], dtype=np.uint8)
    assert notes.ink_mask(gray).tolist() == [[True, True, False, False]]
