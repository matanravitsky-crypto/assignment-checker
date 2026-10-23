"""חשד להעתקה בין הגשות, בלי Claude ובלי טוקנים: רק השוואה של קבצים במחשב.

שתי שכבות, ושתיהן נכנסות לקטגוריה "העתקות" באתר:

  שכבה 0 - אותו קובץ או אותו מקור
    file     אותו קובץ בדיוק (sha256 זהה) אצל שני מספרים: חבר העלה את ה-PDF של מישהו אחר.
    doc_id   אותו מזהה מסמך פנימי של PDF (ה-ID ב-trailer). אפליקציה יוצרת מזהה חדש לכל מסמך, ולכן שני
             קבצים עם אותו מזהה נוצרו מאותו מסמך, גם אם שונו אחר כך (שם, דחיסה, עמוד שנוסף).
    author / created   אותו "מחבר" או אותו רגע יצירה (עד השנייה) במטא-דאטה של ה-PDF. חלש יותר, ולכן
             רק "כדאי להסתכל".
  שכבה 1 - אותו עמוד בקובץ אחר
    page     סריקה: עמוד שנראה כמעט זהה לעמוד בהגשה אחרת (perceptual hash, dHash של 16x16): אותה תמונה
             אחרי דחיסה מחדש, שינוי גודל, צילום מסך או איחוד ל-PDF אחר. רק עמוד שיש עליו כתיבה (MIN_INK):
             כריכה של אפליקציית מחברות, דף ריק או דף משבצות כמעט ריק נראים זהים אצל כולם ולא אומרים כלום.
             (בבדיקה על הגשה 0 באלגברה לינארית, 572 הגשות: 117 "חשדות", כמעט כולם כריכות ועמודים ריקים,
             ובמרחקים של 16-24 ביטים, שהם צילומים שונים שדומים במקרה. אותה תמונה ממש: 0-8.)
    text     עמוד מוקלד (או סריקה שהאפליקציה הוסיפה לה טקסט): שני עמודים שחולקים הרבה רצפים נדירים של 3
             מילים, גם אם שינו שם או כמה מילים. כששני העמודים מוקלדים, הטקסט קובע ולא התמונה: עמודים
             מוקלדים מאותה תבנית נראים כמעט זהים ל-dHash גם כשהתשובות שונות. (לכן גם צילום מסך של עמוד
             מוקלד לא מושווה לעמוד המוקלד עצמו: בלי זיהוי טקסט בתמונה אין דרך להבדיל אותו מהתבנית.)
             רצף שמופיע אצל יותר מ-5% מהמספרים (3 עד COMMON_PAGE) לא נחשב: נוסח השאלה, תבנית, או תשובה נכונה סטנדרטית
             (במתמטיקה תשובות נכונות דומות זו לזו). רק מה שמשותף לשניים ונדיר אצל האחרים הוא סימן להעתקה.

חומר הקורס: כל PDF, .tex, .md ו-.txt ב-"<קורס>/Course material/" ובתיקיית "פדגוגי" של המטלה (דפי תרגילים, חוברות,
פתרונות). עמוד מוקלד שרובו (MATERIAL_SHARE) טקסט מהחומר הזה הוא עמוד שהסטודנט צירף מהחוברת, ולא נחשב בכלל. בשאר
העמודים המוקלדים מורידים את הרצפים שמופיעים בחומר (נוסח השאלה), כך ששני פתרונות מושווים רק במה שהסטודנטים כתבו.

ערך מטא-דאטה שמשותף להרבה הגשות הוא ברירת מחדל של תוכנה ("Microsoft Office User"), לא סימן להעתקה,
ולכן הוא נחשב רק אם הוא אצל COMMON_META מספרים לכל היותר. עמוד סרוק אחד משותף לא מספיק (MIN_PAGES): זה בדרך
כלל כריכה או תבנית, ועבודה שהועתקה חולקת כמה עמודים. עמוד מוקלד שזהה אצל יותר משני מספרים (TEXT_COMMON) הוא
חומר של הקורס, למשל עמוד מחוברת השאלות שסטודנטים צירפו. עמוד שחוזר אצל יותר מ-COMMON_PAGE מספרים
הוא בדרך כלל דף שאלות או תבנית, אבל יכול להיות גם פתרון שעבר בקבוצה: הוא לא נכנס לזוגות, ומופיע בנפרד
ב-"repeated" כדי שאדם יחליט. עמוד כמעט ריק לא נחשב בכלל.

התוצאה, Copying check.json בתיקיית המטלה: זוגות של מספרים ולמה הם חשודים, ותיאור של כל קובץ (גודל, זמן
שינוי, hash, טביעת אצבע של כל עמוד) כדי שהרצה הבאה תקרא רק קבצים חדשים או ששונו. בלי שמות, בלי ערכי
המטא-דאטה ובלי הטקסט עצמו (בכל אחד מהם יכול להיות שם של סטודנט): רק hash שלהם (לטקסט: hash של 32 ביט
לכל רצף של 3 מילים).

זה רק חשד. ההחלטה אם זו העתקה היא של אדם, שמסתכל על שתי ההגשות זו לצד זו.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Callable

import pymupdf

from moodle import lock, paths

REPORT = paths.COPYING
VERSION = 4  # טביעת אצבע בפורמט אחר: קבצים מהמטמון של גרסה אחרת נקראים מחדש
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}  # כמו grading.grade.IMAGE_TYPES

# ---------- הגדרות ----------
GRID = 16             # dHash של GRID x GRID ביטים לכל עמוד (256)
RENDER_SIDE = 256     # העמוד מצויר קטן, באפור, לפני החישוב: הצד הארוך בפיקסלים
MAX_DISTANCE = 10     # עד כמה ביטים שונים (מתוך 256) שני עמודים נחשבים אותה תמונה. אותה תמונה: 0-8. צילומים שונים: 16 ומעלה
MIN_INK = 15          # כמה כתיבה צריכה להיות בעמוד (קצוות חדים לכל 1000 פיקסלים) כדי שישווה כתמונה.
                      # כריכות ודפים ריקים: 0-5. עמודים עם כתב יד: בדרך כלל 20-115
INK_STEP = 24         # הפרש בהירות בין שני פיקסלים שכנים (0-255) שנחשב קצה של קו
MIN_CONTRAST = 6      # הפרש בין המשבצת הבהירה לכהה (0-255) שמתחתיו העמוד נחשב ריק ולא נבדק
BUCKET_LIMIT = 300    # רצועה של dHash שמשותפת ליותר עמודים מזה לא משמשת לחיפוש (ראו _image_matches)
MIN_WORDS = 12        # עמוד עם פחות מילים מזה נחשב לא מוקלד (כותרת, מספר עמוד) ומושווה כתמונה
SHINGLE = 3           # הטקסט מושווה ברצפים של 3 מילים
TEXT_SHARED = 10      # כמה רצפים נדירים לפחות שני עמודים מוקלדים צריכים לחלוק
TEXT_SIMILAR = 0.7    # ואיזה חלק מהרצפים הנדירים של העמוד הקצר מביניהם
COMMON_PAGE = 10      # עמוד שדומה לעמודים אצל יותר מספרים מזה לא נכנס לזוגות, אלא לרשימת העמודים שחוזרים
MIN_PAGES = 2         # כמה עמודים סרוקים זהים (עם כתיבה) זוג צריך לחלוק. עבודה שהועתקה חולקת כמה עמודים
TEXT_COMMON = 2       # עמוד מוקלד שזהה אצל יותר מספרים מזה הוא חומר של הקורס (דף שאלות, חוברת), לא פתרון של סטודנט
MATERIAL_SHARE = 0.8  # עמוד מוקלד שלפחות חלק כזה מהרצפים שלו נמצא בחומר הקורס הוא עמוד מהחוברת. פתרון רגיל: עד 0.3
MATERIAL_TYPES = {".pdf", ".tex", ".md", ".txt"}
COMMON_META = 3       # ערך מטא-דאטה שמשותף ליותר מספרים מזה הוא ברירת מחדל של תוכנה, לא העתקה
STRONG = {"file", "doc_id", "page", "text"}  # מספיק אחד מאלה כדי שהזוג יהיה "חשד חזק"

KIND_TEXT = {
    "file": "אותו קובץ בדיוק",
    "doc_id": "אותו מזהה מסמך פנימי (נוצרו מאותו מסמך)",
    "author": "אותו מחבר במטא-דאטה של ה-PDF",
    "created": "אותו רגע יצירה במטא-דאטה של ה-PDF",
    "page": "עמוד זהה (אותה סריקה או תמונה)",
    "text": "עמוד עם כמעט אותו טקסט",
}


# ---------- טביעת אצבע של קובץ ----------
def _short(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _gray(page: pymupdf.Page) -> pymupdf.Pixmap:
    zoom = RENDER_SIDE / max(page.rect.width, page.rect.height, 1)
    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False)


def page_ink(page: pymupdf.Page, pix: pymupdf.Pixmap | None = None) -> float:
    """כמה כתיבה יש בעמוד: כמה זוגות של פיקסלים שכנים (לרוחב) נבדלים ביותר מ-INK_STEP, לכל 1000 פיקסלים.
    כריכה צבעונית, דף ריק ודף משבצות כמעט ריק מקבלים 0-5, כי אין בהם קווים חדים כמו של כתב יד."""
    pix = pix or _gray(page)
    w, h, data, stride = pix.width, pix.height, pix.samples, pix.stride
    edges = 0
    for y in range(h):
        row = data[y * stride:y * stride + w]
        edges += sum(abs(a - b) > INK_STEP for a, b in zip(row, row[1:]))
    return round(1000 * edges / max(w * h, 1), 1)


def page_hash(page: pymupdf.Page, pix: pymupdf.Pixmap | None = None) -> str | None:
    """dHash של עמוד: GRID x GRID ביטים, כל ביט אומר אם משבצת בהירה מזו שמימינה. None לעמוד ריק."""
    pix = pix or _gray(page)
    w, h, data, stride = pix.width, pix.height, pix.samples, pix.stride
    cols, rows = GRID + 1, GRID
    cells = []
    for r in range(rows):
        y0, y1 = r * h // rows, min(max((r + 1) * h // rows, r * h // rows + 1), h)
        for c in range(cols):
            x0, x1 = c * w // cols, max((c + 1) * w // cols, c * w // cols + 1)
            total = sum(sum(data[y * stride + x0:y * stride + x1]) for y in range(y0, y1))
            cells.append(total / max((y1 - y0) * (x1 - x0), 1))
    if max(cells) - min(cells) < MIN_CONTRAST:
        return None
    bits = 0
    for r in range(rows):
        row = cells[r * cols:(r + 1) * cols]
        for c in range(GRID):
            bits = (bits << 1) | (row[c] > row[c + 1])
    return f"{bits:0{GRID * GRID // 4}x}"


def text_shingles(text: str) -> str | None:
    """הרצפים של 3 מילים בעמוד, כ-hash של 32 ביט (8 ספרות hex לכל אחד, ממוינים). None אם אין מספיק מילים."""
    words = re.findall(r"\w+", text.casefold())
    if len(words) < MIN_WORDS:
        return None
    shingles = {hashlib.blake2b(" ".join(words[i:i + SHINGLE]).encode("utf-8"), digest_size=4).hexdigest()
                for i in range(len(words) - SHINGLE + 1)}
    return "".join(sorted(shingles))


def _shingle_set(text: str) -> frozenset[int]:
    return frozenset(int(text[i:i + 8], 16) for i in range(0, len(text), 8))


def _meta(doc: pymupdf.Document) -> dict[str, str]:
    """ערכי המטא-דאטה שמשווים, כ-hash. ערך ריק לא נשמר."""
    out = {}
    try:
        kind, value = doc.xref_get_key(-1, "ID")
        if kind == "array" and value.strip("[] <>"):
            out["doc_id"] = _short(value.strip("[]").split(">")[0])
    except (RuntimeError, ValueError):
        pass
    meta = doc.metadata or {}
    author = (meta.get("author") or "").strip()
    if author:
        out["author"] = _short(author.casefold())
    created = (meta.get("creationDate") or "").strip()
    if len(created) >= 16:  # D:YYYYMMDDHHmmSS: רק תאריך עם שעה עד השנייה. "D:2024" לבד משותף לכולם
        out["created"] = _short(created[:16])
    return out


def fingerprint(path: Path) -> dict:
    """מה שמשווים בקובץ אחד: sha256, מטא-דאטה (כ-hash), ולכל עמוד dHash (h), כמה כתיבה יש בו (i) ורצפי הטקסט (t, אם יש).
    קובץ פגום או שהוא לא PDF או תמונה: בלי עמודים."""
    data = path.read_bytes()
    fp = {"sha256": hashlib.sha256(data).hexdigest(), "meta": {}, "pages": []}
    kind = path.suffix.lower()
    if kind != ".pdf" and kind not in IMAGE_TYPES:
        return fp
    try:
        with pymupdf.open(stream=data, filetype="pdf" if kind == ".pdf" else kind.lstrip(".")) as doc:
            if kind == ".pdf":
                fp["meta"] = _meta(doc)
            for page in doc:
                pix = _gray(page)
                pg = {"h": page_hash(page, pix), "i": page_ink(page, pix)}
                if kind == ".pdf" and (shingles := text_shingles(page.get_text())):
                    pg["t"] = shingles
                fp["pages"].append(pg)
    except (RuntimeError, ValueError):
        fp["error"] = True
    return fp


# ---------- השוואה ----------
@dataclass
class Page:
    number: str
    page: int                  # מ-1, רץ על כל הקבצים של המספר, כמו ב-PDF המאוחד שהאתר מציג
    bits: int | None           # dHash, None לעמוד ריק או בלי כתיבה (MIN_INK)
    text: frozenset[int] | None  # רצפי הטקסט, None לעמוד לא מוקלד (ריק: מוקלד, אבל כולו נוסח מהחומר)


@dataclass
class Report:
    pairs: list[dict] = field(default_factory=list)
    repeated: list[dict] = field(default_factory=list)  # עמודים שחוזרים אצל הרבה מספרים: דף שאלות, או פתרון שעבר
    checked: int = 0               # כמה מספרים נבדקו
    material: dict = field(default_factory=dict)  # חומר הקורס: כמה קבצים, ובכמה עמודים של סטודנטים הוא נמצא
    read: int = 0                  # כמה קבצים נקראו הפעם (השאר מהמטמון)

    def summary(self) -> str:
        strong = sum(p["level"] == "strong" for p in self.pairs)
        text = (f"נבדקו {self.checked} הגשות: {len(self.pairs)} זוגות חשודים" + (f", מהם {strong} חשד חזק" if strong else "")
                if self.pairs else f"נבדקו {self.checked} הגשות. לא נמצא זוג חשוד")
        if self.repeated:
            text += f". {len(self.repeated)} עמודים חוזרים אצל הרבה הגשות (לבדוק שזה דף שאלות)"
        return text + "."


def _candidates(keys: list[list[tuple]], limit: int | None = None) -> set[tuple[int, int]]:
    """אינדקסים של עמודים שחולקים לפחות מפתח אחד (רצועה של hash). כך לא משווים כל עמוד לכל עמוד."""
    buckets: dict[tuple, list[int]] = {}
    for i, ks in enumerate(keys):
        for k in ks:
            buckets.setdefault(k, []).append(i)
    out: set[tuple[int, int]] = set()
    for members in buckets.values():
        if limit is None or len(members) <= limit:
            out.update(combinations(members, 2))
    return out


def _image_matches(pages: list[Page]) -> dict[tuple[int, int], tuple[str, int]]:
    """עמודים דומים כתמונה, כששניהם לא מוקלדים. מרחק עד MAX_DISTANCE ביטים.

    עמוד מוקלד לא מושווה כתמונה גם מול סריקה: עמודים מוקלדים מאותה תבנית נראים ל-dHash כמעט זהים, ולכן
    צילום מסך של עמוד מוקלד היה "דומה" לכל העמודים מהתבנית. המחיר: צילום מסך של עמוד מוקלד של חבר לא נתפס.

    מחלקים את 256 הביטים ל-MAX_DISTANCE+1 רצועות: שני hash במרחק MAX_DISTANCE לכל היותר זהים לפחות ברצועה
    אחת (שובך היונים). רצועה שכמעט כל העמודים חולקים היא שוליים לבנים (כל הביטים 0), לא תוכן, ומדלגים עליה:
    שני עמודים זהים באמת חולקים גם רצועות של התוכן."""
    bands = MAX_DISTANCE + 1
    width = GRID * GRID // bands
    idx = [i for i, p in enumerate(pages) if p.bits is not None]
    keys = [[(b, (pages[i].bits >> (b * width)) & ((1 << width) - 1)) for b in range(bands)] for i in idx]
    out = {}
    for x, y in _candidates(keys, BUCKET_LIMIT):
        i, j = idx[x], idx[y]
        a, b = pages[i], pages[j]
        if a.number == b.number or a.text is not None or b.text is not None:
            continue
        d = (a.bits ^ b.bits).bit_count()
        if d <= MAX_DISTANCE:
            out[(i, j)] = ("page", d)
    return out


def rare_limit(numbers: int) -> int:
    """אצל כמה מספרים לכל היותר רצף טקסט עוד נחשב נדיר: 5% מהמספרים עם עמודים מוקלדים, בין 3 ל-COMMON_PAGE.
    במטלה קטנה גם 10 הם חצי מהכיתה, ומה שחצי מהכיתה כתבה הוא לא העתקה."""
    return max(3, min(COMMON_PAGE, numbers // 20))


def _text_matches(pages: list[Page]) -> dict[tuple[int, int], tuple[str, int]]:
    """עמודים מוקלדים שחולקים רצפים נדירים: לפחות TEXT_SHARED, ולפחות TEXT_SIMILAR מהרצפים הנדירים של
    הקצר מביניהם. הציון הוא האחוז הזה. רצף שאצל יותר מ-rare_limit מספרים לא נדיר (ראו בראש הקובץ)."""
    holders: dict[int, set[str]] = {}
    for p in pages:
        for s in p.text or ():
            holders.setdefault(s, set()).add(p.number)
    limit = rare_limit(len({p.number for p in pages if p.text}))
    rare = {s for s, ns in holders.items() if len(ns) <= limit}
    idx = [i for i, p in enumerate(pages) if p.text]
    own = {i: pages[i].text & rare for i in idx}
    by_shingle: dict[int, list[int]] = {}
    for i in idx:
        for s in own[i]:
            by_shingle.setdefault(s, []).append(i)
    shared: dict[tuple[int, int], int] = {}
    for members in by_shingle.values():
        for i, j in combinations(members, 2):
            if pages[i].number != pages[j].number:
                shared[(i, j)] = shared.get((i, j), 0) + 1
    out = {}
    for (i, j), n in shared.items():
        part = n / min(len(own[i]), len(own[j]))
        if n >= TEXT_SHARED and part >= TEXT_SIMILAR:
            out[(i, j)] = ("text", round(part * 100))
    return out


def material_shingles(assignment_dir: Path) -> tuple[frozenset[int], int]:
    """רצפי הטקסט של חומר הקורס (ראו בראש הקובץ), וכמה קבצים נקראו. קובץ שלא נקרא מדולג."""
    folders = [assignment_dir.parent / paths.COURSE_MATERIAL] + [assignment_dir / name for name in paths.PEDAGOGY]
    files = sorted(f for d in folders if d.is_dir() for f in d.rglob("*") if f.is_file() and f.suffix.lower() in MATERIAL_TYPES)
    out: set[int] = set()
    for f in files:
        try:
            if f.suffix.lower() == ".pdf":
                with pymupdf.open(f) as doc:
                    texts = [page.get_text() for page in doc]
            else:
                texts = [f.read_text(encoding="utf-8", errors="replace")]
        except (OSError, RuntimeError, ValueError):
            continue
        for text in texts:
            if sh := text_shingles(text):
                out |= _shingle_set(sh)
    return frozenset(out), len(files)


def compare(prints: dict[str, list[dict]], material: frozenset[int] = frozenset()) -> Report:
    """מספר → טביעות האצבע של הקבצים שלו, לפי הסדר → הזוגות החשודים. material: רצפי הטקסט של חומר הקורס."""
    rep = Report(checked=len(prints))
    from_material = 0
    reasons: dict[tuple[str, str], list[dict]] = {}

    def add(a: str, b: str, reason: dict) -> None:
        if a != b:
            reasons.setdefault((min(a, b), max(a, b)), []).append(reason)

    # שכבה 0: אותו קובץ, ואותו ערך מטא-דאטה נדיר
    groups: dict[tuple[str, str], set[str]] = {}
    for n, files in prints.items():
        for fp in files:
            groups.setdefault(("file", fp["sha256"]), set()).add(n)
            for k, v in fp.get("meta", {}).items():
                groups.setdefault((k, v), set()).add(n)
    for (kind, _), numbers in groups.items():
        if len(numbers) < 2 or (kind != "file" and len(numbers) > COMMON_META):
            continue
        for a, b in combinations(sorted(numbers), 2):
            add(a, b, {"kind": kind})

    # שכבה 1: עמודים דומים, כתמונה או כטקסט
    pages: list[Page] = []
    for n, files in prints.items():
        at = 0
        for fp in files:
            for pg in fp.get("pages", []):
                at += 1
                # עמוד בלי כתיבה (כריכה, דף ריק) לא מושווה כתמונה: הוא נראה אותו דבר אצל כולם
                ink = pg.get("h") and pg.get("i", 0) >= MIN_INK
                text = _shingle_set(pg["t"]) if pg.get("t") else None
                if text and material:
                    if len(text & material) >= MATERIAL_SHARE * len(text):  # עמוד מהחוברת: לא מושווה בכלל
                        from_material += 1
                        continue
                    text = text - material  # נוסח השאלה לא אומר כלום על העתקה. ריק עדיין "מוקלד": לא מושווה כתמונה
                pages.append(Page(n, at, int(pg["h"], 16) if ink else None, text))
    rep.material = {"pages": from_material}
    matches = {**_image_matches(pages), **_text_matches(pages)}
    partners: dict[int, set[str]] = {}
    for i, j in matches:
        partners.setdefault(i, set()).add(pages[j].number)
        partners.setdefault(j, set()).add(pages[i].number)
    # partners לא כולל את המספר של העמוד עצמו: עמוד מוקלד אצל 3 מספרים יש לו 2 שותפים
    common = {i for i, ns in partners.items() if (len(ns) + 1 > TEXT_COMMON if pages[i].text else len(ns) > COMMON_PAGE)}
    rep.repeated = _repeated(pages, matches, common)
    by_pair: dict[tuple[str, str, str], list[list[int]]] = {}
    for (i, j), (kind, score) in sorted(matches.items()):
        if i in common or j in common:
            continue
        a, b = sorted((pages[i], pages[j]), key=lambda p: p.number)
        by_pair.setdefault((a.number, b.number, kind), []).append([a.page, b.page, score])
    # מי שצירפו חומר של הקורס (עמוד מוקלד שחוזר אצל כמה): גם עמודים מוקלדים אחרים שהם חולקים הם כנראה מאותה חוברת
    material = [{n for n, _ in g["pages"]} for g in rep.repeated if g["kind"] == "text"]
    for (a, b, kind), found in by_pair.items():
        if kind == "page" and len(found) < MIN_PAGES:  # עמוד סרוק אחד משותף הוא בדרך כלל כריכה או תבנית
            continue
        if kind == "text" and any(a in g and b in g for g in material):
            continue
        add(a, b, {"kind": kind, "pages": sorted(found)})

    for (a, b), rs in sorted(reasons.items()):
        kinds = {r["kind"] for r in rs}
        rep.pairs.append({"a": a, "b": b, "level": "strong" if kinds & STRONG else "weak",
                          "reasons": sorted(rs, key=lambda r: list(KIND_TEXT).index(r["kind"]))})
    rep.pairs.sort(key=lambda p: (p["level"] != "strong", p["a"], p["b"]))
    return rep


def _repeated(pages: list[Page], matches: dict, common: set[int]) -> list[dict]:
    """העמודים שחוזרים אצל הרבה מספרים, מקובצים: כל קבוצה היא עמוד אחד ומי שיש לו אותו (מספר, עמוד)."""
    parent = {i: i for i in common}

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in matches:
        if i in common and j in common:
            parent[root(i)] = root(j)
    groups: dict[int, list[int]] = {}
    for i in common:
        groups.setdefault(root(i), []).append(i)
    out = []
    for members in groups.values():
        found = sorted({(pages[i].number, pages[i].page) for i in members})
        out.append({"numbers": len({n for n, _ in found}), "pages": [list(x) for x in found],
                    "kind": "text" if all(pages[i].text for i in members) else "page"})
    return sorted(out, key=lambda g: -g["numbers"])


# ---------- הרצה על מטלה ----------
def report_path(assignment_dir: Path) -> Path:
    return assignment_dir / REPORT


def read_report(assignment_dir: Path) -> dict:
    try:
        return json.loads(report_path(assignment_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _stamp(path: Path) -> list[int]:
    st = path.stat()
    return [st.st_size, st.st_mtime_ns]


def is_stale(assignment_dir: Path, report: dict | None = None) -> bool:
    """האם הקבצים בתיקיית ההגשות השתנו מאז הבדיקה האחרונה (הגשה חדשה, קובץ שהוחלף או נמחק)."""
    report = read_report(assignment_dir) if report is None else report
    seen = report.get("files") or {}
    now = {p.name: _stamp(p) for files in paths.files_by_number(assignment_dir / paths.TO_GRADE).values() for p in files}
    return report.get("version") != VERSION or {k: v.get("stamp") for k, v in seen.items()} != now


def check_assignment(assignment_dir: Path, on_progress: Callable[[int, int], None] | None = None) -> Report:
    """בודק את כל ההגשות של המטלה וכותב Copying check.json. קורא רק קבצים שהשתנו מאז הפעם הקודמת."""
    old = read_report(assignment_dir)
    cached = (old.get("files") or {}) if old.get("version") == VERSION else {}
    by_number = paths.files_by_number(assignment_dir / paths.TO_GRADE)
    total = sum(len(f) for f in by_number.values())
    files: dict[str, dict] = {}
    prints: dict[str, list[dict]] = {}
    done = read = 0
    for n, paths_ in by_number.items():
        for p in paths_:
            stamp = _stamp(p)
            fp = cached.get(p.name)
            if not fp or fp.get("stamp") != stamp:
                fp = {"stamp": stamp, **fingerprint(p)}
                read += 1
            files[p.name] = fp
            prints.setdefault(n, []).append(fp)
            done += 1
            if on_progress:
                on_progress(done, total)
    material, material_files = material_shingles(assignment_dir)
    rep = compare(prints, material)
    rep.material["files"] = material_files
    rep.read = read
    out = {"version": VERSION, "checked_at": datetime.now().isoformat(timespec="seconds"), "by": lock.me(),
           "summary": rep.summary(), "checked": rep.checked, "pairs": rep.pairs, "repeated": rep.repeated, "material": rep.material,
           "files": files}
    tmp = report_path(assignment_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, report_path(assignment_dir))
    return rep
