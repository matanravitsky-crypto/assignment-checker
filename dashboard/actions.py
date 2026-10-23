"""מה שהאתר המחובר עושה, במקום אחד. השלבים עצמם הם הקוד של אורי ב-`moodle/`:

  משיכה  → claude_driver.ClaudeChromeDriver.download + moodle.ingest.ingest(<מזהה מטלה>)
           אם אין בתיקיית ההורדות (Downloads) ZIP שנגמר ב-"-<מזהה>.zip", Claude בכרום מוריד אותו ממודל
           והמערכת מחכה שיגיע. אחר כך: שומר אותו בתיקיית המטלה, מחלץ עם 7-Zip, ממספר ומעדכן את טבלת המפתח.
  בדיקה  → grading.grade.grade_assignment (שלב 2): שולח את ההגשות הממוספרות ל-Claude (API או Claude Code), כותב
           "Grades by <שם>.csv" ועבודות מסומנות. רץ ברקע, והאתר שואל מה המצב.
  חלוקה  → moodle.claims: כל בודק מסמן אילו עבודות הוא לוקח, וכולם רואים (דרך OneDrive) מי לקח מה.
  החזרה  → moodle.upload.prepare_upload(<תיקיית המטלה>)
           בונה ב-"3 - Ready to upload to Moodle" את גיליון הציונים, את קובצי המשוב ואת
           הוראות ההעלאה. מישהו מהצוות מעלה אותם למודל ומאשר.
  העתקות → copying.check.check_assignment: משווה את ההגשות זו לזו (קובץ זהה, מטא-דאטה, עמודים זהים), בלי Claude.
           רץ ברקע, והתוצאה נכתבת ב-Copying check.json בתיקיית המטלה.
  העלאה  → moodle.send.prepare_batch / run_batch
           מכינים אצווה של עבודות מסומנות שהן חדשות או השתנו, ואחרי "כן" של אדם מעלים אותה ברקע
           דרך Claude in Chrome (מי שהעלה נרשם ב-Upload log.csv). האתר שואל מה המצב עד שהיא נגמרת.

כאן רק מחברים את הקוד הזה לאתר, ומכינים לאתר את המצב של כל מטלה, בלי שמות.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pymupdf

from copying import check as copying
from grading import grade as grading
from moodle import (anonymize as moodle_anonymize, claims, claude_driver, grades as moodle_grades,
                    ingest as moodle_ingest, lock as moodle_lock, paths, send as moodle_send, upload as moodle_upload,
                    upload_log)

from . import folder_view, settings as cfg, shared_folder, usage as grading_usage


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
    if moodle_ingest.NO_FOLDERS in text or "not in a folder per student" in text:  # before "incomplete" and "7-Zip"
        return ("ההגשות הגיעו ממודל בלי תיקייה לכל סטודנט, ולכן לא נקלטו: שום הגשה ושום מספר לא השתנו. "
                "בדף ההגשות במודל מסמנים \"הורדת הגשות המאורגנות לתיקיות לפי סטודנט\" (ליד \"פעולות\") ומושכים שוב.")
    if moodle_anonymize.KEY_EMPTY in text:
        return ("טבלת המפתח של המטלה הזו ריקה או פגומה, אבל כבר יש בה הגשות ממוספרות. משיכה עכשיו הייתה נותנת לכל "
                "סטודנט מספר חדש, וציונים היו מגיעים לסטודנט הלא נכון, ולכן שום דבר לא השתנה. צריך לשחזר את "
                f"\"{paths.KEY}\" (למשל מהגרסאות הקודמות של הקובץ ב-OneDrive) לפני שמושכים.")
    if moodle_ingest.INCOMPLETE in text:  # before "7-Zip": this message names 7-Zip too
        return ("ה-ZIP שהגיע ממודל לא שלם: מודל עצר את ההורדה באמצע. שום הגשה ושום מספר לא השתנו. "
                "לוחצים שוב \"משוך הגשות\" כדי להוריד מחדש.")
    if "7-Zip" in text:
        return "7-Zip לא מותקן במחשב הזה. מתקינים פעם אחת: winget install 7zip.7zip, ומנסים שוב."
    if isinstance(e, paths.TwoFolders):
        return (f"מזהה המודל {mid} שמור בשתי תיקיות מטלה, ולכן לא משכתי: לא ברור לאיזו מהן ההגשות שייכות. "
                f"משאירים את המזהה רק בתיקייה הנכונה (ב-{paths.INFO}) ומושכים שוב. ({text})")
    if isinstance(e, moodle_anonymize.KeyBroken) and "changed during the pull" in text:
        return ("טבלת המפתח השתנתה באמצע המשיכה: כנראה מחשב אחר משך את אותה מטלה, ו-OneDrive הביא את הטבלה שלו. "
                "המשיכה החזירה כל קובץ למקומו ולא שינתה כלום. מחכים ש-OneDrive יסיים לסנכרן ומושכים שוב.")
    if isinstance(e, moodle_anonymize.KeyBroken) and "conflict copies" in text:
        return ("ב-OneDrive יש עותקים כפולים של הגשות, ולכן לא משכתי: לא ברור של מי כל קובץ. "
                f"בודקים אותם מול טבלת המפתח ומוחקים את העותק, ואז מושכים שוב. ({text})")
    if isinstance(e, moodle_anonymize.KeyBroken):
        return ("המשיכה נעצרה לפני ששינתה משהו: טבלת המפתח החדשה הייתה מזיזה או מאבדת סטודנט, או נותנת מספר אחד לשניים. "
                f"שום הגשה ושום מספר לא השתנו. צריך לבדוק את \"{paths.KEY}\" לפני משיכה נוספת. ({text})")
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
LOCK_FILE = paths.PULL_LOCK


def key_conflicts(a: folder_view.Assignment) -> list[str]:
    """עותקים כפולים של טבלת המפתח ש-OneDrive יוצר בהתנגשות (למשל "...-DESKTOP-ABC.csv"). הבדיקה עצמה ב-moodle/anonymize.py."""
    return moodle_anonymize.key_conflicts(a.dir)


def _take_lock(a: folder_view.Assignment) -> Path:
    try:
        return moodle_lock.take(a.dir, LOCK_FILE)
    except moodle_lock.Locked as e:
        raise UserError(f"{e.who} מושך את המטלה הזו עכשיו (התחיל ב-{e.since:%H:%M}). "
                        f"כדאי לחכות כמה דקות, לתת ל-OneDrive לסנכרן, ולנסות שוב.") from e


# ---------- משיכה ----------
def new_assignment(root: Path, course: str, assignment: str, moodle_id: str) -> folder_view.Assignment:
    """הגשה שעוד לא נמשכה (מקום ריק מהעשרה): יוצרים לה תיקייה עם מזהה המודל שלה, ואז מושכים כרגיל.

    הכותרת בעברית נכתבת אחרי המשיכה, מתוך שם ה-ZIP של מודל (כמו ב-ingest)."""
    mid = str(moodle_id).strip()
    if not re.fullmatch(r"\d{4,12}", mid):
        raise UserError("מזהה המטלה במודל הוא מספר: המספר שאחרי id= בכתובת של עמוד המטלה.")
    course_dir = next((c for c in folder_view.courses(root) if c.name == course), None)
    n = folder_view.slot(assignment)
    if course_dir is None or n is None or n >= folder_view.SLOTS or assignment != folder_view.slot_folder(n):
        raise FileNotFoundError(f"המטלה {course} / {assignment} לא נמצאה בתיקייה")
    _use_root(root)
    taken = paths.find_assignment(mid)
    if taken and taken.resolve() != (course_dir / assignment).resolve():
        raise UserError(f"מזהה המודל {mid} כבר שייך למטלה {folder_view.Assignment(taken).title}.")
    other = next((a for a in folder_view.assignments(course_dir) if folder_view.slot(a.dir.name) == n and a.dir.name != assignment), None)
    if other:
        raise UserError(f"ל{folder_view.slot_title(n)} כבר יש תיקייה ({other.dir.name}). כדאי לרענן את הדף.")
    a = folder_view.Assignment(course_dir / assignment)
    old = a.details().get("id")
    if old and str(old) != mid:
        raise UserError(f"ל{a.title} כבר שמור מזהה מודל אחר ({old}).")
    if not old:
        a.dir.mkdir(exist_ok=True)
        _write_info(a, {"id": mid, "course": course, "name": assignment})
    return a


def _write_info(a: folder_view.Assignment, info: dict) -> None:
    (a.dir / paths.INFO).write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _title_from_zip(a: folder_view.Assignment, zip_path: Path, mid: str) -> None:
    """הגשה שנוצרה מכאן עוד בלי כותרת: הכותרת של מודל, מתוך שם ה-ZIP ("הגשה 3 - וקטורים")."""
    info = a.details()
    if info and not info.get("title"):
        info["title"] = moodle_ingest.name_from_zip(zip_path, mid)
        _write_info(a, info)


DUE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _due_from_moodle(a: folder_view.Assignment, listing: dict) -> None:
    """מועד ההגשה כמו שמודל מראה אותו (download_parts.js קורא אותו מעמוד המטלה): נשמר בפרטי המטלה, וממנו המשיכה
    הלילית (dashboard/scheduler.py) יודעת מתי המטלה נסגרת, בלי שמישהו יקליד. מועד שמודל שינה (הארכה) מתעדכן."""
    due = listing.get("due")
    info = a.details()
    if not info or not isinstance(due, str) or not DUE.fullmatch(due):
        return
    if str(info.get("due") or "")[:16] != due[:16]:
        info["due"] = due
        _write_info(a, info)


SINCE_MARGIN_S = 60 * 60  # משיכה חוזרת מבקשת גם את מה שהשתנה בשעה שלפני המשיכה הקודמת: הגשה שנכנסה בזמן שהיא רצה


def _since(a: folder_view.Assignment) -> int:
    """ממתי לבקש ממודל רק את מה שהשתנה (מילישניות מ-1970): המשיכה האחרונה ב-Pull log.csv, פחות שעה.
    0 (את כולם) כשאין משיכה קודמת או שאין עוד אף הגשה ממוספרת."""
    pulled = moodle_ingest.pulls(a.dir)
    if not pulled or not a.key_rows():
        return 0
    try:
        last = datetime.fromisoformat(pulled[-1])
    except ValueError:
        return 0
    return max(0, int((last.timestamp() - SINCE_MARGIN_S) * 1000))


# ---------- כמה התקדמה המשיכה ----------
# הבקשה POST /api/pull נשארת פתוחה עד סוף המשיכה (גם 25 דקות של הורדה). בינתיים האתר שואל GET /api/pull
# ומראה מד התקדמות: phase הוא find (מחפש ZIP בהורדות), claude (Claude מבקש את ה-ZIP ממודל),
# parts (כמה חלקים כבר הגיעו לתיקיית ההורדות, מתוך כמה), download (בבתים),
# check ו-extract (באחוזים), number (בתיקיות של סטודנטים). eta_s: בערך כמה שניות נשארו לשלב הזה, לפי הקצב שלו
# עד עכשיו (None כשעוד לא ידוע). בסוף running=False, עם summary או error
@dataclass
class PullProgress:
    course: str = ""
    assignment: str = ""
    running: bool = False
    phase: str = ""
    done: int = 0
    total: int = 0  # 0 בהורדה: לא ידוע כמה גדול ה-ZIP (אין הורדה קודמת להשוות אליה)
    downloaded: bool = False  # ה-ZIP הורד עכשיו ממודל (ולא חיכה מוכן בתיקיית ההורדות)
    summary: str = ""
    error: str = ""
    started_at: str = ""
    eta_s: int | None = None
    phase_at: float = 0.0  # מתי השלב הזה התחיל (time.time()), ו-phase_done: כמה היה גמור אז. מהם הקצב
    phase_done: int = 0
    moved_at: float = 0.0  # מתי done עלה בפעם האחרונה: מאז הזמן שנשאר יורד, ולא עולה בזמן שמחכים לחלק הבא


_pull = PullProgress()
_pull_lock = threading.Lock()


def pull_status() -> dict:
    with _pull_lock:
        return asdict(_pull)


PART_S = 12  # בערך כמה שניות לוקח חלק אחד של הורדה בחלקים, עד שיש קצב אמיתי (15 חלקים ב-~3 דקות, 2026-10-23)


def _pull_report(phase: str, done: int = 0, total: int = 0) -> None:
    with _pull_lock:
        now = time.time()
        if phase != _pull.phase or done < _pull.phase_done:
            _pull.phase_at, _pull.phase_done, _pull.moved_at = now, done, now
        elif done > _pull.done:
            _pull.moved_at = now
        _pull.phase, _pull.done, _pull.total = phase, done, total
        _pull.downloaded = _pull.downloaded or phase in ("download", "parts")
        _pull.eta_s = _eta(phase, done, total, _pull.moved_at - _pull.phase_at, done - _pull.phase_done,
                           waiting=now - _pull.moved_at)


def _eta(phase: str, done: int, total: int, elapsed: float, measured: int, waiting: float = 0) -> int | None:
    """כמה שניות נשארו לשלב, לפי הקצב שלו מתחילתו ועד ההתקדמות האחרונה, פחות מה שכבר עבר מאז (`waiting`).
    כך הוא יורד בין חלק לחלק, ולא יורד מתחת לזמן של החלקים שעוד לא התחילו. None כשאין ממה לדעת."""
    if total <= 0 or done >= total:
        return 0 if total > 0 else None
    if measured > 0 and elapsed >= 1:
        each = elapsed / measured
    elif phase == "parts":
        each = PART_S
    else:
        return None
    return round(max(each * (total - done) - waiting, each * (total - done - 1)))


def _expected_zip_size(a: folder_view.Assignment) -> int:
    """בערך כמה גדול ה-ZIP: ההורדה הקודמת הכי גדולה של המטלה (אותן הגשות, ועוד מה שהוגש מאז). 0 אם אין."""
    sizes = []
    for folder in (a.dir, _backup_dir(a)):  # kept on this computer; older pulls kept it in the assignment folder
        for p in folder.glob(f"{paths.DOWNLOAD_PREFIX} *") if folder else []:
            if f"({moodle_ingest.INCOMPLETE})" in p.name:  # a cut download is no measure
                continue
            if p.is_file() and p.suffix.lower() == ".zip":
                sizes.append(p.stat().st_size)
            elif p.is_dir():  # a download in parts
                sizes.append(sum(z.stat().st_size for z in p.glob("*.zip")))
    return max(sizes, default=0)


def _backup_dir(a: folder_view.Assignment) -> Path | None:
    try:
        return paths.backup_dir(a.dir)
    except ValueError:  # an assignment outside the data folder (it can't be pulled from here anyway)
        return None


def pull(root: Path, course: str, assignment: str, moodle_id: str | None = None, full: bool = False) -> dict:
    """`full`: ask Moodle for everyone. Otherwise, after a first pull, only for students whose submission changed since
    the last one (minutes instead of GBs); the others keep what they have."""
    global _pull
    with _pull_lock:
        _pull = PullProgress(course, assignment, running=True, phase="find",
                             started_at=datetime.now().isoformat(timespec="seconds"))
        job = _pull
    try:
        rep = _do_pull(root, course, assignment, moodle_id, full)
        job.summary = rep["summary"]
        if rep["result"]["new"]:
            # new submissions: the copying check (no Claude, no tokens) starts by itself, instead of a click on its page
            try:
                start_copying(root, course, assignment)
                rep["notes"].append("בדיקת ההעתקות רצה עכשיו ברקע, והתוצאה תופיע בעמוד \"העתקות\".")
            except (RuntimeError, OSError, UserError):
                pass  # one already runs, or the folder went away: the button on that page still works
        return rep
    except Exception as e:
        job.error = str(e)
        raise
    finally:
        with _pull_lock:
            job.running = False


NOT_SHARED = ("במחשב הזה תיקיית המערכת היא עותק מקומי ({root}), לא התיקייה המשותפת של הקורס ב-OneDrive, ולכן "
              "לא מושכים ממנו. טבלת המפתח של כל מטלה נמצאת בתיקייה המשותפת: משיכה מעותק מקומי לא הייתה רואה את "
              "המספרים שמחשב אחר כבר נתן, ושני סטודנטים היו מקבלים אותו מספר. מושכים ממחשב שהתיקייה YallaLinearit "
              "מסונכרנת בו (OneDrive ← \"הוסף קיצור דרך לקבצים שלי\"), למשל של יוסי.")


def _do_pull(root: Path, course: str, assignment: str, moodle_id: str | None, full: bool = False) -> dict:
    # Pull only into the synced shared folder (moodle/paths.py in_shared_folder); the demo has no Moodle and no OneDrive
    if not paths.in_shared_folder(root) and os.environ.get("MOODLE_DRIVER") != "simulate":
        raise UserError(NOT_SHARED.format(root=root))
    a = new_assignment(root, course, assignment, moodle_id) if moodle_id else find_assignment(root, course, assignment)
    _take_task_if_free(a.dir.parent, assignment, "pull")
    mid = _moodle_id(a)
    conflicts = key_conflicts(a)
    if conflicts:
        raise UserError(f"ב-OneDrive נוצר עותק כפול של טבלת המפתח ({', '.join(conflicts)}). "
                        "לפני משיכה נוספת צריך לאחד אותו עם הטבלה הראשית ולמחוק את העותק, כדי ששני סטודנטים לא יקבלו אותו מספר.")
    copies = moodle_anonymize.submission_conflicts(a.dir)
    if copies:
        raise UserError(f"ב-OneDrive נוצרו עותקים כפולים של הגשות ({', '.join(copies[:5])}): שני מחשבים כתבו את אותו מספר. "
                        "לא מושכים עד שמישהו בודק לאיזה סטודנט שייך כל קובץ (לפי טבלת המפתח) ומוחק את העותק.")
    _use_root(root)
    try:
        moodle_anonymize.check_key(a.dir)  # before downloading anything: a broken key would renumber everyone
        target = paths.find_assignment(mid)  # the ZIP of this id goes to this folder, and only to it
    except ValueError as e:  # paths.TwoFolders is one too
        raise UserError(_hebrew_error(e, mid)) from e
    if target is None or target.resolve() != a.dir.resolve():
        raise UserError(f"מזהה המודל {mid} לא מוביל לתיקייה של {a.title}, ולכן לא משכתי. כדאי לרענן את הדף.")
    old_rows = a.key_rows()
    before = {r["number"] for r in old_rows}
    lock = _take_lock(a)
    try:
        zip_path = _zip_from_moodle(a, mid, 0 if full else _since(a))
        _title_from_zip(a, zip_path, mid)
        listing = _listing(zip_path)
        _due_from_moodle(a, listing)
        without_file = _without_file(zip_path)
        listed = _listed_users(zip_path)
        changed = int(listing.get("changed") or 0) if int(listing.get("since") or 0) > 0 else None
        rows = moodle_ingest.ingest(mid, zip_path, on_progress=_pull_report)
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
        "changed": changed,
        "notes": ([f"ממודל הורדו רק {changed} סטודנטים שההגשה שלהם השתנתה מאז המשיכה הקודמת. כל השאר נשארו כמו שהיו."
                   if changed else "שום הגשה לא השתנתה במודל מאז המשיכה הקודמת, ולכן שום קובץ לא השתנה."]
                  if changed is not None else [])
                 + [f"הקבצים נשמרו ב-\"{paths.TO_GRADE}\". ה-ZIP של מודל נשמר רק במחשב הזה, ב-\"{paths.BACKUP}\"."]
                 + ([f"{without_file} סטודנטים בטבלת ההגשות במודל הגיעו בלי קובץ (לא הגישו קובץ, או שמודל לא שלח אותו)."]
                    if without_file else [])
                 + ([f"בטבלת ההגשות במודל הופיעו רק {listed} סטודנטים, ובטבלת המפתח יש {known}. אף אחד לא נמחק ואף מספר לא השתנה, "
                     "אבל אם בטבלה במודל יש סינון (למשל \"לא נבדקו\" או אות ראשונה של שם), מבטלים אותו ומושכים שוב כדי לא לפספס הגשות."]
                    if listed and listed < (known := len({r["participant_id"] for r in old_rows})) else []),
        "pulled_at": datetime.now().isoformat(timespec="seconds"),
    }


def _listing(download: Path) -> dict:
    """הרשימה של הורדה בחלקים (moodle/download_parts.js), או {} ל-ZIP אחד ולרשימה שאי אפשר לקרוא."""
    if download.suffix.lower() != moodle_ingest.LIST:
        return {}
    try:
        listed = json.loads(download.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return listed if isinstance(listed, dict) else {}


def _without_file(download: Path) -> int:
    """בהורדה בחלקים: כמה סטודנטים ביקשנו ממודל ולא הגיעו באף חלק (לפי הרשימה של moodle/download_parts.js)."""
    if download.suffix.lower() != moodle_ingest.LIST:
        return 0
    try:
        listed = json.loads(download.read_text(encoding="utf-8"))
        asked = sum(int(f.get("asked") or 0) for f in listed.get("files") or [])
        came = sum(int(f.get("students") or 0) for f in listed.get("files") or [])
        return max(0, asked - came) + int(listed.get("empty") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def _listed_users(download: Path) -> int:
    """בהורדה בחלקים: כמה סטודנטים היו בטבלת ההגשות במודל (0 כשלא ידוע)."""
    if download.suffix.lower() != moodle_ingest.LIST:
        return 0
    try:
        return int(json.loads(download.read_text(encoding="utf-8")).get("users") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


DOWNLOAD_POLL_S = 2.0  # כל כמה שניות מסתכלים בתיקיית ההורדות אם ה-ZIP הגיע
DOWNLOAD_WAIT_S = 25 * 60  # הכי הרבה שמחכים להורדה: פחות מ-30 הדקות שאחריהן נעילת המשיכה נחשבת תקועה
# הורדה בחלקים (moodle/download_parts.js): הריצה של Claude נגמרת רק כשכל החלקים הגיעו, ואז נשאר לחכות לרשימה
PARTS_LIST_WAIT_S = 180


def _download_safely(downloader, a: folder_view.Assignment, since: int = 0) -> dict:
    """downloader.download, בלי לזרוק: התשובה חוזרת מה-thread כמו כל תשובה אחרת. `since`: רק מה שהשתנה מאז."""
    try:
        info = paths.read_info(a.dir)
        return downloader.download({**info, "since": since} if since else info)
    except Exception as e:  # noqa: BLE001 — מוצג באתר
        return {"status": "error", "message": f"ההורדה נכשלה ({type(e).__name__})."}


class _SimDownloader:
    """הדגמה (MOODLE_DRIVER=simulate): אין מודל, אז אין ממה להוריד."""

    def download(self, info: dict) -> dict:
        return {"status": "error", "message": "בהדגמה אין מודל. שמים ZIP של המטלה בתיקיית ההורדות ומושכים שוב."}


def _make_downloader():
    return _SimDownloader() if os.environ.get("MOODLE_DRIVER") == "simulate" else claude_driver.ClaudeChromeDriver()


def _zip_from_moodle(a: folder_view.Assignment, mid: str, since: int = 0) -> Path:
    """ה-ZIP של כל ההגשות: מה שכבר מחכה בתיקיית ההורדות (מישהו הוריד ידנית), ואם אין, Claude בכרום מוריד אותו עכשיו.

    ingest מעביר כל ZIP שנקלט מתיקיית ההורדות לתיקיית המטלה, כך ש-ZIP שנשאר שם עוד לא נקלט."""
    global _checking
    try:
        return moodle_ingest.find_download(mid)
    except FileNotFoundError:
        pass
    with _send_lock:  # ההורדה, הבדיקה וההעלאה היו מפעילות את אותו כרום
        if _send.running:
            raise UserError("העלאה למודל רצה עכשיו בכרום. אפשר למשוך כשהיא תסתיים.")
        if _checking:
            raise UserError("בדיקת החיבור למודל רצה עכשיו בכרום. כדאי לנסות שוב בעוד דקה.")
    # One download from Moodle at a time on this computer, for any assignment and from any dashboard on it: two at once
    # in the same Chrome each clicked the folders option on 2026-10-23, and parts came without folders
    try:
        chrome_lock = moodle_lock.take(_work_dir(), CHROME_PULL_LOCK)
    except moodle_lock.Locked as e:
        raise UserError(f"{e.who} מושך עכשיו הגשות ממודל במחשב הזה (התחיל ב-{e.since:%H:%M}). "
                        "משיכה אחת בכל פעם: כדאי לחכות שתסתיים ולנסות שוב.") from e
    try:
        return _download_with_chrome(a, mid, since)
    finally:
        chrome_lock.unlink(missing_ok=True)


CHROME_PULL_LOCK = paths.PULL_LOCK  # בתיקיית העבודה המקומית (ASSIGNMENT_WORK), לא בתיקיית המטלה


def _work_dir() -> Path:
    d = paths.work_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download_with_chrome(a: folder_view.Assignment, mid: str, changed_since: int = 0) -> Path:
    """Claude בכרום מוריד ממודל בחלקים, ומחכים שהכול יגיע לתיקיית ההורדות. `changed_since`: רק מה שהשתנה מאז."""
    global _checking
    with _send_lock:
        _checking = True
    _pull_report("claude")
    # Claude's run lasts until every part is in (it waits for the page's script), so it runs in a thread and
    # the parts that reach Downloads meanwhile move the progress bar
    answer: dict = {}
    downloader = _make_downloader()
    worker = threading.Thread(target=lambda: answer.update(_download_safely(downloader, a, changed_since)), daemon=True)
    try:
        if isinstance(downloader, claude_driver.ClaudeChromeDriver):
            claude_driver.open_chrome()  # closed Chrome (the night pull, nobody at the computer): open it first
        since = time.time()
        worker.start()
        while worker.is_alive():
            worker.join(DOWNLOAD_POLL_S)
            arrived, planned = moodle_ingest.parts_progress(mid, since)
            if arrived:
                _pull_report("parts", arrived, planned)
        result = answer
    finally:
        with _send_lock:
            _checking = False
    if result.get("status") != "started":
        if result.get("message") == claude_driver.NOT_LOGGED_IN:
            _drop_status_cache()
        if "folder" in (result.get("message") or "").lower():
            raise UserError("ההורדה ממודל נעצרה: האפשרות \"הורדת הגשות המאורגנות לתיקיות לפי סטודנט\" כבויה במודל, "
                            "ובלי תיקייה לכל סטודנט אי אפשר לדעת של מי כל קובץ. מסמנים אותה בדף ההגשות (ליד \"פעולות\") "
                            "ומושכים שוב. שום הגשה ושום מספר לא השתנו.")
        raise UserError(f"ההורדה ממודל לא התחילה: {result.get('message') or 'Claude לא פירט למה.'}")
    parts = result.get("parts") or 0
    expected = _expected_zip_size(a)

    def on_size(n: int) -> None:
        # each part reaches Downloads as soon as it is in, and the list of parts comes last. Claude's answer may lack
        # the number of parts (seen on 2026-10-23): then the parts that arrive still show it, out of an unknown total
        arrived, planned = moodle_ingest.parts_progress(mid, since)
        if parts or arrived:
            _pull_report("parts", min(parts, arrived) if parts else arrived, parts or planned)
        elif n:
            _pull_report("download", n, expected)

    # In parts Claude returned once every part was in: only the list of parts is still on its way
    wait_s = PARTS_LIST_WAIT_S if parts else DOWNLOAD_WAIT_S
    try:
        return moodle_ingest.wait_for_download(mid, since, poll_s=DOWNLOAD_POLL_S, total_s=wait_s,
                                               start_s=wait_s if parts else 180, on_size=on_size)
    except TimeoutError as e:
        if parts:
            raise UserError(f"ההורדה בחלקים ({parts} חלקים) הסתיימה בכרום, אבל רשימת החלקים לא הגיעה לתיקיית ההורדות. "
                            "לוחצים שוב \"משוך הגשות\".") from e
        if "did not start" in str(e):
            raise UserError("Claude ביקש ממודל את ה-ZIP, אבל ההורדה לא התחילה בכרום. אם כרום שואל איפה לשמור, "
                            "מכבים בהגדרות שלו את \"שאל איפה לשמור כל קובץ\" ומושכים שוב.") from e
        raise UserError("ההורדה ממודל לא הסתיימה בזמן. כשהיא תסתיים בכרום, לוחצים שוב \"משוך הגשות\": "
                        "ה-ZIP שבתיקיית ההורדות ייקלט בלי להוריד שוב.") from e


# ---------- החזרה ----------
def prepare_return(root: Path, course: str, assignment: str) -> dict:
    a = find_assignment(root, course, assignment)
    mid = _moodle_id(a)
    who = _upload_lock_holder(a)
    with _send_lock:
        if not who and _send.running and (_send.course, _send.assignment) == (course, assignment):
            who = moodle_lock.me()  # ההעלאה שלנו רצה
    if who:  # ההכנה כותבת לתיקיית ההעלאה, וזה לא הזמן לגעת בה
        raise UserError(f"{who} מעלה את המטלה הזו עכשיו. אפשר להכין החזרה כשההעלאה תסתיים.")
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
    stopping: bool = False  # ביקשו לעצור: הגשות שעוד לא נשלחו ל-Claude לא יישלחו


_job = GradeJob()
_job_lock = threading.Lock()
_stop = threading.Event()  # הדגל שהבדיקה שרצה בודקת לפני כל הגשה


def stop_grading() -> dict:
    """עוצר את הבדיקה שרצה: מה שכבר נשלח ל-Claude מסתיים ונשמר, והשאר נשאר "ממתינה לבדיקה"."""
    with _job_lock:
        if _job.running:
            _job.stopping = True
            _stop.set()
    return grade_status()


def grade_status() -> dict:
    with _job_lock:
        return {**asdict(_job), "total": len(_job.numbers)}


def start_grading(root: Path, course: str, assignment: str, numbers: list[str] | None = None,
                  ask: grading.Ask | None = None, wait: bool = False, **opts) -> dict:
    """מתחיל לבדוק ברקע. זורק NoRubric אם למטלה אין מחוון, NoApiKey אם אין מפתח, ו-RuntimeError אם כבר רצה בדיקה."""
    global _job
    a = find_assignment(root, course, assignment)
    grading.require_rubric(grading.load_context(a.dir, send_solution=False))
    if ask is None:
        ask = grading.claude_ask()
    todo = grading.pending(a.dir) if numbers is None else [grading.number_key(n) for n in numbers]
    with _job_lock:
        if _job.running:
            raise RuntimeError("בדיקה אחרת כבר רצה. כדאי לחכות שתסתיים.")
        _job = GradeJob(course, assignment, todo, running=bool(todo),
                        started_at=datetime.now().isoformat(timespec="seconds"))
        job = _job
        _stop.clear()
    if not todo:
        job.summary = "אין הגשות שמחכות לבדיקה."
        job.finished_at = job.started_at
        return grade_status()

    def progress(n: str, what: str) -> None:
        with _job_lock:
            job.done[n] = what

    def run() -> None:
        try:
            rep = grading.grade_assignment(a.dir, todo, ask=ask, on_progress=progress, stop=_stop, **opts)
            job.report, job.summary = asdict(rep), rep.summary()
        except (grading.NoApiKey, grading.ClaudeLimit) as e:
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


# ---------- העתקות ----------
# בדיקת העתקות אחת בכל פעם בתהליך הזה. היא כותבת רק את Copying check.json, אז שתי בדיקות בשני מחשבים
# לכל היותר דורסות זו את התוצאה של זו, באותו תוכן
@dataclass
class CopyJob:
    course: str = ""
    assignment: str = ""
    running: bool = False
    done: int = 0
    total: int = 0
    summary: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


_copy = CopyJob()
_copy_lock = threading.Lock()


def copying_status() -> dict:
    with _copy_lock:
        return asdict(_copy)


def start_copying(root: Path, course: str, assignment: str, wait: bool = False) -> dict:
    """מתחיל בדיקת העתקות ברקע. RuntimeError אם כבר רצה אחת."""
    global _copy
    a = find_assignment(root, course, assignment)
    with _copy_lock:
        if _copy.running:
            raise RuntimeError("בדיקת העתקות כבר רצה. כדאי לחכות שתסתיים.")
        _copy = CopyJob(course, assignment, running=True, started_at=datetime.now().isoformat(timespec="seconds"))
        job = _copy

    def progress(done: int, total: int) -> None:
        with _copy_lock:
            job.done, job.total = done, total

    def run() -> None:
        try:
            job.summary = copying.check_assignment(a.dir, on_progress=progress).summary()
        except Exception as e:  # השגיאה מוצגת באתר במקום שהבדיקה תיעלם בשקט
            job.error = f"בדיקת ההעתקות נכשלה: {e}"
        finally:
            with _copy_lock:
                job.running = False
                job.finished_at = datetime.now().isoformat(timespec="seconds")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    if wait:
        t.join()
    return copying_status()


_copy_reports: dict[str, tuple[int, int, dict]] = {}


def copying_state(assignment_dir: Path) -> dict | None:
    """מה שהאתר מציג בדף "העתקות": הזוגות החשודים (מספרים בלבד), מתי נבדק, והאם הגיעו קבצים מאז."""
    path = copying.report_path(assignment_dir)
    try:
        st = path.stat()
    except OSError:
        return None
    hit = _copy_reports.get(str(path))
    if not hit or hit[:2] != (st.st_size, st.st_mtime_ns):
        hit = (st.st_size, st.st_mtime_ns, copying.read_report(assignment_dir))
        _copy_reports[str(path)] = hit
    rep = hit[2]
    return {"checkedAt": rep.get("checked_at"), "by": rep.get("by") or "", "summary": rep.get("summary") or "",
            "checked": rep.get("checked") or 0, "repeated": rep.get("repeated") or [],
            "pairs": rep.get("pairs") or [], "stale": copying.is_stale(assignment_dir, rep)}


# ---------- חלוקת העבודות בצוות ----------
# כל בודק כותב רק לקובץ שלו ב-"Who grades what" (moodle/claims.py). הנעילה רק מונעת משתי לשוניות באותו מחשב
# לכתוב אותו קובץ בבת אחת. בין מחשבים OneDrive מעביר את הקבצים, והאתר שואל כל כמה שניות (GET /api/claims).
MAX_NAME = 40
_claims_lock = threading.Lock()


def me() -> dict:
    return {"name": claims.me(), "set": claims.name_set()}


def set_my_name(root: Path | None, name: str) -> dict:
    """השם שלי בצוות: נשמר ב-.env של המחשב הזה. מה שכבר לקחתי עובר לשם החדש."""
    name = " ".join(str(name or "").split())
    if not name or len(name) > MAX_NAME:
        raise UserError(f"השם צריך להיות באורך 1 עד {MAX_NAME} תווים.")
    old = claims.me()
    with _claims_lock:
        cfg.save_env("GRADER_NAME", name)
        if root:
            for course_dir in folder_view.courses(root):
                claims.rename_tasks(course_dir, old, name)
                for a in folder_view.assignments(course_dir):
                    claims.rename(a.dir, old, name)
    return me()


def _course_dir(root: Path, course: str) -> Path:
    d = root / course
    if not course or not d.is_dir() or d.resolve().parent != root.resolve():
        raise FileNotFoundError(f"הקורס {course} לא נמצא בתיקייה")
    return d


def set_task(root: Path, course: str, assignment: str, stage: str, take: bool) -> dict:
    """לוקח (או משחרר) את המשיכה או את ההחזרה של מטלה. גם של מטלה שעוד לא נמשכה ואין לה תיקייה."""
    if stage not in claims.STAGES:
        raise UserError("שלב לא מוכר")
    key = claims.task_key(assignment, stage)
    with _claims_lock:
        owner = claims.set_task(_course_dir(root, course), key, take)
    return {"stage": stage, "owner": owner}


def _take_task_if_free(course_dir: Path, assignment: str, stage: str) -> None:
    """מי שמושך או מעלה בלי שמישהו לקח את המשימה נרשם עליה, כדי שהצוות יראה מי עושה אותה."""
    key = claims.task_key(assignment, stage)
    with _claims_lock:
        if key not in claims.task_owners(course_dir):
            claims.set_task(course_dir, key, True)


# ---------- מה השתנה בתיקייה ----------
# האתר שואל כל כמה שניות (GET /api/changes) ומקבל חתימה של התיקייה: שמות, זמני שינוי וגדלים של הקבצים שהמצב
# נבנה מהם. כשמשהו השתנה (בודק אחר לקח עבודות, OneDrive הביא ציונים, מישהו משך), החתימה משתנה והאתר טוען מחדש.
_WATCHED = (paths.TO_GRADE, paths.MARKED, paths.UPLOAD, paths.NOTES, paths.CLAIMS)


def _scan(h, folder: Path) -> None:
    try:
        with os.scandir(folder) as it:
            for e in sorted(it, key=lambda e: e.name):
                if e.is_dir(follow_symlinks=False):  # תיקייה: רק השם. Windows מעדכן את הזמן שלה באיחור, ואת התוכן סורקים בנפרד
                    h.update(f"{e.name}/\n".encode("utf-8", "surrogatepass"))
                    continue
                st = e.stat(follow_symlinks=False)
                h.update(f"{e.name}|{st.st_mtime_ns}|{st.st_size}\n".encode("utf-8", "surrogatepass"))
    except OSError:
        h.update(b"-\n")


def changes(root: Path) -> str:
    h = hashlib.sha1()
    for course_dir in folder_view.courses(root):
        h.update(f"#{course_dir.name}\n".encode("utf-8", "surrogatepass"))
        _scan(h, course_dir)
        _scan(h, course_dir / paths.TASKS)
        for a in folder_view.assignments(course_dir):
            _scan(h, a.dir)
            for sub in _WATCHED:
                _scan(h, a.dir / sub)
    with _job_lock:  # הבדיקה שרצה כאן: כל עבודה שנגמרה משנה את מה שהאתר מציג
        h.update(f"{_job.running}|{len(_job.done)}\n".encode())
    return h.hexdigest()


def claims_view(root: Path, course: str, assignment: str) -> dict:
    """מי לקח מה, ואילו עבודות כבר נבדקו. קל מספיק כדי שהאתר ישאל כל כמה שניות."""
    a = find_assignment(root, course, assignment)
    done = set(grading.read_grades(a.dir)) | set(grading.marked_files(a.dir))
    return {"me": claims.me(), "claims": claims.read_all(a.dir), "graded": sorted(done)}


def change_claims(root: Path, course: str, assignment: str, take: list[str] | None = None,
                  release: list[str] | None = None, next_count: int = 0) -> dict:
    """לוקח עבודות (מספרים מסוימים, או next_count הפנויות הבאות שעוד לא נבדקו) או מחזיר עבודות שלי."""
    a = find_assignment(root, course, assignment)
    existing = set(grading.submission_numbers(a.dir))
    take = [grading.number_key(n) for n in take or [] if grading.number_key(n) in existing]
    out: dict = {"taken": [], "others": {}, "released": []}
    with _claims_lock:
        if next_count:
            # פנויות באקראי ולא הראשונות ברשימה: שניים שלוחצים באותו רגע, לפני ש-OneDrive סנכרן, כמעט לא יקחו
            # את אותן עבודות. מה שבכל זאת נלקח פעמיים נשאר אצל מי שלקח ראשון, והבדיקה של השני מוותרת עליו
            held = claims.read_all(a.dir)
            free = [n for n in grading.pending(a.dir) if n not in held and n not in take]
            take += sorted(random.sample(free, min(next_count, len(free))))
        if take:
            out.update(claims.take(a.dir, take))
        if release:
            out["released"] = claims.release(a.dir, [grading.number_key(n) for n in release])
    return {**claims_view(root, course, assignment), **out}


# ---------- העלאה למודל ----------
# הכנה (prepare_send) בונה אצווה ורושמת אותה ב-Upload batch.json. ההעלאה עצמה (start_send) רצה ברקע,
# ואחרי "כן" של אדם: האתר שולח את ה-id של האצווה שהאדם ראה, ואם בינתיים הוכנה אצווה אחרת, לא מעלים.
# רק העלאה אחת בכל פעם בתהליך הזה, ובין מחשבים הנעילה Upload in progress.txt (moodle/send.py) שומרת.
SIMULATE_DELAY = 1.0  # שניות לכל ZIP כש-MOODLE_DRIVER=simulate, כדי שיראו התקדמות באתר


def _upload_lock_holder(a: folder_view.Assignment) -> str | None:
    """מי מעלה עכשיו את המטלה (נעילה שלא התיישנה, של מישהו אחר או של תהליך אחר שלי שעוד רץ), או None. בלי ה-pid."""
    held = moodle_lock.holder(a.dir / moodle_send.UPLOAD_LOCK)
    return held[0] if held else None


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

    def upload_zip(self, info: dict, zip_path: Path, expected: int, dry_run: bool,
                   sha256: str | None = None) -> moodle_send.UploadResult:
        with _send_lock:
            self.job.current = Path(zip_path).name
        return self.inner.upload_zip(info, zip_path, expected, dry_run, sha256=sha256)


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
        if _checking:  # הבדיקה וההעלאה היו מפעילות את אותו כרום
            raise RuntimeError("בדיקת החיבור למודל רצה עכשיו. אפשר להתחיל בעוד רגע.")
        batch = moodle_send.current_batch(a.dir, batch_id)
        if batch is None:
            raise ValueError("stale")
        uploaded = upload_log.last_hashes(a.dir)
        already = sum(all(uploaded.get(f["file"]) == f["sha256"] for f in z["files"]) for z in batch["zips"])
        _send = job = SendJob(course, assignment, batch_id, dry_run, running=True, total=len(batch["zips"]),
                              done=already, started_at=datetime.now().isoformat(timespec="seconds"))
        _stop.clear()
    _take_task_if_free(a.dir.parent, assignment, "return")
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


# ---------- התחברות למודל, ומוכנות המחשב להעלאה ----------
# כל אחד בצוות מעלה מהמחשב שלו. לפני ההעלאה האתר בודק שהמחשב הזה מוכן: Claude Code מותקן, מחובר לחשבון של האדם,
# והכרום והמודל מחוברים. מה שחסר מחברים כמה שאפשר אוטומטית: ההתקנה וההתחברות רצות ברקע (ההתחברות פותחת דפדפן,
# והאדם מאשר שם), ובדיקת הכרום היא ריצה קצרה של Claude. את התוצאה של בדיקת הכרום זוכרים 30 דקות לכל מטלה.
MOODLE_STATUS_SECONDS = 60
READY_MINUTES = 30  # כמה זמן תוצאה של בדיקת הכרום נחשבת טרייה
LOGIN_MINUTES = 10  # התחברות שלא נגמרה אחרי זמן הזה נהרגת
INSTALL_MINUTES = 20  # וכך גם התקנה (היא מורידה קובץ, ויכולה לקחת יותר)
LOGIN_STARTED = "נפתח דף התחברות בדפדפן. אחרי ההתחברות המערכת תזהה לבד שזה הסתיים."
INSTALL_COMMAND = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://claude.ai/install.ps1 | iex"]
SIM_LOGIN_SECONDS = 2.0  # MOODLE_READY=simulate: כמה זמן "ההתחברות" נמשכת

_moodle_cache: tuple[float, dict] | None = None
_ready_cache: dict[tuple[str, str], tuple[float, dict, str]] = {}  # (קורס, מטלה) → (מתי, התשובה של check, מתי בשעון)
_checking = False  # בדיקת כרום רצה עכשיו (תחת _send_lock): היא והעלאה היו מפעילות את אותו כרום
_sim_login_at: float | None = None


class _Background:
    """תהליך רקע של האתר (`claude auth login` או ההתקנה): אחד בכל פעם, ונהרג אחרי BACKGROUND_MINUTES."""

    def __init__(self, minutes: float) -> None:
        self.minutes = minutes
        self.ended_seen = False  # כבר דיווחנו (take_ended) שהתהליך הנוכחי נגמר
        self.proc: subprocess.Popen | None = None
        self.timer: threading.Timer | None = None
        self.lock = threading.Lock()

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def take_ended(self) -> bool:
        """True פעם אחת, אחרי שהתהליך שרץ נגמר (לבד, או נהרג בגלל הזמן): הסטטוס ששמרנו בזמן שרץ כבר לא נכון."""
        if self.proc is not None and self.proc.poll() is not None and not self.ended_seen:
            self.ended_seen = True
            return True
        return False

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if self.timer:
            self.timer.cancel()
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    def start(self, cmd: list[str], restart: bool = False) -> bool:
        """False אם כבר רץ אחד (ו-restart כבוי). זורק OSError אם התהליך לא עלה."""
        with self.lock:
            if self.running():
                if not restart:
                    return False
                self.stop()
            # stdin סגור, והפלט לא נשמר: ההתחברות נעשית בדפדפן, והתהליך נגמר לבד כשהיא הסתיימה
            self.proc = proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.ended_seen = False
            self.timer = threading.Timer(self.minutes * 60, self._kill, args=(proc,))
            self.timer.daemon = True
            self.timer.start()
            return True

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass


_login = _Background(LOGIN_MINUTES)
_install = _Background(INSTALL_MINUTES)


def _simulated_ready() -> bool:
    """הדגמה (tests/serve_demo): התחברות מדומה, בלי `claude` אמיתי. רק יחד עם MOODLE_DRIVER=simulate."""
    return os.environ.get("MOODLE_READY") == "simulate" and os.environ.get("MOODLE_DRIVER") == "simulate"


def _sim_logged_in() -> bool:
    return _sim_login_at is not None and time.monotonic() - _sim_login_at >= SIM_LOGIN_SECONDS


class _SimChecker:
    def check(self, info: dict) -> dict:
        time.sleep(1.0)
        return {"chrome": True, "moodle": True, "message": "Chrome ו-Moodle מוכנים.", "answered": True}


def _make_checker():
    return _SimChecker() if _simulated_ready() else claude_driver.ClaudeChromeDriver()


def moodle_status() -> dict:
    """האם Claude Code מחובר במחשב הזה. נשמר דקה: הבדיקה מפעילה תהליך, והאתר שואל לעיתים קרובות.

    בזמן התחברות או התקנה (ואחרי שההתקנה הסתיימה) שואלים מחדש כל פעם, כדי שהאתר יראה את השינוי מהר."""
    global _moodle_cache
    # תהליך התחברות או התקנה שזה עתה נגמר: מה ששמרנו בזמן שהוא רץ ("לא מחובר") כבר לא נכון, גם אם עברה פחות מדקה
    ended = [_login.take_ended(), _install.take_ended()]
    if any(ended):
        _moodle_cache = None
    cached = _moodle_cache
    if cached and time.monotonic() - cached[0] < MOODLE_STATUS_SECONDS:
        installed_since = cached[1].get("message") == claude_driver.NOT_INSTALLED and claude_driver.find_claude() is not None
        if not (_login.running() or _install.running() or installed_since):
            return cached[1]
    status = claude_driver.auth_status()
    _moodle_cache = (time.monotonic(), status)
    return status


_status_refresh = threading.Lock()


def refresh_status_soon() -> None:
    """בודק ברקע אם Claude Code מחובר (moodle_status), אם אין כבר בדיקה כזו שרצה. התשובה נשמרת במטמון."""
    if not _status_refresh.acquire(blocking=False):
        return

    def run() -> None:
        try:
            moodle_status()
        except Exception:  # בדיקה שנכשלה לא מפילה את השרת; הבאה תנסה שוב
            pass
        finally:
            _status_refresh.release()
    threading.Thread(target=run, daemon=True).start()


def quick_status() -> dict | None:
    """מה שידוע עכשיו על Claude Code, בלי לחכות: `claude auth status` לוקח במחשב של אורי עד 13 שניות, והאתר לא
    מחכה לו. אם המידע ישן (או שעוד אין), בודקים ברקע. None = עוד לא ידוע."""
    cached = _moodle_cache
    if not cached or time.monotonic() - cached[0] >= MOODLE_STATUS_SECONDS or _login.running() or _install.running():
        refresh_status_soon()
    return cached[1] if cached else None


def quick_via() -> str | None:
    """כמו grading_via, בלי לחכות לבדיקה של Claude Code (quick_status)."""
    if cfg.claude_key():
        return "api"
    st = quick_status()
    return "code" if st and st.get("logged_in") else None


def grading_via() -> str | None:
    """איך הבדיקה מדברת עם Claude: "api" (יש ANTHROPIC_API_KEY), "code" (Claude Code מחובר במחשב, grading/claude_cli.py), או None."""
    if cfg.claude_key():
        return "api"
    return "code" if moodle_status()["logged_in"] else None


def _drop_status_cache() -> None:
    global _moodle_cache
    _moodle_cache = None


def _fresh_check(course: str, assignment: str) -> tuple[dict, str] | None:
    hit = _ready_cache.get((course, assignment))
    if hit and time.monotonic() - hit[0] < READY_MINUTES * 60:
        return hit[1], hit[2]
    return None


def readiness(root: Path, course: str, assignment: str) -> dict:
    """האם המחשב הזה מוכן להעלות את המטלה. מהירה: לא מפעילה בדיקת כרום, רק קוראת את התוצאה האחרונה (אם טרייה)."""
    find_assignment(root, course, assignment)
    if _simulated_ready():
        installed, status = True, {"logged_in": _sim_logged_in(), "message": "Claude Code מחובר." if _sim_logged_in() else claude_driver.NOT_LOGGED_IN}
        login_running = _sim_login_at is not None and not status["logged_in"]
        installing = False
    else:
        installed = claude_driver.find_claude() is not None
        status = moodle_status() if installed else {"logged_in": False, "message": claude_driver.NOT_INSTALLED}
        login_running, installing = _login.running(), _install.running()
    out = {"installed": installed, "logged_in": bool(status["logged_in"]), "chrome": None, "moodle": None,
           "checked_at": None, "message": status["message"], "login_running": login_running, "installing": installing}
    fresh = _fresh_check(course, assignment) if installed and out["logged_in"] else None
    if fresh:
        result, at = fresh
        out.update(chrome=result.get("chrome"), moodle=result.get("moodle"), checked_at=at, message=result.get("message") or "")
    elif out["logged_in"]:
        out["message"] = "עוד לא נבדקו הכרום והמודל."
    return out


def check_moodle(root: Path, course: str, assignment: str) -> dict:
    """האם Chrome ומודל מוכנים להעלאה של המטלה הזו (ריצה קצרה של Claude, בלי להעלות כלום).

    זורק RuntimeError בזמן העלאה (או בדיקה אחרת): היא והבדיקה היו מפעילות את אותו כרום."""
    global _checking
    a = find_assignment(root, course, assignment)
    _moodle_id(a)
    with _send_lock:
        if _send.running:
            raise RuntimeError("העלאה אחרת כבר רצה.")
        if _checking:
            raise RuntimeError("בדיקה אחרת של החיבור כבר רצה.")
        _checking = True
    try:
        result = _make_checker().check(paths.read_info(a.dir))
    finally:
        with _send_lock:
            _checking = False
    if result.get("answered") is True:
        # רק תשובה אמיתית של Claude נשמרת 30 דקות. כשל (זמן קצוב, שגיאה, לא מחובר) לא נשמר, וההעלאה הבאה בודקת מחדש
        stored = {k: result.get(k) for k in ("chrome", "moodle", "message")}
        _ready_cache[(course, assignment)] = (time.monotonic(), stored, datetime.now().isoformat(timespec="seconds"))
    elif result.get("message") == claude_driver.NOT_LOGGED_IN:
        _drop_status_cache()  # Claude Code כבר לא מחובר: הסטטוס ששמרנו התיישן
    return result


def check_ready(root: Path, course: str, assignment: str) -> dict:
    """בודק עכשיו את הכרום והמודל (עולה ריצה קצרה של Claude), מרענן את הזיכרון, ומחזיר את המוכנות."""
    result = check_moodle(root, course, assignment)
    out = readiness(root, course, assignment)
    if result.get("answered") is not True:
        out["check_error"] = result.get("message") or "הבדיקה נכשלה."  # הבדיקה לא נענתה, ולכן chrome ו-moodle נשארים None
    return out


def start_claude_login(restart: bool = False) -> dict:
    """פותח התחברות ל-Claude ברקע: `claude auth login` פותח דפדפן, האדם מתחבר עם החשבון שלו, והתהליך נגמר לבד.

    בלי --email: כל אחד מתחבר לחשבון שלו. תהליך אחד בכל פעם; עם restart=True הקודם נהרג ומתחיל חדש."""
    global _moodle_cache, _sim_login_at
    if _simulated_ready():
        if _sim_login_at is None or restart:
            _sim_login_at = time.monotonic()
        return {"started": True, "running": True, "message": LOGIN_STARTED}
    claude = claude_driver.find_claude()
    if not claude:
        return {"started": False, "running": False, "message": claude_driver.NOT_INSTALLED}
    if claude_driver.auth_status()["logged_in"]:  # בלי התחברות מיותרת (ובלי להרוג התחברות שכבר הצליחה)
        _moodle_cache = None
        return {"started": False, "running": _login.running(), "message": "כבר מחובר ל-Claude."}
    try:
        started = _login.start([claude, "auth", "login"], restart)
    except OSError as e:
        return {"started": False, "running": False, "message": f"ההתחברות לא התחילה: {e}"}
    _moodle_cache = None  # הסטטוס ישתנה בקרוב
    if not started:
        return {"started": False, "running": True, "message": "דף ההתחברות כבר נפתח. אם הוא לא נראה, אפשר ללחוץ 'נסה שוב'."}
    return {"started": True, "running": True, "message": LOGIN_STARTED}


def start_claude_install() -> dict:
    """מתקין את Claude Code ברקע, עם ההתקנה הרשמית של Anthropic. האתר שואל את האדם לפני שהוא קורא לזה."""
    global _moodle_cache
    if _simulated_ready():
        return {"started": False, "running": False, "message": "Claude Code כבר מותקן."}
    if claude_driver.find_claude():
        return {"started": False, "running": False, "message": "Claude Code כבר מותקן."}
    try:
        started = _install.start(INSTALL_COMMAND)
    except OSError as e:
        return {"started": False, "running": False, "message": f"ההתקנה לא התחילה: {e}"}
    _moodle_cache = None
    if not started:
        return {"started": False, "running": True, "message": "ההתקנה כבר רצה."}
    return {"started": True, "running": True, "message": "ההתקנה התחילה ברקע. זה לוקח כדקה."}


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


# ---------- בדיקה ידנית ----------
def save_review(root: Path, course: str, assignment: str, number: str, points: list, comments: list, feedback: str,
                mistakes: list | None = None) -> dict:
    """אדם אישר עבודה בתור הבדיקה הידנית (או תיקן ציון): grading.save_review, עם מי שאישר."""
    a = find_assignment(root, course, assignment)
    return grading.save_review(a.dir, number, points, comments, feedback, by=moodle_lock.me(), mistakes=mistakes)


# Grading notes של כל העבודות נקראים בכל טעינה של האתר. קובץ שלא השתנה לא נקרא שוב
_notes: dict[str, tuple[int, int, dict]] = {}


def cached_notes(assignment_dir: Path, number: str) -> dict:
    path = grading.notes_path(assignment_dir, number)
    try:
        st = path.stat()
    except OSError:
        return {}
    hit = _notes.get(str(path))
    if hit and hit[:2] == (st.st_size, st.st_mtime_ns):
        return hit[2]
    data = grading.read_notes(assignment_dir, number)
    _notes[str(path)] = (st.st_size, st.st_mtime_ns, data)
    return data


# עמודי ההגשה כתמונות, לבדיקה הידנית באתר: בלי מציג ה-PDF של הדפדפן, והסימונים של Claude מצוירים מעליהם.
# כל הקבצים של הגשה (0001.pdf, 0001-2.jpg) הם PDF אחד, כמו ש-Claude ראה אותם, כדי שמספרי העמודים בסימונים יתאימו
_docs: OrderedDict[tuple, bytes] = OrderedDict()
PAGE_DPI = 110


def _submission_doc(root: Path, course: str, assignment: str, number: str) -> bytes:
    a = find_assignment(root, course, assignment)
    files = grading.submission_files(a.dir).get(grading.number_key(number))
    if not files:
        raise FileNotFoundError(f"אין הגשה {number}")
    key = (str(a.dir), number, tuple((f.name, f.stat().st_mtime_ns) for f in files))
    if key not in _docs:
        _docs[key] = grading.submission_pdf(files)[0]
        while len(_docs) > 8:
            _docs.popitem(last=False)
    _docs.move_to_end(key)
    return _docs[key]


def page_count(root: Path, course: str, assignment: str, number: str) -> int:
    data = _submission_doc(root, course, assignment, number)
    if not data:
        return 0
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return doc.page_count


def page_image(root: Path, course: str, assignment: str, number: str, page: int) -> bytes:
    """עמוד אחד (מ-1) כ-JPEG. FileNotFoundError אם אין הגשה כזו או עמוד כזה."""
    data = _submission_doc(root, course, assignment, number)
    with pymupdf.open(stream=data or None, filetype="pdf") as doc:
        if not 1 <= page <= doc.page_count:
            raise FileNotFoundError(f"אין עמוד {page}")
        return doc[page - 1].get_pixmap(dpi=PAGE_DPI).tobytes("jpeg", jpg_quality=80)


def _note_fields(note: dict, res: dict) -> dict:
    """מה שהאתר צריך מ-Grading notes: הערות וטעויות לכל שאלה, מה Claude לא בטוח בו, הסימונים, ולמה צריך אדם."""
    failed = "" if res.get("grade") else str(note.get("error") or "")
    if grading.is_limit(failed):  # נגמרה המכסה באמצע בדיקה: העבודה עוד לא נבדקה, אין מה לבדוק בה ידנית
        failed = ""
    review = res.get("review") or ""
    # מקרה מיוחד (special ב-Grades.csv, מהבדיקה) קודם; אחרת הסוג מ-Grading notes
    kind = str(res.get("special") or note.get("review_kind") or "") if review else ""
    return {
        "comments": [str(c) for c in note.get("comments") or []],
        "mistakes": [[str(m) for m in ms] for ms in note.get("mistakes") or [] if isinstance(ms, list)],
        "unsure": [bool(u) for u in note.get("unsure") or []],
        "marks": [{k: m.get(k) for k in ("page", "x0", "y0", "x1", "y1", "text")} for m in note.get("marks") or [] if isinstance(m, dict)],
        "failed": failed, "reviewKind": "failed" if failed else (kind or ("other" if review else "")),
        "reviewedBy": (note.get("reviewed") or {}).get("by") or "",
        "missing": str(res.get("missing") or "") if review else "",
    }


# ---------- מצב לאתר ----------
# "Moodle download <date>.zip", או תיקייה "Moodle download <date>" של הורדה בחלקים
# "Moodle download 2026-10-23 11-15" (old), "... 11-15-07", "... 11-15-07 (2)", a ZIP or a folder of parts
_DOWNLOAD = re.compile(re.escape(paths.DOWNLOAD_PREFIX)
                       + r" (\d{4}-\d{2}-\d{2} \d{2}-\d{2}(?:-\d{2})?)(?: \(\d+\))?(?:\.zip)?$")


def _download_time(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%d %H-%M-%S" if len(stamp) > 16 else "%Y-%m-%d %H-%M")


def _downloads(a: folder_view.Assignment) -> list[str]:
    """מתי נמשכה המטלה, מהישן לחדש: מיומן המשיכות ("Pull log.csv", שורה לכל משיכה), ומשיכות ישנות שהשאירו את
    ה-ZIP בתיקיית המטלה. ה-ZIP עצמו נשמר היום רק במחשב שמשך, אז היומן הוא מה שכל המחשבים רואים."""
    times = [datetime.fromisoformat(t) for t in moodle_ingest.pulls(a.dir)]
    times += [_download_time(m.group(1)) for p in a.dir.glob(f"{paths.DOWNLOAD_PREFIX} *") if (m := _DOWNLOAD.match(p.name))]
    return [t.isoformat(timespec="minutes") for t in sorted(times)]


def _last_download(a: folder_view.Assignment) -> str | None:
    return (_downloads(a) or [None])[-1]


def _activity(a: folder_view.Assignment, log: list[dict]) -> list[dict]:
    """יומן הפעילות של המטלה, רק ממה שבאמת קרה בתיקייה: משיכות, עדכון קובצי הציונים והעלאות למודל. בלי שמות של סטודנטים."""
    out = [{"at": at, "kind": "pull", "text": "נמשכו הגשות ממודל"} for at in _downloads(a)]
    for f in moodle_grades.files(a.dir):  # Grades.csv, וקובץ לכל בודק
        n = sum(1 for r in moodle_grades.read_file(f).values() if r.get("grade"))
        out.append({"at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes"),
                    "kind": "grade", "text": f"{f.name} עודכן: {n} ציונים"})
    uploads: dict[tuple[str, str], dict] = {}
    for r in log:  # שורה לכל קובץ שעלה. מקבצים לפי ה-ZIP והדקה
        at = (r.get("uploaded_at") or "")[:16]
        u = uploads.setdefault((r.get("zip") or "", at), {"at": at, "by": r.get("by") or "", "numbers": set()})
        u["numbers"].add(r.get("number"))
    for (zip_name, _), u in uploads.items():
        n = len(u["numbers"])
        out.append({"at": u["at"], "kind": "return", "actor": u["by"],
                    "text": f"הועלו למודל {n} עבודות מסומנות" + (f" ({zip_name})" if zip_name else "")})
    return out


def state(root: Path) -> dict:
    """הקורסים, המטלות וההגשות כפי שהם בתיקייה. בלי שמות של סטודנטים: רק מספרים."""
    courses, out = [], []
    with _job_lock:  # הבדיקה שרצה עכשיו במחשב הזה: העבודות שלה שעוד לא נגמרו מוצגות "בבדיקה"
        job = (_job.course, _job.assignment, set(_job.numbers) - set(_job.done)) if _job.running else None
    for ci, course_dir in enumerate(folder_view.courses(root)):
        cid = f"c{ci}"
        courses.append({"id": cid, "name": folder_view.course_title(course_dir), "folder": course_dir.name})
        tasks = claims.task_owners(course_dir)  # מי לקח את המשיכה ואת ההחזרה של כל מטלה
        for ai, a in enumerate(_slots(course_dir)):
            folder = folder_view.slot_folder(a) if isinstance(a, int) else a.dir.name
            owners = {st: tasks.get(claims.task_key(folder, st)) for st in claims.STAGES}
            if isinstance(a, int):
                out.append({**_empty_slot(cid, course_dir, ai, a), "owners": owners})
                continue
            grading_now = job[2] if job and job[:2] == (course_dir.name, a.dir.name) else set()
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
            held = claims.read_all(a.dir)
            subs = []
            for n, files in sorted(by_number.items()):
                res = results.get(grading.number_key(n)) or {}
                grade = res.get("grade")
                graded = n in marked or bool(grade)
                status = "returned" if graded and n in returned else "graded" if graded else "pulled"
                if grading.number_key(n) in grading_now:
                    status = "grading"
                newest = max(f.stat().st_mtime for f in files)
                subs.append({
                    "id": n, "name": f"הגשה {n}", "studentId": n, "email": "",
                    "submittedAt": datetime.fromtimestamp(newest).isoformat(timespec="minutes"),
                    "late": False, "scanned": False, "status": status, "q": grading.parse_points(res.get("points")),
                    "score": _score(grade), "feedback": res.get("feedback") or None, "issue": None,
                    "approved": grading.is_approved(res), "review": res.get("review") or "",
                    "claim": held.get(grading.number_key(n)), "gradedBy": res.get("graded_by") or None,
                    **_note_fields(cached_notes(a.dir, n), res),
                    "files": [{"name": f.name, "pages": 0, "size": f.stat().st_size, "path": f.relative_to(root).as_posix()} for f in files]
                             + [{"name": m.name, "pages": 0, "size": m.stat().st_size, "path": m.relative_to(root).as_posix(),
                                 "marked": True} for m in marked.get(n, [])],
                })
            pulled = _last_download(a) or (
                datetime.fromtimestamp((a.dir / paths.KEY).stat().st_mtime).isoformat(timespec="minutes")
                if subs and (a.dir / paths.KEY).exists() else None)
            graded_at = max((f.stat().st_mtime for f in moodle_grades.files(a.dir)), default=None)
            ctx = grading.load_context(a.dir, send_solution=False)
            out.append({
                "id": f"{cid}a{ai}", "courseId": cid, "course": folder_view.course_title(course_dir),
                "courseFolder": course_dir.name, "folder": a.dir.name, "title": a.title,
                "n": ai + 1, "due": d.get("due"), "questions": a.question_count(), "questionLabels": a.question_labels(),
                "pulledAt": pulled, "returnedAt": max((r["uploaded_at"] for r in log), default=None), "moodleId": d.get("id"),
                "gradedAt": datetime.fromtimestamp(graded_at).isoformat(timespec="minutes") if graded_at else None,
                "rubric": [{"label": q.label, "points": q.points, "criteria": q.criteria, "deductions": q.deductions}
                           for q in ctx.questions],
                "noRubric": ctx.no_rubric, "maxGrade": ctx.max_grade, "solution": (a.dir / grading.SOLUTION).is_file(),
                "notes": d.get("notes") or "", "rules": d.get("submission_rules") or [],
                "warnings": [f"עותק כפול של טבלת המפתח: {c}" for c in key_conflicts(a)]
                            + [f"עותק כפול של הגשה: {c}" for c in moodle_anonymize.submission_conflicts(a.dir)]
                            + [f"עותק כפול של יומן ההעלאה: {c}" for c in upload_log.log_conflicts(a.dir)]
                            + ([f"משיכה בתהליך: {moodle_lock.parse((a.dir / LOCK_FILE).read_text(encoding='utf-8'))[0]}"] if (a.dir / LOCK_FILE).exists() else [])
                            + ([f"העלאה בתהליך: {who}"] if (who := _upload_lock_holder(a)) else []),
                "subs": subs, "log": _activity(a, log), "owners": owners, "copying": copying_state(a.dir),
            })
    return {"root": str(root), "courses": courses, "assignments": out, "me": me(),
            "moodle": False, "claude": quick_via() is not None, "claudeVia": quick_via(), "grading": grade_status(), "sending": send_status(), "copyCheck": copying_status(),
            "usage": grading_usage.summary(root)}


def _slots(course_dir: Path) -> list[folder_view.Assignment | int]:
    """עשר ההגשות של הקורס לפי הסדר: המטלה שבתיקייה, או המספר שלה אם עוד אין לה תיקייה.
    מטלה בלי מספר בשם התיקייה (או מעבר לעשר) מופיעה בסוף."""
    items = folder_view.assignments(course_dir)
    by_slot = {}
    for a in items:
        n = folder_view.slot(a.dir.name)
        if n is not None and n < folder_view.SLOTS and n not in by_slot:
            by_slot[n] = a
    rest = [a for a in items if a not in by_slot.values()]
    return [by_slot.get(n, n) for n in range(folder_view.SLOTS)] + rest


def _empty_slot(cid: str, course_dir: Path, ai: int, n: int) -> dict:
    """הגשה שעוד לא נמשכה: אין תיקייה ואין מזהה מודל. המשיכה הראשונה מקבלת את המזהה ויוצרת אותה."""
    return {
        "id": f"{cid}a{ai}", "courseId": cid, "course": folder_view.course_title(course_dir),
        "courseFolder": course_dir.name, "folder": folder_view.slot_folder(n), "title": folder_view.slot_title(n),
        "n": ai + 1, "due": None, "questions": 4, "questionLabels": [], "pulledAt": None, "returnedAt": None,
        "moodleId": None, "gradedAt": None, "rubric": [], "maxGrade": None, "solution": False, "notes": "", "rules": [],
        "warnings": [], "subs": [], "log": [], "empty": True,
    }


def _score(raw: str | None) -> float | int | None:
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return None
    return int(x) if x.is_integer() else x
