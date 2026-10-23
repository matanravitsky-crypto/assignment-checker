"""משיכה מתוזמנת: מיד אחרי שההגשה נגמרת, המערכת מושכת את ההגשות מעצמה, בלי ללחוץ על כלום.

הזמן והיום:
- היום הוא יום המועד של המטלה (`due` ב-`Assignment details.json`), לפי השעון של המחשב. המשיכה היא בלילה שאחריו,
  ב-`SCHEDULE_PULL_TIME` ב-.env (ברירת מחדל 00:05), כדי שגם מי שהגיש ב-23:59 ייכנס.
- חצי שעה לפני (`SCHEDULE_WARN_MIN`, כלומר 23:35 ביום המועד) יוצאת התראה בווינדוס, ומאותו רגע המחשב לא נרדם
  עד שהמשיכה נגמרת.
- מחשב שנדלק אחרי השעה (עד שלוש שעות) מושך מיד. אחרי זה לא מושכים לבד: לוחצים "משוך הגשות".
- כל מטלה נמשכת פעם אחת. אם המשיכה נכשלה, ההתראה אומרת למה ואין ניסיון חוזר לבד.
- שורה `SCHEDULE_PULL=off` ב-.env מכבה את כל זה.

המשיכה עצמה היא `actions.pull`, אותה אחת של הכפתור, עם אותן נעילות ובדיקות. ה-Claude שבכרום
צריך שכרום יהיה פתוח ומחובר למודל: ההתראה אומרת את זה.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from moodle import paths

from . import actions, folder_view

STATE_FILE = "Scheduled pulls.json"  # בתיקיית העבודה המקומית: שייך למחשב הזה
CATCH_UP = timedelta(hours=3)
TICK_S = 30

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


def tick(root: Path, now: datetime, state: dict, run_pull) -> bool:
    """צעד אחד של התזמון. מחזיר אם המחשב צריך להישאר ער. `run_pull(course, assignment)` מושך ומחזיר טקסט תוצאה."""
    awake = False
    for course, assignment, title, day in scheduled(root):
        at = datetime.combine(day + timedelta(days=1), pull_time())
        warn_at = at - timedelta(minutes=warn_minutes())
        key = f"{course}/{assignment}@{day.isoformat()}"
        job = state.setdefault(key, {})
        if job.get("done"):
            continue
        if now < warn_at or now > at + CATCH_UP:
            continue
        awake = True
        if not job.get("warned") and now < at:
            notify("בודק חכם: משיכה ב-" + at.strftime("%H:%M"),
                   f"{title}: ההגשה נגמרה. משאירים את המחשב דלוק, וכרום פתוח ומחובר למודל.")
            job["warned"] = now.isoformat(timespec="seconds")
            _save(state)
        if now >= at:
            job["done"] = now.isoformat(timespec="seconds")  # לפני המשיכה: קריסה באמצע לא תמשוך שוב ושוב
            _save(state)
            notify("בודק חכם: מתחילה משיכה", f"{title}: מושכים עכשיו ממודל.")
            try:
                job["result"] = run_pull(course, assignment)
            except Exception as e:  # noqa: BLE001 - מוצג בהתראה
                job["result"] = f"נכשלה: {e}"
            _save(state)
            notify("בודק חכם: " + title, job["result"])
    return awake


def start(lock: threading.Lock) -> None:
    """תהליכון ברקע של השרת. `lock` הוא אותו נעילה של הכפתורים: משיכה אחת בכל פעם."""
    if not enabled():
        return

    def run_pull(course: str, assignment: str) -> str:
        root, err = actions.root_info()
        if not root:
            raise RuntimeError(err)
        with lock:
            rep = actions.pull(root, course, assignment)
        return "המשיכה הסתיימה: " + rep["summary"]

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
