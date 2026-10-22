"""הפעולות של המערכת, במקום אחד. גם שורת הפקודה וגם האתר (דרך השרת המקומי) משתמשים בהן.

הכל קורה בתוך המבנה של הצוות (ראו team.py):
  * "משוך הגשות" למטלה: אם יש טוקן של מודל, ההגשות נמשכות ישר ממודל. בכל מקרה נקלטים
    גם קובצי ZIP שמחכים בתיקייה "0 - Moodle download" של המטלה, ורק שם.
  * עם טוקן, מטלות חדשות במודל מקבלות תיקייה לבד, באותו מבנה.
  * קבצים שהמערכת לא שמה (למשל ההורדה המקורית של אורי בתיקיית המטלה) לא נקראים ולא זזים.
  * "בדוק" שולח את ההגשות הממוספרות ל-Claude (ראו grade.py). הבדיקה רצה ברקע, והאתר שואל מה המצב.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import config, grade as grading, settings as cfg, team
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


# ---------- בדיקה ----------
@dataclass
class GradeJob:
    """בדיקה אחת שרצה ברקע. האתר שואל מה המצב עד שהיא נגמרת."""
    course: str = ""
    assignment: str = ""
    numbers: list[str] = field(default_factory=list)
    running: bool = False
    done: dict[str, str] = field(default_factory=dict)  # מספר → graded / failed / skipped
    report: dict | None = None
    summary: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


_job = GradeJob()
_job_lock = threading.Lock()


def grade_status() -> dict:
    with _job_lock:
        return {**asdict(_job), "total": len(_job.numbers)}


def start_grading(root: Path, course: str, assignment: str, numbers: list[str] | None = None,
                  ask: grading.Ask | None = None, wait: bool = False, **opts) -> dict:
    """מתחיל לבדוק ברקע. זורק NoApiKey אם אין מפתח, ו-RuntimeError אם כבר רצה בדיקה."""
    global _job
    asg = find_assignment(root, course, assignment)
    if ask is None:
        ask = grading.claude_ask()
    todo = grading.pending(asg) if numbers is None else [grading.number_key(n) for n in numbers]
    with _job_lock:
        if _job.running:
            raise RuntimeError("בדיקה אחרת כבר רצה. כדאי לחכות שתסתיים.")
        _job = GradeJob(course, assignment, todo, running=bool(todo),
                        started_at=datetime.now().isoformat(timespec="seconds"))
        job = _job
    if not todo:
        job.summary = "אין הגשות שמחכות לבדיקה."
        job.finished_at = job.started_at
        return grade_status()

    def progress(n: str, what: str) -> None:
        with _job_lock:
            job.done[n] = what

    def run() -> None:
        try:
            rep = grading.grade_assignment(asg, todo, ask=ask, on_progress=progress, **opts)
            job.report, job.summary = asdict(rep), rep.summary()
        except grading.NoApiKey as e:
            job.error = str(e)
        except Exception as e:  # השגיאה מוצגת באתר במקום שהבדיקה תיעלם בשקט
            job.error = f"הבדיקה נכשלה: {e}"
            asg.log(job.error)
        finally:
            with _job_lock:
                job.running = False
                job.finished_at = datetime.now().isoformat(timespec="seconds")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    if wait:
        t.join()
    return grade_status()


# ---------- מצב לאתר ----------
_STATUS_ORDER = ("returned", "graded", "pulled")


def _score(raw: str | None) -> float | int | None:
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return None
    return int(x) if x.is_integer() else x


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
            marked, ready, grades = a.marked_files(), a.ready_numbers(), grading.read_grades(a.dir)
            subs = []
            for r in a.key_rows():
                f = a.submissions / r.get("anon_file", "")
                if not f.exists():
                    continue
                n = r["number"]
                row = grades.get(grading.number_key(n))
                status = "returned" if n in ready else "graded" if (n in marked or row) else "pulled"
                st = f.stat()
                files = [{"name": f.name, "pages": 0, "size": st.st_size, "path": f.relative_to(root).as_posix()}]
                files += [{"name": m.name, "pages": 0, "size": m.stat().st_size, "path": m.relative_to(root).as_posix(),
                           "marked": True} for m in marked.get(n, [])]
                subs.append({
                    "id": n, "name": f"הגשה {n}", "studentId": n, "email": "",
                    "submittedAt": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"),
                    "late": False, "scanned": False, "status": status,
                    "q": grading.parse_points(row.get("points")) if row else None,
                    "score": _score(row.get("grade")) if row else None,
                    "feedback": (row.get("feedback") or "") if row else "",
                    "approved": grading.is_approved(row), "review": (row.get("review") or "") if row else "",
                    "issue": None, "files": files,
                })
            log = a.log_lines()
            pulled = next((x["at"] for x in reversed(log) if x["text"].startswith(("נקלט", "נמשך"))), None)
            graded_at = next((x["at"] for x in reversed(log) if x["kind"] == "grade"), None)
            ctx = grading.load_context(a, send_solution=False)
            out.append({
                "id": f"{cid}a{ai}", "courseId": cid, "course": team.course_title(course_dir),
                "courseFolder": course_dir.name, "folder": a.dir.name, "title": a.title,
                "n": ai + 1, "due": d.get("due"), "questions": a.question_count(), "questionLabels": a.question_labels(),
                "rubric": [{"label": q.label, "points": q.points, "criteria": q.criteria} for q in ctx.questions],
                "maxGrade": ctx.max_grade, "solution": (a.dir / grading.SOLUTION).is_file(),
                # מטלה שכבר יש בה הגשות נחשבת כנמשכה, גם אם נמשכה לפני שהמערכת הייתה קיימת
                "pulledAt": pulled or (datetime.fromtimestamp((a.dir / team.KEY).stat().st_mtime).isoformat(timespec="minutes")
                                       if subs and (a.dir / team.KEY).exists() else None),
                "gradedAt": graded_at,
                "moodleId": d.get("id"), "notes": d.get("notes") or "", "rules": d.get("submission_rules") or [],
                "subs": subs, "log": log,
            })
    return {"root": str(root), "courses": courses, "assignments": out,
            "moodle": bool(cfg.moodle_token()), "claude": bool(cfg.claude_key()), "grading": grade_status()}
