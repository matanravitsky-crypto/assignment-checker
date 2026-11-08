"""בדיקת שלמות של מטלה ("doctor"), ותיקון של מה שבטוח לתקן לבד.

check(assignment_dir) -> Report: כל הבעיות במטלה, לפי סוג ורמה (schema.REJECT / WARN / INFO), עם קוד, הודעה בעברית ומספר
ההגשה כשיש. אף פעם לא שמות או מזהי משתתף. מה נבדק:
- פרטי המטלה (JSON תקין, סכמה), המפתח (חד-חד-ערכי), כל שורת ציון בכל קובץ ציונים (מול המחוון), כל קובץ הערות.
- כפילות מספר בתוך קובץ ציונים (reject), אותו מספר בכמה קובצי בודקים (info: ממוזג לפי הכללים).
- "בדיקה לא גמורה": PDF מסומן בלי שורת ציון (קריסה באמצע שמירה; לא נספר כבדוק ולא יעלה למודל).
- נעילות: תקועה (יותר מ-LOCK_MINUTES בלי דופק) או של תהליך מת במחשב הזה.
- עותקים מתנגשים של OneDrive ("<שם>-<מחשב>.<סיומת>") בתיקיית המטלה ובתיקיות שלה, לכל סוג קובץ.
- קובץ האצווה להעלאה (JSON תקין).

fix(assignment_dir, dry_run) מטפל רק במה שאפשר לשחזר או שאין בו מידע: נעילה תקועה או מתה, עותק מתנגש של קובץ בודק
(ממוזג לתוך הקובץ הראשי לפי כללי המיזוג, והעותק עובר ל-"Earlier versions/Conflict copies/"), עותק מתנגש של claims (איחוד,
המוקדם מנצח), ושל קובץ סטטיסטיקה (נמחק: נגזר). המפתח, יומן ההעלאה, האצווה וההגשות נשארים לאדם.
"""
from __future__ import annotations

import csv
import json
import os
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from moodle import claims, grades, lock as moodle_lock, paths

from . import atomic
from .schema import INFO, REJECT, WARN, Problem, check_details, check_grade_row, check_key_rows, check_notes, summarize

CONFLICT_DIR = "Conflict copies"          # בתוך Earlier versions/: עותקים מתנגשים שמוזגו
_CONFLICT = re.compile(r"^(?P<base>.+?)-(?P<pc>[A-Za-z0-9][A-Za-z0-9_]{1,30}(?:-[A-Za-z0-9_]{1,30})*)(?P<ext>\.[A-Za-z0-9]{1,8})$")
WATCHED = (paths.TO_GRADE, paths.MARKED, paths.NOTES, paths.CLAIMS, paths.UPLOAD)


@dataclass
class Report:
    course: str
    folder: str
    moodle_id: str | None
    problems: list[Problem] = field(default_factory=list)
    fixable: list[str] = field(default_factory=list)      # קודים שאפשר לתקן לבד
    checked_at: str = ""

    def as_dict(self) -> dict:
        return {"course": self.course, "folder": self.folder, "moodle_id": self.moodle_id, "checked_at": self.checked_at,
                "summary": summarize(self.problems), "fixable": sorted(set(self.fixable)),
                "problems": [p.as_dict() for p in self.problems]}


def conflict_copies(folder: Path) -> list[tuple[Path, Path]]:
    """(עותק, המקור שלו) לכל קובץ "<שם>-<מחשב>.<סיומת>" בתיקייה שה"<שם>.<סיומת>" שלו קיים."""
    out = []
    if not folder.is_dir():
        return out
    names = {p.name for p in folder.iterdir()}
    for p in sorted(folder.iterdir()):
        if not p.is_file():
            continue
        m = _CONFLICT.match(p.name)
        if m and (m.group("base") + m.group("ext")) in names:
            out.append((p, folder / (m.group("base") + m.group("ext"))))
    return out


def _question_points(assignment_dir: Path, details: dict) -> tuple[float | None, list[float] | None]:
    """הציון המרבי והניקוד לכל שאלה, דרך grading (כולל "פדגוגי"); בלי PyMuPDF נופלים חזרה לפרטי המטלה."""
    try:
        from grading import grade as grading
        ctx = grading.load_context(assignment_dir, send_solution=False)
        return float(ctx.max_grade), [float(q.points) for q in ctx.questions] if ctx.questions and not ctx.no_rubric else None
    except Exception:  # noqa: BLE001
        mg = details.get("max_grade")
        try:
            mg = float(mg) if mg is not None else 100.0
        except (TypeError, ValueError):
            mg = 100.0
        rubric = details.get("rubric")
        qs = rubric.get("questions") if isinstance(rubric, dict) else None
        pts = []
        for q in qs or []:
            try:
                pts.append(float(q.get("points")))
            except (TypeError, ValueError, AttributeError):
                return mg, None
        return mg, pts or None


def check(assignment_dir: Path) -> Report:
    a = Path(assignment_dir)
    problems: list[Problem] = []
    fixable: list[str] = []
    details = atomic.read_json(a / paths.INFO, default=None, problems=problems)
    if details is None and not problems:
        problems.append(Problem("details_missing", f"אין {paths.INFO}", REJECT, paths.INFO))
    details = details if isinstance(details, dict) else {}
    problems += check_details(details) if details else []
    rep = Report(a.parent.name, a.name, str(details.get("id")) if details.get("id") is not None else None, problems, fixable,
                 datetime.now().isoformat(timespec="seconds"))
    max_grade, q_points = _question_points(a, details)

    # המפתח
    key = a / paths.KEY
    if key.is_file():
        try:
            with key.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
                problems += check_key_rows(list(csv.DictReader(fh)))
        except OSError as e:
            problems.append(Problem("key_unreadable", f"המפתח לא נקרא ({e.strerror or e})", REJECT, paths.KEY))

    # ציונים: כל קובץ, כל שורה; כפילות בתוך קובץ; אותו מספר בכמה קבצים
    seen_in: dict[str, list[str]] = {}
    for f in grades.files(a):
        try:
            with f.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
                rows = [r for r in csv.DictReader(fh) if (r.get("number") or "").strip()]
        except OSError as e:
            problems.append(Problem("grades_unreadable", f"{f.name} לא נקרא ({e.strerror or e})", REJECT, f.name))
            continue
        counts: dict[str, int] = {}
        for r in rows:
            n = grades.number_key(r["number"])
            counts[n] = counts.get(n, 0) + 1
            problems += check_grade_row(r, max_grade=max_grade, question_points=q_points, where=f.name)
            seen_in.setdefault(n, []).append(f.name)
        for n, c in sorted(counts.items()):
            if c > 1:
                problems.append(Problem("duplicate_in_file", f"עבודה {n}: {c} שורות באותו קובץ ({f.name}); האחרונה נקראת", REJECT, f.name, n))
    for n, where in sorted(seen_in.items()):
        if len(set(where)) > 1:
            problems.append(Problem("graded_in_several_files", f"עבודה {n}: ציון ב-{len(set(where))} קבצים; המאושר או האחרון גובר", INFO, ", ".join(sorted(set(where))), n))

    # הערות
    notes_dir = a / paths.NOTES
    if notes_dir.is_dir():
        for p in sorted(notes_dir.glob("*.json")):
            if not p.stem.isdigit():
                continue
            note = atomic.read_json(p, default=None, problems=problems)
            if note is not None:
                problems += check_notes(note, number=p.stem, n_questions=len(q_points) if q_points else None, where=p.name)

    # בדיקה לא גמורה: PDF מסומן בלי שורת ציון
    merged = grades.read(a)
    for n in paths.files_by_number(a / paths.MARKED, "*.pdf"):
        if grades.number_key(n) not in merged:
            problems.append(Problem("marked_without_grade", f"עבודה {n}: יש PDF מסומן אבל אין שורת ציון (בדיקה שנקטעה, או סימון ביד). הציון לא יופיע בגיליון למודל", WARN, paths.MARKED, n))

    # נעילות
    for name in (paths.PULL_LOCK, paths.UPLOAD_LOCK):
        lock = a / name
        if lock.is_file():
            try:
                since = datetime.fromtimestamp(lock.stat().st_mtime)
                who, pid = moodle_lock.parse(lock.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            minutes = (datetime.now() - since).total_seconds() / 60
            if minutes >= moodle_lock.LOCK_MINUTES:
                problems.append(Problem("stale_lock", f"{name}: נעילה של {who} בלי דופק {int(minutes)} דקות (תקועה)", WARN, name))
                fixable.append("stale_lock")
            elif pid is not None and socket.gethostname() in who and not moodle_lock.pid_alive(pid):
                problems.append(Problem("dead_lock", f"{name}: נעילה של תהליך שכבר לא רץ במחשב הזה ({who})", WARN, name))
                fixable.append("dead_lock")

    # עותקים מתנגשים, בכל מקום
    for folder in (a, *(a / sub for sub in WATCHED)):
        for copy, original in conflict_copies(folder):
            kind = _copy_kind(copy, a)
            level = REJECT if kind in ("key", "upload_log", "batch", "submission") else WARN
            problems.append(Problem(f"conflict_copy_{kind}", f"עותק מתנגש של OneDrive: {copy.relative_to(a).as_posix()} (המקור: {original.name})", level,
                                    copy.relative_to(a).as_posix()))
            if kind in ("grades", "claims"):
                fixable.append(f"conflict_copy_{kind}")
    stats_dir = a.parent.parent / paths.STATISTICS / a.parent.name
    for copy, _original in conflict_copies(stats_dir):
        problems.append(Problem("conflict_copy_stats", f"עותק מתנגש של סטטיסטיקה: {copy.name} (נגזר, יימחק)", INFO, copy.name))
        fixable.append("conflict_copy_stats")

    # האצווה להעלאה
    batch = a / paths.UPLOAD / "Upload batch.json"
    if batch.is_file():
        atomic.read_json(batch, default=None, problems=problems)
    return rep


def _copy_kind(copy: Path, a: Path) -> str:
    name, parent = copy.name, copy.parent.name
    if name.startswith(paths.KEY[:-4]):
        return "key"
    if name.startswith("Upload log"):
        return "upload_log"
    if name.startswith("Upload batch"):
        return "batch"
    if name.startswith("Grades"):
        return "grades"
    if parent == paths.CLAIMS:
        return "claims"
    if parent == paths.TO_GRADE or parent == paths.MARKED:
        return "submission"
    if parent == paths.NOTES:
        return "notes"
    return "other"


def fix(assignment_dir: Path, dry_run: bool = True) -> list[str]:
    """מתקן מה שבטוח, ומחזיר מה נעשה (או מה היה נעשה, עם dry_run). ראו בראש הקובץ מה נשאר לאדם."""
    a = Path(assignment_dir)
    done: list[str] = []
    verb = "היה" if dry_run else ""
    keep = a / paths.EARLIER / CONFLICT_DIR

    for name in (paths.PULL_LOCK, paths.UPLOAD_LOCK):
        lock = a / name
        if not lock.is_file():
            continue
        try:
            since = datetime.fromtimestamp(lock.stat().st_mtime)
            who, pid = moodle_lock.parse(lock.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        stale = (datetime.now() - since).total_seconds() / 60 >= moodle_lock.LOCK_MINUTES
        dead = pid is not None and socket.gethostname() in who and not moodle_lock.pid_alive(pid)
        if stale or dead:
            done.append(f"{verb} מסיר נעילה {'תקועה' if stale else 'של תהליך מת'}: {name}")
            if not dry_run:
                lock.unlink(missing_ok=True)

    # קובצי בודקים: מיזוג לפי כללי grades.read (מאושר, ואז האחרון), ואז העותק ל-Earlier versions/Conflict copies
    for copy, original in conflict_copies(a):
        if not copy.name.startswith("Grades"):
            continue
        theirs, ours = grades.read_file(copy), grades.read_file(original)
        added = 0
        for n, row in theirs.items():
            if n not in ours or grades._rank(row) > grades._rank(ours[n]):
                ours[n] = row
                added += 1
        done.append(f"{verb} ממזג {copy.name} לתוך {original.name} ({added} שורות עדכניות יותר) ומעביר את העותק ל-{paths.EARLIER}/{CONFLICT_DIR}")
        if not dry_run:
            with atomic.process_lock(str(original)):
                grades.write_file(original, ours)
            keep.mkdir(parents=True, exist_ok=True)
            os.replace(copy, keep / f"{datetime.now():%Y-%m-%d %H-%M-%S} {copy.name}")

    # claims: איחוד, המוקדם מנצח
    for copy, original in conflict_copies(a / paths.CLAIMS):
        theirs, ours = atomic.read_json(copy, {}), atomic.read_json(original, {})
        if not isinstance(theirs, dict) or not isinstance(ours, dict):
            continue
        merged = dict(ours)
        for n, at in theirs.items():
            if n not in merged or (isinstance(at, str) and isinstance(merged[n], str) and at < merged[n]):
                merged[n] = at
        done.append(f"{verb} מאחד {copy.relative_to(a).as_posix()} לתוך {original.name} ומעביר את העותק")
        if not dry_run:
            atomic.write_json_atomic(original, merged)
            keep.mkdir(parents=True, exist_ok=True)
            os.replace(copy, keep / f"{datetime.now():%Y-%m-%d %H-%M-%S} {copy.name}")

    stats_dir = a.parent.parent / paths.STATISTICS / a.parent.name
    for copy, _ in conflict_copies(stats_dir):
        done.append(f"{verb} מוחק עותק מתנגש של סטטיסטיקה: {copy.name} (יחושב מחדש)")
        if not dry_run:
            copy.unlink(missing_ok=True)
    return done


def check_all(root: Path) -> list[Report]:
    out = []
    for p in sorted(Path(root).glob(f"*/*/{paths.INFO}")):
        if p.parent.parent.name == paths.STATISTICS:
            continue
        out.append(check(p.parent))
    return out


__all__ = ["Report", "check", "check_all", "fix", "conflict_copies", "CONFLICT_DIR"]
