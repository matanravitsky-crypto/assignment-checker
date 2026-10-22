"""מה שהאתר המחובר עושה, במקום אחד. השלבים עצמם הם הקוד של אורי ב-`moodle/`:

  משיכה  → moodle.ingest.ingest(<מזהה מטלה>)
           לוקח את ה-ZIP החדש ביותר מתיקיית ההורדות (Downloads) שנגמר ב-"-<מזהה>.zip",
           שומר אותו בתיקיית המטלה, מחלץ עם 7-Zip, ממספר ומעדכן את טבלת המפתח.
  בדיקה  → grading.grade.grade_assignment (שלב 2): שולח את ההגשות הממוספרות ל-Claude, כותב
           Grades.csv ועבודות מסומנות. רץ ברקע, והאתר שואל מה המצב.
  החזרה  → moodle.upload.prepare_upload(<תיקיית המטלה>)
           בונה ב-"3 - Ready to upload to Moodle" את גיליון הציונים, את קובצי המשוב ואת
           הוראות ההעלאה. מישהו מהצוות מעלה אותם למודל ומאשר.
  העלאה  → moodle.send.prepare_batch / run_batch
           מכינים אצווה של עבודות מסומנות שהן חדשות או השתנו, ואחרי "כן" של אדם מעלים אותה ברקע
           דרך Claude in Chrome (מי שהעלה נרשם ב-Upload log.csv). האתר שואל מה המצב עד שהיא נגמרת.

כאן רק מחברים את הקוד הזה לאתר, ומכינים לאתר את המצב של כל מטלה, בלי שמות.
"""
from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from grading import grade as grading
from moodle import (claude_driver, ingest as moodle_ingest, lock as moodle_lock, paths, send as moodle_send,
                    upload as moodle_upload, upload_log)

from . import folder_view, settings as cfg, shared_folder


def root_info() -> tuple[Path | None, str | None]:
    try:
        return shared_folder.find_root(), None
    except shared_folder.FolderNotFound as e:
        return None, str(e)


def find_assignment(root: Path, course: str, assignment: str) -> folder_view.Assignment:
    a = folder_view.Assignment(root / course / assignment)
    if not a.dir.is_dir() or a.dir.resolve().parent.parent != root.resolve():
        raise FileNotFoundError(f"המטלה {course} / {assignment} לא נמצאה בתיקייה")
    return a


def _use_root(root: Path) -> None:
    """הקוד של אורי מוצא את התיקייה דרך ASSIGNMENT_DATA."""
    os.environ["ASSIGNMENT_DATA"] = str(root)


def _moodle_id(a: folder_view.Assignment) -> str:
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


def key_conflicts(a: folder_view.Assignment) -> list[str]:
    """עותקים כפולים של טבלת המפתח ש-OneDrive יוצר בהתנגשות (למשל "...-DESKTOP-ABC.csv")."""
    stem = Path(paths.KEY).stem
    return sorted(p.name for p in a.dir.glob(f"{stem}*.csv") if p.name != paths.KEY)


def _take_lock(a: folder_view.Assignment) -> Path:
    try:
        return moodle_lock.take(a.dir, LOCK_FILE)
    except moodle_lock.Locked as e:
        raise UserError(f"{e.who} מושך את המטלה הזו עכשיו (התחיל ב-{e.since:%H:%M}). "
                        f"כדאי לחכות כמה דקות, לתת ל-OneDrive לסנכרן, ולנסות שוב.") from e


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
    a = find_assignment(root, course, assignment)
    if ask is None:
        ask = grading.claude_ask()
    todo = grading.pending(a.dir) if numbers is None else [grading.number_key(n) for n in numbers]
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
            rep = grading.grade_assignment(a.dir, todo, ask=ask, on_progress=progress, **opts)
            job.report, job.summary = asdict(rep), rep.summary()
        except grading.NoApiKey as e:
            job.error = str(e)
        except Exception as e:  # השגיאה מוצגת באתר במקום שהבדיקה תיעלם בשקט
            job.error = f"הבדיקה נכשלה: {e}"
        finally:
            with _job_lock:
                job.running = False
                job.finished_at = datetime.now().isoformat(timespec="seconds")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    if wait:
        t.join()
    return grade_status()


# ---------- העלאה למודל ----------
# הכנה (prepare_send) בונה אצווה ורושמת אותה ב-Upload batch.json. ההעלאה עצמה (start_send) רצה ברקע,
# ואחרי "כן" של אדם: האתר שולח את ה-id של האצווה שהאדם ראה, ואם בינתיים הוכנה אצווה אחרת, לא מעלים.
# רק העלאה אחת בכל פעם בתהליך הזה, ובין מחשבים הנעילה Upload in progress.txt (moodle/send.py) שומרת.
SIMULATE_DELAY = 1.0  # שניות לכל ZIP כש-MOODLE_DRIVER=simulate, כדי שיראו התקדמות באתר


def _upload_lock_holder(a: folder_view.Assignment) -> str | None:
    """מי מעלה עכשיו את המטלה (נעילה שלא התיישנה), או None."""
    lock_file = a.dir / moodle_send.UPLOAD_LOCK
    try:
        age = datetime.now() - datetime.fromtimestamp(lock_file.stat().st_mtime)
        if age >= timedelta(minutes=moodle_lock.LOCK_MINUTES):
            return None
        return lock_file.read_text(encoding="utf-8").strip() or moodle_lock.SOMEONE_ELSE
    except OSError:
        return None


@dataclass
class SendJob:
    """העלאה אחת שרצה ברקע. האתר שואל מה המצב עד שהיא נגמרת."""
    course: str = ""
    assignment: str = ""
    batch_id: str = ""
    dry_run: bool = False
    running: bool = False
    total: int = 0
    done: int = 0
    current: str = ""  # ה-ZIP שמועלה עכשיו
    stopped: str | None = None  # None: הכול עלה. אחרת: user / needs_login / mismatch / error / stale / locked
    message: str = ""
    started_at: str = ""
    finished_at: str = ""


_send = SendJob()
_send_lock = threading.Lock()
_stop = threading.Event()


def send_status() -> dict:
    with _send_lock:
        return asdict(_send)


def stop_send() -> dict:
    """מבקש לעצור: ה-ZIP שמועלה עכשיו מסתיים, והבא אחריו לא מתחיל."""
    with _send_lock:
        if _send.running:
            _stop.set()
        return asdict(_send)


def prepare_send(root: Path, course: str, assignment: str) -> dict:
    a = find_assignment(root, course, assignment)
    who = _upload_lock_holder(a)
    with _send_lock:
        if not who and _send.running and (_send.course, _send.assignment) == (course, assignment):
            who = moodle_lock.me()  # ההעלאה שלנו רצה, גם אם קובץ הנעילה עוד לא נכתב
    if who:  # הכנה חדשה באמצע העלאה הייתה הופכת את האצווה שרצה לישנה
        raise UserError(f"{who} מעלה את המטלה הזו עכשיו. אפשר להכין העלאה חדשה כשהיא תסתיים.")
    try:
        summary = moodle_send.prepare_batch(a.dir)
    except FileNotFoundError as e:  # למשל אין טבלת מפתח
        raise UserError(f"חסר קובץ במטלה: {Path(e.filename).name if e.filename else e}") from e
    except ValueError as e:  # כולל BatchBlocked: ההודעה כבר בעברית
        raise UserError(str(e)) from e
    rep = asdict(summary)
    rep["summary"] = (f'מטלה "{summary.title}" (מודל {summary.assignment_id}): '
                      f"{summary.files} קבצים של {summary.students} סטודנטים, ב-{len(summary.zips)} קובצי ZIP.")
    return rep


def _make_driver() -> moodle_send.MoodleDriver:
    if os.environ.get("MOODLE_DRIVER") == "simulate":  # הדגמה: לא נוגעים במודל
        return moodle_send.SimulatedDriver(delay=SIMULATE_DELAY)
    return claude_driver.ClaudeChromeDriver()


class _Tracking:
    """עוטף את הנהג ורושם ב-SendJob איזה ZIP מועלה עכשיו."""

    def __init__(self, inner: moodle_send.MoodleDriver, job: SendJob):
        self.inner, self.job = inner, job

    def upload_zip(self, info: dict, zip_path: Path, expected: int, dry_run: bool) -> moodle_send.UploadResult:
        with _send_lock:
            self.job.current = Path(zip_path).name
        return self.inner.upload_zip(info, zip_path, expected, dry_run)


def start_send(root: Path, course: str, assignment: str, batch_id: str,
               driver: moodle_send.MoodleDriver | None = None, wait: bool = False,
               dry_run: bool = False) -> dict:
    """מתחיל להעלות ברקע את האצווה `batch_id`. זורק RuntimeError אם כבר רצה העלאה,
    ו-ValueError("stale") אם האצווה כבר לא זו שבקובץ Upload batch.json (הוכנה אחרת מאז)."""
    global _send
    a = find_assignment(root, course, assignment)
    base_driver = driver if driver is not None else _make_driver()
    with _send_lock:
        if _send.running:
            raise RuntimeError("העלאה אחרת כבר רצה.")
        batch = moodle_send.current_batch(a.dir, batch_id)
        if batch is None:
            raise ValueError("stale")
        uploaded = upload_log.last_hashes(a.dir)
        already = sum(all(uploaded.get(f["file"]) == f["sha256"] for f in z["files"]) for z in batch["zips"])
        _send = job = SendJob(course, assignment, batch_id, dry_run, running=True, total=len(batch["zips"]),
                              done=already, started_at=datetime.now().isoformat(timespec="seconds"))
        _stop.clear()
    tracked = _Tracking(base_driver, job)

    def progress(index: int, total: int, name: str) -> None:
        with _send_lock:
            job.done = index  # ZIPs שדולגו בהמשך אחרי עצירה נספרים באינדקס

    def run() -> None:
        try:
            rep = moodle_send.run_batch(a.dir, batch_id, tracked, dry_run=dry_run,
                                        should_stop=_stop.is_set, on_progress=progress)
            with _send_lock:
                job.done = len(rep.done_zips)
                job.total = rep.total_zips or job.total
                job.stopped, job.message = rep.stopped, rep.message
        except Exception as e:  # השגיאה מוצגת באתר במקום שההעלאה תיראה כרצה לנצח
            with _send_lock:
                job.stopped, job.message = "error", f"ההעלאה נכשלה: {e}"
        finally:
            with _send_lock:
                job.running, job.current = False, ""
                job.finished_at = datetime.now().isoformat(timespec="seconds")

    t = threading.Thread(target=run, daemon=True)
    try:
        t.start()
    except Exception:  # אם התהליכון לא עלה, ההעלאה לא נשארת "רצה"
        with _send_lock:
            job.running = False
        raise
    if wait:
        t.join()
    return send_status()


# ---------- התחברות למודל ----------
MOODLE_STATUS_SECONDS = 60
_moodle_cache: tuple[float, dict] | None = None


def moodle_status() -> dict:
    """האם Claude Code מחובר במחשב הזה. נשמר דקה: הבדיקה מפעילה תהליך, והאתר שואל לעיתים קרובות."""
    global _moodle_cache
    cached = _moodle_cache
    if cached and time.monotonic() - cached[0] < MOODLE_STATUS_SECONDS:
        return cached[1]
    status = claude_driver.auth_status()
    _moodle_cache = (time.monotonic(), status)
    return status


def check_moodle(root: Path, course: str, assignment: str) -> dict:
    """האם Chrome ומודל מוכנים להעלאה של המטלה הזו (ריצה קצרה של Claude, בלי להעלות כלום)."""
    a = find_assignment(root, course, assignment)
    _moodle_id(a)
    return claude_driver.ClaudeChromeDriver().check(paths.read_info(a.dir))


# ---------- הוחזרו: לפי יומן ההעלאה ----------
# ה-hash של קובץ נשמר לפי (גודל, זמן שינוי): האתר שואל על המצב כל כמה שניות, ואלפי PDF של 1-2MB
# לא נקראים מחדש אם לא השתנו. קובץ ששונה מקבל גודל או זמן אחרים, ולכן נחשב מחדש.
_hashes: dict[str, tuple[int, int, str]] = {}


def cached_hash(path: Path) -> str:
    st = path.stat()
    hit = _hashes.get(str(path))
    if hit and hit[:2] == (st.st_size, st.st_mtime_ns):
        return hit[2]
    digest = upload_log.file_hash(path)
    _hashes[str(path)] = (st.st_size, st.st_mtime_ns, digest)
    return digest


def returned_numbers(assignment_dir: Path, marked: dict[str, list[Path]]) -> set[str]:
    """כמו upload_log.returned_numbers, עם מטמון ל-hash."""
    uploaded = upload_log.last_hashes(assignment_dir)
    return {number for number, files in marked.items()
            if files and all(p.name in uploaded and cached_hash(p) == uploaded[p.name] for p in files)}


# ---------- מצב לאתר ----------
_DOWNLOAD = re.compile(re.escape(paths.DOWNLOAD_PREFIX) + r" (\d{4}-\d{2}-\d{2} \d{2}-\d{2})\.zip$")


def _last_download(a: folder_view.Assignment) -> str | None:
    stamps = [m.group(1) for p in a.dir.glob("*.zip") if (m := _DOWNLOAD.match(p.name))]
    if not stamps:
        return None
    return datetime.strptime(max(stamps), "%Y-%m-%d %H-%M").isoformat(timespec="minutes")


def state(root: Path) -> dict:
    """הקורסים, המטלות וההגשות כפי שהם בתיקייה. בלי שמות של סטודנטים: רק מספרים."""
    courses, out = [], []
    for ci, course_dir in enumerate(folder_view.courses(root)):
        items = folder_view.assignments(course_dir)
        if not items:
            continue
        cid = f"c{ci}"
        courses.append({"id": cid, "name": folder_view.course_title(course_dir), "folder": course_dir.name})
        for ai, a in enumerate(items):
            d = a.details()
            marked, results = grading.marked_files(a.dir), grading.read_grades(a.dir)
            # הוחזרה = הועלתה למודל בפועל: כל הקבצים המסומנים של המספר זהים למה שביומן ההעלאה
            log = upload_log.read_log(a.dir)
            returned = returned_numbers(a.dir, marked)
            by_number: dict[str, list[Path]] = {}
            for r in a.key_rows():  # סטודנט יכול להגיש כמה קבצים: 0001.pdf, 0001-2.pdf
                f = a.submissions / r.get("anon_file", "")
                if r.get("number") and f.exists():
                    by_number.setdefault(r["number"], []).append(f)
            subs = []
            for n, files in sorted(by_number.items()):
                res = results.get(grading.number_key(n)) or {}
                grade = res.get("grade")
                graded = n in marked or bool(grade)
                status = "returned" if graded and n in returned else "graded" if graded else "pulled"
                newest = max(f.stat().st_mtime for f in files)
                subs.append({
                    "id": n, "name": f"הגשה {n}", "studentId": n, "email": "",
                    "submittedAt": datetime.fromtimestamp(newest).isoformat(timespec="minutes"),
                    "late": False, "scanned": False, "status": status, "q": grading.parse_points(res.get("points")),
                    "score": _score(grade), "feedback": res.get("feedback") or None, "issue": None,
                    "approved": grading.is_approved(res), "review": res.get("review") or "",
                    "files": [{"name": f.name, "pages": 0, "size": f.stat().st_size, "path": f.relative_to(root).as_posix()} for f in files]
                             + [{"name": m.name, "pages": 0, "size": m.stat().st_size, "path": m.relative_to(root).as_posix(),
                                 "marked": True} for m in marked.get(n, [])],
                })
            pulled = _last_download(a) or (
                datetime.fromtimestamp((a.dir / paths.KEY).stat().st_mtime).isoformat(timespec="minutes")
                if subs and (a.dir / paths.KEY).exists() else None)
            grades_file = a.dir / grading.GRADES
            ctx = grading.load_context(a.dir, send_solution=False)
            out.append({
                "id": f"{cid}a{ai}", "courseId": cid, "course": folder_view.course_title(course_dir),
                "courseFolder": course_dir.name, "folder": a.dir.name, "title": a.title,
                "n": ai + 1, "due": d.get("due"), "questions": a.question_count(), "questionLabels": a.question_labels(),
                "pulledAt": pulled, "returnedAt": max((r["uploaded_at"] for r in log), default=None), "moodleId": d.get("id"),
                "gradedAt": datetime.fromtimestamp(grades_file.stat().st_mtime).isoformat(timespec="minutes") if grades_file.exists() else None,
                "rubric": [{"label": q.label, "points": q.points, "criteria": q.criteria} for q in ctx.questions],
                "maxGrade": ctx.max_grade, "solution": (a.dir / grading.SOLUTION).is_file(),
                "notes": d.get("notes") or "", "rules": d.get("submission_rules") or [],
                "warnings": [f"עותק כפול של טבלת המפתח: {c}" for c in key_conflicts(a)]
                            + [f"עותק כפול של יומן ההעלאה: {c}" for c in upload_log.log_conflicts(a.dir)]
                            + ([f"משיכה בתהליך: {(a.dir / LOCK_FILE).read_text(encoding='utf-8').strip()}"] if (a.dir / LOCK_FILE).exists() else [])
                            + ([f"העלאה בתהליך: {who}"] if (who := _upload_lock_holder(a)) else []),
                "subs": subs, "log": [],
            })
    return {"root": str(root), "courses": courses, "assignments": out,
            "moodle": False, "claude": bool(cfg.claude_key()), "grading": grade_status(), "sending": send_status()}


def _score(raw: str | None) -> float | int | None:
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return None
    return int(x) if x.is_integer() else x
