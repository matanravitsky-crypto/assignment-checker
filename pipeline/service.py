"""הפעולות של המערכת, במקום אחד. גם שורת הפקודה וגם האתר (דרך השרת המקומי) משתמשים בהן.

ארגון התיקייה ב-OneDrive קורה לבד:
  * בהפעלה הראשונה נוצרים "הגדרות.json", "איך זה עובד.txt" ותיקייה לכל קורס ומטלה שבהגדרות.
  * אם יש טוקן של מודל ומזהה קורס, המערכת מביאה ממודל את רשימת המטלות ויוצרת תיקייה לכל אחת.
  * קובץ ZIP שמונח בתיקיית הקליטה הראשית (YallaLinearit/0-קליטה) מנותב לבד למטלה הנכונה
    לפי השם שמודל נותן לו: "<קורס>-<מטלה>-<מספר>.zip".
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pymupdf

from . import config, settings as cfg
from .gradebook import GradeBook
from .moodle_api import Moodle, MoodleError
from .pull import PullResult, import_submissions, pull_zip
from .workspace import Workspace, safe_name

README_NAME = "איך זה עובד.txt"
README_TEXT = """בודק העבודות: תיקיית העבודה של הקורס
=====================================

את התיקייה הזו מנהלת מערכת "בודק העבודות". כל קורס מקבל תיקייה, ובתוכו תיקייה לכל מטלה:

  <קורס>/<מטלה>/
    0-קליטה/      קובצי ZIP שהורדו ממודל מחכים כאן. אחרי הקליטה הם עוברים ל-"נקלטו".
    1-הגשות/      תיקייה לכל סטודנט, עם הקבצים המקוריים שהגיש.
    2-נבדקו/      העבודות אחרי הבדיקה, עם סימונים והערות.
    3-הוחזרו/     מה שכבר הועלה חזרה למודל.
    ציונים.xlsx   שורה לכל סטודנט: מצב, ניקוד לכל שאלה, ציון, משוב ואישור.
    יומן.txt      כל פעולה שהמערכת עשתה, עם תאריך ושעה.

איך מכניסים הגשות:
  * אוטומטית: לוחצים "משוך הגשות" באתר. אם הוגדר טוקן של מודל, ההגשות נמשכות ישר ממודל.
  * ידנית: במודל, במטלה, "הצגת כל ההגשות" ← "הורדת כל ההגשות". שמים את קובץ ה-ZIP
    בתיקייה 0-קליטה (הראשית, או של המטלה) ולוחצים "משוך הגשות".

בטבלת הציונים:
  * מותר לערוך את העמודות ש1, ש2..., ציון, משוב ומאושר. המערכת לא דורסת אותן.
  * עדיף לא לערוך את הקובץ בזמן שמושכים הגשות.

הגדרות.json: קורסים, מטלות ומזהים במודל. אין בו סיסמאות, ואסור להוסיף לו.
"""

_ZIP_NAME = re.compile(r"^(?P<course>.+?)-(?P<assign>.+)-(?P<cmid>\d+)$")


@dataclass
class PullReport:
    course: str
    assignment: str
    result: PullResult = field(default_factory=PullResult)
    source: list[str] = field(default_factory=list)   # מאיפה הגיעו ההגשות
    notes: list[str] = field(default_factory=list)    # הסברים למשתמש
    routed: list[dict] = field(default_factory=list)  # ZIP שנקלטו למטלות אחרות
    pulled_at: str = ""


# ---------- תיקייה והגדרות ----------
def root_info() -> tuple[Path | None, str | None]:
    try:
        return config.find_root(), None
    except config.FolderNotFound as e:
        return None, str(e)


def init(root: Path) -> cfg.Settings:
    """מכין את התיקייה: קובץ הגדרות, קובץ הסבר, ותיקייה לכל קורס ומטלה."""
    s = cfg.load(root)
    if not (root / cfg.SETTINGS_FILE).exists():
        cfg.save(root, s)
    readme = root / README_NAME
    if not readme.exists():
        readme.write_text(README_TEXT, encoding="utf-8")
    (root / config.INBOX).mkdir(exist_ok=True)
    for c in s.courses:
        for a in c.assignments:
            Workspace(root, c.name, a.name).ensure()
    return s


# ---------- מודל ----------
def moodle_client(s: cfg.Settings) -> Moodle | None:
    token = cfg.moodle_token()
    return Moodle(s.moodle_url, token) if token else None


def sync_assignments(root: Path, s: cfg.Settings, m: Moodle) -> list[str]:
    """מביא ממודל את המטלות של כל קורס שיש לו מזהה, ויוצר תיקייה לכל מטלה חדשה."""
    added = []
    for c in s.courses:
        if not c.moodle_course_id:
            continue
        for ma in m.assignments(c.moodle_course_id):
            a = next((x for x in c.assignments if x.moodle_assign_id == ma["id"]), None) or c.assignment(ma["name"])
            if not a:
                a = cfg.AssignmentCfg(name=ma["name"])
                c.assignments.append(a)
                added.append(f"{c.name} / {a.name}")
            a.moodle_assign_id = ma["id"]
            a.moodle_cmid = ma.get("cmid")
            if ma.get("duedate"):
                a.due = datetime.fromtimestamp(ma["duedate"]).isoformat(timespec="minutes")
            Workspace(root, c.name, a.name).ensure()
    cfg.save(root, s)
    return added


# ---------- ניתוב ZIP מהקליטה הראשית ----------
def route_root_inbox(root: Path, s: cfg.Settings) -> list[tuple[str, str, Path]]:
    """מעביר כל ZIP מהקליטה הראשית לתיקיית הקליטה של המטלה שלו. מחזיר (קורס, מטלה, נתיב) לכל אחד."""
    inbox = root / config.INBOX
    if not inbox.is_dir():
        return []
    routed = []
    for z in sorted(inbox.glob("*.zip")):
        course, assign = _match_zip(s, z.stem)
        ws = Workspace(root, course.name, assign.name)
        ws.ensure()
        target = ws.inbox / z.name
        shutil.move(str(z), str(target))
        routed.append((course.name, assign.name, target))
    cfg.save(root, s)
    return routed


def _match_zip(s: cfg.Settings, stem: str) -> tuple[cfg.CourseCfg, cfg.AssignmentCfg]:
    m = _ZIP_NAME.match(stem)
    if m:
        cmid = int(m.group("cmid"))
        for c in s.courses:
            for a in c.assignments:
                if a.moodle_cmid == cmid:
                    return c, a
        course = next((c for c in s.courses if c.moodle_shortname == m.group("course") or c.name == m.group("course")), None)
        course = course or (s.courses[0] if s.courses else s.ensure_course("קורס כללי"))
        assign = course.assignment(m.group("assign").strip())
        if not assign:
            assign = cfg.AssignmentCfg(name=safe_name(m.group("assign").strip()), moodle_cmid=cmid)
            course.assignments.append(assign)
        return course, assign
    course = s.courses[0] if s.courses else s.ensure_course("קורס כללי")
    assign = course.assignment("לא מסווג") or cfg.AssignmentCfg(name="לא מסווג")
    if assign not in course.assignments:
        course.assignments.append(assign)
    return course, assign


# ---------- משיכה ----------
def pull(root: Path, course: str, assignment: str) -> PullReport:
    """'משוך הגשות' למטלה אחת: ממודל (אם יש טוקן), ומכל ZIP שמחכה בקליטה."""
    s = init(root)
    rep = PullReport(course=course, assignment=assignment)
    c = s.ensure_course(course)
    a = c.assignment(assignment)
    if not a:
        a = cfg.AssignmentCfg(name=assignment)
        c.assignments.append(a)
        cfg.save(root, s)
    ws = Workspace(root, c.name, a.name)
    ws.ensure()

    m = moodle_client(s)
    if m and c.moodle_course_id:
        try:
            sync_assignments(root, s, m)
            a = s.course(course).assignment(assignment) or a
            if a.moodle_assign_id:
                subs = m.submissions(a.moodle_assign_id)
                r = import_submissions(ws, subs, a.due_dt, a.questions)
                _add(rep.result, r)
                rep.source.append("מודל")
                ws.log(f"נמשך ממודל: {r.summary()}")
            else:
                rep.notes.append("המטלה לא נמצאה במודל. כדאי לבדוק את שם המטלה או את מזהה הקורס בהגדרות.json.")
        except MoodleError as e:
            rep.notes.append(str(e))
            ws.log(f"משיכה ממודל נכשלה: {e}")
    elif not m:
        rep.notes.append("אין טוקן של מודל, ולכן נקלטים רק קובצי ZIP שהורדו ממודל.")
    else:
        rep.notes.append(f"לקורס {c.name} אין מזהה מודל בהגדרות.json, ולכן נקלטים רק קובצי ZIP.")

    # ZIP בקליטה הראשית: מנותב למטלה שלו ונקלט מיד, גם אם זו מטלה אחרת
    for course_name, assign_name, path in route_root_inbox(root, s):
        if (course_name, assign_name) == (c.name, a.name):
            continue  # ייקלט למטה, יחד עם הקליטה של המטלה הזו
        other = cfg.load(root).course(course_name).assignment(assign_name)
        r = pull_zip(Workspace(root, course_name, assign_name), path, other.due_dt, other.questions, move=True)
        rep.notes.append(f"{path.name} נקלט ל-{course_name} / {assign_name}: {r.summary()}")
        rep.routed.append({"course": course_name, "assignment": assign_name, "total": r.total})

    s = cfg.load(root)
    a = s.course(course).assignment(assignment) or a
    for z in sorted(ws.inbox.glob("*.zip")):
        r = pull_zip(ws, z, a.due_dt, a.questions, move=True)
        _add(rep.result, r)
        rep.source.append(z.name)

    if not rep.source and not rep.routed:
        rep.notes.append(f"לא נמצאו הגשות חדשות. אפשר להוריד ZIP ממודל ולשים אותו בתיקייה {config.INBOX}.")
        ws.log("משיכה: לא נמצאו הגשות חדשות")
    rep.pulled_at = datetime.now().isoformat(timespec="seconds")
    s = cfg.load(root)
    s.course(course).assignment(assignment).last_pulled = rep.pulled_at
    for r in rep.routed:  # גם מטלות שקיבלו ZIP מהקליטה הראשית נחשבות כנמשכו עכשיו
        s.course(r["course"]).assignment(r["assignment"]).last_pulled = rep.pulled_at
    cfg.save(root, s)
    return rep


def _add(total: PullResult, r: PullResult) -> None:
    for k in ("total", "new", "updated", "same"):
        setattr(total, k, getattr(total, k) + getattr(r, k))
    total.problems += r.problems
    total.zips += r.zips


# ---------- מצב לאתר ----------
def state(root: Path) -> dict:
    """כל הקורסים, המטלות וההגשות, כפי שהם בתיקייה. זה מה שהאתר מציג."""
    s = init(root)
    courses, assignments = [], []
    for ci, c in enumerate(s.courses):
        courses.append({"id": f"c{ci}", "name": c.name})
        for ai, a in enumerate(c.assignments):
            ws = Workspace(root, c.name, a.name)
            subs = []
            if ws.grades_path.exists():
                book = GradeBook(ws.grades_path, a.questions)
                for mid, r in book.rows().items():
                    row = {name: book.ws.cell(row=r, column=i + 1).value for i, name in enumerate(book.cols)}
                    subs.append(_sub_for_site(ws, a, mid, row))
            assignments.append({
                "id": f"c{ci}a{ai}", "courseId": f"c{ci}", "course": c.name, "title": a.name,
                "n": ai + 1, "due": a.due, "questions": a.questions,
                "pulledAt": a.last_pulled,
                "moodle": bool(a.moodle_assign_id), "folder": str(ws.dir), "subs": subs,
                "log": _read_log(ws),
            })
    return {"root": str(root), "courses": courses, "assignments": assignments,
            "moodle": bool(cfg.moodle_token()), "claude": bool(cfg.claude_key())}


def _read_log(ws: Workspace, limit: int = 40) -> list[dict]:
    """השורות האחרונות ביומן של המטלה, לתצוגה ב"פעילות אחרונה" באתר."""
    path = ws.dir / config.LOG_FILE
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        stamp, _, text = line.partition("  ")
        try:
            at = datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M").isoformat()
        except ValueError:
            continue
        text = text.strip()
        kind = "error" if ("נכשל" in text or "דורשת טיפול" in text) else "pull"
        out.append({"at": at, "kind": kind, "text": text})
    return out


_STATUS = {"ממתינה לבדיקה": "pulled", "נבדקה": "graded", "הוחזרה": "returned", "דורשת טיפול": "error"}


def _sub_for_site(ws: Workspace, a: cfg.AssignmentCfg, mid: str, row: dict) -> dict:
    folder = next(ws.submissions.glob(f"* ({mid})"), None)
    files = []
    if folder:
        for p in sorted(folder.iterdir()):
            if p.is_file():
                pages = 1
                if p.suffix.lower() == ".pdf":
                    try:
                        with pymupdf.open(p) as d:
                            pages = d.page_count
                    except Exception:
                        pages = 0
                files.append({"name": p.name, "pages": pages, "path": p.relative_to(ws.root).as_posix()})
    q = [row.get(f"ש{i}") for i in range(1, a.questions + 1)]
    score = row.get("ציון")
    when = row.get("הוגשה") or ""
    try:
        submitted = datetime.strptime(when, "%Y-%m-%d %H:%M").isoformat()
    except (TypeError, ValueError):
        submitted = None
    notes = row.get("הערות מערכת") or ""
    return {
        "id": f"{mid}", "name": row.get("שם מלא") or "", "studentId": str(row.get("ת״ז") or mid),
        "email": row.get("מייל") or "", "submittedAt": submitted, "late": "באיחור" in notes,
        "scanned": any(f["name"].lower().endswith((".jpg", ".jpeg", ".png", ".heic")) for f in files),
        "files": files, "status": _STATUS.get(row.get("מצב"), "pulled"),
        "q": q if all(isinstance(x, (int, float)) for x in q) else None,
        "score": score if isinstance(score, (int, float)) else None,
        "issue": notes if row.get("מצב") == "דורשת טיפול" else None,
        "feedback": row.get("משוב"), "approved": row.get("מאושר") == "כן",
    }
