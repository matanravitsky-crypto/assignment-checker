"""עברית עם מתמטיקה על PDF, בלי ה-bidi של MuPDF: השורות נשברות ומסודרות כאן, וכל קטע מצויר במקום שלו.

למה: insert_htmlbox (Story של MuPDF) מפעיל את אלגוריתם ה-bidi, אבל מתעלם מכל סימן כיוון מפורש (LRE/PDF, LRI,
LRM, <bdo>, dir=ltr, unicode-bidi). הסטודנטים ראו "yi-" במקום "-yi", "7-=1+8" במקום "1+8=-7" ו-"(1-,1)" (נבדק
2026-11-13/14). תיקון של סימן שמוצג הפוך הוא תיקון שגוי.

איך:
- הטקסט מתחלק לקטעים (segments): קטע מתמטי (אותו ביטוי רגולרי וכללי קצוות כמו grade._ltr) מצויר משמאל לימין בדיוק
  כמו שנכתב. קטע עברי מצויר מימין לשמאל, אות אחרי אות, עם סוגריים במראה. בתוך עברית, רצף של סימנים "חזקים" משמאל
  לימין (ℝ², λ, ≠) נשאר בסדר שלו.
- מילה (בין רווחים) לא נשברת, גם כשהיא עברית ומתמטיקה צמודות ("ל-+yi,"). ביטוי מתמטי לא נשבר באמצע, אלא אם הוא
  רחב מהשורה: אז הוא נשבר ברווחים שבתוכו, וחלקיו באותה שורה עדיין נקראים משמאל לימין.
- שורה מסודרת מימין לשמאל ומיושרת לימין (או למרכז/לשמאל). פסיק ונקודה אחרי ביטוי נשארים בצד השמאלי שלו.
- כל אות נכתבת ב-TextWriter בסדר הלוגי (מימין לשמאל בעברית), כדי ש-get_text יחזיר את הטקסט קריא. אות שאין
  בגופן העברי (∉, ℝ, ✓) נלקחת מגופן סמלים של המערכת, והרוחב שלה נמדד באותו גופן.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

# אותו ביטוי כמו grade._MATH (tests/grading/test_rtl.py בודקת שהם זהים)
MATH = re.compile(r"[^\u0590-\u05FF\s,;:]*[A-Za-z0-9∅][^\u0590-\u05FF]*")
_HEB = re.compile(r"[\u0590-\u05FF]")
_MIRROR = str.maketrans("()[]{}<>", ")(][}{><")
_OPEN, _CLOSE = "([{", ")]}"
# בתוך עברית: רצף של תווים שאינם עברית, רווח או פיסוק נשאר משמאל לימין (ℝ², λ, ≠, ✓)
_ISLAND = re.compile(r"[^\u0590-\u05FF\s.,;:!?()\[\]{}<>\"'\-–־/]+")
_ALNUM = re.compile(r"[A-Za-z0-9∅]")

_BOLD_NAMES = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "NotoSansHebrew-Bold.ttf", "FreeSansBold.ttf"]
# לתווים שאין בגופן העברי: Segoe UI Symbol ב-Windows, DejaVu/Noto ב-Linux, Apple Symbols ב-macOS
_FALLBACKS = [
    Path("C:/Windows/Fonts/seguisym.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Apple Symbols.ttf"),
]


def _heb(c: str) -> bool:
    return bool(_HEB.match(c))


# ---------- קטעים ----------
def _depth(s: str) -> int:
    return sum(c in _OPEN for c in s) - sum(c in _CLOSE for c in s)


def segments(text: str, math: bool = True) -> list[tuple[str, bool]]:
    """הטקסט בסדר הלוגי, כקטעים (טקסט, מתמטי?). כללי הקצוות של grade._ltr: מקף אחרי אות עברית ("ל-A"), מקף של
    משפט ("הגשה 0 - ...") וסוגר פותח בסוף ("0 (הערה)") שייכים לעברית; "7-" בסוף ביטוי הוא "-7". ובנוסף: סוגר
    שאין לו זוג בקצה הביטוי ("(ראו 3)") שייך לעברית שסביבו."""
    out: list[tuple[str, bool]] = []

    def add(s: str, m: bool) -> None:
        if not s:
            return
        if out and not m and not out[-1][1]:
            out[-1] = (out[-1][0] + s, False)
        else:
            out.append((s, m))

    pos = 0
    if math:
        for mt in MATH.finditer(text):
            start, run = mt.start(), mt.group(0)
            if run.startswith("-") and start > 0 and _heb(text[start - 1]):
                start, run = start + 1, run[1:]
            core = re.sub(r"\s+[-–]\s*$", "", run).rstrip(" ,;:.([{")
            lead = 0
            while core and core[0] in _OPEN and _depth(core) > 0:
                core, lead = core[1:], lead + 1
            while core and core[-1] in _CLOSE and _depth(core) < 0:
                core = core[:-1]
            if not _ALNUM.search(core):
                continue
            start += lead
            add(text[pos:start], False)
            add(re.sub(r"(\d+(?:[./]\d+)?)-$", r"-\1", core), True)
            pos = start + len(core)
    add(text[pos:], False)
    return out


# ---------- גופנים ----------
class _Fonts:
    """הגופנים של חוט אחד (הבדיקה מסמנת כמה עבודות במקביל, ואובייקט Font של MuPDF לא משותף בין חוטים)."""

    def __init__(self):
        from .grade import _FONT
        self.regular = pymupdf.Font(fontfile=str(_FONT)) if _FONT else pymupdf.Font("helv")
        bold = next((_FONT.parent / n for n in _BOLD_NAMES if _FONT and (_FONT.parent / n).is_file()), None)
        self.bold = pymupdf.Font(fontfile=str(bold)) if bold else self.regular
        self.fallbacks = [pymupdf.Font(fontfile=str(p)) for p in _FALLBACKS if p.is_file()][:2]
        self.asc = self.regular.ascender
        self.desc = self.regular.descender
        self._cache: dict[tuple[str, bool], tuple[pymupdf.Font, float]] = {}

    def glyph(self, c: str, bold: bool) -> tuple[pymupdf.Font, float]:
        """הגופן שמצייר את התו, והרוחב שלו בגודל 1."""
        key = (c, bold)
        hit = self._cache.get(key)
        if hit is None:
            order = [self.bold, self.regular] if bold else [self.regular]
            font = next((f for f in order + self.fallbacks if f.has_glyph(ord(c))), order[0])
            hit = self._cache[key] = (font, font.text_length(c, fontsize=1))
        return hit

    def width(self, s: str, bold: bool) -> float:
        return sum(self.glyph(c, bold)[1] for c in s)


_local = threading.local()


def _fonts() -> _Fonts:
    f = getattr(_local, "fonts", None)
    if f is None:
        f = _local.fonts = _Fonts()
    return f


# ---------- פריסה ----------
@dataclass
class Piece:
    text: str
    ltr: bool
    w: float          # רוחב בגודל גופן 1
    run: int = -1     # מספר הביטוי המתמטי (כדי לחבר מחדש חלקים של ביטוי שנשבר ושנפלו באותה שורה)


@dataclass
class Layout:
    lines: list[list[list[Piece]]] = field(default_factory=list)   # שורה = מילים (בסדר הלוגי), מילה = חלקים
    widths: list[float] = field(default_factory=list)              # רוחב כל שורה, בגודל 1
    space: float = 0.0


def _words(par: str, bold: bool, math: bool) -> list[list[Piece]]:
    F = _fonts()
    words: list[list[Piece]] = []
    cur: list[Piece] = []

    def piece(s: str, ltr: bool, run: int = -1) -> None:
        cur.append(Piece(s, ltr, F.width(s, bold), run))

    for i, (seg, is_math) in enumerate(segments(par, math)):
        if is_math:
            piece(seg, True, i)
            continue
        for tok in re.split(r"(\s+)", seg):
            if not tok:
                continue
            if tok.isspace():
                if cur:
                    words.append(cur)
                    cur = []
                continue
            pos = 0
            for m in _ISLAND.finditer(tok):
                if m.start() > pos:
                    piece(tok[pos:m.start()], False)
                piece(m.group(0), True)
                pos = m.end()
            if pos < len(tok):
                piece(tok[pos:], False)
    if cur:
        words.append(cur)
    return words


def _split(word: list[Piece], bold: bool) -> list[list[Piece]]:
    """מילה רחבה מהשורה: נשברת ברווחים שבתוך הביטויים המתמטיים שלה."""
    F = _fonts()
    out: list[list[Piece]] = []
    cur: list[Piece] = []
    for p in word:
        parts = [s for s in p.text.split(" ") if s] if p.ltr and p.run >= 0 else [p.text]
        for j, s in enumerate(parts):
            if j:
                out.append(cur)
                cur = []
            cur.append(Piece(s, p.ltr, F.width(s, bold), p.run))
    out.append(cur)
    return [w for w in out if w]


def _join(line: list[list[Piece]], space: float) -> list[list[Piece]]:
    """חלקים של אותו ביטוי מתמטי שנשבר ונפלו באותה שורה: חלק אחד, משמאל לימין, עם רווח ביניהם."""
    out: list[list[Piece]] = []
    for word in line:
        if out and word[0].run >= 0 and out[-1][-1].run == word[0].run:
            a, b = out[-1][-1], word[0]
            out[-1] = out[-1][:-1] + [Piece(a.text + " " + b.text, True, a.w + space + b.w, a.run)] + word[1:]
        else:
            out.append(list(word))
    return out


def layout(text: str, width: float, bold: bool = False, math: bool = True) -> Layout:
    """שבירת שורות חמדנית לפי רוחב (ביחידות של גודל גופן 1: width = רוחב בנקודות / גודל הגופן)."""
    F = _fonts()
    space = F.glyph(" ", bold)[1]
    out = Layout(space=space)
    for par in str(text).split("\n"):
        queue = _words(par, bold, math)
        lines: list[list[list[Piece]]] = []
        cur: list[list[Piece]] = []
        cw = 0.0
        while queue:
            word = queue.pop(0)
            ww = sum(p.w for p in word)
            if cur and cw + space + ww > width + 1e-6:
                lines.append(cur)
                cur, cw = [], 0.0
            if not cur and ww > width + 1e-6:
                parts = _split(word, bold)
                if len(parts) > 1:
                    queue[:0] = parts
                    continue
            cw += ww + (space if cur else 0)
            cur.append(word)
        lines.append(cur)   # פסקה ריקה היא שורה ריקה
        for line in lines:
            line = _join(line, space)
            out.lines.append(line)
            out.widths.append(sum(p.w for w in line for p in w) + space * max(len(line) - 1, 0))
    return out


def width(text: str, size: float, bold: bool = False, math: bool = True) -> float:
    """הרוחב של הטקסט בשורה אחת, בנקודות."""
    lay = layout(text, float("inf"), bold, math)
    return max(lay.widths, default=0.0) * size


def measure(text: str, width: float, size: float, bold: bool = False, lh: float = 1.25, math: bool = True) -> float:
    """הגובה (נקודות) שהטקסט צריך ברוחב width ובגודל size."""
    return len(layout(text, width / size, bold, math).lines) * size * lh


def fit(text: str, rect: pymupdf.Rect, size: float, bold: bool = False, lh: float = 1.25, math: bool = True,
        min_size: float = 4.0) -> tuple[float, Layout] | None:
    """הגודל הגדול ביותר (עד size) שבו הטקסט נכנס למלבן, והפריסה שלו. None אם גם min_size לא נכנס."""
    s = size
    while s >= min_size:
        lay = layout(text, rect.width / s, bold, math)
        if len(lay.lines) * s * lh <= rect.height + 0.01 and max(lay.widths, default=0) * s <= rect.width + 0.01:
            return s, lay
        s *= 0.93
    return None


def _rgb(color) -> tuple[float, float, float]:
    if isinstance(color, str):
        return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return tuple(color)


def draw(page: pymupdf.Page, rect, text: str, size: float, color="#000000", *, bold: bool = False,
         align: str = "right", lh: float = 1.25, math: bool = True, shrink: bool = True,
         min_size: float = 4.0) -> float | None:
    """כותב את הטקסט במלבן (בקואורדינטות של העמוד כפי שהוא מוצג, גם כשהעמוד מסובב), מלמעלה, מיושר ל-align.
    shrink: מקטין עד שהכול נכנס (כמו scale_low=0 של insert_htmlbox), ו-None כשגם min_size לא נכנס.
    בלי shrink: כותב בגודל size גם אם זה חורג. מחזיר את הגובה שנכתב."""
    rect = pymupdf.Rect(rect)
    if rect.is_empty or rect.width <= 0 or rect.height <= 0 or not str(text).strip():
        return None if rect.is_empty or rect.width <= 0 or rect.height <= 0 else 0.0
    if shrink:
        got = fit(text, rect, size, bold, lh, math, min_size)
        if got is None:
            return None
        size, lay = got
    else:
        lay = layout(text, rect.width / size, bold, math)
    write(page, rect, lay, size, color, bold=bold, align=align, lh=lh)
    return len(lay.lines) * size * lh


def write(page: pymupdf.Page, rect: pymupdf.Rect, lay: Layout, size: float, color, *, bold: bool = False,
          align: str = "right", lh: float = 1.25) -> None:
    """מצייר פריסה מוכנה. כל אות לחוד, בסדר הלוגי: בעברית מימין לשמאל, בקטע מתמטי משמאל לימין."""
    F = _fonts()
    rot = page.rotation
    tw = pymupdf.TextWriter(page.rect)
    if rot:   # פורסים כאילו העמוד לא מסובב, ומסובבים את כל הטקסט סביב הפינה של המלבן
        fix_d = rect.tl
        fix_u = fix_d * page.derotation_matrix

        def at(x: float, y: float) -> pymupdf.Point:
            return pymupdf.Point(fix_u.x + x - fix_d.x, fix_u.y + y - fix_d.y)
    else:
        def at(x: float, y: float) -> pymupdf.Point:
            return pymupdf.Point(x, y)

    def put(x: float, y: float, c: str) -> float:
        font, w = F.glyph(c, bold)
        tw.append(at(x, y), c, font=font, fontsize=size)
        return w * size

    line_h = size * lh
    base0 = rect.y0 + (line_h - (F.asc - F.desc) * size) / 2 + F.asc * size
    for k, (line, w1) in enumerate(zip(lay.lines, lay.widths)):
        base = base0 + k * line_h
        w = w1 * size
        x = rect.x1 if align == "right" else rect.x0 + w if align == "left" else (rect.x0 + rect.x1 + w) / 2
        for j, word in enumerate(line):
            if j:
                x -= put(x - lay.space * size, base, " ")
            for p in word:
                pw = p.w * size
                x -= pw
                if p.ltr:
                    xx = x
                    for c in p.text:
                        xx += put(xx, base, c)
                else:
                    xx = x + pw
                    for c in p.text:
                        c = c.translate(_MIRROR)
                        xx -= F.glyph(c, bold)[1] * size
                        put(xx, base, c)
    if rot:
        m = page.derotation_matrix
        tw.write_text(page, color=_rgb(color), morph=(fix_u, pymupdf.Matrix(m.a, -m.b, -m.c, m.d, 0, 0)))
    else:
        tw.write_text(page, color=_rgb(color))
