"""Zoom pass: after grading, every box is placed again on a close-up of its part of the page.

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
HINT = (0.1, 0.35, 0.95)  # the rough box, drawn in blue on the crop


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
- found=false רק אם הביטוי שההערה מדברת עליו לא נמצא בחיתוך בכלל. אז שאר השדות 0.
- i: מספר החיתוך, כמו בכותרת שלו. מחזירים שורה אחת לכל חיתוך."""

SCHEMA = {
    "type": "object",
    "properties": {"boxes": {"type": "array", "items": {
        "type": "object",
        "properties": {"i": {"type": "integer"}, "found": {"type": "boolean"}, "x0": {"type": "number"},
                       "y0": {"type": "number"}, "x1": {"type": "number"}, "y1": {"type": "number"}},
        "required": ["i", "found", "x0", "y0", "x1", "y1"], "additionalProperties": False,
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


def _band(lo: float, hi: float, pad: float, least: float) -> tuple[float, float]:
    a, b = max(lo - pad, 0), min(hi + pad, 1000)
    if b - a < least:
        grow = (least - (b - a)) / 2
        a, b = max(a - grow, 0), min(b + grow, 1000)
        if b - a < least:
            a, b = (0, least) if a == 0 else (1000 - least, 1000)
    return a, b


def crops(pdf: bytes, marks: list) -> list[Crop]:
    """A close-up of the page around each mark (page coordinates, as the page is shown), with a grid and the rough box."""
    import numpy as np
    out: list[Crop] = []
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        renders: dict[int, tuple] = {}
        for k, m in enumerate(marks):
            if not 1 <= m.page <= len(doc):
                continue
            if m.page not in renders:
                page = doc[m.page - 1]
                zoom = 2.6 * SIDE / max(page.rect.width, page.rect.height)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width * 3]
                renders[m.page] = (arr.reshape(pix.height, pix.width, 3), pix.width, pix.height)
            arr, w, h = renders[m.page]
            bx = min(max(1.5 * (m.x1 - m.x0), BAND_X[0]), BAND_X[1])
            by = min(max(2.5 * (m.y1 - m.y0), BAND_Y[0]), BAND_Y[1])
            x0, x1 = _band(m.x0, m.x1, bx, MIN_W)
            y0, y1 = _band(m.y0, m.y1, by, MIN_H)
            a, b, c, d = int(x0 / 1000 * w), int(y0 / 1000 * h), int(x1 / 1000 * w), int(y1 / 1000 * h)
            sub = np.ascontiguousarray(arr[b:d, a:c])
            piece = pymupdf.Pixmap(pymupdf.csRGB, c - a, d - b, sub.tobytes(), False)
            scale = min(SIDE / max(piece.width, piece.height), 1.0)
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
                pg.draw_rect(pymupdf.Rect(fx(m.x0), fy(m.y0), fx(m.x1), fy(m.y1)), color=HINT, width=1.2,
                             stroke_opacity=0.7)
                piece = pg.get_pixmap(alpha=False)
            piece = _with_grid(piece, f"crop {len(out) + 1}")
            out.append(Crop(len(out) + 1, k, m.page, (x0, y0, x1, y1), piece.tobytes("png")))
    return out


def build_request(items: list[Crop], marks: list, model_id: str) -> dict:
    content: list[dict] = [{"type": "text", "text": f"{len(items)} חיתוכים, לפי הסדר."}]
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
            bx = sorted(min(max(float(b[k]), 0), 1000) for k in ("x0", "x1"))
            by = sorted(min(max(float(b[k]), 0), 1000) for k in ("y0", "y1"))
        except (TypeError, ValueError, KeyError):
            continue
        if bx[1] - bx[0] < 5 or by[1] - by[0] < 5:
            continue
        x0, y0, x1, y1 = c.area
        m = marks[c.mark]
        out[c.mark] = make(m.page, x0 + bx[0] / 1000 * (x1 - x0), y0 + by[0] / 1000 * (y1 - y0),
                           x0 + bx[1] / 1000 * (x1 - x0), y0 + by[1] / 1000 * (y1 - y0), m.text)
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
    return apply(answer, items, marks, make)[0]
