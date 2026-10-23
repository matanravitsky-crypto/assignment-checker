"""מה מעלים לוואן דרייב של המרצה: תיקיות הקורסים שבתיקיית הנתונים במחשב הזה.

onedrive/sync.js רץ בלשונית של הוואן דרייב, קורא דרך web_server את רשימת הקבצים של קורס (נתיב, גודל, מתי
נשמר), משווה לוואן דרייב, ומעלה רק מה שחדש או השתנה. כאן רק קוראים, ורק מתוך תיקיית קורס בתוך
paths.data_dir(): אי אפשר לבקש קובץ מחוץ לה, ו-Moodle originals (עם שמות הסטודנטים) לא נמצא שם.
"""
from __future__ import annotations

import re
from pathlib import Path

from moodle import paths

# הסקריפט שרץ בלשונית של הוואן דרייב. טוענים אותו בשורה אחת:
#   eval(await (await fetch("http://127.0.0.1:8765/api/sync/script.js")).text()); await window.__ecsSyncAll()
SCRIPT = Path(__file__).resolve().parents[1] / "onedrive" / "sync.js"

# לא מעלים: קבצים זמניים של Windows ו-Office, קבצים חצי כתובים, ומנעולים של משיכה, בדיקה והעלאה
# (מנעול שעולה לוואן דרייב היה נשאר שם תקוע)
SKIP = re.compile(r"(^|/)(desktop\.ini|thumbs\.db|~\$[^/]*|[^/]*\.tmp|[^/]* in progress\.txt)$", re.I)


def courses() -> list[str]:
    root = paths.data_dir()
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def course_dir(course: str) -> Path:
    """תיקיית הקורס, רק אם היא תיקייה ישירה בתוך תיקיית הנתונים."""
    root = paths.data_dir().resolve()
    folder = (root / course).resolve()
    if not course or folder.parent != root or not folder.is_dir():
        raise FileNotFoundError(course)
    return folder


def list_files(course: str) -> list[dict]:
    """[{path, size, mtime}] של כל הקבצים בקורס. path יחסי לתיקיית הקורס, עם "/", ו-mtime במילישניות."""
    folder = course_dir(course)
    out = []
    for f in sorted(folder.rglob("*")):
        rel = f.relative_to(folder).as_posix()
        if f.is_file() and not SKIP.search(rel):
            st = f.stat()
            out.append({"path": rel, "size": st.st_size, "mtime": int(st.st_mtime * 1000)})
    return out


def read_file(course: str, rel: str) -> bytes:
    folder = course_dir(course)
    target = (folder / rel).resolve()
    if not rel or not target.is_relative_to(folder) or not target.is_file() or SKIP.search(rel.replace("\\", "/")):
        raise FileNotFoundError(rel)
    return target.read_bytes()
