"""יומן האירועים של הציונים (הצעה A): ההקרנה, ההשוואה לקבצים, והשחזור.

היומן הוא `activity_log` (קובץ לכל כותב, שורות שרק נוספות, עם `id` דטרמיניסטי ו-`seq` לכל כותב; עותקים מתנגשים
מאוחדים בקריאה). כל שינוי ציון נרשם בו:
  grade_set           הבדיקה האוטומטית כתבה שורת ציון (grading.grade_assignment)
  grade_failed        הבדיקה של עבודה נכשלה (עם הסיבה)
  grade_edit_intent   עריכה או אישור התחילו (DatabaseTarget, לפני שאר היעדים)
  grade_edit          עריכה או אישור הושלמו בכל היעדים (grade_edit.edit_grade)
  grade_edit_failed   עריכה שלא הגיעה לכל היעדים

projection(assignment_dir): לכל מספר, מה היומן אומר שהציון צריך להיות: אישור (grade_edit) גובר על בדיקה (grade_set),
ובתוך אותה מחלקה האירוע המאוחר (`at`), ובשוויון לפי `id`. דטרמיניסטי: אותו יומן = אותה הקרנה בכל מחשב.
compare(assignment_dir): איפה קובצי הציונים לא תואמים ליומן (עדכון שאבד, קובץ שנדרס לפני שהיו נעילות).
replay(assignment_dir, dry_run): כותב את מה שחסר חזרה לקובץ של הכותב המקורי, דרך grades.update_own (נעילה + סכמה).

מספרים בלבד. שורות ישנות בלי אירוע ביומן (מלפני היומן) נשארות כפי שהן: אין אירוע = אין מה להשוות.
"""
from __future__ import annotations

from pathlib import Path

import activity_log
from moodle import grades

SET, FAILED, INTENT, EDIT, EDIT_FAILED = "grade_set", "grade_failed", "grade_edit_intent", "grade_edit", "grade_edit_failed"
GRADE_ACTIONS = (SET, FAILED, INTENT, EDIT, EDIT_FAILED)


def _key(e: dict) -> tuple:
    return (str(e.get("at") or ""), str(e.get("id") or ""))


def events(assignment_dir: Path, number: str | None = None) -> list[dict]:
    """כל אירועי הציונים של המטלה (או של מספר אחד), מהישן לחדש."""
    out = [e for e in activity_log.read(assignment_dir) if e.get("action") in GRADE_ACTIONS]
    if number is not None:
        n = grades.number_key(number)
        out = [e for e in out if grades.number_key(str(e.get("number") or "")) == n]
    return sorted(out, key=_key)


def history(assignment_dir: Path, number: str) -> list[dict]:
    """מי נתן לעבודה איזה ציון ומתי, לפי הסדר: לתצוגה ולערעורים."""
    return events(assignment_dir, number)


def projection(assignment_dir: Path) -> dict[str, dict]:
    """number -> {"grade", "points", "by", "at", "approved", "event"}: מה היומן אומר שהציון צריך להיות."""
    best: dict[str, dict] = {}
    for e in events(assignment_dir):
        if e.get("action") not in (SET, EDIT):
            continue
        n = grades.number_key(str(e.get("number") or ""))
        if not n:
            continue
        approved = e["action"] == EDIT
        grade = e.get("to") if approved else e.get("grade")
        points = e.get("points_to") if approved else e.get("points")
        cand = {"grade": _pts(grade), "points": str(points or ""), "by": str(e.get("by") or ""), "at": str(e.get("at") or ""),
                "approved": approved, "event": e.get("id") or "", "kind": e.get("kind") or ""}
        cur = best.get(n)
        if cur is None or (cand["approved"], cand["at"], cand["event"]) > (cur["approved"], cur["at"], cur["event"]):
            best[n] = cand
    return best


def _pts(x) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x if x is not None else "")
    return str(int(v)) if v.is_integer() else str(v)


def compare(assignment_dir: Path) -> list[dict]:
    """איפה קובצי הציונים לא אומרים מה שהיומן אומר: רק כשהאירוע מאוחר משורת הקובץ (או שאין שורה)."""
    rows = grades.read(assignment_dir)
    out = []
    for n, want in sorted(projection(assignment_dir).items()):
        row = rows.get(n)
        file_grade = _pts(row.get("grade")) if row and (row.get("grade") or "").strip() else ""
        file_at = str(row.get("graded_at") or "") if row else ""
        if file_grade == want["grade"] and bool(row and grades.is_approved(row)) == want["approved"]:
            continue
        if row and file_at and file_at[:19] > want["at"][:19]:
            continue  # the file is newer than the ledger's latest event: a hand edit, not a lost update
        out.append({"number": n, "ledger_grade": want["grade"], "file_grade": file_grade, "by": want["by"], "at": want["at"],
                    "approved": want["approved"]})
    return out


def replay(assignment_dir: Path, dry_run: bool = True, max_grade: float | None = None) -> list[str]:
    """מחזיר לקבצים מה שהיומן אומר ואבד: כותב לקובץ של הכותב המקורי דרך update_own. מחזיר מה נעשה (או היה נעשה)."""
    done = []
    verb = "היה" if dry_run else ""
    for m in compare(assignment_dir):
        done.append(f"{verb} מחזיר לעבודה {m['number']} ציון {m['ledger_grade']} מהיומן (בקובץ: {m['file_grade'] or 'אין'}) לקובץ של {m['by']}")
        if dry_run:
            continue
        want = projection(assignment_dir)[m["number"]]
        row = {"grade": want["grade"], "points": want["points"], "graded_at": want["at"], "graded_by": want["by"],
               "approved": f"{want['by']} {want['at'][:16].replace('T', ' ')} (שוחזר מהיומן)" if want["approved"] else "",
               "review": "", "feedback": ""}
        old = grades.read(assignment_dir).get(m["number"]) or {}
        grades.update_own(assignment_dir, m["number"], {**old, **row}, who=want["by"], max_grade=max_grade)
        activity_log.record(assignment_dir, "grade_replayed", want["by"], number=m["number"], grade=want["grade"], source=want["event"])
    return done


def incomplete_edits(assignment_dir: Path) -> list[dict]:
    """עריכות שהתחילו (intent) ולא נרשמו כגמורות או ככושלות אחריהן: קריסה באמצע עריכה."""
    pending: dict[str, dict] = {}
    for e in events(assignment_dir):
        n = grades.number_key(str(e.get("number") or ""))
        if e.get("action") == INTENT:
            pending[n] = e
        elif e.get("action") in (EDIT, EDIT_FAILED):
            pending.pop(n, None)
    return [{"number": n, "by": e.get("by"), "at": e.get("at")} for n, e in sorted(pending.items())]


class LedgerStore:
    """ה-store של DatabaseTarget ב-grade_edit: רושם ביומן שעריכה התחילה, לפני שאר היעדים."""

    def save_grade(self, edit) -> None:
        activity_log.record(edit.assignment_dir, INTENT, edit.by, number=edit.number, **{"from": edit.old_grade, "to": edit.new_grade},
                            kind=edit.kind)


__all__ = ["events", "history", "projection", "compare", "replay", "incomplete_edits", "LedgerStore", "GRADE_ACTIONS"]
