"""מה רשומה חוקית, לכל סוג. מחזיר רשימת בעיות (ריקה = תקין); `require` זורק Invalid על בעיה ברמת reject.

רמות:
  reject  כתיבה חדשה כזו נדחית (ציון "abc", מספר לא תקין, ניקוד מעל המחוון). ברשומה ישנה: מדווח ולא עולה למודל.
  warn    חשוד אבל לא שובר (זמן לא בפורמט ISO, סוג בעיה לא מוכר).
  info    ידיעה (אותו מספר בשני קובצי בודקים: ממוזג לפי הכללים).
בהודעות: מספרי הגשה בלבד, אף פעם לא שמות או מזהי משתתף.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

REJECT, WARN, INFO = "reject", "warn", "info"
REVIEW_KINDS = {"", "missing_question", "missing_page", "other_assignment", "unreadable_file",
                "unreadable", "missing", "uncertain", "format", "other"}
NUMBER = re.compile(r"[0-9]{1,6}")  # ASCII digits only: str.isdigit() accepts Arabic-Indic digits too
MAX_FEEDBACK = 5000


@dataclass
class Problem:
    code: str
    message: str
    level: str = WARN
    where: str = ""              # קובץ או מקום
    number: str | None = None    # מספר ההגשה, כשיש

    def as_dict(self) -> dict:
        return asdict(self)


class Invalid(ValueError):
    """רשומה שאסור לכתוב. `problems`: למה."""

    def __init__(self, problems: list[Problem]):
        super().__init__("; ".join(p.message for p in problems if p.level == REJECT) or "רשומה לא חוקית")
        self.problems = problems


def require(problems: list[Problem]) -> None:
    if any(p.level == REJECT for p in problems):
        raise Invalid(problems)


def _num(x) -> float | None:
    try:
        v = float(str(x).strip())
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _iso(s: str) -> bool:
    try:
        datetime.fromisoformat(s)
        return True
    except ValueError:
        return False


def valid_grade(row: dict | None, max_grade: float | None = None) -> float | None:
    """הציון כמספר אם הוא חוקי (מספרי, 0 עד המרבי), אחרת None. למי שמעלה ציונים למודל או סופר אותם."""
    if not row:
        return None
    g = _num(row.get("grade"))
    if g is None or g < 0:
        return None
    if max_grade is not None and g > max_grade:
        return None
    return g


def parse_points(raw) -> list[float] | None:
    s = str(raw or "").strip()
    if not s:
        return None
    vals = [_num(x) for x in s.split(";")]
    return vals if all(v is not None for v in vals) else None  # type: ignore[return-value]


def check_grade_row(row: dict, *, max_grade: float | None = None, question_points: list[float] | None = None,
                    where: str = "") -> list[Problem]:
    """שורת ציון (Grades.csv / Grades by <שם>.csv)."""
    out: list[Problem] = []
    n = str(row.get("number") or "").strip()
    if not NUMBER.fullmatch(n):
        out.append(Problem("bad_number", "מספר הגשה לא תקין", REJECT, where, None))  # never echo the bad value, not even as the number
        return out
    raw = str(row.get("grade") or "").strip()
    if raw:
        g = _num(raw)
        if g is None:
            out.append(Problem("grade_not_numeric", f"עבודה {n}: הציון אינו מספר", REJECT, where, n))
        elif g < 0 or (max_grade is not None and g > max_grade):
            out.append(Problem("grade_out_of_range", f"עבודה {n}: הציון מחוץ לטווח 0 עד {max_grade if max_grade is not None else '∞'}", REJECT, where, n))
    pts_raw = str(row.get("points") or "").strip()
    if pts_raw:
        pts = parse_points(pts_raw)
        if pts is None:
            out.append(Problem("points_not_numeric", f"עבודה {n}: הניקוד לפי שאלה אינו מספרים", REJECT, where, n))
        else:
            if question_points is not None and len(pts) != len(question_points):
                out.append(Problem("points_length", f"עבודה {n}: {len(pts)} ניקודים במקום {len(question_points)} שאלות במחוון", REJECT, where, n))
            elif question_points is not None:
                over = [i + 1 for i, (p, q) in enumerate(zip(pts, question_points)) if p < 0 or (q is not None and p > q + 1e-9)]
                if over:
                    out.append(Problem("points_out_of_rubric", f"עבודה {n}: ניקוד מחוץ למחוון בשאלות {', '.join(map(str, over))}", REJECT, where, n))
            elif any(p < 0 for p in pts):
                out.append(Problem("points_out_of_rubric", f"עבודה {n}: ניקוד שלילי", REJECT, where, n))
    at = str(row.get("graded_at") or "").strip()
    if at and not _iso(at):
        out.append(Problem("bad_time", f"עבודה {n}: graded_at אינו זמן ISO", WARN, where, n))
    if len(str(row.get("feedback") or "")) > MAX_FEEDBACK:
        out.append(Problem("feedback_too_long", f"עבודה {n}: המשוב ארוך מ-{MAX_FEEDBACK} תווים", WARN, where, n))
    return out


def check_notes(note, *, number: str = "", n_questions: int | None = None, where: str = "") -> list[Problem]:
    """Grading notes/NNNN.json."""
    out: list[Problem] = []
    n = number or None
    if not isinstance(note, dict):
        return [Problem("notes_not_object", f"עבודה {number}: קובץ ההערות אינו אובייקט JSON", REJECT, where, n)]
    ms = note.get("mistakes")
    if ms is not None:
        if not isinstance(ms, list) or not all(isinstance(q, list) and all(isinstance(t, str) for t in q) for q in ms):
            out.append(Problem("notes_mistakes_shape", f"עבודה {number}: mistakes צריך להיות רשימה של רשימות טקסט", REJECT, where, n))
        elif n_questions is not None and ms and len(ms) != n_questions:
            out.append(Problem("notes_length", f"עבודה {number}: {len(ms)} שאלות בהערות במקום {n_questions} במחוון", WARN, where, n))
    for key in ("unsure",):
        v = note.get(key)
        if v is not None and (not isinstance(v, list) or not all(isinstance(x, (bool, int)) for x in v)):
            out.append(Problem("notes_unsure_shape", f"עבודה {number}: {key} צריך להיות רשימת כן/לא", WARN, where, n))
    pts = note.get("points")
    if pts is not None and (not isinstance(pts, list) or any(_num(p) is None for p in pts)):
        out.append(Problem("notes_points_shape", f"עבודה {number}: points בהערות אינו רשימת מספרים", WARN, where, n))
    kind = note.get("review_kind")
    if kind is not None and (not isinstance(kind, str) or kind not in REVIEW_KINDS):
        out.append(Problem("notes_review_kind", f"עבודה {number}: סוג בעיה לא מוכר", WARN, where, n))
    marks = note.get("marks")
    if marks is not None and (not isinstance(marks, list) or not all(isinstance(m, dict) for m in marks)):
        out.append(Problem("notes_marks_shape", f"עבודה {number}: marks אינו רשימת סימונים", WARN, where, n))
    return out


def check_details(d, *, where: str = "Assignment details.json") -> list[Problem]:
    """Assignment details.json: המזהה, השמות, הציון המרבי, המחוון והשאלות."""
    if not isinstance(d, dict):
        return [Problem("details_not_object", "פרטי המטלה אינם אובייקט JSON", REJECT, where)]
    out: list[Problem] = []
    mid = d.get("id")
    if mid is not None and not str(mid).strip().isdigit():
        out.append(Problem("details_id", "מזהה המודל אינו מספר", REJECT, where))
    for key in ("course", "name"):
        if key in d and not isinstance(d[key], str):
            out.append(Problem("details_type", f"{key} צריך להיות טקסט", REJECT, where))
    mg = d.get("max_grade")
    if mg is not None:
        v = _num(mg)
        if v is None or not 1 <= v <= 1000:
            out.append(Problem("details_max_grade", "ציון מרבי לא סביר (צריך להיות בין 1 ל-1000)", REJECT, where))
    rubric = d.get("rubric")
    if isinstance(rubric, dict):
        qs = rubric.get("questions")
        if qs is not None and not isinstance(qs, list):
            out.append(Problem("details_rubric", "rubric.questions צריך להיות רשימה", REJECT, where))
        else:
            total = 0.0
            for i, q in enumerate(qs or [], start=1):
                if not isinstance(q, dict):
                    out.append(Problem("details_rubric", f"שאלה {i} במחוון אינה אובייקט", REJECT, where))
                    continue
                p = q.get("points")
                if p is not None:
                    v = _num(p)
                    if v is None or v < 0:
                        out.append(Problem("details_rubric_points", f"שאלה {i} במחוון: ניקוד לא תקין", REJECT, where))
                    else:
                        total += v
                for dd in q.get("deductions") or []:
                    if not isinstance(dd, dict) or not isinstance(dd.get("text"), str):
                        out.append(Problem("details_rubric_deduction", f"שאלה {i} במחוון: הורדה בלי טקסט", WARN, where))
            mg_v = _num(mg) if mg is not None else 100.0
            if total and mg_v and total > mg_v + 1e-9:
                out.append(Problem("details_rubric_sum", f"סכום הניקוד במחוון ({total:g}) גדול מהציון המרבי ({mg_v:g})", WARN, where))
    elif rubric is not None and not isinstance(rubric, str):
        out.append(Problem("details_rubric", "rubric צריך להיות אובייקט או טקסט", REJECT, where))
    qs = d.get("questions")
    if qs is not None and not isinstance(qs, list):
        out.append(Problem("details_questions", "questions צריך להיות רשימה", REJECT, where))
    return out


def check_key_rows(rows: list[dict], *, where: str = "Key - number to student.csv") -> list[Problem]:
    """טבלת המפתח: מספר ↔ משתתף הוא חד-חד-ערכי, הכול ספרות, והתיקייה המקורית נושאת את המשתתף. בהודעות: מספרים בלבד."""
    out: list[Problem] = []
    pids: dict[str, set[str]] = {}
    numbers: dict[str, set[str]] = {}
    for r in rows:
        n, pid = str(r.get("number") or "").strip(), str(r.get("participant_id") or "").strip()
        if not NUMBER.fullmatch(n):
            out.append(Problem("key_bad_number", "שורה במפתח בלי מספר תקין", REJECT, where))
            continue
        if not pid.isascii() or not pid.isdigit():
            out.append(Problem("key_bad_participant", f"עבודה {n}: מזהה המשתתף במפתח אינו מספר", REJECT, where, n))
            continue
        pids.setdefault(n, set()).add(pid)
        numbers.setdefault(pid, set()).add(n)
        folder = str(r.get("original_folder") or "")
        if folder and f"_{pid}_" not in folder and not folder.endswith(f"_{pid}"):
            out.append(Problem("key_folder_mismatch", f"עבודה {n}: התיקייה המקורית במפתח לא נושאת את מזהה המשתתף שלה", REJECT, where, n))
    for n, ps in sorted(pids.items()):
        if len(ps) > 1:
            out.append(Problem("key_number_two_participants", f"עבודה {n}: שני סטודנטים על אותו מספר", REJECT, where, n))
    for pid, ns in numbers.items():
        if len(ns) > 1:
            for n in sorted(ns):
                out.append(Problem("key_participant_two_numbers", f"עבודה {n}: אותו סטודנט גם במספר אחר ({', '.join(sorted(ns - {n}))})", REJECT, where, n))
    return out


def summarize(problems: list[Problem]) -> dict:
    return {"reject": sum(p.level == REJECT for p in problems), "warn": sum(p.level == WARN for p in problems),
            "info": sum(p.level == INFO for p in problems)}


__all__ = ["Problem", "Invalid", "REJECT", "WARN", "INFO", "require", "valid_grade", "parse_points", "check_grade_row",
           "check_notes", "check_details", "check_key_rows", "summarize", "field"]
