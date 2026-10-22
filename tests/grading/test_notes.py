"""בדיקות למציאת מקום להערות (grading/notes.py), על עמודים מדומים במערכי numpy."""
import math

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


def gap(note, box):
    return max(box[0] - note[2], note[0] - box[2], box[1] - note[3], note[1] - box[3], 0)


def test_a_far_empty_spot_is_not_used_and_no_arrow_crosses_the_page():
    """צילום של מחברת: כמעט הכל כתוב, ויש מקום ריק רק בצד השני של העמוד. ההערה לא הולכת לשם עם חץ ארוך:
    היא נכתבת צמוד למלבן, על רקע לבן."""
    mask = np.ones((400, 300), dtype=bool)
    mask[340:390, 10:120] = False    # ריק, אבל רחוק
    box = (180, 40, 260, 70)
    spot = notes.find_spot(mask, box, (60, 14))
    assert not spot.clear and spot.backed
    assert gap(spot.note, box) <= 2 and not overlaps(spot.note, box)
    assert math.dist(*spot.arrow) <= notes.REACH * 400


def test_the_note_stays_within_reach_even_when_the_only_clean_spot_is_far():
    mask = page(400, 300)
    mask[:, :] = True
    mask[0:30, :] = False            # שוליים ריקים למעלה
    mask[200:260, 100:300] = False   # ומקום ריק קרוב למלבן, עם קצת כתב
    mask[230, 100:300] = True
    box = (150, 270, 220, 290)
    spot = notes.find_spot(mask, box, (60, 14))
    assert spot.note[1] >= 200 and gap(spot.note, box) <= notes.REACH * 400


def test_ink_is_much_darker_than_the_paper_around_it():
    """צילום: נייר אפור בצל (170), קווי משבצות (150) ודיו (60). רק הדיו נחשב."""
    gray = np.full((80, 80), 170, dtype=np.uint8)
    gray[::8, :] = 150
    gray[40:43, 20:60] = 60
    ink = notes.ink_mask(gray)
    assert ink[41, 30] and not ink[8, 30] and not ink[20, 20]
    assert ink.sum() == 3 * 40


def test_a_box_half_a_line_low_moves_up_onto_the_writing():
    ink = page(300, 300)
    ink[100:120, 50:200:4] = True      # שורת הכתב של הטעות (כתב יד: קווים דלילים)
    ink[160:180, 50:200:4] = True      # השורה הבאה
    x0, y0, x1, y1 = notes.snap_box(ink, (40, 110, 210, 135))   # Claude: חצי שורה מתחת
    assert (x0, x1) == (40, 210)                                # הרוחב לא משתנה
    assert y0 <= 100 and 120 <= y1 < 160                        # על השורה, בלי השורה הבאה


def test_a_box_over_empty_paper_or_a_photo_edge_stays_where_it_is():
    ink = page(300, 300)
    assert notes.snap_box(ink, (40, 110, 210, 135)) == (40, 110, 210, 135)
    ink[120:300, :] = True              # קצה של הצילום: שורות שכולן "דיו"
    assert notes.snap_box(ink, (40, 110, 210, 135)) == (40, 110, 210, 135)


def test_a_box_never_shrinks_onto_one_small_mark():
    ink = page(300, 300)
    ink[118:121, 100:103] = True        # נקודה קטנה בלבד
    x0, y0, x1, y1 = notes.snap_box(ink, (40, 100, 210, 140))
    assert y1 - y0 >= notes.SNAP_MIN * 40 - 1 and (x0, x1) == (40, 210)


def test_two_attached_notes_of_close_boxes_do_not_land_on_each_other():
    """Two boxes close together on a page full of writing: both notes are attached, and the second one goes
    where the first one isn't (a placed note is blocked in the mask, as _mark_page does)."""
    mask = np.ones((400, 300), dtype=bool)
    mask[::3, :] = False                     # dense writing, never a clean spot
    first, second = (150, 100, 230, 120), (90, 100, 170, 120)   # side by side on one line
    one = notes.find_spot(mask, first, (100, 14))
    notes.block(mask, one.note)
    two = notes.find_spot(mask, second, (100, 14))
    assert one.backed and two.backed
    assert not overlaps(one.note, two.note)
    assert not overlaps(two.note, second) and gap(two.note, second) <= notes.REACH * 400


def test_a_note_never_covers_an_earlier_one_even_at_the_bottom_of_a_full_width_page():
    """Seen on a real submission (from the other session's trace): two boxes almost the full width of the page,
    the second at the bottom. Every spot around the second box is off the page or on the first note, so the
    note goes into the corner of its own box rather than onto the other note."""
    rnd = np.random.default_rng(0)
    mask = rnd.random((800, 619)) < 0.17
    first, second = (36, 588, 538, 640), (23, 743, 538, 795)
    for b in (first, second):
        notes.block(mask, b)
    one = notes.find_spot(mask, first, (211, 65))
    notes.block(mask, one.note)
    two = notes.find_spot(mask, second, (211, 65), avoid=[one.note])
    assert not overlaps(one.note, two.note)
    assert 0 <= two.note[0] and two.note[2] <= 619 and 0 <= two.note[1] and two.note[3] <= 800
    assert gap(two.note, second) <= notes.REACH * 800
