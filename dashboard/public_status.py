"""לוח מספרים ציבורי: כל מי שפותח את האתר רואה מה נעשה, מכל מחשב או טלפון, בלי להתקין כלום (מתן, 2026-11-03:
"רק מספרים, לכולם").

האתר הציבורי לא מחזיק נתונים, וקבצי הסטודנטים נשארים ב-OneDrive של האוניברסיטה. מחשב אחד שהמערכת רצה בו (זה שיש
ב-.env שלו PUBLIC_STATUS_GIST, ו-gh מחובר בו ל-GitHub) מפרסם סיכום של מספרים בלבד ל-gist, והאתר קורא אותו כשאין
במחשב של הצופה מערכת (website/app.js, PUBLIC_STATUS_URL).

מה יש בסיכום: שמות הקורסים והמטלות, מועד ההגשה, כמה הגשות נמשכו, נבדקו, מחכות לבדיקה ידנית, אושרו והוחזרו למודל,
מתי, ומי מהצוות אחראי על המשיכה ועל ההחזרה. מה אין בו: מספרי הגשות, ציונים, ממוצעים, הערות, העתקות, קבצים, ושום
דבר על סטודנט מסוים. הבדיקה בודקת את זה (tests/dashboard/test_public_status.py).

מתי: כל PUBLISH_CHECK_S בודקים את החתימה הזולה של התיקייה (actions.changes). רק כשהיא השתנתה בונים את הסיכום,
ומפרסמים רק כשהמספרים השתנו, או פעם ב-HEARTBEAT_S בלי שינוי, כדי שהאתר יידע שהמחשב חי ויציג "עודכן לפני...".
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

PUBLISH_CHECK_S = 120
HEARTBEAT_S = 60 * 60
FILE = "status.json"
GH_PATHS = (r"C:\Program Files\GitHub CLI\gh.exe",)
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def gist_id() -> str:
    return os.environ.get("PUBLIC_STATUS_GIST", "").strip()


def find_gh() -> str | None:
    return shutil.which("gh") or next((p for p in GH_PATHS if Path(p).is_file()), None)


def _owner(a: dict, stage: str) -> str | None:
    o = (a.get("owners") or {}).get(stage)
    return o.get("who") if isinstance(o, dict) else None


def summary(state: dict) -> dict:
    """המספרים מתוך actions.state, בלי שום דבר על הגשה מסוימת. מטלה ריקה (עוד לא נמשכה) מופיעה רק בשמה."""
    courses = []
    for c in state.get("courses") or []:
        rows = []
        for a in (a for a in state.get("assignments") or [] if a.get("courseId") == c.get("id")):
            subs = a.get("subs") or []
            graded = [s for s in subs if s.get("status") in ("graded", "returned")]
            rows.append({
                "title": a.get("title") or "", "n": a.get("n"), "empty": bool(a.get("empty")), "due": a.get("due"),
                "pulled": len(subs), "graded": len(graded),
                "review": sum(1 for s in subs if s.get("review") and not s.get("approved")),
                "approved": sum(1 for s in subs if s.get("approved")),
                "returned": sum(1 for s in subs if s.get("status") == "returned"),
                "pulledAt": a.get("pulledAt"), "gradedAt": a.get("gradedAt"), "returnedAt": a.get("returnedAt"),
                "pullOwner": _owner(a, "pull"), "returnOwner": _owner(a, "return"),
            })
        courses.append({"name": c.get("name") or "", "assignments": rows})
    return {"courses": courses}


def document(body: dict, by: str, now: datetime) -> str:
    return json.dumps({**body, "publishedAt": now.isoformat(timespec="seconds"), "publishedBy": by},
                      ensure_ascii=False, indent=1)


def publish(gist: str, text: str, run=subprocess.run, gh: str | None = None) -> bool:
    """מחליף את status.json ב-gist (gh api, עם ההתחברות של gh במחשב הזה). False כשלא הצליח: ננסה שוב בסיבוב הבא."""
    gh = gh or find_gh()
    if not gh:
        return False
    payload = json.dumps({"files": {FILE: {"content": text}}}, ensure_ascii=False)
    try:
        p = run([gh, "api", "--method", "PATCH", f"gists/{gist}", "--input", "-"], input=payload.encode("utf-8"),
                capture_output=True, timeout=60, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0


class Publisher:
    """סיבוב אחד בכל פעם (tick). מחזיק את מה שפורסם אחרון, כדי לפרסם רק שינוי או דופק."""

    def __init__(self, gist: str, state, changes, by, publish=publish, clock=datetime.now):
        self.gist, self.state, self.changes, self.by, self._publish, self.clock = gist, state, changes, by, publish, clock
        self.sig: str | None = None
        self.body: dict | None = None
        self.at: datetime | None = None

    def tick(self, root: Path) -> bool:
        """True כשפורסם עכשיו."""
        now = self.clock()
        due = self.at is None or (now - self.at).total_seconds() >= HEARTBEAT_S
        sig = self.changes(root)
        if sig == self.sig and not due:
            return False
        body = summary(self.state(root))
        if body == self.body and not due:
            self.sig = sig
            return False
        if not self._publish(self.gist, document(body, self.by(), now)):
            return False  # החתימה לא נשמרת: בסיבוב הבא מנסים שוב
        self.sig, self.body, self.at = sig, body, now
        return True


def start() -> threading.Thread | None:
    """תהליכון ברקע של השרת, רק במחשב שיש ב-.env שלו PUBLIC_STATUS_GIST."""
    gist = gist_id()
    if not gist:
        return None
    from . import actions

    pub = Publisher(gist, actions.state, actions.changes, lambda: actions.me()["name"])

    def loop() -> None:
        sleeper = threading.Event()
        while True:
            try:
                root, _ = actions.root_info()
                if root:
                    pub.tick(root)
            except Exception:  # noqa: BLE001 - פרסום שנכשל לא מפיל את השרת
                pass
            sleeper.wait(PUBLISH_CHECK_S)

    t = threading.Thread(target=loop, name="public-status", daemon=True)
    t.start()
    return t
