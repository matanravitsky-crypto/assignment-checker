"""עריכת ציון: פונקציה אחת (edit_grade), רשימת יעדים לעדכון (TARGETS), ורשומה ביומן (activity_log).

    edit_grade(assignment_dir, "0001", points=[...], comments=[...], feedback="...", by="dana (PC)", reason="...")

1. בודקת את הקלט: יש הגשה כזו, יש מחוון, ניקוד לכל שאלה ולא מעל המחוון, ויש סיבה כשמשנים ציון קיים.
2. מחשבת את הציון החדש מהניקוד (כמו הבדיקה: המערכת מחשבת, לא האדם).
3. מעדכנת אותו בכל יעד ב-TARGETS, לפי הסדר. יעד שנכשל עוצר את השאר, והשגיאה אומרת איפה כן עודכן ואיפה לא
   (אפשר לשמור שוב: כל יעד פשוט כותב את הציון החדש).
4. כותבת ליומן מי, מתי, מאיזה ציון לאיזה ולמה (או, אם נכשלה, מה הגיע לאן).

מקום חדש שצריך לעדכן בו ציון = מחלקה חדשה עם name, label, enabled() ו-apply(edit), ושורה ב-TARGETS. הפונקציה לא משתנה.

מסד הנתונים (DatabaseTarget): כבוי עד ש-connect_database(store) מחבר אליו store עם save_grade(edit: GradeEdit) -> None.
datastore/ledger.py נותן LedgerStore: רושם "grade_edit_intent" ביומן לפני שאר היעדים (קריסה באמצע = עריכה לא גמורה
שה-doctor מראה). הדשבורד יחבר אותו בהפעלה (שלב 3 של הצעה A); העריכה הגמורה נרשמת תמיד ("grade_edit").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import activity_log
from moodle import grades, paths

from . import grade as g_

ACTION = "grade_edit"
ACTION_FAILED = "grade_edit_failed"
MAX_REASON = 1000


class ReasonRequired(g_.GradingError):
    """שינוי של ציון קיים בלי סיבה."""


class EditIncomplete(g_.GradingError):
    """הציון עודכן רק בחלק מהמקומות."""

    def __init__(self, message: str, updated: list[str], failed: str):
        super().__init__(message)
        self.updated, self.failed = updated, failed


@dataclass
class GradeEdit:
    """כל מה שיעד צריך כדי לעדכן את הציון אצלו."""
    assignment_dir: Path
    number: str
    ctx: g_.Context
    graded: g_.Graded           # הציון החדש: ניקוד, הערות, משוב, סימונים
    files: list[Path]           # קבצי ההגשה
    old: dict                   # שורת הציון לפני העריכה (מאוחדת מכל קבצי הציונים), {} אם לא היה ציון
    note: dict                  # Grading notes לפני העריכה
    by: str
    at: str
    reason: str
    kind: str                   # edit / review / first

    @property
    def new_grade(self) -> str:
        return g_._pts(self.graded.grade)

    @property
    def old_grade(self) -> str | None:
        return (self.old.get("grade") or "").strip() or None

    @property
    def points(self) -> list[float]:
        return self.graded.points


class Target(Protocol):
    name: str    # ביומן
    label: str   # בהודעות לאדם

    def enabled(self) -> bool: ...

    def apply(self, edit: GradeEdit) -> None: ...


# ---------- היעדים ----------
class GradeStore(Protocol):
    def save_grade(self, edit: GradeEdit) -> None: ...


@dataclass
class DatabaseTarget:
    """מסד הנתונים. כבוי עד ש-connect_database מחבר אליו store."""
    name: str = "database"
    label: str = "מסד הנתונים"
    store: GradeStore | None = None

    def enabled(self) -> bool:
        return self.store is not None

    def apply(self, edit: GradeEdit) -> None:
        self.store.save_grade(edit)


@dataclass
class MarkedPdfTarget:
    """עמוד הסיכום ב-PDF המסומן (2 - Graded with comments/0001.pdf)."""
    name: str = "marked_pdf"
    label: str = "עמוד הסיכום ב-PDF המסומן"

    def enabled(self) -> bool:
        return True

    def apply(self, edit: GradeEdit) -> None:
        marked = edit.assignment_dir / paths.MARKED / f"{edit.number}.pdf"
        if marked.exists() and "marks" not in edit.note:
            out = g_._resummarize(marked.read_bytes(), edit.graded, edit.ctx)  # נבדקה לפני שהיו Grading notes: הסימונים רק ב-PDF
        else:
            pdf, _ = g_.submission_pdf(edit.files)
            out = g_.mark_pdf(pdf, edit.graded, edit.ctx) if pdf else None
        if out:
            marked.parent.mkdir(exist_ok=True)
            tmp = marked.with_suffix(".pdf.tmp")
            tmp.write_bytes(out)
            tmp.replace(marked)


@dataclass
class NotesTarget:
    """Grading notes/0001.json: ההערות, הטעויות ומי בדק. מזה האתר מראה את העבודה."""
    name: str = "notes"
    label: str = "Grading notes"

    def enabled(self) -> bool:
        return True

    def apply(self, edit: GradeEdit) -> None:
        note = {k: v for k, v in edit.note.items() if k != "error"}
        g_.write_notes(edit.assignment_dir, edit.number, {
            **note, "comments": edit.graded.comments, "mistakes": edit.graded.mistakes,
            "reviewed": {"by": edit.by, "at": edit.at, "points": edit.points}})


@dataclass
class GradesCsvTarget:
    """Grades by <name>.csv של מי שעורך: משם הציון עולה למודל. השורה מאושרת (approved), ולכן גוברת על כל
    שורה אחרת של העבודה בכל קבצי הציונים (moodle/grades.py) והבדיקה האוטומטית לא דורסת אותה."""
    name: str = "grades_csv"
    label: str = "קובץ הציונים (Grades by <name>.csv)"

    def enabled(self) -> bool:
        return True

    def apply(self, edit: GradeEdit) -> None:
        # נעילת תהליך ובדיקת סכמה (datastore): שתי עריכות מאותו מחשב לא דורסות זו את זו, וציון לא חוקי לא נכתב
        grades.update_own(edit.assignment_dir, edit.number,
                          {**edit.old, "number": edit.number, "grade": edit.new_grade, "feedback": edit.graded.feedback,
                           "points": ";".join(g_._pts(p) for p in edit.points),
                           "approved": f"{edit.by} {edit.at[:16].replace('T', ' ')}",
                           "graded_at": edit.at, "graded_by": edit.by},
                          max_grade=edit.ctx.max_grade, question_points=[q.points for q in edit.ctx.questions])


# הסדר הוא סדר העדכון. מקום חדש = שורה חדשה כאן
TARGETS: list[Target] = [DatabaseTarget(), MarkedPdfTarget(), NotesTarget(), GradesCsvTarget()]


def connect_database(store: GradeStore | None) -> None:
    """מחבר את מסד הנתונים (או מנתק, עם None). store צריך save_grade(edit: GradeEdit)."""
    for t in TARGETS:
        if isinstance(t, DatabaseTarget):
            t.store = store


# ---------- הפונקציה ----------
def kind_of(old: dict) -> str:
    """edit: לעבודה כבר יש ציון. review: היא מחכה בתור הבדיקה הידנית. first: אין לה ציון (הבדיקה נכשלה)."""
    if not (old.get("grade") or "").strip():
        return "first"
    if (old.get("review") or "").strip() and not grades.is_approved(old):
        return "review"
    return "edit"


def needs_reason(old: dict) -> bool:
    """סיבה חובה כשמשנים ציון שכבר יש (לא באישור ראשון מהתור הידני ולא בציון ראשון)."""
    return kind_of(old) == "edit"


def history_all(assignment_dir: Path) -> list[dict]:
    """כל עריכות הציון של המטלה, מהישנה לחדשה."""
    return [e for e in activity_log.read(assignment_dir) if e.get("action") in (ACTION, ACTION_FAILED)]


def history(assignment_dir: Path, number: str) -> list[dict]:
    """כל העריכות של עבודה, מהישנה לחדשה (גם אלה שלא הגיעו לכל המקומות)."""
    n = g_.number_key(number)
    return [e for e in activity_log.read(assignment_dir, number=n) if e.get("action") in (ACTION, ACTION_FAILED)]


def edit_grade(assignment_dir: Path, number: str, points: list, comments: list, feedback: str, by: str,
               reason: str = "", mistakes: list | None = None, targets: list[Target] | None = None) -> dict:
    """עורכת ציון של עבודה אחת ומעדכנת אותו בכל היעדים (ראו בראש הקובץ). מחזירה {number, grade, from, updated}."""
    n = g_.number_key(number)
    files = g_.submission_files(assignment_dir)
    if n not in files:
        raise g_.GradingError(f"אין הגשה {n} בתיקייה \"{paths.TO_GRADE}\".")
    ctx = g_.load_context(assignment_dir, send_solution=False)
    g_.require_rubric(ctx)
    if not isinstance(points, list) or len(points) != len(ctx.questions):
        raise g_.GradingError(f"צריך ניקוד לכל אחת מ-{len(ctx.questions)} השאלות.")
    pts = [g_._round_half_up(g_._num(p)) for p in points]
    over = [f"{q.label}: {g_._pts(p)} מתוך {g_._pts(q.points)}" for p, q in zip(pts, ctx.questions) if p > q.points]
    if over:  # לא חותכים בשקט: מי שמאשר רואה שהניקוד עובר את המחוון
        raise g_.GradingError(f"הניקוד עובר את המחוון ({'; '.join(over)}). {g_.RUBRIC_RULE}")
    texts = [str(c or "").strip()[:500] for c in (comments if isinstance(comments, list) else [])]
    texts = (texts + [""] * len(pts))[:len(pts)]
    picked = [g_._mistakes(m) for m in mistakes] if isinstance(mistakes, list) and len(mistakes) == len(pts) else None
    names = g_.student_names(assignment_dir).get(n, [])
    why = g_.scrub(" ".join(str(reason or "").split())[:MAX_REASON], names)
    with g_._write_lock:
        old = g_.read_grades(assignment_dir).get(n, {})
        kind = kind_of(old)
        if kind == "edit" and not why:
            raise ReasonRequired(f"לעבודה {n} כבר יש ציון ({old.get('grade')}). כדי לשנות אותו צריך לכתוב סיבה.")
        note = g_.read_notes(assignment_dir, n)
        graded = g_.Graded(pts, texts, g_.compute_grade(pts, ctx), str(feedback or "").strip()[:3000],
                           [g_.Mark(**m) for m in note.get("marks") or []
                            if isinstance(m, dict) and set(m) == {"page", "x0", "y0", "x1", "y1", "text"}],
                           mistakes=picked or note.get("mistakes") or [])
        g_.scrub_graded(graded, names)
        # graded_at עד המיקרו-שנייה: שתי עריכות באותה שנייה (שני אנשים, או אחד שתיקן מיד) - האחרונה גוברת במיזוג
        at = datetime.now().isoformat(timespec="microseconds")
        edit = GradeEdit(assignment_dir, n, ctx, graded, files[n], old, note, by, at, why, kind)
        base = {"number": n, "from": edit.old_grade, "to": edit.new_grade, "points_from": old.get("points") or None,
                "points_to": ";".join(g_._pts(p) for p in pts), "reason": why, "kind": kind}
        updated: list[str] = []
        for t in (TARGETS if targets is None else targets):
            if not t.enabled():
                continue
            try:
                t.apply(edit)
            except Exception as e:
                activity_log.record(assignment_dir, ACTION_FAILED, by, **base, updated=updated, failed=t.name,
                                    error=str(e)[:500])
                done = ", ".join(_label(x, targets) for x in updated) or "בשום מקום"
                raise EditIncomplete(f"הציון של עבודה {n} לא עודכן ב{t.label}: {e}. עודכן: {done}. "
                                     "אפשר לשמור שוב.", updated, t.name) from e
            updated.append(t.name)
        activity_log.record(assignment_dir, ACTION, by, **base, updated=updated)
    g_._update_stats(assignment_dir)  # מסד הנתונים הסטטיסטי (stats/): נגזר מקובצי הציונים, מתעדכן אחרי כל עריכה
    return {"number": n, "grade": graded.grade, "from": edit.old_grade, "updated": updated}


def _label(name: str, targets: list[Target] | None) -> str:
    return next((t.label for t in (TARGETS if targets is None else targets) if t.name == name), name)
