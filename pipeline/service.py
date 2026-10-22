"""הפעולות של המערכת, במקום אחד. גם שורת הפקודה וגם האתר (דרך השרת המקומי) משתמשים בהן.

הכל קורה בתוך המבנה של הצוות (ראו team.py):
  * "משוך הגשות" למטלה: אם יש טוקן של מודל, ההגשות נמשכות ישר ממודל. בכל מקרה נקלטים
    גם קובצי ZIP שמחכים בתיקייה "0 - Moodle download" של המטלה, ורק שם.
  * עם טוקן, מטלות חדשות במודל מקבלות תיקייה לבד, באותו מבנה.
  * קבצים שהמערכת לא שמה (למשל ההורדה המקורית של אורי בתיקיית המטלה) לא נקראים ולא זזים.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config, settings as cfg, team
from .moodle_api import Moodle, MoodleError
from .pull import PullResult, import_submissions, pull_zip, waiting_zips


@dataclass
class PullReport:
    course: str
    assignment: str
    result: PullResult = field(default_factory=PullResult)
    source: list[str] = field(default_factory=list)   # מאיפה הגיעו ההגשות
    notes: list[str] = field(default_factory=list)    # הסברים למשתמש
    routed: list[dict] = field(default_factory=list)  # ZIP שנקלטו למטלות אחרות
    pulled_at: str = ""


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


# ---------- מודל ----------
def _moodle() -> Moodle | None:
    token = cfg.moodle_token()
    return Moodle(cfg.moodle_url(), token) if token else None


def sync_course(m: Moodle, course_dir: Path) -> dict[str, int]:
    """מביא ממודל את המטלות של הקורס, פותח תיקייה לכל מטלה חדשה, ומחזיר מזהה-תצוגה → מזהה פנימי."""
    cid = team.course_id(course_dir)
    if not cid:
        return {}
    existing = {str(a.details().get("id")): a for a in team.assignments(course_dir)}
    instances = {}
    for ma in m.assignments(int(cid)):
        a = existing.get(str(ma.get("cmid"))) or existing.get(str(ma["id"]))
        due = datetime.fromtimestamp(ma["duedate"]).astimezone().isoformat() if ma.get("duedate") else None
        if not a:
            a = team.create_assignment(course_dir, ma["name"], {"id": str(ma.get("cmid") or ma["id"]), "course_id": cid,
                                                               "due": due, "title": ma["name"]})
        elif due and a.details().get("due") != due:
            d = a.details()
            d["due"] = due
            a.save_details(d)
        instances[a.dir.name] = ma["id"]
    return instances


# ---------- משיכה ----------
def pull(root: Path, course: str, assignment: str) -> PullReport:
    asg = find_assignment(root, course, assignment)
    rep = PullReport(course=course, assignment=assignment)

    m = _moodle()
    if m:
        try:
            instances = sync_course(m, asg.course_dir)
            iid = instances.get(asg.dir.name)
            if iid:
                r = import_submissions(asg, m.submissions(iid))
                rep.result.add(r)
                rep.source.append("מודל")
                asg.log(f"נמשך ממודל: {r.summary()}")
            elif not team.course_id(asg.course_dir):
                rep.notes.append("אין מזהה קורס במודל (course_id) ב-Assignment details.json, ולכן נקלטים רק קובצי ZIP.")
            else:
                rep.notes.append("המטלה לא נמצאה במודל. כדאי לבדוק את המזהה (id) ב-Assignment details.json.")
        except MoodleError as e:
            rep.notes.append(str(e))
            asg.log(f"משיכה ממודל נכשלה: {e}")
    else:
        rep.notes.append("אין טוקן של מודל, ולכן נקלטים רק קובצי ZIP שהורדו ממודל.")

    for z in waiting_zips(asg):
        rep.result.add(pull_zip(asg, z))
        rep.source.append(z.name)

    if not rep.source and not rep.routed:
        rep.notes.append(f"לא נמצאו הגשות חדשות. מורידים ממודל את ZIP של כל ההגשות ושמים אותו בתיקייה \"{team.INBOX}\" של המטלה.")
        asg.log("משיכה: לא נמצאו הגשות חדשות")
    rep.notes += rep.result.notes
    team.update_course_readme(asg.course_dir)
    rep.pulled_at = datetime.now().isoformat(timespec="seconds")
    return rep


# ---------- מצב לאתר ----------
_STATUS_ORDER = ("returned", "graded", "pulled")


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
            graded, ready = a.graded_numbers(), a.ready_numbers()
            subs = []
            for r in a.key_rows():
                f = a.submissions / r.get("anon_file", "")
                if not f.exists():
                    continue
                n = r["number"]
                status = "returned" if n in ready else "graded" if n in graded else "pulled"
                st = f.stat()
                subs.append({
                    "id": n, "name": f"הגשה {n}", "studentId": n, "email": "",
                    "submittedAt": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"),
                    "late": False, "scanned": False, "status": status, "q": None, "score": None, "issue": None,
                    "files": [{"name": f.name, "pages": 0, "size": st.st_size,
                               "path": f.relative_to(root).as_posix()}],
                })
            log = a.log_lines()
            pulled = next((x["at"] for x in reversed(log) if x["text"].startswith(("נקלט", "נמשך"))), None)
            out.append({
                "id": f"{cid}a{ai}", "courseId": cid, "course": team.course_title(course_dir),
                "courseFolder": course_dir.name, "folder": a.dir.name, "title": a.title,
                "n": ai + 1, "due": d.get("due"), "questions": a.question_count(), "questionLabels": a.question_labels(),
                # מטלה שכבר יש בה הגשות נחשבת כנמשכה, גם אם נמשכה לפני שהמערכת הייתה קיימת
                "pulledAt": pulled or (datetime.fromtimestamp((a.dir / team.KEY).stat().st_mtime).isoformat(timespec="minutes")
                                       if subs and (a.dir / team.KEY).exists() else None),
                "moodleId": d.get("id"), "notes": d.get("notes") or "", "rules": d.get("submission_rules") or [],
                "subs": subs, "log": log,
            })
    return {"root": str(root), "courses": courses, "assignments": out,
            "moodle": bool(cfg.moodle_token()), "claude": bool(cfg.claude_key())}
