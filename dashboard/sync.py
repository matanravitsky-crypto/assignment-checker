"""הסנכרון עם הוואן דרייב של המרצה: תיקיות הקורסים שבתיקיית הנתונים במחשב הזה, בשני הכיוונים.

onedrive/sync.js רץ בלשונית של הוואן דרייב, קורא דרך web_server את רשימת הקבצים של קורס (נתיב, גודל, מתי
נשמר), משווה לוואן דרייב, מעלה מה שחדש או השתנה במחשב, ומוריד לכאן (put_file) מה שחדש או השתנה בוואן דרייב.
קובץ שהיה בוואן דרייב בסנכרון הקודם ונעלם משם (הועבר או נמחק בענן) לא נמחק במחשב: הוא עובר (remove_file) ל-
"Removed from OneDrive/<תאריך>/<הנתיב>" בתיקיית המטלה, כדי שמצב הענן ישתקף כאן בלי לאבד דבר.

הכל רק מתוך תיקיית קורס בתוך paths.data_dir(): אי אפשר לבקש או לכתוב קובץ מחוץ לה, ו-Moodle originals (עם שמות
הסטודנטים) לא נמצא שם. מנעולים, קבצים זמניים, Key history ו-Removed from OneDrive לא נוגעים בהם בשום כיוון,
ומטלה שבדיקה, משיכה או העלאה רצות בה עכשיו (מנעול "... in progress.txt" טרי) לא נכתבת.

מה הסקריפט ראה בסנכרון הקודם (snapshot, לכל קורס: לכל קובץ הזמן והגודל בשני הצדדים) נשמר במחשב הזה מחוץ
לתיקיית הנתונים (state_dir), כדי להבדיל "חדש במחשב" מ"נמחק בענן" ולזהות קובץ שהשתנה בשני הצדדים.
"""
from __future__ import annotations

import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from datastore import atomic
from moodle import lock, paths

# הסקריפט שרץ בלשונית של הוואן דרייב. טוענים אותו בשורה אחת:
#   eval(await (await fetch("http://127.0.0.1:8765/api/sync/script.js")).text()); window.__ecsLive.start()
SCRIPT = Path(__file__).resolve().parents[1] / "onedrive" / "sync.js"

# מה שהענן הוריד או העביר: במחשב הזה בלבד, בתיקיית המטלה (או הקורס), לפי תאריך הסנכרון
REMOVED = "Removed from OneDrive"
# לא מסנכרנים בשום כיוון: קבצים זמניים של Windows ו-Office, קבצים חצי כתובים, מנעולים של משיכה, בדיקה והעלאה
# (מנעול שעולה לוואן דרייב היה נשאר שם תקוע), אף פעם לא ZIP: קובצי ה-ZIP של מודל (עד 2.8GB למטלה, עם השמות
# של הסטודנטים) נשארים במחשב שהוריד, וקובצי ה-ZIP להחזרה למודל נבנים מחדש בכל הכנה. וגם מה שהענן הסיר (REMOVED):
# זה הארכיון של המחשב הזה. אותו ביטוי ב-sync.js
SKIP = re.compile(r"(^|/)(desktop\.ini|thumbs\.db|~\$[^/]*|[^/]*\.tmp|[^/]* in progress\.txt|[^/]*\.zip"
                  r"|Removed from OneDrive/.*)$", re.I)
# לא כותבים ולא מזיזים במחשב (רק מעלים, כמו קודם): ההיסטוריה של טבלת המפתח
PROTECTED = re.compile(r"(^|/)Key history(/|$)", re.I)
LOCK_NAME = re.compile(r" in progress\.txt$", re.I)
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}$")
# שעון המחשב ושעון השרת לא מסונכרנים בדיוק: הפרש קטן מזה לא נחשב "השתנה" (כמו ב-sync.js)
CLOCK_SLACK_MS = 2 * 60 * 1000
# הלשונית מדווחת כל חצי דקה; בלי דיווח בזמן הזה הסנכרון החי לא רץ (הלשונית נסגרה, הדפדפן ישן)
ALIVE_SECONDS = 100


class Busy(Exception):
    """בדיקה, משיכה או העלאה רצות עכשיו במטלה הזו (מנעול טרי): לא כותבים בה."""


class Conflict(Exception):
    """הקובץ במחשב השתנה מאז שהסקריפט השווה אותו: לא דורסים."""


def courses() -> list[str]:
    root = paths.data_dir()
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def course_dir(course: str) -> Path:
    """תיקיית הקורס, רק אם היא תיקייה ישירה בתוך תיקיית הנתונים. course ריק: התיקייה הראשית עצמה,
    שממנה עולים רק הקבצים שבה (README, הפרוטוקול, "Pull only on this computer.txt"), בלי תיקיות."""
    root = paths.data_dir().resolve()
    if course == "":
        if not root.is_dir():
            raise FileNotFoundError(str(root))
        return root
    folder = (root / course).resolve()
    if folder.parent != root or not folder.is_dir():
        raise FileNotFoundError(course)
    return folder


def list_files(course: str) -> list[dict]:
    """[{path, size, mtime}] של כל הקבצים בקורס (course ריק: רק הקבצים שבתיקייה הראשית).
    path יחסי לתיקיית הקורס, עם "/", ו-mtime במילישניות."""
    folder = course_dir(course)
    out = []
    for f in sorted(folder.iterdir() if course == "" else folder.rglob("*")):
        rel = f.relative_to(folder).as_posix()
        if f.is_file() and not SKIP.search(rel):
            st = f.stat()
            out.append({"path": rel, "size": st.st_size, "mtime": int(st.st_mtime * 1000)})
    return out


def busy_assignments(course: str) -> list[str]:
    """תיקיות המטלות בקורס שמנעול טרי ("... in progress.txt" צעיר מ-LOCK_MINUTES) נמצא בהן: הסקריפט לא נוגע בהן בסיבוב הזה."""
    if course == "":
        return []
    folder = course_dir(course)
    return sorted(p.name for p in folder.iterdir() if p.is_dir() and busy(p))


def busy(assignment_dir: Path) -> str | None:
    """שם המנעול הטרי בתיקיית המטלה, או None. גם המנעול שלי: בזמן שהמחשב הזה בודק או מושך לא כותבים בתיקייה."""
    try:
        names = os.listdir(assignment_dir)
    except OSError:
        return None
    now = time.time()
    for name in names:
        if LOCK_NAME.search(name):
            try:
                age = now - (assignment_dir / name).stat().st_mtime
            except OSError:
                continue
            if age < lock.LOCK_MINUTES * 60:
                return name
    return None


def _target(course: str, rel: str) -> tuple[Path, Path]:
    """(תיקיית הקורס, הקובץ) של נתיב יחסי, אחרי הבדיקות: בתוך הקורס, לא מנעול, לא זמני, לא מוגן."""
    folder = course_dir(course)
    rel = rel.replace("\\", "/").strip("/")
    parts = rel.split("/")
    if (not rel or any(p in ("", ".", "..") for p in parts) or SKIP.search(rel) or PROTECTED.search(rel)
            or (course == "" and len(parts) > 1)):
        raise FileNotFoundError(rel)
    target = folder / rel
    if not target.resolve().is_relative_to(folder) or target.is_dir():
        raise FileNotFoundError(rel)
    return folder, target


def _assignment_of(course: str, folder: Path, target: Path) -> Path | None:
    """תיקיית המטלה שהקובץ בתוכה (<קורס>/<מטלה>/...), או None לקובץ בתיקיית הקורס או בראשית."""
    if course == "":
        return None
    rel = target.relative_to(folder).parts
    return folder / rel[0] if len(rel) > 1 and (folder / rel[0] / paths.INFO).is_file() else None


def _long(p: Path) -> Path:
    """הנתיב בצורה ש-Windows מקבל גם מעבר ל-260 תווים (תיקיית המטלה + Removed from OneDrive + תאריך + הנתיב הם הרבה)."""
    return Path("\\\\?\\" + str(p.resolve())) if os.name == "nt" and not str(p).startswith("\\\\?\\") else p


def _check_unchanged(target: Path, expect_mtime_ms: int | None) -> None:
    """הקובץ במחשב כמו שהסקריפט ראה אותו (expect: הזמן שלו אז, במילישניות; None = לא היה)."""
    if not target.exists():
        if expect_mtime_ms is not None:
            raise Conflict(f"{target.name}: הקובץ נעלם מהמחשב בינתיים")
        return
    local_ms = int(target.stat().st_mtime * 1000)
    if expect_mtime_ms is None:
        raise Conflict(f"{target.name}: הקובץ כבר קיים במחשב")
    if abs(local_ms - expect_mtime_ms) > CLOCK_SLACK_MS:
        raise Conflict(f"{target.name}: הקובץ במחשב השתנה מאז ההשוואה")


def put_file(course: str, rel: str, data: bytes, mtime_ms: int, expect_mtime_ms: int | None) -> dict:
    """כותב את הגרסה מהוואן דרייב למחשב, בבת אחת, עם זמן השינוי של הענן (כך שבסיבוב הבא שני הצדדים זהים).

    expect_mtime_ms: הזמן של הקובץ במחשב כשהסקריפט השווה (None = לא היה קובץ). קובץ שהשתנה כאן בינתיים לא
    נדרס (Conflict). מטלה עם מנעול טרי לא נכתבת (Busy)."""
    folder, target = _target(course, rel)
    a = _assignment_of(course, folder, target)
    if a and (held := busy(a)):
        raise Busy(f"{a.name}: {held}")
    _check_unchanged(target, expect_mtime_ms)
    _long(target.parent).mkdir(parents=True, exist_ok=True)
    tmp = _long(atomic._tmp_name(target))
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.utime(tmp, ns=(int(mtime_ms * 1_000_000), int(mtime_ms * 1_000_000)))
        atomic._replace(tmp, _long(target))
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return {"path": rel, "size": len(data), "mtime": int(_long(target).stat().st_mtime * 1000)}


def remove_file(course: str, rel: str, expect_mtime_ms: int | None, stamp: str | None = None) -> dict:
    """קובץ שהיה בוואן דרייב ונעלם משם: עובר ל-"Removed from OneDrive/<stamp>/<הנתיב בתוך המטלה>" בתיקיית המטלה
    (קובץ בתיקיית הקורס או הראשית: ב-REMOVED שלהן). לא נמחק. stamp: תאריך הסיבוב, כדי שכל מה שהוסר באותו
    סנכרון ישב יחד; ברירת המחדל עכשיו."""
    folder, target = _target(course, rel)
    if not target.is_file():
        raise FileNotFoundError(rel)
    a = _assignment_of(course, folder, target)
    if a and (held := busy(a)):
        raise Busy(f"{a.name}: {held}")
    _check_unchanged(target, expect_mtime_ms)
    base = a or folder
    stamp = stamp if stamp and STAMP.match(stamp) else datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    dest = base / REMOVED / stamp / target.relative_to(base)
    _long(dest.parent).mkdir(parents=True, exist_ok=True)
    n = 2
    while _long(dest).exists():
        dest = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        n += 1
    shutil.move(str(_long(target)), str(_long(dest)))
    return {"path": rel, "moved_to": dest.relative_to(folder).as_posix()}


def read_file(course: str, rel: str) -> bytes:
    folder = course_dir(course)
    target = (folder / rel).resolve()
    top_level_only = course == "" and target.parent != folder
    if (not rel or top_level_only or not target.is_relative_to(folder) or not target.is_file()
            or SKIP.search(rel.replace("\\", "/"))):
        raise FileNotFoundError(rel)
    return target.read_bytes()


# ---------- מה נראה בסנכרון הקודם ----------
def state_dir() -> Path:
    """איפה המחשב הזה שומר מה הסקריפט ראה בסנכרון הקודם: מחוץ לתיקיית הנתונים (שלא יעלה לענן) ומחוץ לריפו."""
    explicit = os.environ.get("ASSIGNMENT_SYNC_STATE")
    if explicit:
        return Path(explicit)
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".bodek-hacham") / "Bodek Hacham" / "onedrive-sync"


def _snapshot_file(course: str) -> Path:
    course_dir(course)  # רק קורס שקיים
    return state_dir() / (f"{course}.json" if course else "_root.json")


def read_snapshot(course: str) -> dict:
    data = atomic.read_json(_snapshot_file(course), default={})
    return data if isinstance(data, dict) else {}


def write_snapshot(course: str, data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("snapshot must be an object")
    atomic.write_json_atomic(_snapshot_file(course), data, indent=None)


# ---------- הסנכרון החי: מה הלשונית דיווחה לאחרונה ----------
_live_lock = threading.Lock()
_live: dict = {"received": None, "report": None}
# מה נשמר מהדיווח של הלשונית (מספרים, שמות קבצים ממוספרים והודעות שגיאה; לא יותר מזה)
_REPORT_KEYS = ("running", "interval_s", "syncedAt", "stage", "error", "needsLogin", "summary", "conflicts", "busy", "failed")


def set_live(report: dict) -> None:
    """POST /api/sync/status: הלשונית אומרת שהיא חיה, ומה קרה בסיבוב האחרון."""
    if not isinstance(report, dict):
        raise ValueError("status must be an object")
    kept = {k: report[k] for k in _REPORT_KEYS if k in report}
    for k in ("conflicts", "busy", "failed"):
        if k in kept:
            kept[k] = [str(x)[:300] for x in (kept[k] if isinstance(kept[k], list) else [])][:200]
    for k in ("error", "stage", "syncedAt"):
        if k in kept and kept[k] is not None:
            kept[k] = str(kept[k])[:500]
    with _live_lock:
        _live["received"] = time.monotonic()
        _live["report"] = kept


def live_status() -> dict:
    """מה האתר מראה בשורת OneDrive: alive (הלשונית דיווחה בזמן האחרון), agoS (לפני כמה שניות), והדיווח האחרון."""
    with _live_lock:
        received, report = _live["received"], _live["report"]
    if received is None:
        return {"alive": False, "agoS": None, "report": None}
    ago = int(time.monotonic() - received)
    return {"alive": ago < ALIVE_SECONDS, "agoS": ago, "report": report}


def reset_live() -> None:
    with _live_lock:
        _live.update(received=None, report=None)
