"""בדיקה של הגשה אחת מחוץ למערכת, בדיוק כמו שלב הבדיקה: Claude שבשיחה קורא ובודק, והקוד של grading עושה את כל
השאר. הסקיל exercise-grader (grading/skill/SKILL.md, נבנה ב-tools/extract_skill.py) מריץ את זה דרך `python -m grading`:

  python -m grading prepare <תיקיית עבודה> <קובצי ההגשה...>
      הקבצים (PDF או תמונות, לפי הסדר) הופכים ל-PDF אחד, submission.pdf (grade.submission_pdf), וכל עמוד לתמונה
      שהמערכת שולחת ל-Claude: עם רשת העזר, חתוכה לכתב כמו בבדיקה (render.render_pdf), ועמוד גדול כ-JPEG
      (grade._image_block). page_001.png ... ו-pages.json (העמודים, והחלק של העמוד שכל תמונה מראה).
  python -m grading rules
      הוראות הבדיקה של המערכת (grade.SYSTEM) ומבנה התשובה (grade.SCHEMA), מילה במילה.
  python -m grading rubric <rubric.json | Assignment details.json | תיקיית מטלה>
      המחוון כמו שהבדיקה קוראת אותו (grade.load_context), והטקסט שהמערכת שולחת ל-Claude על המטלה (grade.context_text).
      קוד יציאה 2 = אין מחוון עם ניקוד לכל שאלה (grade.NoRubric): שואלים את המשתמש, לא מחלקים ניקוד לבד.
  python -m grading preview <תיקיית עבודה> <העבודה המסומנת.pdf> [עמודים...]
      עמודים של העבודה המסומנת (ברירת מחדל 1 ו-2) כתמונות PNG בתיקיית העבודה, כדי לבדוק בצעד אחד שעמוד הסיכום
      והסימונים נראים נכון. הכלי Read לא פותח PDF בכל מחשב (צריך poppler), ותמונה קטנה עולה פחות טוקנים.
  python -m grading zoom <תיקיית עבודה> <עמוד> [x0 y0 x1 y1]
      חלק מעמוד (באלפיות של תמונת העמוד שנקראה) בהגדלה, מהעבודה עצמה ובלי רשת: zoom_p<עמוד>.png, לסימן שלא קריא.
  python -m grading mark <תיקיית עבודה> <המחוון, כמו ב-rubric> <answer.json> <קובץ הפלט.pdf> [--no-zoom]
      התשובה של Claude (במבנה של grade.SCHEMA) עוברת דרך grade.parse_answer (ניקוד עד המחוון, בחצאי נקודות, הציון
      מחושב מהניקוד), הסימונים חוזרים מהתמונות החתוכות לעמוד השלם (grade.marks_to_page), מעבר הזום של המערכת
      (locate.py, Sonnet דרך Claude Code שמחובר במחשב; --no-zoom בלעדיו) ממקם מחדש כל סימון ותחילת סעיף שהם סותרים,
      ו-grade.mark_pdf מצייר את
      העבודה המסומנת (מלבנים אדומים צמודים לכתב היד, הערות, עמוד סיכום ראשון, עד 2 MB). מדפיס סיכום JSON וכותב
      אותו ליד ה-PDF (<הפלט>.json). קובץ פלט שכבר קיים לא נדרס: נוסף לשם " (2)", " (3)"...

כאן לא נכתב כלום בתיקיית מטלה: לא ציונים, לא Grading notes, לא מי בודק מה. בדיקה של מטלה שלמה: `python -m grading <id>`.
"""
from __future__ import annotations

import base64
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pymupdf

from moodle import paths

from . import grade, render

COMMANDS = ("prepare", "rules", "rubric", "mark", "preview", "zoom")
SUBMISSION = "submission.pdf"
PAGES = "pages.json"
UNTITLED = "מטלה"
PREVIEW_SIDE = 1568  # פיקסלים בצד הארוך: מה ש-Claude רואה בכל מקרה (תמונה גדולה יותר מוקטנת לזה), וההערות קריאות
# קובץ פרטים שמגיע לבד, בלי תיקיית המטלה: official_key_points נכתבים בו רק כשהועלה מכוון (POST /api/official-key),
# אז הוא עומד במקום המכוון, והניקוד שלו גובר כמו במערכת (grade.load_context)
KEY_STAND_IN = f"הניקוד לכל שאלה נלקח מהמכוון הרשמי של המרצה (official_key_points ב-{paths.INFO})."


# ---------- המחוון ----------
def _details(data: dict) -> dict:
    """קובץ אחד כ-Assignment details.json: קובץ פרטים של המערכת כמו שהוא, או rubric.json של הסקיל
    ({"title", "course", "max_grade", "questions": [...], "notes", "official_key_points"})."""
    if "rubric" in data or "id" in data:
        return data
    return {"title": data.get("title"), "course_title": data.get("course") or data.get("course_title"),
            "max_grade": data.get("max_grade"),
            "rubric": {"questions": data.get("questions") or [], "notes": data.get("notes") or ""},
            **({"official_key_points": data["official_key_points"]} if "official_key_points" in data else {}),
            **({"moodle_grade": data["moodle_grade"]} if "moodle_grade" in data else {})}


def context(source: Path) -> grade.Context:
    """המחוון כמו שהבדיקה קוראת אותו. תיקיית מטלה נקראת כמו שהיא (Assignment details.json, פדגוגי/, Official key/).
    קובץ אחד נקרא דרך תיקייה זמנית משלו, באותה פונקציה של המערכת. זורק NoRubric אם לשאלה כלשהי אין ניקוד."""
    source = Path(source)
    if source.is_dir():
        ctx = grade.load_context(source, send_solution=False)
    else:
        text = source.read_text(encoding="utf-8-sig")  # קובץ שלא קיים: OSError, לא "אין מחוון"
        try:
            data = json.loads(text)
        except ValueError as e:  # PDF, Word או טקסט: Claude קורא אותו וכותב rubric.json (SKILL.md, שלב 2)
            raise grade.NoRubric(f"אי אפשר לקרוא את המחוון {source.name}: {e}. {grade.RUBRIC_RULE}") from e
        if not isinstance(data, dict):
            raise grade.NoRubric(f"המחוון {source.name} הוא לא אובייקט JSON. {grade.RUBRIC_RULE}")
        details = _details(data)
        with tempfile.TemporaryDirectory(prefix="exercise-grader-") as tmp:
            folder = Path(tmp)
            (folder / paths.INFO).write_text(json.dumps(details, ensure_ascii=False), encoding="utf-8")
            key_points = details.get("official_key_points")
            if isinstance(key_points, dict) and any(grade.to_points(v) for v in key_points.values()):
                (folder / paths.OFFICIAL_KEY_TEXT).write_text(KEY_STAND_IN, encoding="utf-8")
            ctx = grade.load_context(folder, send_solution=False)
        # שם התיקייה הזמנית הוא לא שם המטלה
        ctx.title = str(details.get("title") or UNTITLED)
        ctx.course = str(details.get("course_title") or details.get("course") or "")
    grade.require_rubric(ctx)
    return ctx


def materials(source: Path) -> list[str]:
    """מה Claude קורא לפני העמודים, כשהמחוון הוא תיקיית מטלה: רק מה שאין כבר ב-context, כמו בבדיקה של המערכת.
    המכוון כקבצים (תמונה, PDF), והפתרון הרשמי רק כשהמערכת שולחת אותו (grade.send_solution_default: כשבפדגוגי אין
    קובץ פתרונות). קובצי פדגוגי ו-Official key.txt כבר בתוך context (grade.context_text): עד 2026-11-15 הם היו
    גם כאן, ו-Claude קרא את המחוון פעמיים (כ-80 אלף טוקנים נוספים בכל בדיקה)."""
    source = Path(source)
    if not source.is_dir():
        return []
    key = grade.official_key(source)
    found = list(key.files) if key else []
    solution = source / grade.SOLUTION
    if solution.is_file() and grade.send_solution_default(grade.pedagogy_files(source)):
        found.append(solution)
    return [str(p.resolve()) for p in found]


def rubric(source: Path) -> dict:
    ctx = context(source)
    return {"title": ctx.title, "course": ctx.course, "max_grade": ctx.max_grade,
            "total_points": sum(q.points for q in ctx.questions),
            "questions": [{"label": q.label, "points": q.points} for q in ctx.questions],  # the rest is in context
            "official_key": ctx.official_key is not None, "read_first": materials(source),
            "context": grade.context_text(ctx)}


# ---------- העמודים ----------
def prepare(work: Path, files: list[Path], crop: bool = render.CROP_DEFAULT) -> dict:
    """submission.pdf, תמונה לכל עמוד (בדיוק מה שהמערכת שולחת ל-Claude), ו-pages.json."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    pdf, skipped = grade.submission_pdf([Path(f) for f in files])
    if not pdf:
        raise grade.GradingError("אין בהגשה קובץ PDF או תמונה שאפשר לבדוק.")
    for old in work.glob("page_*.*"):  # עמודים של הגשה קודמת באותה תיקייה
        old.unlink()
    (work / SUBMISSION).write_bytes(pdf)
    pages = []
    for img in render.render_pdf(pdf, grid=True, crop=crop):
        block = grade._image_block(img)
        ext = "jpg" if block["source"]["media_type"] == "image/jpeg" else render.IMAGE_FORMAT
        image = work / f"page_{img.page:03d}.{ext}"
        image.write_bytes(base64.b64decode(block["source"]["data"]))
        pages.append({"page": img.page, "image": str(image.resolve()), "width": img.width, "height": img.height,
                      "clip": list(img.clip) if img.clip else None})
    info = {"pages": pages, "skipped": skipped}
    (work / PAGES).write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


# ---------- העבודה המסומנת ----------
def _free(path: Path) -> Path:
    """path, או "<שם> (2).pdf", "(3)"... אם הוא כבר קיים: לא דורסים הגשה או בדיקה קודמת."""
    n = 2
    out = path
    while out.exists():
        out = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return out


def zoom_ask():
    """How the zoom pass asks Claude (Sonnet, like the system): through ANTHROPIC_API_KEY or the Claude Code signed in on
    this computer. None when there is neither, or LOCATE=off: then the boxes stay where the answer put them."""
    from . import locate
    if not locate.enabled():
        return None
    try:
        return grade.claude_ask(locate.SCHEMA, locate.EFFORT)
    except Exception:  # noqa: BLE001 - no Claude Code / not signed in: draw without the pass
        return None


def mark(work: Path, source: Path, answer_file: Path, output: Path, ask=zoom_ask) -> dict:
    """ask: how the zoom pass reaches Claude (a function returning an Ask, or None for none). The pass places every
    mark again on a close-up of the page, and a part's start the marks contradict (locate.py), as in the system: on
    graph paper the rough boxes were off by a fifth of the page (2026-11-16, Nadav: 0093)."""
    work = Path(work)
    ctx = context(source)
    info = json.loads((work / PAGES).read_text(encoding="utf-8"))
    images = [render.PageImage(p["page"], b"", p.get("width") or 0, p.get("height") or 0,
                               tuple(p["clip"]) if p.get("clip") else None) for p in info["pages"]]
    g = grade.parse_answer(Path(answer_file).read_text(encoding="utf-8-sig"), ctx, len(images))
    g.marks = grade.marks_to_page(g.marks, images)
    g.places = grade.marks_to_page(g.places, images)
    submission = (work / SUBMISSION).read_bytes()
    zoom = "off"
    asker = ask() if ask else None
    if asker is not None:
        from . import locate
        before = [(m.page, m.x0, m.y0, m.x1, m.y1) for m in g.marks + g.places]
        g.marks, g.places = locate.relocate_all(submission, g.marks, g.places, g.firsts, asker, grade.Mark)
        after = [(m.page, m.x0, m.y0, m.x1, m.y1) for m in g.marks + g.places]
        zoom = f"{sum(a != b for a, b in zip(before, after))} of {len(before)} boxes placed again"
    grade.course_grade(g, ctx)  # ציון הקורס לפי מה שהוגש, כשלמטלה יש מדיניות כזו (העתקה נבדקת במערכת, על כל ההגשות)
    asked = Counter((m.page, m.text) for m in g.marks if m.text)
    pdf = grade.mark_pdf(submission, g, ctx)  # g.marks = מה שצויר באמת על העבודה
    moved = asked - Counter((m.page, m.text) for m in g.marks if m.text)
    out = _free(Path(output))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf)
    summary = {"grade": g.grade, "max_grade": ctx.max_grade,
               "questions": [{"label": q.label, "points": p, "of": q.points, "comment": c, "mistakes": m, "unsure": u}
                             for q, p, c, m, u in zip(ctx.questions, g.points, g.comments, g.mistakes, g.unsure)],
               "feedback": g.feedback, "review": g.review, "review_kind": g.review_kind,
               "course_grade": g.course, "course_why": g.course_why, "typed": g.typed,
               "not_submitted": [q.label for q, d in zip(ctx.questions, g.submitted) if not d],
               "marks": [m.__dict__ for m in g.marks],
               "notes_moved_to_summary": [f"עמוד {page}: {text}" for (page, text), k in moved.items() for _ in range(k)],
               "zoom": zoom,
               "output": str(out.resolve()), "size_kb": round(len(pdf) / 1024)}
    out.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def preview(work: Path, pdf: Path, pages: list[int] | None = None) -> dict:
    """עמודים של העבודה המסומנת כתמונות בתיקיית העבודה (check_p1.png...), לבדיקה של הסימונים בקריאה אחת."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    out = []
    with pymupdf.open(str(pdf)) as doc:
        for n in pages or [1, 2]:
            if not 1 <= n <= doc.page_count:
                continue
            page = doc[n - 1]
            zoom = PREVIEW_SIDE / max(page.rect.width, page.rect.height)
            path = work / f"check_p{n}.png"
            page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(str(path))
            out.append(str(path.resolve()))
    return {"pages": out}


ZOOM_SIDE = 1500


def zoom(work: Path, page: int, box: list[float] | None = None) -> dict:
    """A close-up of a part of a page, for a symbol that can't be made out on the page image: the box in thousandths of
    that page image (the cropped one, with the grid), from the submission itself, about 1500 pixels on the long side,
    with no grid. zoom_p<page>.png in the work folder. Two graders wrote their own crop script for this (2026-11-18)."""
    work = Path(work)
    info = json.loads((work / PAGES).read_text(encoding="utf-8"))
    p = next((x for x in info["pages"] if x["page"] == page), None)
    if p is None:
        raise ValueError(f"אין עמוד {page} בעבודה")
    img = render.PageImage(page, b"", p.get("width") or 0, p.get("height") or 0, tuple(p["clip"]) if p.get("clip") else None)
    x0, y0, x1, y1 = box if box and len(box) == 4 else (0, 0, 1000, 1000)
    (a, b), (c, d) = img.to_page(min(x0, x1), min(y0, y1)), img.to_page(max(x0, x1), max(y0, y1))
    with pymupdf.open(str(work / SUBMISSION)) as doc:
        pg = doc[page - 1]
        r = pg.rect
        clip = pymupdf.Rect(r.x0 + a / 1000 * r.width, r.y0 + b / 1000 * r.height,
                            r.x0 + c / 1000 * r.width, r.y0 + d / 1000 * r.height) & r
        if clip.is_empty:
            raise ValueError("המלבן מחוץ לעמוד")
        scale = ZOOM_SIDE / max(clip.width, clip.height)
        path = work / f"zoom_p{page}.png"
        pg.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip).save(str(path))
    return {"image": str(path.resolve())}


# ---------- שורת הפקודה ----------
def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    try:
        if cmd == "prepare" and len(args) >= 2:
            out = prepare(Path(args[0]), [Path(a) for a in args[1:]])
        elif cmd == "rules" and not args:
            print(grade.SYSTEM)
            print("\nמבנה התשובה (JSON schema):")
            out = grade.SCHEMA
        elif cmd == "rubric" and len(args) == 1:
            out = rubric(Path(args[0]))
        elif cmd == "mark" and len(args) in (4, 5) and (len(args) == 4 or args[4] == "--no-zoom"):
            out = mark(*(Path(a) for a in args[:4]), ask=None if len(args) == 5 else zoom_ask)
        elif cmd == "zoom" and len(args) in (2, 6):
            out = zoom(Path(args[0]), int(args[1]), [float(a) for a in args[2:]] or None)
        elif cmd == "preview" and len(args) >= 2:
            out = preview(Path(args[0]), Path(args[1]), [int(a) for a in args[2:]] or None)
        else:
            print(__doc__)
            return 1
    except grade.NoRubric as e:
        print(str(e), file=sys.stderr)
        return 2
    except (grade.GradingError, OSError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if cmd in ("prepare", "mark") and grade._archive() is None:
        print("warning: no Hebrew font found on this computer; the notes may not show", file=sys.stderr)
    return 0
