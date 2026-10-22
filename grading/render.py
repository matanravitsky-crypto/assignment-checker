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


def render_page(page: pymupdf.Page, max_side: int = MAX_SIDE) -> PageImage:
    """מקבלת עמוד אחד מתוך PDF ומחזירה תמונה שלו, שהצד הארוך שלה max_side פיקסלים."""
    # כמה להגדיל את העמוד, כדי שהצד הארוך שלו יהיה בדיוק max_side
    zoom = max_side / max(page.rect.width, page.rect.height)
    # alpha=False: רקע לבן מלא, בלי שקיפות
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
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
