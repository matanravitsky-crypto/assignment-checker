"""איפה לכתוב הערה על דף של סטודנט: במקום ריק, לא על מה שהוא כתב.

העמוד מצויר פעם אחת ברזולוציה נמוכה ומחולק לרשת של משבצות. משבצת עם דיו (פיקסלים כהים) תפוסה.
לכל הערה מחפשים את המלבן הריק הקרוב ביותר למלבן הסימון, ואם ההערה לא צמודה אליו מציירים חץ קצר.
בלי numpy: טבלת סכומים (integral image) על הרשת, כך שכל בדיקה של מלבן היא ארבע קריאות.
"""
from __future__ import annotations

import pymupdf

CELL = 6          # גודל משבצת בנקודות PDF
DARK = 110        # פיקסל אפור כהה מזה הוא דיו. קווי מחברת בהירים יותר
INK_SHARE = 0.03  # משבצת שיותר מזה מהפיקסלים שלה כהים תפוסה
MARGIN = 4


class FreeSpace:
    def __init__(self, page: pymupdf.Page):
        r = page.rect  # העמוד כפי שהוא מוצג
        self.rect = r
        self.cols = max(1, int(r.width // CELL))
        self.rows = max(1, int(r.height // CELL))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1, 1), colorspace=pymupdf.csGRAY, alpha=False)
        sx, sy = pix.width / self.cols, pix.height / self.rows
        dark = [0] * (self.cols * self.rows)
        data, stride = pix.samples, pix.stride
        col = [min(int(x / sx), self.cols - 1) for x in range(pix.width)]
        for y in range(pix.height):
            row, base = min(int(y / sy), self.rows - 1) * self.cols, y * stride
            for x, v in enumerate(data[base:base + pix.width]):
                if v < DARK:
                    dark[row + col[x]] += 1
        limit = INK_SHARE * sx * sy
        self.busy = [d > limit for d in dark]
        self._build()

    def _build(self) -> None:
        c = self.cols
        s = [0] * ((c + 1) * (self.rows + 1))
        for j in range(self.rows):
            acc = 0
            for i in range(c):
                acc += self.busy[j * c + i]
                s[(j + 1) * (c + 1) + i + 1] = s[j * (c + 1) + i + 1] + acc
        self._sum = s

    def _ink(self, i0: int, j0: int, i1: int, j1: int) -> int:
        c, s = self.cols + 1, self._sum
        return s[j1 * c + i1] - s[j0 * c + i1] - s[j1 * c + i0] + s[j0 * c + i0]

    def occupy(self, r: pymupdf.Rect) -> None:
        """מסמן מלבן כתפוס (הערה או סימון שכבר צוירו)."""
        i0, j0, i1, j1 = self._cells(r)
        for j in range(j0, j1):
            for i in range(i0, i1):
                self.busy[j * self.cols + i] = True
        self._build()

    def _cells(self, r: pymupdf.Rect) -> tuple[int, int, int, int]:
        clamp = lambda v, n: max(0, min(n, v))
        return (clamp(int(r.x0 // CELL), self.cols), clamp(int(r.y0 // CELL), self.rows),
                clamp(int(-(-r.x1 // CELL)), self.cols), clamp(int(-(-r.y1 // CELL)), self.rows))

    def place(self, box: pymupdf.Rect, width: float, height: float) -> pymupdf.Rect:
        """המלבן הריק (או הכי פחות כתוב) שהכי קרוב ל-box, בגודל width x height."""
        w = max(1, int(-(-min(width, self.rect.width - 2 * MARGIN) // CELL)))
        h = max(1, int(-(-min(height, self.rect.height - 2 * MARGIN) // CELL)))
        bi0, bj0, bi1, bj1 = self._cells(box)
        best, best_score = None, None
        for j in range(0, self.rows - h + 1):
            dy = max(bj0 - (j + h), j - bj1, 0)
            for i in range(0, self.cols - w + 1):
                dx = max(bi0 - (i + w), i - bi1, 0)
                if dx == 0 and dy == 0:
                    continue  # לא על המלבן עצמו
                # דיו עולה הרבה יותר ממרחק; עדיפות קלה לצד ימין (עברית)
                score = self._ink(i, j, i + w, j + h) * 1000 + dx + dy * 1.5 + (self.cols - i - w) * 0.01
                if best_score is None or score < best_score:
                    best, best_score = (i, j), score
        if best is None:
            return pymupdf.Rect(MARGIN, MARGIN, MARGIN + width, MARGIN + height)
        x0, y0 = best[0] * CELL, best[1] * CELL
        x1, y1 = min(x0 + width, self.rect.width - MARGIN), min(y0 + height, self.rect.height - MARGIN)
        return pymupdf.Rect(max(x1 - width, MARGIN), max(y1 - height, MARGIN), x1, y1)


def note_size(text: str, width: float = 160, font: float = 10) -> tuple[float, float]:
    """כמה מקום הערה צריכה, בערך: אורך הטקסט חלקי תווים לשורה."""
    per_line = max(1, int(width / (font * 0.5)))
    lines = sum(max(1, -(-len(part) // per_line)) for part in text.split("\n"))
    return width, lines * font * 1.3 + 4


def arrow(note: pymupdf.Rect, box: pymupdf.Rect) -> tuple[pymupdf.Point, pymupdf.Point] | None:
    """קו מההערה למלבן, אם הם לא צמודים: מהנקודה הקרובה בהערה לנקודה הקרובה במלבן."""
    def near(r: pymupdf.Rect, p: pymupdf.Point) -> pymupdf.Point:
        return pymupdf.Point(min(max(p.x, r.x0), r.x1), min(max(p.y, r.y0), r.y1))
    a = near(note, (box.tl + box.br) / 2)
    b = near(box, a)
    return None if abs(a - b) < 2 * CELL else (a, b)
