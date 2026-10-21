"""הגשות לדוגמה, בדיוק בפורמט של "הורדת כל ההגשות" במודל.

משמש לבדיקות ולהדגמה: יוצר קובץ ZIP שאפשר לשים בתיקיית הקליטה, והמערכת קולטת אותו
כמו ZIP אמיתי ממודל. השמות בדויים.
"""
from __future__ import annotations

import io
import random
import zipfile
from pathlib import Path

import pymupdf

NAMES = ["נועה כהן", "איתי לוי", "מאיה מזרחי", "יונתן פרץ", "שירה ביטון", "עומר אברהם", "תמר פרידמן", "אלון דהן",
         "רוני אזולאי", "דניאל שפירא", "הילה גבאי", "אורי קליין", "ליאור חדד", "יעל רוזנברג", "אביב סויסה", "גל אוחיון"]

_FONTS = Path("C:/Windows/Fonts")
_CSS = "@font-face {font-family: heb; src: url(arial.ttf);} * {font-family: heb, sans-serif; font-size: 13px; line-height: 1.6;}"


def homework_pdf(name: str, title: str, pages: int = 2) -> bytes:
    doc = pymupdf.open()
    archive = pymupdf.Archive(str(_FONTS)) if (_FONTS / "arial.ttf").exists() else None
    for p in range(pages):
        page = doc.new_page()
        html = (
            f'<div dir="rtl"><h3>{title}</h3><p>{name}</p>'
            f"<p>שאלה {2 * p + 1}: נבצע פעולות שורה ונקבל rank(A) = 2.</p>"
            f"<p>שאלה {2 * p + 2}: det(A) · det(A⁻¹) = det(I) = 1.</p></div>"
        )
        page.insert_htmlbox(pymupdf.Rect(50, 50, 545, 790), html, css=_CSS, archive=archive)
    data = doc.tobytes()
    doc.close()
    return data


def moodle_zip(title: str = "תרגיل בית 1", count: int = 6, seed: int | None = None, empty_one: bool = True,
               in_folders: bool = True) -> bytes:
    """בונה ZIP כמו של מודל. empty_one=True מכניס הגשה אחת עם קובץ ריק, כדי לראות טיפול בתקלות."""
    rnd = random.Random(seed)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, name in enumerate(rnd.sample(NAMES, k=min(count, len(NAMES)))):
            pid = 100000 + rnd.randint(1000, 99999)
            data = b"" if (empty_one and i == count - 1) else homework_pdf(name, title, pages=rnd.randint(1, 3))
            fname = "hw.pdf"
            entry = (f"{name}_{pid}_assignsubmission_file/{fname}" if in_folders
                     else f"{name}_{pid}_assignsubmission_file_{fname}")
            zf.writestr(zipfile.ZipInfo(entry, date_time=(2026, 10, 20, rnd.randint(8, 23), rnd.randint(0, 59), 0)), data)
    return buf.getvalue()
