"""מדגם הגשות לבניית מחוון: בוחר הגשות באקראי והופך את העמודים שלהן לתמונות קלות לקריאה.

  python -m grading.sample <מזהה מטלה> --out <תיקייה>             50 למדגם + 6 לניסוי בשטח
  python -m grading.sample <מזהה מטלה> --out <תיקייה> --n 30 --fresh 6
  python -m grading.sample <מזהה מטלה> --out <תיקייה> --max-side 1000 --crop   זול יותר: תמונות קטנות, בלי שוליים

כותב לתיקייה:
  pages/<מספר>_pNN.jpg   עמוד לתמונה. עמודים ריקים (שער, משבצות) לא נכתבים
  manifest.json          אילו הגשות במדגם, אילו לניסוי, כמה עמודים לכל אחת, ומה דולג

התמונות קטנות מאלה של הבדיקה עצמה (render.py): כאן קוראים כדי למצוא טעויות נפוצות,
לא כדי לסמן עליהן, ותמונה קטנה יותר עולה פחות טוקנים.
התיקייה מכילה עבודות של סטודנטים: לא בתוך ה-repo, ומוחקים אותה בסוף.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import pymupdf

from moodle import paths

# ---------- הגדרות ----------

# אורך הצד הארוך של כל תמונה. מספיק כדי לקרוא כתב יד מסריקת טלפון.
MAX_SIDE = 1200
JPEG_QUALITY = 60

# עמוד נחשב ריק אם פחות מהחלק הזה של הפיקסלים כהה (עמוד משבצות או עמוד לבן).
# נמדד על סריקות של הגשה 0: עמוד ריק יוצא 0, ועמוד בעיפרון חיוור יוצא לפחות 0.0013.
BLANK_INK = 0.0008
DARK = 140

# הגשה עם יותר עמודים מזה נקראת רק עד כאן, ומסומנת (למשל חוברת שלמה של 33 עמודים שהועלתה בטעות).
# בהגשה 0 היו גם עבודות תקינות של 20 עמודים (סעיף לעמוד), ולכן לא פחות מזה.
MAX_PAGES = 24

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def ink_ratio(pix: pymupdf.Pixmap) -> float:
    """החלק של הפיקסלים הכהים בתמונה (אפור, 0-255)."""
    gray = pymupdf.Pixmap(pymupdf.csGRAY, pix) if pix.n > 1 else pix
    data = gray.samples
    return sum(1 for b in data if b < DARK) / max(len(data), 1)


def is_blank(page: pymupdf.Page) -> bool:
    small = page.get_pixmap(matrix=pymupdf.Matrix(0.5, 0.5), colorspace=pymupdf.csGRAY, alpha=False)
    return ink_ratio(small) < BLANK_INK


# חיתוך שוליים: שורה או עמודה של התמונה המוקטנת נחשבת "עם דיו" אם לפחות כך וכך מהפיקסלים שלה כהים.
# סריקת טלפון של דף A4 היא בדרך כלל 20-35% שוליים לבנים, שעולים טוקנים כמו כתב.
CROP_SCALE = 0.25
CROP_LINE_INK = 0.004
CROP_MARGIN = 0.02


def ink_bbox(page: pymupdf.Page) -> pymupdf.Rect | None:
    """המלבן שבו יש כתב בעמוד, עם שוליים של 2%, בקואורדינטות של העמוד. None אם אין מה לחתוך
    (הכתב ממלא את העמוד, או שלא נמצא כתב)."""
    pix = page.get_pixmap(matrix=pymupdf.Matrix(CROP_SCALE, CROP_SCALE), colorspace=pymupdf.csGRAY, alpha=False)
    w, h, data = pix.width, pix.height, pix.samples
    rows = [sum(1 for x in range(w) if data[y * w + x] < DARK) >= CROP_LINE_INK * w for y in range(h)]
    cols = [sum(1 for y in range(h) if data[y * w + x] < DARK) >= CROP_LINE_INK * h for x in range(w)]
    if not any(rows) or not any(cols):
        return None
    y0, y1 = rows.index(True), h - 1 - rows[::-1].index(True)
    x0, x1 = cols.index(True), w - 1 - cols[::-1].index(True)
    mx, my = CROP_MARGIN * w, CROP_MARGIN * h
    x0, y0, x1, y1 = max(0, x0 - mx), max(0, y0 - my), min(w, x1 + 1 + mx), min(h, y1 + 1 + my)
    area = (x1 - x0) * (y1 - y0) / (w * h)
    if area > 0.9 or area < 0.4:   # הכתב ממלא את העמוד, או שנמצא "כתב" קטן מדי (עיפרון חיוור שרובו לא נראה): בלי חיתוך
        return None
    r = page.rect
    return pymupdf.Rect(r.x0 + x0 / CROP_SCALE, r.y0 + y0 / CROP_SCALE, r.x0 + x1 / CROP_SCALE, r.y0 + y1 / CROP_SCALE)


def render_file(path: Path, number: int | str, out: Path, start: int,
                max_side: int = MAX_SIDE, crop: bool = False) -> tuple[list[str], int]:
    """כותב תמונה לכל עמוד לא ריק בקובץ. מחזיר את שמות התמונות ואת מספר העמודים הריקים שדולגו.
    crop: רק המלבן שיש בו כתב (ink_bbox), כדי שהשוליים הלבנים לא יעלו טוקנים."""
    names: list[str] = []
    blank = 0
    with pymupdf.open(path) as doc:
        for page in doc:
            if start + len(names) >= MAX_PAGES:
                break
            if is_blank(page):
                blank += 1
                continue
            clip = (ink_bbox(page) if crop else None) or page.rect
            zoom = max_side / max(page.rect.width, page.rect.height)  # לפי העמוד: חיתוך רק מקטין, לא מגדיל
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
            name = f"{number}_p{start + len(names) + 1:02d}.jpg"
            pix.save(out / name, jpg_quality=JPEG_QUALITY)
            names.append(name)
    return names, blank


def pick(numbers: list[str], n: int, fresh: int, seed: int) -> tuple[list[str], list[str]]:
    """n הגשות למדגם ועוד fresh אחרות לניסוי בשטח, באקראי אבל קבוע לפי seed."""
    rnd = random.Random(seed)
    chosen = rnd.sample(numbers, k=min(n + fresh, len(numbers)))
    return sorted(chosen[:n]), sorted(chosen[n:])


def build(assignment_dir: Path, out: Path, n: int = 50, fresh: int = 6, seed: int | None = None,
          max_side: int = MAX_SIDE, crop: bool = False) -> dict:
    files = paths.files_by_number(assignment_dir / paths.TO_GRADE)
    info = paths.read_info(assignment_dir)
    if seed is None:
        seed = int(info.get("id") or 0)
    sample, field = pick(list(files), n, fresh, seed)

    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"assignment": info.get("id"), "seed": seed, "sample": sample, "fresh": field,
                "pages": {}, "blank_skipped": {}, "flags": {}}
    for number in sample + field:
        names: list[str] = []
        blank = 0
        for f in files[number]:
            suffix = f.suffix.lower()
            if suffix == ".pdf" or suffix in IMAGE_SUFFIXES:
                got, skipped = render_file(f, number, pages_dir, len(names), max_side, crop)
                names += got
                blank += skipped
            else:
                manifest["flags"].setdefault(number, []).append(f"not read: {f.name}")
        manifest["pages"][number] = names
        if blank:
            manifest["blank_skipped"][number] = blank
        if len(names) >= MAX_PAGES:
            manifest["flags"].setdefault(number, []).append(f"only the first {MAX_PAGES} pages")
        if not names:
            manifest["flags"].setdefault(number, []).append("no readable page")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m grading.sample", description="מדגם הגשות לבניית מחוון")
    p.add_argument("assignment_id")
    p.add_argument("--out", required=True, help="תיקייה זמנית מחוץ ל-repo")
    p.add_argument("--n", type=int, default=50, help="כמה הגשות למדגם")
    p.add_argument("--fresh", type=int, default=6, help="כמה הגשות נוספות לניסוי בשטח")
    p.add_argument("--seed", type=int, help="ברירת מחדל: מזהה המטלה")
    p.add_argument("--max-side", type=int, default=MAX_SIDE, help=f"אורך הצד הארוך של תמונה בפיקסלים (ברירת מחדל {MAX_SIDE})")
    p.add_argument("--crop", action="store_true", help="לחתוך את השוליים הלבנים: רק המלבן שיש בו כתב")
    args = p.parse_args(argv)
    try:
        folder = paths.assignment_dir(args.assignment_id)
    except FileNotFoundError as e:
        print(e)
        return 2
    m = build(folder, Path(args.out), args.n, args.fresh, args.seed, args.max_side, args.crop)
    total = sum(len(v) for v in m["pages"].values())
    print(f"מדגם: {len(m['sample'])}, ניסוי: {len(m['fresh'])}, עמודים: {total}, "
          f"ריקים שדולגו: {sum(m['blank_skipped'].values())}")
    for number, why in m["flags"].items():
        print(f"  {number}: {'; '.join(why)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
