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


# רשת עזר שמצוירת על התמונה ש-Claude רואה (לא על הקובץ של הסטודנט): קו כל 100 אלפיות, ומספרים בארבעת הקצוות.
# בלי הרשת Claude טועה במיקום של המלבנים, והסימונים נופלים על מקום ריק
GRID_STEP = 100
GRID_COLOR = (1, 0.45, 0)


def _with_grid(pix: pymupdf.Pixmap) -> pymupdf.Pixmap:
    w, h = pix.width, pix.height
    with pymupdf.open() as tmp:
        page = tmp.new_page(width=w, height=h)
        page.insert_image(page.rect, pixmap=pix)
        size = max(9, w / 80)
        for v in range(0, 1001, GRID_STEP):
            x, y = v / 1000 * w, v / 1000 * h
            if 0 < v < 1000:
                page.draw_line((x, 0), (x, h), color=GRID_COLOR, width=0.7, stroke_opacity=0.55)
                page.draw_line((0, y), (w, y), color=GRID_COLOR, width=0.7, stroke_opacity=0.55)
            label = str(v)
            dx = min(max(x + 2, 1), w - size * 1.8)
            dy = min(max(y + size, size), h - 2)
            page.insert_text((dx, size), label, fontsize=size, color=GRID_COLOR)
            page.insert_text((dx, h - 3), label, fontsize=size, color=GRID_COLOR)
            page.insert_text((2, dy), label, fontsize=size, color=GRID_COLOR)
            page.insert_text((w - size * 1.9, dy), label, fontsize=size, color=GRID_COLOR)
        return page.get_pixmap(alpha=False)


def render_page(page: pymupdf.Page, grid: bool = False) -> PageImage:
    """מקבלת עמוד אחד מתוך PDF ומחזירה תמונה שלו. grid=True: עם רשת עזר למיקום הסימונים."""
    # כמה להגדיל את העמוד, כדי שהצד הארוך שלו יהיה בדיוק MAX_SIDE
    zoom = MAX_SIDE / max(page.rect.width, page.rect.height)
    # alpha=False: רקע לבן מלא, בלי שקיפות
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    if grid:
        pix = _with_grid(pix)
    return PageImage(page.number + 1, pix.tobytes(IMAGE_FORMAT), pix.width, pix.height)


def render_pdf(data: bytes, grid: bool = False) -> list[PageImage]:
    """מקבלת את התוכן של קובץ PDF ומחזירה רשימה של תמונות, אחת לכל עמוד, לפי הסדר."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [render_page(page, grid) for page in doc]


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
