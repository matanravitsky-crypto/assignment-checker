"""משיכה בחלקים: מה השרת המקומי עונה לסקריפט שבלשונית של מודל (moodle/parts.js).

הסקריפט מבקש ממודל ZIP לכל חלק של 50 סטודנטים, ואחרי כל חלק שואל כאן (/api/pull/zip) אם ה-ZIP הגיע לתיקיית
ההורדות שלם ועם מספר הסטודנטים הנכון. ZIP קטוע מקבל את התחילית "BROKEN", כדי שלא ייקלט, והסקריפט מבקש את
אותם סטודנטים שוב בשני חצאים. בסוף הסקריפט מודיע (/api/pull/finish), והמשיכה (actions.pull) קולטת את כל החלקים.

המצב נשמר בזיכרון, לכל מטלה: מספרים ושמות קבצים בלבד, בלי שמות של סטודנטים.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from moodle import ingest as moodle_ingest

SCRIPT = Path(__file__).resolve().parents[1] / "moodle" / "parts.js"
BROKEN_PREFIX = "BROKEN "

_lock = threading.Lock()
_runs: dict[str, dict] = {}


def begin(mid: str) -> None:
    with _lock:
        _runs[str(mid)] = {"started": time.time(), "finished": False, "stage": "starting", "ok": [], "broken": [],
                           "sizes": {}, "users": None, "submitted": None, "parts": 0, "error": ""}


def status(mid: str) -> dict:
    with _lock:
        run = _runs.get(str(mid))
        return {k: v for k, v in run.items() if k != "sizes"} if run else {}


def _zips(mid: str, downloads: Path, since: float) -> list[Path]:
    pattern = re.compile(rf"-{re.escape(str(mid))}( \(\d+\))?$")
    found = []
    for p in downloads.glob("*.zip"):
        try:
            if pattern.search(p.stem) and not p.name.startswith(BROKEN_PREFIX) and p.stat().st_mtime >= since - 2:
                found.append(p)
        except OSError:
            continue
    return sorted(found, key=lambda p: p.stat().st_mtime)


def check(mid: str, since_ms: float, expect: int, downloads: Path | None = None) -> dict:
    """Has the ZIP of the part asked for at `since_ms` arrived whole? {"status": "waiting"|"ok"|"broken", ...}.

    "ok" carries how many students are in it. A ZIP must hold the same size twice in a row before it is tested
    (Chrome renames it when done, but OneDrive or the antivirus may still hold it)."""
    mid = str(mid)
    downloads = downloads or moodle_ingest.downloads_dir()
    since = since_ms / 1000
    with _lock:
        run = _runs.setdefault(mid, {"started": since, "finished": False, "stage": "downloading", "ok": [], "broken": [],
                                     "sizes": {}, "users": None, "submitted": None, "parts": 0, "error": ""})
        seen = set(run["ok"]) | set(run["broken"])
    if any(moodle_ingest._mtime(p) >= since - 2 for p in downloads.glob("*.crdownload")):
        return {"status": "waiting"}  # כרום עוד מוריד
    fresh = [p for p in _zips(mid, downloads, since) if p.name not in seen]
    if not fresh:
        return {"status": "waiting"}
    zip_path = fresh[0]
    size = zip_path.stat().st_size
    with _lock:
        if run["sizes"].get(zip_path.name) != size:
            run["sizes"][zip_path.name] = size
            return {"status": "waiting"}
    try:
        moodle_ingest.check_zip(zip_path)
    except ValueError:
        broken = zip_path.with_name(BROKEN_PREFIX + zip_path.name)
        zip_path.rename(broken)
        with _lock:
            run["broken"].append(broken.name)
        return {"status": "broken", "name": broken.name}
    count = len(moodle_ingest.participants_in(zip_path))
    with _lock:
        run["ok"].append(zip_path.name)
    return {"status": "ok", "name": zip_path.name, "participants": count, "expected": expect}


def finish(mid: str, stage: str, users: str, submitted: str, parts: str, error: str) -> None:
    def number(v):
        return int(v) if str(v).isdigit() else None
    with _lock:
        run = _runs.setdefault(str(mid), {"started": time.time(), "ok": [], "broken": [], "sizes": {}})
        run.update({"finished": True, "stage": stage, "users": number(users), "submitted": number(submitted),
                    "parts": number(parts) or 0, "error": error[:300]})
