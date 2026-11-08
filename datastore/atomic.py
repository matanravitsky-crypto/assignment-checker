"""כתיבה אטומית ונעילות.

write_atomic / write_json_atomic   קובץ זמני ייחודי באותה תיקייה (pid + מספר אקראי), fsync, ואז os.replace. קריסה באמצע
                                   משאירה לכל היותר קובץ .tmp יתום, אף פעם לא קובץ חצי כתוב.
read_json                          קריאה סובלנית: JSON שבור, קידוד לא תקין או קובץ חסר = ברירת המחדל, והבעיה נרשמת.
create_exclusive                   נעילה בתיקייה המשותפת: O_CREAT|O_EXCL, אז שני תהליכים שמנסים באותה אלפית שנייה לא
                                   יכולים שניהם להצליח (בניגוד ל"בדוק ואז כתוב").
process_lock                       נעילת תהליך מקומית (לא ב-OneDrive) לפי שם, ב-%LOCALAPPDATA%\\bodek-hacham\\locks.
                                   msvcrt.locking בווינדוס, fcntl.flock באחרים. סביב קריאה-שינוי-כתיבה של קובץ.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class LockTimeout(TimeoutError):
    """נעילת התהליך לא התפנתה בזמן: תהליך אחר במחשב הזה כותב את אותו קובץ."""


def _tmp_name(path: Path) -> Path:
    # Short on purpose: Windows refuses paths over 260 characters, and the shared folder's paths are already long
    return path.with_name(f"~{random.getrandbits(24):06x}.tmp")


def write_atomic(path: Path, data: bytes | str, *, encoding: str = "utf-8") -> None:
    """כותב את data ל-path בבת אחת: או שהקובץ הישן נשאר, או שהחדש שלם."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_name(path)
    raw = data.encode(encoding) if isinstance(data, str) else data
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            raise
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def write_json_atomic(path: Path, obj, *, bom: bool = False, indent: int | None = 2) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=indent, allow_nan=False) + "\n"
    write_atomic(path, text, encoding="utf-8-sig" if bom else "utf-8")


def read_json(path: Path, default=None, problems: list | None = None):
    """JSON מהקובץ, או default כשהוא חסר או פגום (ואז הבעיה נוספת ל-problems אם ניתנה רשימה)."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        if problems is not None:
            from .schema import Problem
            problems.append(Problem("unreadable_json", f"{path.name}: הקובץ לא נקרא כ-JSON ({type(e).__name__})", where=path.name))
        return default


def create_exclusive(path: Path, text: str) -> bool:
    """יוצר את הקובץ עם text רק אם הוא לא קיים. מחזיר False אם מישהו הקדים (הקובץ קיים)."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return True


def local_lock_dir() -> Path:
    base = os.environ.get("BODEK_LOCK_DIR") or os.environ.get("LOCALAPPDATA") or os.environ.get("TMPDIR") or "/tmp"
    d = Path(base) / "bodek-hacham" / "locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


@contextmanager
def process_lock(name: str, timeout: float = 30.0) -> Iterator[None]:
    """נעילה בין תהליכים במחשב הזה לפי שם (למשל הנתיב של קובץ הציונים שלי). חוסמת עד timeout שניות, ואז LockTimeout."""
    lock_path = local_lock_dir() / (hashlib.sha1(str(name).encode("utf-8", "surrogatepass")).hexdigest()[:24] + ".lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"תהליך אחר במחשב הזה כותב עכשיו את אותו קובץ ({name}). נסו שוב בעוד רגע.")
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(fd)
