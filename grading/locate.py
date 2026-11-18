"""Zoom pass: after grading, every box is placed again on a close-up of its part of the page, and so is where a part
starts (its score is drawn there) when the placed boxes contradict it. The system runs it after each grading, the
skill's `mark` before it draws.

Claude grades a whole page at a time (about 1568 pixels on the long side, a grid line every 10%), while a line of
handwriting is about 4% of the page. So the boxes it returns are roughly right but loose: they often wrap 3-5 lines,
or slip one line down (audit of 20 graded works, 2026-11-12, docs/Meta-evaluator report). Here each box gets a crop
of the page around it, about twice as large, with its own fine grid and the rough box drawn in blue, and a cheaper
model (LOCATE_MODEL, Sonnet by default) is asked for the tight box around exactly what the note is about.
One request per submission, with all its crops. If it fails, the rough boxes stay: this pass can only improve them.

LOCATE=off in .env turns it off.
"""
from __future__ import annotations

import base64
import json
import re
from difflib import SequenceMatcher
from dataclasses import dataclass

import pymupdf

from moodle import settings

from .render import _with_grid

DEFAULT_MODEL = "claude-sonnet-5-5"
EFFORT = "high"  # medium: ב-2 מ-22 סימונים חצי שורה ליד (2026-11-12); עדיין כמה סנטים לעבודה
MAX_TOKENS = 4000
# how much page around the rough box: about 2.5 of its heights above and below and 1.5 of its widths to each side,
# within these limits (thousandths of the page). Small writing (a photographed page) gets a closer crop
BAND_Y = (60, 170)
BAND_X = (120, 260)
MIN_H = 180         # a crop is at least this tall, so a box that slipped a line still has its line inside
MIN_W = 300
SIDE = 1568         # long side of a crop, in pixels (more is scaled down by the API anyway)
# second chance: a mark whose expression is not in its close-up gets a tall view of the page around it. On graph paper
# Claude sometimes read the height wrong by a fifth of the page (2026-11-16, Nadav: work 0093, a note on the line
# above the answer it was about), so the close-up never showed the right place
WIDE_Y = 400        # thousandths of the page above and below the rough box
WIDE_X = 350        # and to each side
WRONG_LINE = 0.35   # what the close-up read is this unlike the note's quote: it is on the wrong line
# a part's first line is read whole on both sides, so the right line reads 0.55-0.95 against it, while a line of the
# part above with the same symbols read 0.38-0.41 (0093: "(2-y)/(1+i)=1+i+iy" against "ג. (1+i)x+2y=2+2i")
PLACE_LINE = 0.5
HINT = (0.1, 0.35, 0.95)  # the rough box, drawn in blue on the crop
# where a part starts (the ✓ or "2/3" is drawn there), when the placed marks contradict it, gets the same pass, as a
# "note" that quotes the part's first line (2026-11-16, Nadav: in 0093 the ✓ of 8ג sat in the middle of 8ב, its height
# read wrong like the note above it). One line of writing needs less detail than a mistake: a smaller close-up
PLACE = "תחילת סעיף"
PLACE_SIDE = 900


def enabled() -> bool:
    return settings.get("LOCATE", "on").strip().lower() not in ("off", "0", "false", "no")


def model() -> str:
    return settings.get("LOCATE_MODEL", DEFAULT_MODEL)


SYSTEM = """אתה מקבל חיתוכים מוגדלים מעבודה בכתב יד של סטודנט במתמטיקה. לכל חיתוך יש הערה של בודק על טעות או על משהו חסר.
המשימה: למצוא בכתב היד את המקום המדויק שההערה מדברת עליו, ולהחזיר מלבן צמוד סביבו. לא בודקים את העבודה מחדש.

- בכל תמונה רשת כתומה, ובקצוות מספרים מ-0 עד 1000: אלה הקואורדינטות של החיתוך הזה (לא של העמוד). (0, 0) היא הפינה השמאלית העליונה. קוראים את המספרים מהרשת, לא מנחשים.
- המלבן הכחול הדק הוא ניחוש גס של המקום. הוא בדרך כלל בסביבה הנכונה, אבל רחב מדי או שורה למעלה או למטה. לא מעתיקים אותו.
- המלבן הכחול יכול גם לטעות לגמרי. קודם קוראים את ההערה ומחפשים בכל החיתוך את הביטוי שהיא מתארת (למשל "חסר סוגר של הזוג" = הביטוי שבו כתוב הזוג, לא שורת חישוב לידו). רק כשיש כמה מקומות שמתאימים באותה מידה, בוחרים את הקרוב למלבן הכחול.
- המלבן מקיף רק את הביטוי שההערה מדברת עליו: בדרך כלל חלק משורה אחת (משוואה, קבוצה, תשובה סופית), לפעמים שורה שלמה, לכל היותר 2-3 שורות כשהטעות באמת נמשכת עליהן. אף פעם לא שורות נכונות מעל או מתחת, ואף פעם לא סעיף שלם.
- הערה על משהו שחסר (סוגר, שייכות ∉, מסקנה, סוגרי קבוצה): המלבן סביב הביטוי שבו זה חסר, למשל התשובה הסופית.
- הערה כללית על נימוק: המלבן סביב שורת הנימוק עצמה.
- המלבן צמוד לכתב: קצת אוויר מסביב, לא חצי רוחב התמונה כשהביטוי קצר. הוא לא חוצה קו הפרדה, כותרת של סעיף אחר או שורה של סעיף אחר.
- found=true רק כשרואים בחיתוך את מה שההערה מדברת עליו. הערה שמצטטת ביטוי של הסטודנט (אחרי "שגוי:", או ביטוי בסוגריים כמו {(3-i),(-2i-2)}): found=true רק אם הביטוי הזה עצמו כתוב בחיתוך, לא ביטוי אחר שדומה לו ולא שורה שכנה. אחרת found=false ושאר השדות 0: אז תישלח תמונה גבוהה יותר של העמוד סביב המלבן הכחול.
- read: מה כתוב בכתב היד בתוך המלבן שבחרת, כמו שהוא כתוב (למשל {(3-i),(-2i-2)}). ריק כש-found=false.
- חיתוך שההערה שלו היא "תחילת סעיף X: «...»": מחפשים את השורה הראשונה של התשובה לסעיף X, זו שמתחילה כמו הציטוט (בדרך כלל עם מספר הסעיף שהסטודנט כתב, כמו ג, 8ג או (ג)). המלבן סביב מספר הסעיף והשורה הזאת בלבד. found=true רק כשזו באמת תחילת הסעיף הזה, לא שורה באמצע סעיף אחר שדומה לה; read הוא מה שכתוב בה.
- i: מספר החיתוך, כמו בכותרת שלו. מחזירים שורה אחת לכל חיתוך."""

SCHEMA = {
    "type": "object",
    "properties": {"boxes": {"type": "array", "items": {
        "type": "object",
        "properties": {"i": {"type": "integer"}, "found": {"type": "boolean"}, "x0": {"type": "number"},
                       "y0": {"type": "number"}, "x1": {"type": "number"}, "y1": {"type": "number"},
                       "read": {"type": "string"}},
        "required": ["i", "found", "x0", "y0", "x1", "y1", "read"], "additionalProperties": False,
    }}},
    "required": ["boxes"],
    "additionalProperties": False,
}


@dataclass
class Crop:
    i: int                       # 1-based, as shown to Claude
    mark: int                    # index in the marks list
    page: int
    area: tuple[float, float, float, float]  # the crop, in thousandths of the page
    png: bytes
    size: tuple[int, int] = (0, 0)           # the image's width and height, in pixels


def _band(lo: float, hi: float, pad: float, least: float) -> tuple[float, float]:
    a, b = max(lo - pad, 0), min(hi + pad, 1000)
    if b - a < least:
        grow = (least - (b - a)) / 2
        a, b = max(a - grow, 0), min(b + grow, 1000)
        if b - a < least:
            a, b = (0, least) if a == 0 else (1000 - least, 1000)
    return a, b


def crops(pdf: bytes, marks: list, wide: bool = False, only: set[int] | None = None) -> list[Crop]:
    """A close-up of the page around each mark (page coordinates, as the page is shown), with a grid and the rough box.
    wide: a tall view instead (WIDE_Y, WIDE_X), for the second chance. only: the marks (by index) to crop."""
    import numpy as np
    out: list[Crop] = []
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        renders: dict[int, tuple] = {}
        for k, m in enumerate(marks):
            if not 1 <= m.page <= len(doc) or (only is not None and k not in only):
                continue
            if m.page not in renders:
                page = doc[m.page - 1]
                zoom = 2.6 * SIDE / max(page.rect.width, page.rect.height)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width * 3]
                renders[m.page] = (arr.reshape(pix.height, pix.width, 3), pix.width, pix.height)
            arr, w, h = renders[m.page]
            if wide:
                x0, x1 = _band(m.x0, m.x1, WIDE_X, MIN_W)
                y0, y1 = _band(m.y0, m.y1, WIDE_Y, MIN_H)
            else:
                bx = min(max(1.5 * (m.x1 - m.x0), BAND_X[0]), BAND_X[1])
                by = min(max(2.5 * (m.y1 - m.y0), BAND_Y[0]), BAND_Y[1])
                x0, x1 = _band(m.x0, m.x1, bx, MIN_W)
                y0, y1 = _band(m.y0, m.y1, by, MIN_H)
            a, b, c, d = int(x0 / 1000 * w), int(y0 / 1000 * h), int(x1 / 1000 * w), int(y1 / 1000 * h)
            sub = np.ascontiguousarray(arr[b:d, a:c])
            piece = pymupdf.Pixmap(pymupdf.csRGB, c - a, d - b, sub.tobytes(), False)
            side = PLACE_SIDE if is_place(m.text) and not wide else SIDE
            scale = min(side / max(piece.width, piece.height), 1.0)
            if scale < 1:
                with pymupdf.open() as tmp:
                    pg = tmp.new_page(width=piece.width, height=piece.height)
                    pg.insert_image(pg.rect, pixmap=piece)
                    piece = pg.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            # the rough box, in blue, then the grid of the crop
            with pymupdf.open() as tmp:
                pg = tmp.new_page(width=piece.width, height=piece.height)
                pg.insert_image(pg.rect, pixmap=piece)
                fx = lambda v: (v - x0) / (x1 - x0) * piece.width   # noqa: E731
                fy = lambda v: (v - y0) / (y1 - y0) * piece.height  # noqa: E731
                if not wide:  # in the tall view the rough box is known to be off, and it pulled the answer to itself
                    pg.draw_rect(pymupdf.Rect(fx(m.x0), fy(m.y0), fx(m.x1), fy(m.y1)), color=HINT, width=1.2,
                                 stroke_opacity=0.7)
                piece = pg.get_pixmap(alpha=False)
            piece = _with_grid(piece, f"crop {len(out) + 1}")
            out.append(Crop(len(out) + 1, k, m.page, (x0, y0, x1, y1), piece.tobytes("png"), (piece.width, piece.height)))
    return out


WIDE_INTRO = ("סבב שני: אלה תמונות גבוהות של העמוד, בלי מלבן כחול, כי הניחוש הגס היה רחוק מדי. מחפשים בכל החיתוך את "
              "הביטוי שההערה מצטטת, ומחזירים מלבן צמוד סביבו ואת מה שכתוב בו (read). לא מוצאים: found=false.")


def build_request(items: list[Crop], marks: list, model_id: str, intro: str = "") -> dict:
    content: list[dict] = [{"type": "text", "text": (intro + "\n" if intro else "") + f"{len(items)} חיתוכים, לפי הסדר."}]
    for c in items:
        content.append({"type": "text", "text": f"חיתוך {c.i} (מעמוד {c.page}). ההערה: \"{marks[c.mark].text}\""})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                    "data": base64.b64encode(c.png).decode("ascii")}})
    return {"model": model_id, "max_tokens": MAX_TOKENS, "system": SYSTEM, "file_prefix": "crop",
            "messages": [{"role": "user", "content": content}],
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}}}


def apply(answer: str, items: list[Crop], marks: list, make) -> tuple[list, int]:
    """The new boxes, in thousandths of the page; a mark Claude did not find (or a broken answer) keeps its box.
    `make(page, x0, y0, x1, y1, text)` builds a mark. Returns (marks, how many moved)."""
    try:
        boxes = {int(b["i"]): b for b in json.loads(answer).get("boxes") or [] if isinstance(b, dict)}
    except (ValueError, TypeError, KeyError):
        return marks, 0
    out, moved = list(marks), 0
    for c in items:
        b = boxes.get(c.i)
        if not b or not b.get("found"):
            continue
        try:
            xs, ys = [float(b[k]) for k in ("x0", "x1")], [float(b[k]) for k in ("y0", "y1")]
        except (TypeError, ValueError, KeyError):
            continue
        # beyond 1000 = the image's pixels, not the grid's thousandths (2026-11-16: a tall view answered 1070-1128 on an
        # image 1568 pixels tall, and the box was dropped)
        w, h = c.size
        if w and h and max(xs + ys) > 1000.5 and max(xs) <= w + 1 and max(ys) <= h + 1:
            xs, ys = [v / w * 1000 for v in xs], [v / h * 1000 for v in ys]
        bx = sorted(min(max(v, 0), 1000) for v in xs)
        by = sorted(min(max(v, 0), 1000) for v in ys)
        if bx[1] - bx[0] < 5 or by[1] - by[0] < 5:
            continue
        x0, y0, x1, y1 = c.area
        m = marks[c.mark]
        out[c.mark] = make(m.page, x0 + bx[0] / 1000 * (x1 - x0), y0 + by[0] / 1000 * (y1 - y0),
                           x0 + bx[1] / 1000 * (x1 - x0), y0 + by[1] / 1000 * (y1 - y0), m.text)
        for extra in ("part", "deduct"):  # what the mark carries besides its box stays with it
            if hasattr(m, extra):
                setattr(out[c.mark], extra, getattr(m, extra))
        moved += 1
    return out, moved


def relocate(pdf: bytes, marks: list, ask, make, model_id: str | None = None) -> list:
    """The marks with tight boxes, or the same marks when there is nothing to do or the pass fails."""
    items = crops(pdf, [m for m in marks]) if marks else []
    if not items:
        return marks
    try:
        answer = ask(build_request(items, marks, model_id or model()))
    except Exception as e:  # noqa: BLE001 - this pass only improves the boxes; grading never fails because of it
        import sys
        print(f"מיקום הסימונים בזום לא הצליח, נשארים הסימונים המקוריים: {e}", file=sys.stderr)
        return marks
    out = apply(answer, items, marks, make)[0]
    ok = found(answer)
    reads = _reads(answer)
    # not found, or found something that is not what the note quotes ("{(3-i),(-2i-2)}" read as "(2-y)/(1+i)=1+i+iy"):
    # the same request answered "found" on the wrong line once and "not found" another time (2026-11-16, 0093)
    # 0.35: a wrong line read 0.24-0.30 against the quote, a right box at least 0.40 (a quote over two lines, 0092)
    missing = {c.mark for c in items if c.i not in ok or not matches(
        marks[c.mark].text, reads.get(c.i, ""), PLACE_LINE if is_place(marks[c.mark].text) else WRONG_LINE)}
    if not missing:
        return out
    # second chance, only for what the close-up did not show: a tall view of the page around the rough box
    wide = crops(pdf, out, wide=True, only=missing)
    if not wide:
        return out
    try:
        again = ask(build_request(wide, out, model_id or model(), WIDE_INTRO))
    except Exception:  # noqa: BLE001 - as above: the boxes stay as they are
        return out
    # only a box whose writing is what the note quotes replaces the one from the close-up
    try:
        boxes = [b for b in json.loads(again).get("boxes") or [] if isinstance(b, dict) and b.get("found")]
    except (ValueError, TypeError):
        return out
    by_i = {c.i: c for c in wide}
    first = {c.mark: c.area for c in items}

    def outside(b: dict) -> bool:
        # a box the close-up had in view stays as the close-up drew it (tighter); only one beyond it replaces it
        c = by_i[int(b["i"])]
        x0, y0, x1, y1 = c.area
        try:
            cy = y0 + (float(b["y0"]) + float(b["y1"])) / 2 / (c.size[1] if max(float(b["y0"]), float(b["y1"])) > 1000.5 and c.size[1] else 1000) * (y1 - y0)
        except (TypeError, ValueError, KeyError):
            return False
        fy0, fy1 = first[c.mark][1], first[c.mark][3]
        return not fy0 <= cy <= fy1

    keep = [b for b in boxes if int(b.get("i", 0)) in by_i and outside(b)
            and matches(out[by_i[int(b["i"])].mark].text, str(b.get("read") or ""))]
    return apply(json.dumps({"boxes": keep}), wide, out, make)[0]


def suspicious(marks: list, places: list, tol: float = 10) -> set[int]:
    """The parts' starts (by index) that the marks, already placed on close-ups, contradict: a part's own mark above its
    start, a mark of an earlier part below it, or two starts out of order, on the same page and in the same column (the
    boxes overlap across). Only these get a close-up: zooming every start was 39 crops in one request, which mixed up
    the notes and ran past 15 minutes (2026-11-16)."""
    out: set[int] = set()
    label = {m.text: k for k, m in enumerate(places)}

    def across(a, b) -> bool:
        return min(a.x1, b.x1) - max(a.x0, b.x0) > 0

    for k, p in enumerate(places):
        if p is None or p.page < 1:
            continue
        for m in marks:
            j = label.get(getattr(m, "part", ""), -1)
            if m.page != p.page or j < 0 or not across(m, p):
                continue
            if (j == k and m.y1 < p.y0 - tol) or (j < k and m.y0 > p.y1 + tol):
                out.add(k)
        for j, q in enumerate(places[:k]):
            if q is not None and q.page == p.page and across(p, q) and q.y0 > p.y1 + tol:
                out |= {j, k}
    return out


def relocate_all(pdf: bytes, marks: list, places: list, firsts: list[str], ask, make,
                 model_id: str | None = None) -> tuple[list, list]:
    """The marks, each placed again on a close-up (as always), and then only the parts' starts they contradict
    (suspicious), in a second, small request. A place keeps its label as its text."""
    marks = relocate(pdf, marks, ask, make, model_id) if marks else marks
    firsts = list(firsts) + [""] * (len(places) - len(firsts))
    starts = sorted(suspicious(marks, places))
    if not starts:
        return marks, places
    probes = [make(places[k].page, places[k].x0, places[k].y0, places[k].x1, places[k].y1,
                   place_note(places[k].text, firsts[k])) for k in starts]
    moved = relocate(pdf, probes, ask, make, model_id)
    new_places = list(places)
    for k, m in zip(starts, moved):
        new_places[k] = make(m.page, m.x0, m.y0, m.x1, m.y1, places[k].text)
    return marks, new_places


def is_place(note: str) -> bool:
    return note.startswith(PLACE)


def place_note(label: str, first: str) -> str:
    """The "note" of where a part starts: its label and its first line as the grader read it."""
    return f"{PLACE} {label}: «{first.strip()}»" if first.strip() else f"{PLACE} {label}"


def quoted(note: str) -> str:
    """The student's expression a note quotes ("שגוי: {(3-i),(-2i-2)} היא ..." -> "{(3-i),(-2i-2)}"), or "" when it
    quotes none: the math right after "שגוי:", up to the first Hebrew word. A part's start quotes its first line."""
    if is_place(note):
        m = re.search(r"«(.*)»", note)
        q = m.group(1).strip() if m else ""
    else:
        m = re.search(r"שגוי:\s*([^֐-׿\n]+)", note)
        q = m.group(1).strip(" ,;.") if m else ""
    return q if len(re.sub(r"\s", "", q)) >= 3 else ""


def matches(note: str, read: str, least: float = 0.5) -> bool:
    """Whether what the zoom pass read in its box is the expression the note quotes (no quote: nothing to check)."""
    q = quoted(note)
    if not q:
        return True
    def norm(s: str) -> str:
        s = re.sub(r"\s", "", s).lower()
        for a, b in (("−", "-"), ("–", "-"), ("φ", "∅"), ("ϕ", "∅"), ("ø", "∅"), ("·", ""), ("ℝ", "r"), ("ℂ", "c"),
                     ("«", ""), ("»", ""), ('"', "")):
            s = s.replace(a, b)
        return s
    return SequenceMatcher(None, norm(q), norm(read)).ratio() >= least


def _reads(answer: str) -> dict[int, str]:
    try:
        return {int(b["i"]): str(b.get("read") or "") for b in json.loads(answer).get("boxes") or [] if isinstance(b, dict)}
    except (ValueError, TypeError, KeyError):
        return {}


def found(answer: str) -> set[int]:
    """The crops (their i) where Claude found what the note is about."""
    try:
        return {int(b["i"]) for b in json.loads(answer).get("boxes") or [] if isinstance(b, dict) and b.get("found")}
    except (ValueError, TypeError, KeyError):
        return set()
