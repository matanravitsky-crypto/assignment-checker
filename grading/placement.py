"""איפה לכתוב הערה על דף של סטודנט: במקום ריק, לא על מה שהוא כתב, עם קו אליה שלא עובר על דיו.

העמוד מצויר פעם אחת ברזולוציה נמוכה ומחולק לרשת של משבצות. משבצת עם דיו (פיקסלים כהים) תפוסה.
מהמלבן של הסימון מתפשטים (BFS) רק דרך משבצות נקיות לגמרי. ההערה הולכת למקום הריק שהדרך אליו
הכי קצרה, והקו הולך בדיוק בדרך הזו: הוא יכול להתכופף כמה פעמים שצריך, אבל לא עובר על דיו.
אם אין מקום ריק שאפשר להגיע אליו, ההערה נכתבת במקום הכי פחות כתוב, בלי קו.
בלי numpy: טבלת סכומים (integral image) על הרשת, כך שכל בדיקה של מלבן היא ארבע קריאות.

בלי Claude ובלי טוקנים. הכללים, ההסבר המלא והעלות: grading/COMMENTS_PROTOCOL.md
"""
from __future__ import annotations

from collections import deque
from typing import Callable

import pymupdf

CELL = 6          # גודל משבצת בנקודות PDF
ZOOM = 1.5        # רזולוציית הציור (108 dpi): עט דק לא מתמזג לאפור בהיר
DARK = 140        # פיקסל אפור כהה מזה הוא דיו. קווי מחברת בהירים יותר
INK_SHARE = 0.03  # להערה: משבצת שיותר מזה מהפיקסלים שלה כהים תפוסה
LINE_INK = 1      # לקו: משבצת עם יותר פיקסלים כהים מזה תפוסה (כמעט אפס, רק רעש סריקה)
CLEARANCE = 1.5   # כמה נקודות מכל צד של הקו צריכות להיות נקיות כשמיישרים אותו

_STEPS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


class FreeSpace:
    def __init__(self, page: pymupdf.Page):
        r = page.rect  # העמוד כפי שהוא מוצג
        self.rect = r
        self.cols = max(1, int(r.width // CELL))
        self.rows = max(1, int(r.height // CELL))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), colorspace=pymupdf.csGRAY, alpha=False)
        sx, sy = pix.width / self.cols, pix.height / self.rows
        bounds = [(int(i * sx), int((i + 1) * sx)) for i in range(self.cols)]
        is_dark = bytes(1 if v < DARK else 0 for v in range(256))
        dark = [0] * (self.cols * self.rows)
        data, stride = pix.samples, pix.stride
        for y in range(pix.height):
            row = data[y * stride:y * stride + pix.width].translate(is_dark)
            base = min(int(y / sy), self.rows - 1) * self.cols
            for i, (a, b) in enumerate(bounds):
                dark[base + i] += sum(row[a:b])
        limit = INK_SHARE * sx * sy
        self.busy = [d > limit for d in dark]     # להערה
        self.clear = [d <= LINE_INK for d in dark]  # לקו
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

    def _cells(self, r: pymupdf.Rect) -> tuple[int, int, int, int]:
        clamp = lambda v, n: max(0, min(n, v))
        return (clamp(int(r.x0 // CELL), self.cols), clamp(int(r.y0 // CELL), self.rows),
                clamp(int(-(-r.x1 // CELL)), self.cols), clamp(int(-(-r.y1 // CELL)), self.rows))

    def snap(self, r: pymupdf.Rect) -> pymupdf.Rect:
        """המלבן מורחב לגבולות המשבצות, כדי שהקו יגיע לשפה שלו רק דרך משבצת נקייה."""
        i0, j0, i1, j1 = self._cells(r)
        return pymupdf.Rect(i0 * CELL, j0 * CELL, i1 * CELL, j1 * CELL)

    def occupy(self, r: pymupdf.Rect) -> None:
        """מסמן מלבן כתפוס (הערה או סימון שכבר צוירו)."""
        i0, j0, i1, j1 = self._cells(r)
        for j in range(j0, j1):
            for i in range(i0, i1):
                self.busy[j * self.cols + i] = True
                self.clear[j * self.cols + i] = False
        self._build()

    def occupy_line(self, points: list[pymupdf.Point]) -> None:
        """המשבצות שקו שכבר צויר עובר בהן תפוסות, כדי שקו אחר לא יחצה אותו."""
        for a, b in zip(points, points[1:]):
            for p in _samples(a, b):
                k = self._cell_at(p)
                if k is not None:
                    self.busy[k], self.clear[k] = True, False
        self._build()

    def _cell_at(self, p: pymupdf.Point) -> int | None:
        i, j = int(p.x // CELL), int(p.y // CELL)
        return j * self.cols + i if 0 <= i < self.cols and 0 <= j < self.rows else None

    def _open(self, i: int, j: int) -> bool:
        return 0 <= i < self.cols and 0 <= j < self.rows and self.clear[j * self.cols + i]

    def _paths_from(self, box: pymupdf.Rect) -> tuple[list[int], list[int]]:
        """מרחק (בצעדים) מכל משבצת נקייה אל המלבן, ולאן הצעד הבא לכיוונו. -1 = אין דרך נקייה."""
        n = self.cols * self.rows
        dist, toward = [-1] * n, [-1] * n
        i0, j0, i1, j1 = self._cells(box)
        queue = deque()
        for j in range(j0 - 1, j1 + 1):
            for i in range(i0 - 1, i1 + 1):
                if (i0 <= i < i1 and j0 <= j < j1) or not self._open(i, j):
                    continue
                dist[j * self.cols + i] = 0
                queue.append((i, j))
        while queue:
            i, j = queue.popleft()
            k = j * self.cols + i
            for di, dj in _STEPS:
                ni, nj = i + di, j + dj
                if not self._open(ni, nj) or dist[nj * self.cols + ni] >= 0:
                    continue
                if di and dj and not (self._open(i + di, j) and self._open(i, j + dj)):
                    continue  # באלכסון רק כששתי המשבצות שבצדדים נקיות: לא חותכים פינה של דיו
                dist[nj * self.cols + ni], toward[nj * self.cols + ni] = dist[k] + 1, k
                queue.append((ni, nj))
        return dist, toward

    def place(self, box: pymupdf.Rect, width: float, height: float) -> tuple[pymupdf.Rect, list[pymupdf.Point] | None]:
        """איפה לכתוב הערה בגודל width x height ליד box, והקו אליה (None = צמודה למלבן, או שאין דרך נקייה).
        box צריך להיות כבר מיושר למשבצות (snap) ותפוס (occupy)."""
        w = max(1, min(int(-(-width // CELL)), self.cols - 2))
        h = max(1, min(int(-(-height // CELL)), self.rows - 2))
        dist, toward = self._paths_from(box)
        bi0, bj0, bi1, bj1 = self._cells(box)
        best, best_score = None, None
        for j in range(1, self.rows - h):
            for i in range(1, self.cols - w):
                # מתחת לזה הדרך לא יכולה להיות: מרחק בצעדי שחמט
                low = max(bi0 - (i + w), i - bi1, bj0 - (j + h), j - bj1, 0)
                if best_score is not None and low >= best_score or self._ink(i, j, i + w, j + h):
                    continue
                d, start = self._nearest_on_ring(i, j, w, h, dist)
                if start is None:
                    continue
                score = d + (self.cols - i - w) * 0.001  # בשוויון: צד ימין, כמו עברית
                if best_score is None or score < best_score:
                    best, best_score = (i, j, start), score
        if best is None:
            return self._least_ink(box, w, h), None
        i, j, start = best
        note = pymupdf.Rect(i * CELL, j * CELL, (i + w) * CELL, (j + h) * CELL)
        return note, self._line(note, box, start, toward)

    def _nearest_on_ring(self, i: int, j: int, w: int, h: int, dist: list[int]) -> tuple[int, int | None]:
        """המשבצת הכי קרובה למלבן בטבעת שמסביב להערה."""
        best, start = None, None
        ring = ([(x, j - 1) for x in range(i - 1, i + w + 1)] + [(x, j + h) for x in range(i - 1, i + w + 1)]
                + [(i - 1, y) for y in range(j, j + h)] + [(i + w, y) for y in range(j, j + h)])
        for x, y in ring:
            if 0 <= x < self.cols and 0 <= y < self.rows:
                d = dist[y * self.cols + x]
                if d >= 0 and (best is None or d < best):
                    best, start = d, y * self.cols + x
        return best, start

    def _line(self, note: pymupdf.Rect, box: pymupdf.Rect, start: int, toward: list[int]) -> list[pymupdf.Point] | None:
        cells = [start]
        while toward[cells[-1]] >= 0:
            cells.append(toward[cells[-1]])
        centers = [pymupdf.Point((k % self.cols + 0.5) * CELL, (k // self.cols + 0.5) * CELL) for k in cells]
        a, b = _nearest(note, centers[0]), _nearest(box, centers[-1])
        if len(centers) == 1 and abs(a - b) <= CELL:
            return None  # ההערה ממש ליד המלבן
        return [a] + self._straighten(centers) + [b]

    def _straighten(self, pts: list[pymupdf.Point]) -> list[pymupdf.Point]:
        """מוותר על פיתולים מיותרים: קופץ לנקודה הכי רחוקה שהקו הישר אליה עדיין נקי."""
        out, i = [pts[0]], 0
        while i < len(pts) - 1:
            j = len(pts) - 1
            while j > i + 1 and not self._clean(pts[i], pts[j]):
                j -= 1
            out.append(pts[j])
            i = j
        return out

    def _clean(self, a: pymupdf.Point, b: pymupdf.Point) -> bool:
        for p in _samples(a, b):
            for dx, dy in ((0, 0), (CLEARANCE, 0), (-CLEARANCE, 0), (0, CLEARANCE), (0, -CLEARANCE)):
                k = self._cell_at(pymupdf.Point(p.x + dx, p.y + dy))
                if k is None or not self.clear[k]:
                    return False
        return True

    def _least_ink(self, box: pymupdf.Rect, w: int, h: int) -> pymupdf.Rect:
        """אין מקום ריק עם דרך נקייה: המקום הכי פחות כתוב ליד המלבן, בלי קו."""
        bi0, bj0, bi1, bj1 = self._cells(box)
        best, best_score = (1, 1), None
        for j in range(1, self.rows - h):
            for i in range(1, self.cols - w):
                dx, dy = max(bi0 - (i + w), i - bi1, 0), max(bj0 - (j + h), j - bj1, 0)
                if dx == 0 and dy == 0:
                    continue
                score = self._ink(i, j, i + w, j + h) * 1000 + dx + dy * 1.5
                if best_score is None or score < best_score:
                    best, best_score = (i, j), score
        i, j = best
        return pymupdf.Rect(i * CELL, j * CELL, (i + w) * CELL, (j + h) * CELL)


def _nearest(r: pymupdf.Rect, p: pymupdf.Point) -> pymupdf.Point:
    return pymupdf.Point(min(max(p.x, r.x0), r.x1), min(max(p.y, r.y0), r.y1))


def _samples(a: pymupdf.Point, b: pymupdf.Point, step: float = 1.0):
    n = max(1, int(abs(b - a) / step))
    for t in range(n + 1):
        yield a + (b - a) * (t / n)


def note_size(text: str, width: float = 160, font: float = 10) -> tuple[float, float]:
    """כמה מקום הערה צריכה, בערך: אורך הטקסט חלקי תווים לשורה."""
    per_line = max(1, int(width / (font * 0.5)))
    lines = sum(max(1, -(-len(part) // per_line)) for part in text.split("\n"))
    return width, lines * font * 1.3 + 4


# ---------- ציור ----------
RED = (0.85, 0, 0)
FONT = 14    # גודל הכתב של ההערות
WIDTH = 210  # רוחב ההערה בנקודות


def draw(page: pymupdf.Page, marks: list[tuple[pymupdf.Rect, str]],
         write: Callable[[pymupdf.Page, pymupdf.Rect, str], None]) -> list[bool | None]:
    """מצייר על עמוד אחד: מלבן אדום סביב כל סימון, ההערה במקום ריק, וקו עם ראש חץ שלא עובר על דיו.
    marks: (מלבן בנקודות של העמוד כפי שהוא מוצג, הערה). write(page, rect, text) כותב את ההערה.
    מחזיר לכל סימון: True = הערה עם קו, False = הערה צמודה בלי קו, None = בלי הערה או בלי דרך נקייה."""
    free = FreeSpace(page) if any(text for _, text in marks) else None
    if free:
        # מיושר למשבצות, כדי שהקו יגיע לשפה של המלבן רק דרך משבצת נקייה
        marks = [(free.snap(box), text) for box, text in marks]
    m = page.derotation_matrix
    for box, _ in marks:
        page.draw_rect(box * m, color=RED, width=1.4, overlay=True)
        if free:
            free.occupy(box)
    result: list[bool | None] = []
    for box, text in marks:
        if not text:
            result.append(None)
            continue
        note, line = free.place(box, *note_size(text, WIDTH, FONT))
        free.occupy(note)
        write(page, note, text)
        if line:
            page.draw_polyline([p * m for p in line], color=RED, width=1, overlay=True)
            page.draw_polyline([p * m for p in _head(line[-2], line[-1])], color=RED, fill=RED, closePath=True, overlay=True)
            free.occupy_line(line)
            result.append(True)
        else:
            result.append(False if free.snap(note + (-CELL, -CELL, CELL, CELL)).intersects(box) else None)
    return result


def _head(a: pymupdf.Point, b: pymupdf.Point, size: float = 5) -> list[pymupdf.Point]:
    """ראש חץ קטן בקצה b, בכיוון a->b."""
    d = b - a
    n = abs(d) or 1
    u = pymupdf.Point(d.x / n, d.y / n)
    side = pymupdf.Point(-u.y, u.x) * (size * 0.45)
    base = b - u * size
    return [b, base + side, base - side]


def from_thousandths(page: pymupdf.Page, x0: float, y0: float, x1: float, y1: float) -> pymupdf.Rect:
    """מלבן באלפיות של העמוד (כמו ש-Claude מחזיר) -> נקודות של העמוד כפי שהוא מוצג."""
    r = page.rect
    return pymupdf.Rect(x0 / 1000 * r.width, y0 / 1000 * r.height, x1 / 1000 * r.width, y1 / 1000 * r.height)


# ---------- שורת פקודה, לכל צ'אט או סקריפט ----------
def main(argv: list[str] | None = None) -> int:
    """python -m grading.placement in.pdf marks.json out.pdf

    marks.json: רשימה של {"page": 1, "x0": .., "y0": .., "x1": .., "y1": .., "text": ".."} באלפיות של העמוד,
    או קובץ Grading notes/0001.json (משתמשים ב-"marks" שבו). מדפיס שורה אחת, כדי לחסוך טוקנים למי שקורא."""
    import argparse
    import json
    import sys

    from .grade import _archive, _html, _write

    ap = argparse.ArgumentParser(prog="python -m grading.placement", description=main.__doc__.splitlines()[0])
    ap.add_argument("pdf")
    ap.add_argument("marks")
    ap.add_argument("out")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # בחלון של Windows העברית אחרת יוצאת משובשת
    with open(a.marks, encoding="utf-8-sig") as f:
        data = json.load(f)
    marks = data.get("marks", []) if isinstance(data, dict) else data
    archive = _archive()
    write = lambda page, rect, text: _write(page, rect, _html(text, FONT), archive)
    counts = {True: 0, False: 0, None: 0}
    with pymupdf.open(a.pdf) as doc:
        by_page: dict[int, list] = {}
        for mk in marks:
            n = int(mk["page"]) - 1
            if not 0 <= n < doc.page_count:
                print(f"סימון בעמוד {mk['page']}, אבל ב-PDF יש {doc.page_count} עמודים", file=sys.stderr)
                return 2
            box = from_thousandths(doc[n], *(float(mk[k]) for k in ("x0", "y0", "x1", "y1")))
            by_page.setdefault(n, []).append((box, str(mk.get("text") or "").strip()))
        for n, page_marks in by_page.items():
            for r in draw(doc[n], page_marks, write):
                counts[r] += 1
        doc.save(a.out, garbage=4, deflate=True)
    print(f"{len(marks)} סימונים ב-{len(by_page)} עמודים: {counts[True]} עם קו נקי, {counts[False]} צמודים, "
          f"{counts[None]} בלי קו (בלי הערה או בלי דרך נקייה) -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
