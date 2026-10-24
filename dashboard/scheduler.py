"""משיכה מתוזמנת: אחרי שההגשה נגמרת, המערכת מושכת את ההגשות מעצמה, בלי ללחוץ על כלום.

הזמן והיום:
- היום הוא יום המועד של המטלה (`due` ב-`Assignment details.json`), לפי השעון של המחשב. כל משיכה קוראת אותו ממודל
  ושומרת אותו (actions._due_from_moodle), כך שאחרי המשיכה הראשונה אף אחד לא מקליד אותו.
- המשיכה הראשונה היא בלילה שאחריו, ב-`SCHEDULE_PULL_TIME` ב-.env (ברירת מחדל 00:05), כדי שגם מי שהגיש ב-23:59 ייכנס.
  היא מושכת את כולם. חצי שעה לפני (`SCHEDULE_WARN_MIN`) יוצאת התראה בווינדוס, ומאותו רגע המחשב לא נרדם עד שהיא נגמרת.
- אחריה, באותה שעה בכל לילה במשך `SCHEDULE_REPULL_DAYS` לילות (ברירת מחדל 7): משיכה חוזרת של מה שהשתנה בלבד
  (הגשות מאוחרות, הארכות, החלפת קובץ). כמה דקות, בלי התראה, חוץ מכשנכנסו הגשות חדשות או כשהיא נכשלה.
- מחשב שנדלק אחרי השעה (עד שלוש שעות) מושך מיד. אחרי זה לא מושכים לבד באותו לילה.
- משיכה שנכשלה (מודל לא ענה, כרום לא התחבר) מנסה שוב אחרי חצי שעה, עד 3 פעמים בלילה. ההתראה אומרת למה.
- שורה `SCHEDULE_PULL=off` ב-.env מכבה את כל זה.

מי מושך: רק המחשב של מי שלקח את "משיכה" של המטלה באתר (claims.task_owners; המשיכה הראשונה בכפתור רושמת את
מי שלחץ), ורק כשהתיקייה המשותפת מסונכרנת בו (paths.in_shared_folder). כך שני מחשבים מסונכרנים לא מושכים את אותה
מטלה באותו לילה, לפני ש-OneDrive הספיק להעביר ביניהם את הנעילה ואת טבלת המפתח. מטלה שאף אחד לא לקח את המשיכה
שלה לא נמשכת לבד.

המשיכה עצמה היא `actions.pull`, אותה אחת של הכפתור, עם אותן נעילות ובדיקות. כרום סגור נפתח לבד
(claude_driver.open_chrome), אבל צריך שיהיה מחובר למודל ולתוסף של Claude: ההתראה אומרת את זה.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from moodle import claims, paths

from . import actions, folder_view

STATE_FILE = "Scheduled pulls.json"  # בתיקיית העבודה המקומית: שייך למחשב הזה
CATCH_UP = timedelta(hours=3)
TICK_S = 30
TRIES = 3  # ניסיונות בלילה אחד
RETRY_AFTER = timedelta(minutes=30)

_ES_CONTINUOUS, _ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


def enabled() -> bool:
    return os.environ.get("SCHEDULE_PULL", "on").strip().lower() not in ("off", "0", "no")


def pull_time() -> dtime:
    try:
        h, m = os.environ.get("SCHEDULE_PULL_TIME", "00:05").split(":")
        return dtime(int(h), int(m))
    except ValueError:
        return dtime(0, 5)


def warn_minutes() -> int:
    try:
        return max(0, int(os.environ.get("SCHEDULE_WARN_MIN", "30")))
    except ValueError:
        return 30


def repull_days() -> int:
    try:
        return min(30, max(0, int(os.environ.get("SCHEDULE_REPULL_DAYS", "7"))))
    except ValueError:
        return 7


def due_day(details: dict) -> date | None:
    raw = details.get("due")
    if not raw:
        return None
    try:
        d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d.astimezone() if d.tzinfo else d).date()


def scheduled(root: Path) -> list[tuple[str, str, str, date]]:
    """(course folder, assignment folder, title, יום המועד) של כל מטלה עם מועד הגשה ומזהה במודל."""
    out = []
    for course_dir in folder_view.courses(root):
        for a in folder_view.assignments(course_dir):
            d = a.details()
            day = due_day(d) if d.get("id") else None
            if day:
                out.append((course_dir.name, a.dir.name, a.title, day))
    return out


def puller(root: Path, course: str, assignment: str) -> str | None:
    """מי לקח את המשיכה של המטלה (השם שלו בצוות), או None."""
    owner = claims.task_owners(root / course).get(claims.task_key(assignment, "pull"))
    return owner["who"] if owner else None


def mine(root: Path, course: str, assignment: str) -> bool:
    """המחשב הזה מושך את המטלה בלילה: המשיכה שלה רשומה עליי, והתיקייה המשותפת מסונכרנת כאן."""
    if not paths.in_shared_folder(root) and os.environ.get("MOODLE_DRIVER") != "simulate":
        return False
    return puller(root, course, assignment) == claims.me()


def _state_path() -> Path:
    d = paths.work_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / STATE_FILE


def _load() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(state: dict) -> None:
    today = date.today()
    keep = {k: v for k, v in state.items() if (today - date.fromisoformat(k.rsplit("@", 1)[1])).days < 30}
    _state_path().write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")


def notify(title: str, text: str) -> None:
    """התראה בווינדוס (בלון ליד השעון). נכשלת בשקט: אין לה תפקיד חוץ מלהודיע."""
    if os.name != "nt":
        return
    script = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;$n.Icon=[System.Drawing.SystemIcons]::Information;"
        "$n.Visible=$true;$n.ShowBalloonTip(15000,$env:AC_T,$env:AC_M,'Info');Start-Sleep -Seconds 16;$n.Dispose()")
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                         env={**os.environ, "AC_T": title, "AC_M": text}, creationflags=0x08000000)
    except OSError:
        pass


def keep_awake(on: bool) -> None:
    """רק מהתהליכון שקורא לזה: ווינדוס קושר את הדגל לתהליכון, והוא נשאר עד שמבטלים או שהתהליכון מסתיים."""
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS | (_ES_SYSTEM_REQUIRED if on else 0))


def tick(root: Path, now: datetime, state: dict, run_pull, is_mine=mine) -> bool:
    """צעד אחד של התזמון. מחזיר אם המחשב צריך להישאר ער.

    `run_pull(course, assignment, full)` מושך ומחזיר {"text": תוצאה, "new": כמה הגשות חדשות}; full בלילה הראשון."""
    awake = False
    for course, assignment, title, day in scheduled(root):
        if not is_mine(root, course, assignment):
            continue
        for k in range(repull_days() + 1):
            night = day + timedelta(days=1 + k)
            first = k == 0
            at = datetime.combine(night, pull_time())
            warn_at = at - timedelta(minutes=warn_minutes()) if first else at
            if now < warn_at or now > at + CATCH_UP:
                continue
            job = state.setdefault(f"{course}/{assignment}@{night.isoformat()}", {})
            if job.get("done"):
                continue
            awake = True
            if first and not job.get("warned") and now < at:
                notify("בודק חכם: משיכה ב-" + at.strftime("%H:%M"),
                       f"{title}: ההגשה נגמרה. משאירים את המחשב דלוק, וכרום מחובר למודל.")
                job["warned"] = now.isoformat(timespec="seconds")
                _save(state)
            if now < at or (job.get("retry_at") and now < datetime.fromisoformat(job["retry_at"])):
                continue
            # לפני המשיכה: קריסה באמצע לא תמשוך שוב ושוב, והניסיון הבא רק אחרי חצי שעה
            job["tries"] = job.get("tries", 0) + 1
            job["retry_at"] = (now + RETRY_AFTER).isoformat(timespec="seconds")
            _save(state)
            if first:
                notify("בודק חכם: מתחילה משיכה", f"{title}: מושכים עכשיו ממודל.")
            try:
                res = run_pull(course, assignment, first)
            except Exception as e:  # noqa: BLE001 - מוצג בהתראה
                job["result"] = f"נכשלה: {e}"
                if job["tries"] < TRIES:
                    notify("בודק חכם: " + title,
                           f"המשיכה נכשלה ({e}). מנסה שוב ב-{(now + RETRY_AFTER):%H:%M}.")
                else:
                    job["done"] = now.isoformat(timespec="seconds")
                    notify("בודק חכם: " + title,
                           f"המשיכה נכשלה {TRIES} פעמים ({e}). לוחצים \"משוך הגשות\" באתר כשאפשר.")
                _save(state)
                continue
            job["done"] = now.isoformat(timespec="seconds")
            job["result"] = res["text"]
            _save(state)
            if first or res.get("new"):
                notify("בודק חכם: " + title, res["text"])
    return awake


def start(lock: threading.Lock) -> None:
    """תהליכון ברקע של השרת. `lock` הוא אותו נעילה של הכפתורים: משיכה אחת בכל פעם."""
    if not enabled():
        return

    def run_pull(course: str, assignment: str, full: bool) -> dict:
        root, err = actions.root_info()
        if not root:
            raise RuntimeError(err)
        with lock:
            rep = actions.pull(root, course, assignment, full=full)
        return {"text": "המשיכה הסתיימה: " + rep["summary"], "new": rep["result"]["new"]}

    def loop() -> None:
        state, awake = _load(), False
        stop = threading.Event()
        while not stop.is_set():
            root, _ = actions.root_info()
            try:
                now_awake = bool(root) and tick(root, datetime.now(), state, run_pull)
            except Exception:  # noqa: BLE001 - תזמון שנפל לא מפיל את השרת
                now_awake = awake
            if now_awake != awake:
                keep_awake(now_awake)
                awake = now_awake
            stop.wait(TICK_S)

    threading.Thread(target=loop, name="scheduled-pull", daemon=True).start()
