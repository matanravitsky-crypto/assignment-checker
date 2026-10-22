"""מה שהאתר המחובר עושה, במקום אחד. השלבים עצמם הם הקוד של אורי ב-`moodle/`:

  משיכה  → moodle.ingest.ingest(<מזהה מטלה>)
           לוקח את ה-ZIP החדש ביותר מתיקיית ההורדות (Downloads) שנגמר ב-"-<מזהה>.zip",
           שומר אותו בתיקיית המטלה, מחלץ עם 7-Zip, ממספר ומעדכן את טבלת המפתח.
  החזרה  → moodle.upload.prepare_upload(<תיקיית המטלה>)
           בונה ב-"3 - Ready to upload to Moodle" את גיליון הציונים, את קובצי המשוב ואת
           הוראות ההעלאה. מישהו מהצוות מעלה אותם למודל ומאשר.

כאן רק מחברים את הקוד הזה לאתר, ומכינים לאתר את המצב של כל מטלה, בלי שמות.
"""
from __future__ import annotations

import csv
import getpass
import os
import re
import socket
from datetime import datetime, timedelta
from pathlib import Path

from moodle import ingest as moodle_ingest, paths, upload as moodle_upload

from . import config, settings as cfg, team


def root_info() -> tuple[Path | None, str | None]:
    try:
        return config.find_root(), None
    except config.FolderNotFound as e:
        return None, str(e)


def find_assignment(root: Path, course: str, assignment: str) -> team.Assignment:
    a = team.Assignment(root / course / assignment)
    if not a.dir.is_dir() or a.dir.resolve().parent.parent != root.resolve():
        raise FileNotFoundError(f"המטלה {course} / {assignment} לא נמצאה בתיקייה")
    return a


def _use_root(root: Path) -> None:
    """הקוד של אורי מוצא את התיקייה דרך ASSIGNMENT_DATA."""
    os.environ["ASSIGNMENT_DATA"] = str(root)


def _moodle_id(a: team.Assignment) -> str:
    mid = a.details().get("id")
    if not mid:
        raise ValueError(f"אין מזהה מודל (id) בקובץ {paths.INFO} של המטלה")
    return str(mid)


def _hebrew_error(e: Exception, mid: str) -> str:
    text = str(e)
    if "7-Zip" in text:
        return "7-Zip לא מותקן במחשב הזה. מתקינים פעם אחת: winget install 7zip.7zip, ומנסים שוב."
    if "No ZIP" in text:
        return (f"לא נמצא ZIP של המטלה בתיקיית ההורדות (Downloads). במודל: \"הצגת כל ההגשות\" ← "
                f"\"הורדת כל ההגשות\", ושם הקובץ צריך להיגמר ב-\"-{mid}.zip\".")
    return text


# ---------- כל אחד בצוות יכול למשוך ----------
# טבלת המפתח יושבת בתיקייה המשותפת, ו-ingest קורא אותה לפני שהוא ממספר, כך שכל סטודנט שומר
# על המספר שלו לא משנה מי משך. הסיכון היחיד: שני אנשים מושכים את אותה מטלה באותו זמן, לפני
# ש-OneDrive סנכרן את טבלת המפתח ביניהם. לכן:
#   * נעילה: בזמן משיכה יש בתיקיית המטלה קובץ שאומר מי מושך. אחרים מחכים.
#   * התנגשות: אם OneDrive בכל זאת יצר עותק כפול של טבלת המפתח, לא מושכים עד שמתקנים.
LOCK_FILE = "Pull in progress.txt"
LOCK_MINUTES = 30


def key_conflicts(a: team.Assignment) -> list[str]:
    """עותקים כפולים של טבלת המפתח ש-OneDrive יוצר בהתנגשות (למשל "...-DESKTOP-ABC.csv")."""
    stem = Path(paths.KEY).stem
    return sorted(p.name for p in a.dir.glob(f"{stem}*.csv") if p.name != paths.KEY)


def _me() -> str:
    return f"{getpass.getuser()} ({socket.gethostname()})"


def _take_lock(a: team.Assignment) -> Path:
    lock = a.dir / LOCK_FILE
    if lock.exists():
        started = datetime.fromtimestamp(lock.stat().st_mtime)
        who = lock.read_text(encoding="utf-8").strip() or "מישהו אחר"
        if datetime.now() - started < timedelta(minutes=LOCK_MINUTES) and who != _me():
            raise UserError(f"{who} מושך את המטלה הזו עכשיו (התחיל ב-{started:%H:%M}). "
                            f"כדאי לחכות כמה דקות, לתת ל-OneDrive לסנכרן, ולנסות שוב.")
    lock.write_text(_me(), encoding="utf-8")
    return lock


# ---------- משיכה ----------
def pull(root: Path, course: str, assignment: str) -> dict:
    a = find_assignment(root, course, assignment)
    mid = _moodle_id(a)
    conflicts = key_conflicts(a)
    if conflicts:
        raise UserError(f"ב-OneDrive נוצר עותק כפול של טבלת המפתח ({', '.join(conflicts)}). "
                        "לפני משיכה נוספת צריך לאחד אותו עם הטבלה הראשית ולמחוק את העותק, כדי ששני סטודנטים לא יקבלו אותו מספר.")
    _use_root(root)
    before = {r["number"] for r in a.key_rows()}
    lock = _take_lock(a)
    try:
        rows = moodle_ingest.ingest(mid)
    except (FileNotFoundError, ValueError) as e:
        raise UserError(_hebrew_error(e, mid)) from e
    finally:
        lock.unlink(missing_ok=True)
    numbers = {r["number"] for r in rows}
    new = sorted(numbers - before)
    return {
        "course": course, "assignment": assignment,
        "result": {"total": len(numbers), "new": len(new), "files": len(rows)},
        "summary": f"{len(numbers)} הגשות" + (f", {len(new)} חדשות" if new else ", אין חדשות"),
        "notes": [f"הקבצים נשמרו ב-\"{paths.TO_GRADE}\", וה-ZIP נשמר בתיקיית המטלה."],
        "pulled_at": datetime.now().isoformat(timespec="seconds"),
    }


# ---------- החזרה ----------
def prepare_return(root: Path, course: str, assignment: str) -> dict:
    a = find_assignment(root, course, assignment)
    mid = _moodle_id(a)
    _use_root(root)
    worksheet = moodle_upload.find_worksheet(mid)
    rep = moodle_upload.prepare_upload(a.dir, worksheet)
    notes = []
    if rep["missing_results"]:
        notes.append(f"עוד אין ציון ל-{len(rep['missing_results'])} הגשות (למשל {', '.join(rep['missing_results'][:5])}).")
    if rep["unknown_numbers"]:
        notes.append(f"יש ציונים למספרים שלא בטבלת המפתח: {', '.join(rep['unknown_numbers'][:5])}.")
    if rep["grades_filled"] is None:
        notes.append(f"לא נמצא גיליון ציונים של מודל בהורדות. במודל: \"הורדת גיליון ציונים\" (שם הקובץ נגמר ב-\"-{mid}.csv\").")
    if rep["too_big"]:
        notes.append(f"קבצים גדולים מדי למודל: {', '.join(rep['too_big'][:5])}.")
    notes.append(f"ההוראות להעלאה נמצאות בקובץ \"{moodle_upload.INSTRUCTIONS_FILE}\" בתיקייה \"{paths.UPLOAD}\".")
    return {
        "course": course, "assignment": assignment,
        "summary": f"{rep['results']} ציונים מתוך {rep['submissions']} הגשות, {len(rep['feedback_zips'])} קובצי ZIP של משוב",
        "report": rep, "notes": notes,
    }


class UserError(Exception):
    """שגיאה עם הסבר בעברית למשתמש."""


# ---------- מצב לאתר ----------
_DOWNLOAD = re.compile(re.escape(paths.DOWNLOAD_PREFIX) + r" (\d{4}-\d{2}-\d{2} \d{2}-\d{2})\.zip$")


def _results(a: team.Assignment) -> dict[str, dict]:
    path = a.dir / paths.GRADES
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {r["number"]: r for r in csv.DictReader(fh) if r.get("number")}


def _last_download(a: team.Assignment) -> str | None:
    stamps = [m.group(1) for p in a.dir.glob("*.zip") if (m := _DOWNLOAD.match(p.name))]
    if not stamps:
        return None
    return datetime.strptime(max(stamps), "%Y-%m-%d %H-%M").isoformat(timespec="minutes")


def state(root: Path) -> dict:
    """הקורסים, המטלות וההגשות כפי שהם בתיקייה. בלי שמות של סטודנטים: רק מספרים."""
    courses, out = [], []
    for ci, course_dir in enumerate(team.courses(root)):
        items = team.assignments(course_dir)
        if not items:
            continue
        cid = f"c{ci}"
        courses.append({"id": cid, "name": team.course_title(course_dir), "folder": course_dir.name})
        for ai, a in enumerate(items):
            d = a.details()
            marked, results = a.graded_numbers(), _results(a)
            # הוחזרה = הועלתה למודל בפועל. מי שמעלה רושם כל ZIP ב-Uploaded.txt (ראו CLAUDE.md)
            uploaded = (a.dir / paths.UPLOAD / "Uploaded.txt").exists()
            by_number: dict[str, list[Path]] = {}
            for r in a.key_rows():  # סטודנט יכול להגיש כמה קבצים: 0001.pdf, 0001-2.pdf
                f = a.submissions / r.get("anon_file", "")
                if r.get("number") and f.exists():
                    by_number.setdefault(r["number"], []).append(f)
            subs = []
            for n, files in sorted(by_number.items()):
                res = results.get(n) or {}
                grade = res.get("grade")
                graded = n in marked or bool(grade)
                status = "returned" if graded and uploaded else "graded" if graded else "pulled"
                newest = max(f.stat().st_mtime for f in files)
                subs.append({
                    "id": n, "name": f"הגשה {n}", "studentId": n, "email": "",
                    "submittedAt": datetime.fromtimestamp(newest).isoformat(timespec="minutes"),
                    "late": False, "scanned": False, "status": status, "q": None,
                    "score": float(grade) if grade and grade.replace(".", "", 1).isdigit() else None,
                    "feedback": res.get("feedback") or None, "issue": None,
                    "files": [{"name": f.name, "pages": 0, "size": f.stat().st_size, "path": f.relative_to(root).as_posix()} for f in files],
                })
            pulled = _last_download(a) or (
                datetime.fromtimestamp((a.dir / paths.KEY).stat().st_mtime).isoformat(timespec="minutes")
                if subs and (a.dir / paths.KEY).exists() else None)
            out.append({
                "id": f"{cid}a{ai}", "courseId": cid, "course": team.course_title(course_dir),
                "courseFolder": course_dir.name, "folder": a.dir.name, "title": a.title,
                "n": ai + 1, "due": d.get("due"), "questions": a.question_count(), "questionLabels": a.question_labels(),
                "pulledAt": pulled, "returnedAt": None, "moodleId": d.get("id"),
                "notes": d.get("notes") or "", "rules": d.get("submission_rules") or [],
                "warnings": [f"עותק כפול של טבלת המפתח: {c}" for c in key_conflicts(a)]
                            + ([f"משיכה בתהליך: {(a.dir / LOCK_FILE).read_text(encoding='utf-8').strip()}"] if (a.dir / LOCK_FILE).exists() else []),
                "subs": subs, "log": [],
            })
    return {"root": str(root), "courses": courses, "assignments": out,
            "moodle": False, "claude": bool(cfg.claude_key())}
