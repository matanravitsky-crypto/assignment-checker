"""מסד הנתונים הסטטיסטי: הדלת היחידה לסטטיסטיקה של המטלות (ראו docs/Statistics database plan.md).

שלב 1 (כאן): `compute.py` מחשב, ו-`gather` אוסף מתיקיית המטלה את מה שהחישוב צריך. השמירה בתיקייה המשותפת,
שורת הפקודה והאתר באים בשלבים הבאים. האתר, Claude ושורת הפקודה קוראים דרך המודול הזה ולא פותחים קבצים בעצמם.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from moodle import claims, grades, paths

from . import compute as _compute


def gather(assignment_dir: Path) -> dict:
    """כל מה ש-`compute.compute` צריך, מתיקיית המטלה: המחוון (דרך grading, כולל הניקוד מתיקיית "פדגוגי"),
    הציונים הממוזגים, הערות הבדיקה, כמה הגשות וכמה מסומנות, וזוגות ההעתקה. מספרים בלבד."""
    from grading import grade as grading  # טוען PyMuPDF: רק כאן, לא בחישוב עצמו

    a = Path(assignment_dir)
    d = paths.read_info(a)
    ctx = grading.load_context(a, send_solution=False)
    notes = {}
    for p in sorted((a / paths.NOTES).glob("*.json")) if (a / paths.NOTES).is_dir() else []:
        if not p.stem.isdigit():
            continue
        note = grading.read_notes(a, p.stem)
        if grading.is_limit(str(note.get("error") or "")):  # נגמרה המכסה: העבודה עוד לא נבדקה
            note = {k: v for k, v in note.items() if k != "error"}
        notes[grades.number_key(p.stem)] = note
    copying = a / paths.COPYING
    pairs = None
    if copying.is_file():
        try:
            data = json.loads(copying.read_text(encoding="utf-8"))
            pairs = len(data.get("pairs") or []) if isinstance(data, dict) else None
        except (OSError, ValueError):
            pairs = None
    return {
        "course": a.parent.name, "folder": a.name, "moodle_id": d.get("id"),
        "title": str(d.get("title") or d.get("name") or a.name), "max_grade": ctx.max_grade,
        "questions": [{"label": q.label, "points": q.points, "deductions": q.deductions} for q in ctx.questions],
        "rows": grades.read(a), "notes": notes,
        "submitted": len(paths.files_by_number(a / paths.TO_GRADE)),
        "marked": set(paths.files_by_number(a / paths.MARKED, "*.pdf")),
        "copying_pairs": pairs,
        "sources": sources(a),
    }


def sources(assignment_dir: Path) -> dict:
    """ממה הסטטיסטיקה חושבה: שמות, גדלים וזמני שינוי של קובצי הציונים, וכמה קובצי הערות יש ומתי השתנה האחרון.
    `read` ישווה את זה למה שבתיקייה כדי לדעת אם לחשב מחדש (שלב 2)."""
    a = Path(assignment_dir)
    files = [{"name": p.name, "size": p.stat().st_size, "mtime": int(p.stat().st_mtime)} for p in grades.files(a)]
    notes = [p for p in (a / paths.NOTES).glob("*.json")] if (a / paths.NOTES).is_dir() else []
    return {"grades": files, "notes": len(notes), "notes_mtime": max((int(p.stat().st_mtime) for p in notes), default=0),
            "marked": len(paths.files_by_number(a / paths.MARKED, "*.pdf")),
            "submitted": len(paths.files_by_number(a / paths.TO_GRADE))}


def compute_assignment(assignment_dir: Path, by: str | None = None) -> dict:
    """הסטטיסטיקה של מטלה אחת, מחושבת עכשיו מהתיקייה."""
    data = gather(assignment_dir)
    return _compute.compute(**data, computed_at=datetime.now().isoformat(timespec="seconds"),
                            computed_by=by or claims.me() or os.environ.get("USERNAME", ""))
