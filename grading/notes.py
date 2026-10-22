"""איפה לכתוב כל הערה על העבודה: ליד הטעות שלה, במקום הריק הקרוב ביותר, עם חץ קצר שלא עובר על שום דבר.

העמוד נסרק לתמונה קטנה, ומה שכהה בה בהרבה מהנייר שסביבו הוא "דיו" (כתב היד). צילום של מחברת כהה יותר
בפינות ובצללים, וקווי המשבצות כהים רק קצת מהנייר, ולכן משווים כל נקודה לנייר שסביבה ולא לערך קבוע.

ההערה לא מתרחקת מהמלבן שלה יותר מ-REACH: הערה שנכתבה בצד השני של העמוד, עם חץ שחוצה את כל הדף,
לא עוזרת לאף אחד. אם אין ליד המלבן מקום נקי, ההערה הולכת למקום הקרוב שיש בו הכי מעט דיו, ואם גם בו
יש הרבה דיו, היא נכתבת צמוד למלבן (מתחתיו או מעליו) על רקע לבן שקוף למחצה, כדי שאפשר יהיה לקרוא אותה.

הכל כאן בפיקסלים של התמונה הקטנה. grade.py ממיר מנקודות של ה-PDF ובחזרה.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# דיו: כהה מ-INK_RATIO מהנייר שסביבו (קווי משבצות וצללים כהים ממנו רק קצת), או כהה מ-INK_BELOW בכל מקרה
INK_RATIO = 0.72
INK_BELOW = 70
# הנייר סביב כל נקודה: הממוצע בריבוע בגודל הזה (בפיקסלים של התמונה הקטנה)
PAPER_WINDOW = 41
# הכי רחוק שהערה מתרחקת מהמלבן שלה, כחלק מהצלע הארוכה של העמוד
REACH = 0.07
# כמה דיו (כחלק מהשטח) מותר מתחת להערה לפני שכותבים אותה צמוד למלבן על רקע לבן
MAX_INK = 0.04
# כמה פיקסלים ריקים להשאיר סביב ההערה, כדי שלא תיגע בשום דבר
PAD = 3
# הצעד שבו מחפשים מקום. קטן יותר: מדויק יותר ואיטי יותר
STEP = 2


@dataclass
class Spot:
    note: tuple[int, int, int, int]                 # המלבן של ההערה: x0, y0, x1, y1
    arrow: tuple[tuple[int, int], tuple[int, int]]  # מההערה אל המלבן האדום
    clear: bool                                     # True: ההערה והחץ לא נוגעים בשום דבר
    backed: bool = False                            # True: יש מתחת להערה כתב, ולכן היא נכתבת על רקע לבן


def _box_mean(img: np.ndarray, size: int) -> np.ndarray:
    """הממוצע בריבוע בגודל size סביב כל פיקסל (בקצוות: מה שבתוך התמונה)."""
    h, w = img.shape
    r = size // 2
    s = np.zeros((h + 1, w + 1), dtype=np.float64)
    s[1:, 1:] = img.astype(np.float64).cumsum(0).cumsum(1)
    y0, y1 = np.clip(np.arange(h) - r, 0, h), np.clip(np.arange(h) + r + 1, 0, h)
    x0, x1 = np.clip(np.arange(w) - r, 0, w), np.clip(np.arange(w) + r + 1, 0, w)
    total = s[y1][:, x1] - s[y0][:, x1] - s[y1][:, x0] + s[y0][:, x0]
    return total / ((y1 - y0)[:, None] * (x1 - x0)[None, :])


def ink_mask(gray: np.ndarray) -> np.ndarray:
    paper = _box_mean(gray, PAPER_WINDOW)
    return (gray < paper * INK_RATIO) | (gray < INK_BELOW)


def block(mask: np.ndarray, rect: tuple[float, float, float, float], width: int = 0) -> None:
    """מסמן מלבן כתפוס. width>0: רק המסגרת שלו, בעובי הזה."""
    h, w = mask.shape
    x0, y0, x1, y1 = (int(max(0, math.floor(rect[0]))), int(max(0, math.floor(rect[1]))),
                      int(min(w, math.ceil(rect[2]))), int(min(h, math.ceil(rect[3]))))
    if x1 <= x0 or y1 <= y0:
        return
    if width <= 0:
        mask[y0:y1, x0:x1] = True
        return
    mask[y0:min(y1, y0 + width), x0:x1] = True
    mask[max(y0, y1 - width):y1, x0:x1] = True
    mask[y0:y1, x0:min(x1, x0 + width)] = True
    mask[y0:y1, max(x0, x1 - width):x1] = True


def block_line(mask: np.ndarray, p0: tuple[float, float], p1: tuple[float, float], width: int = 2) -> None:
    for x, y in _line_points(p0, p1):
        block(mask, (x - width, y - width, x + width + 1, y + width + 1))


def _line_points(p0, p1):
    n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
    for i in range(n + 1):
        t = i / n
        yield round(p0[0] + (p1[0] - p0[0]) * t), round(p0[1] + (p1[1] - p0[1]) * t)


def _nearest_on_rect(rect, p) -> tuple[float, float]:
    return min(max(p[0], rect[0]), rect[2]), min(max(p[1], rect[1]), rect[3])


def _arrow(note, box) -> tuple[tuple[int, int], tuple[int, int]]:
    """מהנקודה בהערה שהכי קרובה למלבן, אל הנקודה במלבן שהכי קרובה למרכז ההערה."""
    center = ((note[0] + note[2]) / 2, (note[1] + note[3]) / 2)
    end = _nearest_on_rect(box, center)
    start = _nearest_on_rect(note, end)
    return (round(start[0]), round(start[1])), (round(end[0]), round(end[1]))


def _path_is_clear(mask: np.ndarray, start, end) -> bool:
    """החץ לא עובר על שום דבר. רק הקצה שלו נוגע במלבן האדום, ולכן בודקים עד קצת לפניו."""
    h, w = mask.shape
    length = math.dist(start, end)
    if length < 1:
        return True
    stop = max(0.0, 1 - (PAD + 2) / length)
    points = list(_line_points(start, (start[0] + (end[0] - start[0]) * stop, start[1] + (end[1] - start[1]) * stop)))
    for x, y in points[PAD:]:
        if 0 <= y < h and 0 <= x < w and mask[max(0, y - 1):y + 2, max(0, x - 1):x + 2].any():
            return False
    return True


def _attached(mask: np.ndarray, box, nw: int, nh: int) -> tuple[int, int, int, int]:
    """ההערה צמודה למלבן: מתחתיו אם יש מקום בעמוד, אחרת מעליו. מיושרת לצד ימין שלו, כמו עברית."""
    h, w = mask.shape
    x1 = int(min(max(box[2], nw), w))
    y0 = int(box[3]) + 1 if box[3] + 1 + nh <= h else int(box[1]) - 1 - nh
    y0 = max(0, min(y0, h - nh))
    return x1 - nw, y0, x1, y0 + nh


def find_spot(mask: np.ndarray, box: tuple[float, float, float, float], size: tuple[int, int]) -> Spot:
    """המקום הריק הקרוב ביותר למלבן `box` להערה בגודל `size` (רוחב, גובה), עם חץ שלא עובר על שום דבר.
    לא רחוק מהמלבן יותר מ-REACH. בלי מקום נקי שם: המקום הקרוב עם הכי מעט דיו, או צמוד למלבן על רקע לבן.

    `mask` הוא מה שתפוס בעמוד (דיו, מלבנים, הערות וחצים קודמים), והמלבן עצמו בתוכו.
    """
    h, w = mask.shape
    nw, nh = min(size[0], w), min(size[1], h)
    padded = (nw + 2 * PAD, nh + 2 * PAD)
    # סכום מצטבר: כמה פיקסלים תפוסים יש בכל מלבן, בבת אחת לכל המקומות האפשריים
    s = np.zeros((h + 1, w + 1), dtype=np.int32)
    s[1:, 1:] = mask.astype(np.int32).cumsum(0).cumsum(1)
    ys = np.arange(0, max(1, h - padded[1] + 1), STEP)
    xs = np.arange(0, max(1, w - padded[0] + 1), STEP)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    y1, x1 = np.minimum(yy + padded[1], h), np.minimum(xx + padded[0], w)
    taken = s[y1, x1] - s[yy, x1] - s[y1, xx] + s[yy, xx]
    # המרחק מההערה (בלי השוליים הריקים שלה) אל המלבן
    nx0, ny0 = xx + PAD, yy + PAD
    dx = np.maximum(np.maximum(box[0] - (nx0 + nw), nx0 - box[2]), 0)
    dy = np.maximum(np.maximum(box[1] - (ny0 + nh), ny0 - box[3]), 0)
    dist = np.hypot(dx, dy)

    near = dist <= max(REACH * max(h, w), float(dist.min()))

    free = np.argwhere((taken == 0) & near)
    order = free[np.argsort(dist[free[:, 0], free[:, 1]], kind="stable")]
    for i, j in order[:400]:
        note = (int(nx0[i, j]), int(ny0[i, j]), int(nx0[i, j]) + nw, int(ny0[i, j]) + nh)
        start, end = _arrow(note, box)
        if _path_is_clear(mask, start, end):
            return Spot(note, (start, end), True)
    # אין ליד המלבן מקום נקי: הכי מעט דיו, ואחריו הכי קרוב
    inked = np.where(near, taken, np.iinfo(np.int32).max)
    i, j = np.unravel_index(np.lexsort((dist.ravel(), inked.ravel()))[0], taken.shape)
    if taken[i, j] <= MAX_INK * padded[0] * padded[1]:
        note = (int(nx0[i, j]), int(ny0[i, j]), int(nx0[i, j]) + nw, int(ny0[i, j]) + nh)
        return Spot(note, _arrow(note, box), False, backed=bool(taken[i, j]))
    # גם שם יש הרבה כתב: צמוד למלבן, על רקע לבן, בלי חץ
    note = _attached(mask, box, nw, nh)
    return Spot(note, _arrow(note, box), False, backed=True)


# כמה למעלה ולמטה ממלבן מחפשים את הכתב שלו, כחלק מגובה המלבן (חצי שורה בערך)
SNAP_REACH = 0.5
# שורה שכמעט כולה "דיו" היא קצה של הצילום או צל, לא כתב
SNAP_FULL_ROW = 0.5
# המלבן אחרי ההתאמה: לא נמוך מזה ולא גבוה מזה, ביחס לגובה המקורי
SNAP_MIN, SNAP_MAX = 0.6, 1.5
# כמה פיקסלים ריקים להשאיר בין הכתב למלבן שמקיף אותו
SNAP_PAD = 3


def _bands(rows: np.ndarray, gap: int) -> list[tuple[int, int]]:
    """רצפים של שורות עם כתב (עם רווחים של עד gap שורות בתוכם): (ראשונה, אחרי האחרונה)."""
    bands: list[tuple[int, int]] = []
    for r in rows:
        if bands and r - bands[-1][1] <= gap:
            bands[-1] = (bands[-1][0], int(r) + 1)
        else:
            bands.append((int(r), int(r) + 1))
    return bands


def snap_box(ink: np.ndarray, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """מקרב את המלבן של Claude אל שורת הכתב שהוא אמור להקיף, למעלה או למטה בלבד.

    Claude נותן מיקום מקורב, ולפעמים המלבן יושב חצי שורה מתחת לכתב או מעליו. בודקים את הכתב
    ברוחב של המלבן, עד SNAP_REACH מגובהו מעליו ומתחתיו, מחלקים אותו לשורות כתב, ובוחרים את השורות
    שהכי חופפות למלבן. בזהירות: הרוחב לא משתנה, הגובה נשאר בין SNAP_MIN ל-SNAP_MAX מהמקורי, ואם אין
    שם כתב המלבן נשאר כמו שהוא.
    """
    h, w = ink.shape
    x0, y0, x1, y1 = (int(max(0, box[0])), int(max(0, box[1])), int(min(w, box[2])), int(min(h, box[3])))
    height = y1 - y0
    reach = int(height * SNAP_REACH)
    top, bottom = max(0, y0 - reach), min(h, y1 + reach)
    if x1 <= x0 or height < 4 or bottom <= top:
        return x0, y0, x1, y1
    share = ink[top:bottom, x0:x1].mean(axis=1)
    rows = top + np.flatnonzero((share > 0) & (share < SNAP_FULL_ROW))
    bands = [b for b in _bands(rows, max(2, height // 8)) if b[1] - b[0] >= 3]
    if not bands:
        return x0, y0, x1, y1
    # השורה שהכי חופפת למלבן, ואם אף אחת לא חופפת, הקרובה ביותר
    def score(b):
        overlap = min(b[1], y1) - max(b[0], y0)
        return (overlap, -abs((b[0] + b[1]) / 2 - (y0 + y1) / 2))
    b0, b1 = max(bands, key=score)
    # שורות צמודות לשורה שנבחרה (למשל שבר, או אינדקס מתחת לשורה) נכנסות איתה, כל עוד המלבן לא גבוה מדי
    for c0, c1 in bands:
        if (c1 <= b0 and b0 - c1 <= height // 6) or (c0 >= b1 and c0 - b1 <= height // 6):
            if max(b1, c1) - min(b0, c0) + 2 * SNAP_PAD <= SNAP_MAX * height:
                b0, b1 = min(b0, c0), max(b1, c1)
    ny0, ny1 = b0 - SNAP_PAD, b1 + SNAP_PAD
    if ny1 - ny0 < SNAP_MIN * height:  # שורה דקה: המלבן נשאר בגובה סביר, ממורכז עליה
        mid, half = (ny0 + ny1) / 2, SNAP_MIN * height / 2
        ny0, ny1 = int(mid - half), int(mid + half)
    if ny1 - ny0 > SNAP_MAX * height:
        return x0, y0, x1, y1
    return x0, max(0, ny0), x1, min(h, ny1)
