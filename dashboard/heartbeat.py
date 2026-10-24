"""מי עובד עכשיו: כל מחשב כותב כל דקה קובץ משלו ברמת תיקיית השורש.

כל קובץ שייך לאדם אחד (claims.file_name), OneDrive לא ממזג כלום.
הקוד שמריץ בדיקה, משיכה או העלאה קורא ל-set_activity לפני שמתחיל, וריק או "idle" כשנגמר.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

from moodle import claims, paths

STALE_MINUTES = 3
_INTERVAL = 60  # שניות בין כתיבות


def _folder(root: Path) -> Path:
    return root / paths.WHO_WORKING


def write(root: Path, activity: dict) -> None:
    who = claims.me()
    folder = _folder(root)
    folder.mkdir(exist_ok=True)
    path = folder / f"{claims.file_name(who)}.json"
    tmp = path.with_name(path.name + ".tmp")
    data = {"name": who, "at": datetime.now().isoformat(timespec="seconds"), **activity}
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def read_all(root: Path) -> list[dict]:
    folder = _folder(root)
    if not folder.is_dir():
        return []
    cutoff = STALE_MINUTES * 60
    now = datetime.now()
    out = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            at_str = str(data.get("at") or "")
            at = datetime.fromisoformat(at_str)
            if (now - at).total_seconds() < cutoff:
                out.append(data)
        except (OSError, ValueError):
            continue
    return out


# ---------- פעילות נוכחית ----------
_lock = threading.Lock()
_current: dict = {}
_root: Path | None = None
_thread: threading.Thread | None = None


def set_activity(root: Path, **kwargs: object) -> None:
    """עדכן את הפעילות הנוכחית (מיד + בכתיבה הבאה בלולאה)."""
    global _root
    with _lock:
        _root = root
        _current.update(kwargs)
    try:
        write(root, dict(_current))
    except OSError:
        pass


def clear_activity(root: Path, *keys: str) -> None:
    """הסר שדות מהפעילות הנוכחית."""
    with _lock:
        for k in keys:
            _current.pop(k, None)
        snap = dict(_current)
    try:
        write(root, snap)
    except OSError:
        pass


def start(root: Path) -> None:
    """הפעל את לולאת הכתיבה ברקע (פעם אחת בהפעלת השרת)."""
    global _thread, _root
    _root = root
    if _thread and _thread.is_alive():
        return

    def _run() -> None:
        while True:
            time.sleep(_INTERVAL)
            with _lock:
                snap = dict(_current)
                r = _root
            if r:
                try:
                    write(r, snap)
                except OSError:
                    pass

    _thread = threading.Thread(target=_run, daemon=True, name="heartbeat")
    _thread.start()
