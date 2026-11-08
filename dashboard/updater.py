"""המערכת מתעדכנת לבד מ-GitHub בזמן שהיא רצה, כך שכל מחשב בצוות עובד על הגרסה האחרונה של main בלי שאף אחד
יעשה כלום (מתן, 2026-11-03).

start.bat מתעדכן (git pull --ff-only, claude update, pip install) רק כשהוא עולה, ו-autostart.vbs מעלה אותו רק כשהמערכת
למטה. לכן מערכת שנשארה דלוקה רצה על קוד ישן ימים שלמים. התהליכון הזה שואל את GitHub כל UPDATE_CHECK_MINUTES דקות
(.env, ברירת מחדל 60). כש-main זז קדימה, והכול כאן נכון, השרת עוצר את עצמו:
- התיקייה על main, בלי שינויים בקבצים של הריפו (מי שמפתח כאן מתעדכן בעצמו), ו-main רק התקדם (git pull --ff-only יעבוד);
- שום דבר לא רץ: משיכה, בדיקה, העלאה, בדיקת העתקות, בדיקת כרום, התחברות או התקנה של Claude Code, ואין משיכת לילה
  שמתקרבת (scheduler.in_night_window). כפתור שנלחץ בדיוק עכשיו מחכה: העצירה מחזיקה את אותה נעילה של הכפתורים;
- autostart.vbs של התיקייה הזו רץ, והשרת על 8765: רק כך מישהו מעלה אותו שוב. תוך דקה הוא מריץ את start.bat, שמושך,
  מעדכן ומעלה את הגרסה החדשה (בערך 1-3 דקות בסך הכול).
האתר רואה גרסה חדשה ב-/api/changes וטוען את עצמו מחדש. עדכון שלא הצליח (ה-pull נכשל והשרת עלה שוב על אותה גרסה)
לא מנסה שוב לאותה גרסה, כדי שלא ייווצר מעגל של הפעלות. `AUTO_UPDATE=off` ב-.env מכבה את כל זה.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from moodle import paths

REPO = Path(__file__).resolve().parents[1]
BRANCH = "main"
WATCHED_PORT = 8765  # autostart.vbs בודק רק את הפורט הזה
FIRST_CHECK_S = 10 * 60  # לא מיד אחרי עלייה: מערכת שהרגע התעדכנה נרגעת קודם
BUSY_RETRY_S = 5 * 60  # משהו רץ: בודקים שוב בקרוב
GIT_TIMEOUT_S = 60
STATE_FILE = "Self update.json"  # בתיקיית העבודה המקומית: לאיזו גרסה כבר ניסינו לעבור
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: שום חלון לא קופץ

_version: str | None = None


def enabled() -> bool:
    return os.environ.get("AUTO_UPDATE", "on").strip().lower() not in ("off", "0", "no")


def check_s() -> float:
    try:
        return max(5, int(os.environ.get("UPDATE_CHECK_MINUTES", "60"))) * 60
    except ValueError:
        return 60 * 60


def git(*args: str, run=subprocess.run) -> str | None:
    """פלט של פקודת git בתיקיית הריפו, או None כשהיא נכשלה (אין git, אין רשת, קוד יציאה שאינו 0)."""
    try:
        p = run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S,
                stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return (p.stdout or "").strip() if p.returncode == 0 else None


def version(git=git) -> str:
    """הגרסה שהשרת הזה רץ עליה (commit קצר), כפי שהייתה כשעלה. "" בלי git. האתר נטען מחדש כשהיא משתנה."""
    global _version
    if _version is None:
        _version = git("rev-parse", "--short", "HEAD") or ""
    return _version


def waiting_update(git=git) -> str | None:
    """ה-commit של main ב-GitHub, כשהוא לפני התיקייה הזו ואפשר פשוט להתקדם אליו. None בכל מקרה אחר: ענף אחר,
    שינויים מקומיים, בלי git או בלי רשת, היסטוריה שהתפצלה, או שאין שום חדש."""
    if git("rev-parse", "--abbrev-ref", "HEAD") != BRANCH:
        return None
    if git("status", "--porcelain", "--untracked-files=no") != "":  # None (git נכשל) עוצר כאן גם הוא
        return None
    if git("fetch", "-q", "origin", BRANCH) is None:
        return None
    target = git("rev-parse", f"origin/{BRANCH}")
    if not target or target == git("rev-parse", "HEAD"):
        return None
    if git("merge-base", "--is-ancestor", "HEAD", target) is None:  # לא רק התקדמות: git pull --ff-only ייכשל
        return None
    return target


def watchdog_running(run=subprocess.run) -> bool:
    """האם autostart.vbs של התיקייה הזו רץ? רק הוא מעלה מחדש מערכת שעצרה."""
    if os.name != "nt":
        return False
    script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
              "Get-CimInstance Win32_Process -Filter \"Name='wscript.exe'\" | ForEach-Object { $_.CommandLine }")
    try:
        out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                  timeout=GIT_TIMEOUT_S, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    vbs = str(REPO / "autostart.vbs").lower()
    return any(vbs in line.lower() for line in (out or b"").decode("utf-8", "replace").splitlines())


def _state_path() -> Path:
    return paths.work_dir() / STATE_FILE


def tried(target: str) -> bool:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8")).get("to") == target
    except (OSError, ValueError, AttributeError):
        return False


def remember_try(target: str) -> None:
    try:
        _state_path().parent.mkdir(parents=True, exist_ok=True)
        _state_path().write_text(json.dumps({"to": target, "from": version(),
                                             "at": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
    except OSError:
        pass  # בלי הזיכרון: לכל היותר ניסיון נוסף אחרי שעה


def tick(busy, *, waiting=waiting_update, watchdog=watchdog_running, tried=tried) -> tuple[str | None, float]:
    """בדיקה אחת. (commit לעבור אליו, או None כשנשארים; כמה שניות עד הבדיקה הבאה). `busy()`: מה רץ עכשיו."""
    target = waiting()
    if not target or tried(target):
        return None, check_s()
    if busy():
        return None, BUSY_RETRY_S
    if not watchdog():
        return None, check_s()
    return target, 0


def start(port: int, stop_server, lock: threading.Lock, busy) -> threading.Thread | None:
    """תהליכון ברקע של השרת. `stop_server` עוצר את השרת (httpd.shutdown). `lock` הוא הנעילה של הכפתורים: מחזיקים
    אותה מהבדיקה האחרונה ועד העצירה, כדי שמשיכה לא תתחיל באמצע. `busy()` מחזיר מה רץ (ריק = כלום)."""
    if not enabled() or port != WATCHED_PORT:
        return None
    version()  # הגרסה שהשרת עלה איתה, לפני ש-git pull ידני ישנה את התיקייה

    def loop() -> None:
        wait, sleeper = min(FIRST_CHECK_S, check_s()), threading.Event()
        while not sleeper.wait(wait):
            wait = check_s()
            if not lock.acquire(blocking=False):  # כפתור באמצע: מנסים שוב בקרוב
                wait = BUSY_RETRY_S
                continue
            stopped = False
            try:
                target, wait = tick(busy)
                if target:
                    remember_try(target)
                    _say(f"יש גרסה חדשה ב-GitHub ({target[:7]}). השרת נעצר, ו-autostart.vbs יעלה אותו מעודכן תוך דקה.")
                    stop_server()
                    stopped = True
                    return
            except Exception:  # noqa: BLE001 - עדכון שנכשל לא מפיל את השרת
                wait = check_s()
            finally:
                if not stopped:  # אחרי עצירה הנעילה נשארת תפוסה עד שהתהליך נגמר: שום כפתור לא מתחיל
                    lock.release()

    t = threading.Thread(target=loop, name="self-update", daemon=True)
    t.start()
    return t


def _say(text: str) -> None:
    try:
        print(f"\n{text}", flush=True)  # ל-%TEMP%\\bodek-hacham.log
    except (OSError, ValueError):
        pass
