"""הפיכת הגשה לתמונות: כל עמוד ב-PDF הופך לתמונה אחת.

אלה התמונות שנשלחות ל-Claude לבדיקה. הן נוצרות בזיכרון ולא נשמרות בתיקייה.

חיתוך שוליים (crop): סריקת טלפון של דף A4 היא בדרך כלל 20-35% שוליים לבנים, שעולים טוקנים כמו כתב.
עם crop=True נשלח רק המלבן שיש בו כתב (ink_bbox), באותה רזולוציה של העמוד המלא: החיתוך רק מקטין את התמונה,
לא מגדיל אותה. המלבנים ש-Claude מחזיר הם באלפיות של התמונה ששלחנו לו; PageImage.to_page מחזיר אותם
לאלפיות של העמוד השלם, כדי שהסימונים ייפלו במקום הנכון על הקובץ של הסטודנט. (נמדד על 63 עמודים אמיתיים
בדגימת המחוון: 1,471 → 585 טוקנים לעמוד עם חיתוך וצד ארוך של 1000.)
"""
from __future__ import annotations

import os
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

# חיתוך שוליים בבדיקה: ברירת המחדל דלוקה; GRADE_CROP=off ב-.env או בסביבה מכבה.
CROP_DEFAULT = os.environ.get("GRADE_CROP", "on").strip().lower() not in ("off", "0", "false", "no")

# פיקסל אפור כהה מזה נחשב "דיו" (0-255) בספירת העמודים הריקים של הדגימה
DARK = 140
# חיתוך שוליים. הדיו נמדד יחסית לרקע של העמוד (חציון האפור פחות CROP_CONTRAST), כי עיפרון וסריקה בהירה
# לא עוברים סף קבוע. שורה או עמודה נחשבת "עם דיו" כשלפחות CROP_LINE_INK מהפיקסלים שלה כהים (ולפחות 2).
CROP_SCALE = 0.5
CROP_CONTRAST = 45
CROP_LINE_INK = 0.003
CROP_MARGIN = 0.025
CROP_MIN_AREA = 0.12   # מלבן קטן מזה הוא כנראה רעש (כתם, מספר עמוד) ולא כתב: לא חותכים
CROP_MIN_SAVING = 0.12  # חיתוך שחוסך פחות מזה לא שווה את הסיכון


@dataclass
class PageImage:
    """תמונה של עמוד אחד מההגשה."""
    page: int     # מספר העמוד, מתחיל מ-1
    data: bytes   # התמונה עצמה
    width: int    # רוחב בפיקסלים
    height: int   # גובה בפיקסלים
    # החלק של העמוד שהתמונה מראה, כשברי העמוד (0..1): (x0, y0, x1, y1). None = העמוד כולו
    clip: tuple[float, float, float, float] | None = None

    @property
    def media_type(self) -> str:
        """סוג התמונה, בצורה ש-Claude מצפה לקבל (למשל image/png)."""
        return f"image/{IMAGE_FORMAT}"

    def to_page(self, x: float, y: float) -> tuple[float, float]:
        """נקודה באלפיות של התמונה → אלפיות של העמוד השלם."""
        if not self.clip:
            return x, y
        cx0, cy0, cx1, cy1 = self.clip
        return (cx0 + x / 1000 * (cx1 - cx0)) * 1000, (cy0 + y / 1000 * (cy1 - cy0)) * 1000


def ink_bbox(page: pymupdf.Page) -> pymupdf.Rect | None:
    """המלבן שבו יש כתב בעמוד, עם שוליים של 2%, בקואורדינטות של העמוד. None אם אין מה לחתוך
    (הכתב ממלא את העמוד, או שלא נמצא כתב)."""
    import numpy as np
    pix = page.get_pixmap(matrix=pymupdf.Matrix(CROP_SCALE, CROP_SCALE), colorspace=pymupdf.csGRAY, alpha=False)
    w, h = pix.width, pix.height
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(h, w)
    bg = int(np.median(gray))
    if bg < 90:  # דף כהה (צילום לילה): אין רקע לבן לחתוך
        return None
    ink = gray < max(bg - CROP_CONTRAST, 40)
    rows = np.flatnonzero(ink.sum(1) >= max(2, CROP_LINE_INK * w))
    cols = np.flatnonzero(ink.sum(0) >= max(2, CROP_LINE_INK * h))
    if not len(rows) or not len(cols):
        return None
    y0, y1 = int(rows[0]), int(rows[-1])
    x0, x1 = int(cols[0]), int(cols[-1])
    mx, my = CROP_MARGIN * w, CROP_MARGIN * h
    x0, y0, x1, y1 = max(0, x0 - mx), max(0, y0 - my), min(w, x1 + 1 + mx), min(h, y1 + 1 + my)
    area = (x1 - x0) * (y1 - y0) / (w * h)
    if area > 1 - CROP_MIN_SAVING or area < CROP_MIN_AREA:
        return None
    r = page.rect
    return pymupdf.Rect(r.x0 + x0 / CROP_SCALE, r.y0 + y0 / CROP_SCALE, r.x0 + x1 / CROP_SCALE, r.y0 + y1 / CROP_SCALE)


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


def render_page(page: pymupdf.Page, grid: bool = False, crop: bool = False) -> PageImage:
    """מקבלת עמוד אחד מתוך PDF ומחזירה תמונה שלו. grid=True: עם רשת עזר למיקום הסימונים.
    crop=True: רק המלבן שיש בו כתב, באותה רזולוציה (התמונה יוצאת קטנה יותר, לא מוגדלת)."""
    # כמה להגדיל את העמוד, כדי שהצד הארוך שלו יהיה בדיוק MAX_SIDE
    zoom = MAX_SIDE / max(page.rect.width, page.rect.height)
    clip = None
    if crop:
        try:
            clip = ink_bbox(page)
        except Exception:  # החיתוך הוא רק חיסכון: בלעדיו שולחים את העמוד כולו
            clip = None
    # alpha=False: רקע לבן מלא, בלי שקיפות
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
    if grid:
        pix = _with_grid(pix)
    frac = None
    if clip is not None:
        r = page.rect
        frac = ((clip.x0 - r.x0) / r.width, (clip.y0 - r.y0) / r.height, (clip.x1 - r.x0) / r.width, (clip.y1 - r.y0) / r.height)
    return PageImage(page.number + 1, pix.tobytes(IMAGE_FORMAT), pix.width, pix.height, frac)


def render_pdf(data: bytes, grid: bool = False, crop: bool = False) -> list[PageImage]:
    """מקבלת את התוכן של קובץ PDF ומחזירה רשימה של תמונות, אחת לכל עמוד, לפי הסדר."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [render_page(page, grid, crop) for page in doc]


def render_submission(sub: Submission, crop: bool = False) -> list[PageImage]:
    """מחזירה את התמונות של כל העמודים בהגשה של סטודנט.

    לוקחת רק את קובצי ה-PDF. קבצים אחרים, כמו onlinetext.html שמודל מוסיף, לא נבדקים.
    (בקורס מותר להגיש רק PDF אחד, כך שבפועל יהיה כאן קובץ אחד.)
    """
    images: list[PageImage] = []
    for f in sub.files:
        if Path(f.name).suffix.lower() == ".pdf":
            images += render_pdf(f.content(), crop=crop)
    return images
