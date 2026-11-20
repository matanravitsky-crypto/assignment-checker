"""הסנכרון עם הוואן דרייב של המרצה דרך הדפדפן: תיקיות הקורסים שבתיקיית הנתונים במחשב הזה.

onedrive/sync.js רץ בלשונית של הוואן דרייב, קורא דרך web_server את רשימת הקבצים של קורס (נתיב, גודל, מתי
נשמר), משווה לוואן דרייב, ומעלה רק מה שחדש או השתנה. רק מתוך תיקיית קורס בתוך paths.data_dir(): אי אפשר לבקש
קובץ מחוץ לה, ו-Moodle originals (עם שמות הסטודנטים) לא נמצא שם.

ובכיוון השני (2026-11-20, בשביל Mac: שם אפליקציית OneDrive לא יכולה לסנכרן את התיקייה של המרצה, כי חשבונות
הצוות אורחים ב-BGU ו-BGU דורשת מהם אימות דו-שלבי שהאפליקציה לא מציגה) הסקריפט מוריד מהוואן דרייב מה שחדש שם,
ושומר דרך write_file. השמירה:
- רק לתיקיית נתונים מקומית. תיקייה ש-OneDrive מסנכרן בעצמו (paths.in_shared_folder) מסרבת: שם OneDrive כבר מביא הכל.
- רק בתוך תיקיית קורס, בלי ".." ובלי חלקים שמתחילים בנקודה (.claude, .git), ולא קבצים שלא מסנכרנים (SKIP).
- רק אם הקובץ במחשב הוא בדיוק מה שהסקריפט ראה ברשימה (expect): נוצר או השתנה מאז = מסרבים, לא דורסים.
- לא בזמן משיכה, בדיקה או העלאה של אותה מטלה במחשב הזה ("* in progress.txt" טרי בתיקיית המטלה).
- כתיבה אטומית, וזמן השמירה של הקובץ נקבע לזמן שלו בוואן דרייב.
אף פעם לא מוחקים.

מצב הסנכרון (state): לכל קובץ שסונכרן, הגודל והזמן שלו במחשב ובוואן דרייב באותו רגע. כך הסקריפט יודע איזה צד
השתנה מאז: רק המחשב = מעלים, רק הוואן דרייב = מורידים, שניהם = התנגשות, לא נוגעים ומדווחים. נשמר במחשב הזה
בלבד (work_dir, לא ב-OneDrive), כי הוא מתאר את העותק שבמחשב הזה.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from moodle import atomic, paths

# הסקריפט שרץ בלשונית של הוואן דרייב. טוענים אותו בשורה אחת:
#   eval(await (await fetch("http://127.0.0.1:8765/api/sync/script.js")).text()); await window.__ecsSyncAll()
SCRIPT = Path(__file__).resolve().parents[1] / "onedrive" / "sync.js"

# לא מעלים: קבצים זמניים של Windows ו-Office, קבצים חצי כתובים, מנעולים של משיכה, בדיקה והעלאה
# (מנעול שעולה לוואן דרייב היה נשאר שם תקוע), ואף פעם לא ZIP: קובצי ה-ZIP של מודל (עד 2.8GB למטלה, עם השמות
# של הסטודנטים) נשארים במחשב שהוריד, וקובצי ה-ZIP להחזרה למודל נבנים מחדש בכל הכנה
# Finder של Mac כותב .DS_Store בכל תיקייה שנפתחה, ו-"._<שם>" ליד קבצים בדיסקים מסוימים: גם הם לא עולים
SKIP = re.compile(r"(^|/)(desktop\.ini|thumbs\.db|\.DS_Store|\._[^/]*|~\$[^/]*|[^/]*\.tmp|[^/]* in progress\.txt|[^/]*\.zip)$",
                  re.I)


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


def read_file(course: str, rel: str) -> bytes:
    folder = course_dir(course)
    target = (folder / rel).resolve()
    top_level_only = course == "" and target.parent != folder
    if (not rel or top_level_only or not target.is_relative_to(folder) or not target.is_file()
            or SKIP.search(rel.replace("\\", "/"))):
        raise FileNotFoundError(rel)
    return target.read_bytes()


# ---------- הכיוון השני: מהוואן דרייב למחשב ----------
STATE_FOLDER = "OneDrive sync state"   # בתוך work_dir: מצב הסנכרון של המחשב הזה, קובץ לכל קורס
LOCK_FILE = re.compile(r".* in progress\.txt$", re.I)
LOCK_FRESH_S = 30 * 60                 # כמו moodle/lock.py: מנעול ישן מזה נחשב תקוע


class Refused(Exception):
    """השמירה נדחתה. ההודעה בעברית, לדוח שבחלון של הסקריפט."""


def _valid_course(course: str) -> bool:
    return course == "" or (course not in (".", "..") and not course.startswith(".")
                            and not re.search(r"[\\/:]", course) and course.strip() == course)


def _valid_rel(rel: str) -> bool:
    parts = rel.split("/")
    return (bool(rel) and not re.search(r'[\\:<>"|?*\x00-\x1f]', rel)
            and all(p and p not in (".", "..") and not p.startswith(".") and p.strip() == p for p in parts)
            and not SKIP.search(rel))


def writable() -> str | None:
    """None אם מותר להוריד לתיקיית הנתונים הזו, אחרת למה לא."""
    root = paths.data_dir()
    if paths.in_shared_folder(root):
        return (f"תיקיית הנתונים במחשב הזה ({root}) היא תיקייה ש-OneDrive מסנכרן בעצמו, אז לא מורידים אליה דרך "
                "הדפדפן: OneDrive כבר מביא את הקבצים.")
    return None


def _assignment_busy(folder: Path) -> str | None:
    """אם במחשב הזה רצה עכשיו משיכה, בדיקה או העלאה של המטלה: שם המנעול."""
    try:
        for f in folder.iterdir():
            if f.is_file() and LOCK_FILE.match(f.name) and time.time() - f.stat().st_mtime < LOCK_FRESH_S:
                return f.name
    except OSError:
        pass
    return None


def write_file(course: str, rel: str, data: bytes, mtime_ms: int, expect: str) -> dict:
    """שומר קובץ שהגיע מהוואן דרייב. expect: "none" (הקובץ לא קיים במחשב) או "<גודל>:<זמן במילישניות>" כפי שהיה
    ברשימה שהסקריפט השווה. מחזיר את הגודל והזמן החדשים, או זורק Refused."""
    why = writable()
    if why:
        raise Refused(why)
    if not _valid_course(course) or not _valid_rel(rel) or (course == "" and "/" in rel):
        raise Refused(f"נתיב לא חוקי: {course}/{rel}")
    root = paths.data_dir()
    folder = root / course if course else root
    target = folder / rel
    resolved_root = root.resolve() if root.exists() else root.absolute()
    if not target.absolute().is_relative_to(root.absolute()) or (
            target.parent.exists() and not target.parent.resolve().is_relative_to(resolved_root)):
        raise Refused(f"נתיב מחוץ לתיקיית הנתונים: {course}/{rel}")
    if course and "/" in rel:
        busy = _assignment_busy(folder / rel.split("/")[0])
        if busy:
            raise Refused(f"{rel.split('/')[0]}: רץ עכשיו במחשב הזה ({busy}). מורידים אחרי שזה נגמר.")
    if target.is_dir():
        raise Refused(f"במחשב יש תיקייה בשם הזה: {rel}")
    if target.is_file():
        st = target.stat()
        now = f"{st.st_size}:{int(st.st_mtime * 1000)}"
        if expect != now:
            raise Refused(f"הקובץ השתנה במחשב מאז ההשוואה, אז הוא לא נדרס: {rel}")
    elif expect != "none":
        raise Refused(f"הקובץ נמחק או הועבר במחשב מאז ההשוואה, אז הוא לא נכתב מחדש: {rel}")
    atomic.write_atomic(target, data)
    seconds = mtime_ms / 1000
    os.utime(target, (seconds, seconds))
    st = target.stat()
    return {"path": rel, "size": st.st_size, "mtime": int(st.st_mtime * 1000)}


def _state_file(course: str) -> Path:
    if not _valid_course(course):
        raise FileNotFoundError(course)
    return paths.work_dir() / STATE_FOLDER / f"{course or '(top folder)'}.json"


def read_state(course: str) -> dict:
    """{נתיב: {"local": [גודל, זמן], "remote": [גודל, זמן]}} מהסנכרון האחרון של הקורס במחשב הזה."""
    files = atomic.read_json(_state_file(course), default={})
    return files if isinstance(files, dict) else {}


def record_state(course: str, entries: dict) -> int:
    """מוסיף או מעדכן קבצים שסונכרנו עכשיו. entries כמו ב-read_state. מחזיר כמה נרשמו."""
    good = {}
    for rel, e in (entries or {}).items():
        if not isinstance(rel, str) or not isinstance(e, dict):
            continue
        pair = [e.get("local"), e.get("remote")]
        if all(isinstance(p, list) and len(p) == 2 and all(isinstance(n, (int, float)) for n in p) for p in pair):
            good[rel] = {"local": [int(n) for n in pair[0]], "remote": [int(n) for n in pair[1]]}
    if good:
        path = _state_file(course)
        with atomic.process_lock("onedrive-sync-state"):
            files = read_state(course)
            files.update(good)
            atomic.write_atomic(path, json.dumps(files, ensure_ascii=False, sort_keys=True))
    return len(good)
