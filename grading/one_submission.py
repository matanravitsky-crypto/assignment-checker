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
  python -m grading mark <תיקיית עבודה> <המחוון, כמו ב-rubric> <answer.json> <קובץ הפלט.pdf>
      התשובה של Claude (במבנה של grade.SCHEMA) עוברת דרך grade.parse_answer (ניקוד עד המחוון, בחצאי נקודות, הציון
      מחושב מהניקוד), הסימונים חוזרים מהתמונות החתוכות לעמוד השלם (grade.marks_to_page), ו-grade.mark_pdf מצייר את
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

from moodle import paths

from . import grade, render

COMMANDS = ("prepare", "rules", "rubric", "mark")
SUBMISSION = "submission.pdf"
PAGES = "pages.json"
UNTITLED = "מטלה"
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
            **({"official_key_points": data["official_key_points"]} if "official_key_points" in data else {})}


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
    """מה Claude קורא לפני העמודים, כשהמחוון הוא תיקיית מטלה: המכוון, הפתרון הרשמי וחומר הבדיקה, לפי הסדר."""
    source = Path(source)
    if not source.is_dir():
        return []
    key = grade.official_key(source)
    found = list(key.files) if key else []
    found += [p for p in (source / paths.OFFICIAL_KEY_TEXT, source / grade.SOLUTION) if p.is_file()]
    return [str(p.resolve()) for p in found + grade.pedagogy_files(source)]


def rubric(source: Path) -> dict:
    ctx = context(source)
    return {"title": ctx.title, "course": ctx.course, "max_grade": ctx.max_grade,
            "total_points": sum(q.points for q in ctx.questions),
            "questions": [{"label": q.label, "points": q.points, "criteria": q.criteria, "deductions": q.deductions}
                          for q in ctx.questions],
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


def mark(work: Path, source: Path, answer_file: Path, output: Path) -> dict:
    work = Path(work)
    ctx = context(source)
    info = json.loads((work / PAGES).read_text(encoding="utf-8"))
    images = [render.PageImage(p["page"], b"", p.get("width") or 0, p.get("height") or 0,
                               tuple(p["clip"]) if p.get("clip") else None) for p in info["pages"]]
    g = grade.parse_answer(Path(answer_file).read_text(encoding="utf-8-sig"), ctx, len(images))
    g.marks = grade.marks_to_page(g.marks, images)
    asked = Counter((m.page, m.text) for m in g.marks if m.text)
    pdf = grade.mark_pdf((work / SUBMISSION).read_bytes(), g, ctx)  # g.marks = מה שצויר באמת על העבודה
    moved = asked - Counter((m.page, m.text) for m in g.marks if m.text)
    out = _free(Path(output))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf)
    summary = {"grade": g.grade, "max_grade": ctx.max_grade,
               "questions": [{"label": q.label, "points": p, "of": q.points, "comment": c, "mistakes": m, "unsure": u}
                             for q, p, c, m, u in zip(ctx.questions, g.points, g.comments, g.mistakes, g.unsure)],
               "feedback": g.feedback, "review": g.review, "review_kind": g.review_kind,
               "marks": [m.__dict__ for m in g.marks],
               "notes_moved_to_summary": [f"עמוד {page}: {text}" for (page, text), k in moved.items() for _ in range(k)],
               "output": str(out.resolve()), "size_kb": round(len(pdf) / 1024)}
    out.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


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
        elif cmd == "mark" and len(args) == 4:
            out = mark(*(Path(a) for a in args))
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
