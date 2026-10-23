"""משיכה בחלקים: מחכים בתיקיית ההורדות לחלקים שהסקריפט בלשונית של מודל (moodle/parts.js) שומר שם.

הדף של מודל לא יכול לפנות לשרת במחשב (מדיניות האבטחה של מודל חוסמת http://127.0.0.1), ולכן הכל עובר דרך
תיקיית ההורדות: הסקריפט בודק בעצמו שכל ZIP שלם לפני שהוא שומר אותו, ובסוף שומר קובץ סיכום
"ECS pull <מזהה מטלה> <מזהה ריצה>.json" עם הגודל וכמה סטודנטים בכל חלק (מספרים בלבד).
כאן מחכים לקובץ הזה, ומחזירים את ה-ZIPים שהגודל שלהם מתאים לחלקים שבסיכום. 7-Zip בודק אותם שוב ב-ingest.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Callable

from moodle import ingest as moodle_ingest

SCRIPT = Path(__file__).resolve().parents[1] / "moodle" / "parts.js"
POLL_S = 5.0  # כל כמה שניות מסתכלים בתיקיית ההורדות
WAIT_S = 90 * 60  # הכי הרבה שמחכים לכל החלקים (מטלה של 1,000 סטודנטים: 20 חלקים)
STALL_S = 20 * 60  # בלי שום שינוי בתיקיית ההורדות כל הזמן הזה: הלשונית נסגרה או נתקעה
SETTLE_S = 3 * 60  # אחרי הסיכום: עד כמה מחכים שכרום יסיים לכתוב את החלקים


class PartsError(Exception):
    """ההורדה בחלקים לא הסתיימה. ההודעה בעברית, בלי שמות."""


def new_run() -> str:
    """מזהה ריצה: ספרות בלבד, כי הוא נכנס להנחיה של Claude ולשם קובץ הסיכום."""
    return str(secrets.randbelow(90_000_000) + 10_000_000)


def summary_name(mid: str, run: str) -> str:
    return f"ECS pull {mid} {run}.json"


def plan_name(mid: str, run: str) -> str:
    """הקובץ שהסקריפט שומר מיד אחרי שאסף מי הגיש: כמה סטודנטים וכמה חלקים, בשביל מד ההתקדמות."""
    return f"ECS pull {mid} {run} plan.json"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # עוד לא שם, או שכרום עוד כותב אותו


def count_students(zip_path: Path) -> int:
    return len(moodle_ingest.participants_in(zip_path))


def _students(zips: list[Path], cache: dict) -> int:
    """כמה סטודנטים יש בחלקים שכבר הגיעו (7-Zip מונה את התיקיות). חלק שכרום עוד כותב לא נספר עדיין."""
    total = 0
    for p in zips:
        try:
            key = (p.name, p.stat().st_size)
            if key not in cache:
                cache[key] = count_students(p)
            total += cache[key]
        except Exception:
            continue
    return total


def _zips(mid: str, downloads: Path, since: float) -> list[Path]:
    pattern = re.compile(rf"-{re.escape(str(mid))}( \(\d+\))?$")
    return [p for p in downloads.glob("*.zip") if pattern.search(p.stem) and moodle_ingest._mtime(p) >= since - 2]


def _snapshot(mid: str, downloads: Path, since: float) -> tuple:
    """מה השתנה בתיקיית ההורדות מאז שהמשיכה התחילה: ZIPים של המטלה והורדות שכרום עוד כותב."""
    zips = sorted((p.name, p.stat().st_size) for p in _zips(mid, downloads, since) if p.exists())
    partial = sorted(p.name for p in downloads.glob("*.crdownload") if moodle_ingest._mtime(p) >= since - 2)
    return tuple(zips), tuple(partial)


def match(summary: dict, mid: str, downloads: Path, since: float) -> list[Path] | None:
    """ה-ZIP של כל חלק שבסיכום, לפי הגודל המדויק שלו, או None כל עוד חסר אחד (כרום עוד כותב)."""
    free = sorted(_zips(mid, downloads, since), key=moodle_ingest._mtime)
    found = []
    for part in summary.get("parts") or []:
        same = [p for p in free if p.exists() and p.stat().st_size == part.get("size")]
        if not same:
            return None
        found.append(same[0])
        free.remove(same[0])
    return found


def wait(mid: str, run: str, since: float, downloads: Path | None = None, keep_alive: Callable[[], None] = lambda: None,
         sleep: Callable[[float], None] = time.sleep,
         on_progress: Callable[[int, int | None], None] = lambda done, total: None) -> tuple[list[Path], dict]:
    """מחכה לקובץ הסיכום של הריצה, ומחזיר (ה-ZIPים של החלקים, הסיכום). keep_alive נקרא בכל סיבוב (מחדש את הנעילה).

    on_progress(כמה סטודנטים כבר הגיעו, מתוך כמה או None כל עוד הסקריפט לא שמר את התוכנית) נקרא בכל סיבוב."""
    mid = str(mid)
    downloads = downloads or moodle_ingest.downloads_dir()
    path, plan_path = downloads / summary_name(mid, run), downloads / plan_name(mid, run)
    start = last_change = time.monotonic()
    seen = None
    summary, summary_at, plan, counted = None, None, None, {}
    while True:
        keep_alive()
        now = time.monotonic()
        if plan is None:
            plan = _read_json(plan_path)
        if summary is None:
            summary = _read_json(path)
            summary_at = now if summary is not None else None
        total = (plan or summary or {}).get("users") or None
        on_progress(min(_students(_zips(mid, downloads, since), counted), total or 10**9), total)
        if summary is not None:
            if summary.get("stage") != "done":
                _forget(path, plan_path)
                raise PartsError(_stopped(summary.get("error") or ""))
            zips = match(summary, mid, downloads, since)
            if zips:
                _forget(path, plan_path)  # שלנו, בלי נתונים של סטודנטים
                return zips, summary
            if now - summary_at > SETTLE_S:
                raise PartsError("ההורדה בחלקים הסתיימה, אבל לא כל החלקים נמצאו בתיקיית ההורדות. מושכים שוב.")
        else:
            snap = _snapshot(mid, downloads, since)
            if snap != seen:
                seen, last_change = snap, now
            if now - start > WAIT_S or now - last_change > STALL_S:
                raise PartsError("ההורדה בחלקים לא הסתיימה בזמן (אולי הלשונית של מודל נסגרה, או שכרום שואל אם "
                                 "לאפשר למודל להוריד כמה קבצים: עונים \"אפשר\"). מושכים שוב.")
        sleep(POLL_S)


def _forget(*files: Path) -> None:
    for f in files:
        f.unlink(missing_ok=True)


def _stopped(error: str) -> str:
    if error == "needs_login":
        return "מודל ביקש להתחבר מחדש באמצע ההורדה. מתחברים למודל בכרום ומושכים שוב."
    if error == "no_submissions":
        return "במודל אין עדיין אף הגשה במטלה הזו."
    return f"ההורדה בחלקים נעצרה ({error or 'לא ידוע'}). מושכים שוב."
