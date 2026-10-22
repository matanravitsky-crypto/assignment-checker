"""הפיכת הגשה לתמונות: כל עמוד ב-PDF הופך לתמונה אחת.

אלה התמונות שנשלחות ל-Claude לבדיקה. הן נוצרות בזיכרון ולא נשמרות בתיקייה.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .submission import Submission

# ---------- הגדרות: כדי לשנות גודל או פורמט, משנים רק כאן ----------

# אורך הצד הארוך של כל תמונה, בפיקסלים.
# Claude מקטין ממילא תמונות גדולות מזה, אז אין טעם לשלוח גדול יותר.
MAX_SIDE = 1568

# פורמט התמונה. PNG שומר על הקווים החדים של כתב היד (JPEG מטשטש אותם קצת).
IMAGE_FORMAT = "png"


@dataclass
class PageImage:
    """תמונה של עמוד אחד מההגשה."""
    page: int     # מספר העמוד, מתחיל מ-1
    data: bytes   # התמונה עצמה
    width: int    # רוחב בפיקסלים
    height: int   # גובה בפיקסלים

    @property
    def media_type(self) -> str:
        """סוג התמונה, בצורה ש-Claude מצפה לקבל (למשל image/png)."""
        return f"image/{IMAGE_FORMAT}"


# סרגלים בשוליים של כל תמונה: מסגרת סביב העמוד ושנתות כל 50 אלפיות, עם מספרים כל 100 (0 עד 1000).
# אלה אותן יחידות שבהן Claude מחזיר את המלבן של כל טעות, ולכן הוא ממקם אותו מדויק יותר.
RULERS = True
RULER_MARGIN = 0.045  # רוחב השוליים, כחלק מהצלע הארוכה של העמוד
RULER_COLOR = (0.35, 0.35, 0.35)


def with_rulers(page: pymupdf.Page) -> tuple[pymupdf.Document, pymupdf.Page]:
    """עמוד חדש: העמוד המקורי (כפי שהוא מוצג) במרכז, ובשוליים סביבו סרגלים באלפיות של העמוד."""
    shown = page.rect
    m = RULER_MARGIN * max(shown.width, shown.height)
    doc = pymupdf.open()
    out = doc.new_page(width=shown.width + 2 * m, height=shown.height + 2 * m)
    inner = pymupdf.Rect(m, m, m + shown.width, m + shown.height)
    out.show_pdf_page(inner, page.parent, page.number)
    out.draw_rect(inner, color=RULER_COLOR, width=0.6)
    size, side_size = m * 0.38, m * 0.27  # בצדדים "1000" צריך להיכנס לרוחב השוליים, ליד השנתה
    for k in range(0, 1001, 50):
        tick = m * (0.3 if k % 100 else 0.55)
        side_tick = m * (0.12 if k % 100 else 0.2)
        x = inner.x0 + inner.width * k / 1000
        y = inner.y0 + inner.height * k / 1000
        for a, b in (((x, inner.y0), (x, inner.y0 - tick)), ((x, inner.y1), (x, inner.y1 + tick)),
                     ((inner.x0, y), (inner.x0 - side_tick, y)), ((inner.x1, y), (inner.x1 + side_tick, y))):
            out.draw_line(a, b, color=RULER_COLOR, width=0.6)
        if k % 100 == 0:
            label = str(k)
            width = pymupdf.get_text_length(label, fontsize=size)
            out.insert_text((x - width / 2, inner.y0 - tick - 1), label, fontsize=size, color=RULER_COLOR)
            out.insert_text((x - width / 2, inner.y1 + tick + size), label, fontsize=size, color=RULER_COLOR)
            width = pymupdf.get_text_length(label, fontsize=side_size)
            out.insert_text((inner.x0 - side_tick - width - 1, y + side_size / 3), label, fontsize=side_size, color=RULER_COLOR)
            out.insert_text((inner.x1 + side_tick + 1, y + side_size / 3), label, fontsize=side_size, color=RULER_COLOR)
    return doc, out


def render_page(page: pymupdf.Page, max_side: int = MAX_SIDE, rulers: bool = RULERS) -> PageImage:
    """מקבלת עמוד אחד מתוך PDF ומחזירה תמונה שלו, שהצד הארוך שלה max_side פיקסלים (עם הסרגלים, אם יש)."""
    doc, shown = with_rulers(page) if rulers else (None, page)
    try:
        # כמה להגדיל את העמוד, כדי שהצד הארוך שלו יהיה בדיוק max_side
        zoom = max_side / max(shown.rect.width, shown.rect.height)
        # alpha=False: רקע לבן מלא, בלי שקיפות
        pix = shown.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    finally:
        if doc is not None:
            doc.close()
    return PageImage(page.number + 1, pix.tobytes(IMAGE_FORMAT), pix.width, pix.height)


def render_pdf(data: bytes, max_side: int = MAX_SIDE) -> list[PageImage]:
    """מקבלת את התוכן של קובץ PDF ומחזירה רשימה של תמונות, אחת לכל עמוד, לפי הסדר."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [render_page(page, max_side) for page in doc]


def render_submission(sub: Submission) -> list[PageImage]:
    """מחזירה את התמונות של כל העמודים בהגשה של סטודנט.

    לוקחת רק את קובצי ה-PDF. קבצים אחרים, כמו onlinetext.html שמודל מוסיף, לא נבדקים.
    (בקורס מותר להגיש רק PDF אחד, כך שבפועל יהיה כאן קובץ אחד.)
    """
    images: list[PageImage] = []
    for f in sub.files:
        if Path(f.name).suffix.lower() == ".pdf":
            images += render_pdf(f.content())
    return images
