"""איפה לכתוב כל הערה על העבודה: במקום הריק הקרוב ביותר לטעות, עם חץ שלא עובר על שום דבר.

העמוד נסרק לתמונה קטנה, ומה שכהה בה הוא "דיו" (כתב היד, קווים, צללים של הצילום). קווי המשבצות
של דף המחברת בהירים, ולכן הם לא נחשבים. הערה נכתבת רק במקום שאין בו דיו, מלבן אדום או הערה אחרת,
והחץ ממנה אל המלבן לא עובר על כל אלה. אם אין מקום כזה, ההערה הולכת למקום הקרוב שיש בו הכי מעט דיו.

הכל כאן בפיקסלים של התמונה הקטנה. grade.py ממיר מנקודות של ה-PDF ובחזרה.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# פיקסל כהה מזה הוא דיו (0 שחור, 255 לבן). קווי המשבצות של המחברת בהירים יותר
INK_BELOW = 150
# כמה פיקסלים ריקים להשאיר סביב ההערה, כדי שלא תיגע בשום דבר
PAD = 3
# הצעד שבו מחפשים מקום. קטן יותר: מדויק יותר ואיטי יותר
STEP = 2


@dataclass
class Spot:
    note: tuple[int, int, int, int]                 # המלבן של ההערה: x0, y0, x1, y1
    arrow: tuple[tuple[int, int], tuple[int, int]]  # מההערה אל המלבן האדום
    clear: bool                                     # True: ההערה והחץ לא נוגעים בשום דבר


def ink_mask(gray: np.ndarray) -> np.ndarray:
    return gray < INK_BELOW


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


def find_spot(mask: np.ndarray, box: tuple[float, float, float, float], size: tuple[int, int]) -> Spot:
    """המקום הריק הקרוב ביותר למלבן `box` להערה בגודל `size` (רוחב, גובה), עם חץ שלא עובר על שום דבר.

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

    free = np.argwhere(taken == 0)
    order = free[np.argsort(dist[free[:, 0], free[:, 1]], kind="stable")]
    for i, j in order[:400]:
        note = (int(nx0[i, j]), int(ny0[i, j]), int(nx0[i, j]) + nw, int(ny0[i, j]) + nh)
        start, end = _arrow(note, box)
        if _path_is_clear(mask, start, end):
            return Spot(note, (start, end), True)
    # אין מקום נקי: הכי מעט דיו, ואחריו הכי קרוב
    i, j = np.unravel_index(np.lexsort((dist.ravel(), taken.ravel()))[0], taken.shape)
    note = (int(nx0[i, j]), int(ny0[i, j]), int(nx0[i, j]) + nw, int(ny0[i, j]) + nh)
    return Spot(note, _arrow(note, box), False)
