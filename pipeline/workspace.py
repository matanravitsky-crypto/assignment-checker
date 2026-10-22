"""התיקייה של מטלה אחת בתוך OneDrive, והשמירה של הגשות לתוכה.

המבנה:
    YallaLinearit/
      <קורס>/
        <מטלה>/
          0-קליטה/            קובצי ZIP שהורדו ממודל מחכים כאן
            נקלטו/            אחרי הקליטה הם עוברים לכאן
          1-הגשות/
            <שם הסטודנט> (<מזהה במודל>)/   הקבצים המקוריים של הסטודנט
          2-נבדקו/            PDF מסומן אחרי הבדיקה (שלב הבדיקה)
          3-הוחזרו/           מה שכבר עלה חזרה למודל (שלב ההחזרה)
          ציונים.xlsx         שורה לכל סטודנט: מצב, ניקוד, ציון, משוב, אישור
          יומן.txt            כל פעולה שהמערכת עשתה, עם תאריך ושעה
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config


@dataclass
class SubmittedFile:
    name: str
    data: bytes


@dataclass
class Submission:
    """הגשה אחת של סטודנט, כפי שהגיעה ממודל."""
    moodle_id: str
    name: str
    files: list[SubmittedFile]
    submitted_at: datetime | None = None
    student_id: str = ""
    email: str = ""
    issues: list[str] = field(default_factory=list)
    pages: int = 0


_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str) -> str:
    """שם שמותר בתיקיות של Windows ו-OneDrive."""
    cleaned = _BAD_CHARS.sub("_", name).strip().rstrip(".")
    return cleaned or "ללא שם"


class Workspace:
    def __init__(self, root: Path, course: str, assignment: str):
        self.root = root
        self.course = course
        self.assignment = assignment
        self.dir = root / safe_name(course) / safe_name(assignment)

    # ---------- מבנה ----------
    @property
    def inbox(self) -> Path:
        return self.dir / config.INBOX

    @property
    def submissions(self) -> Path:
        return self.dir / config.SUBMISSIONS

    @property
    def grades_path(self) -> Path:
        return self.dir / config.GRADES_FILE

    def ensure(self) -> None:
        """יוצר את כל התיקיות של המטלה, אם הן עוד לא קיימות."""
        for sub in (config.INBOX, f"{config.INBOX}/{config.INBOX_DONE}", config.SUBMISSIONS, config.CHECKED, config.RETURNED):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)

    def student_dir(self, sub: Submission) -> Path:
        return self.submissions / f"{safe_name(sub.name)} ({sub.moodle_id})"

    # ---------- שמירת הגשה ----------
    def store(self, sub: Submission) -> str:
        """שומר את קבצי ההגשה בתיקייה של הסטודנט.

        מחזיר "new" להגשה חדשה, "updated" אם הקבצים השתנו מאז הקליטה הקודמת,
        ו-"same" אם לא השתנה כלום (ואז לא נוגעים בקבצים).
        """
        target = self.student_dir(sub)
        existed = target.is_dir()
        old = _fingerprint(target) if existed else None
        named = sorted(((safe_name(f.name), f.data) for f in sub.files), key=lambda x: x[0])
        new = hashlib.sha256(b"".join(n.encode() + d for n, d in named)).hexdigest()
        if old == new:
            return "same"
        if existed:
            for p in target.iterdir():
                if p.is_file():
                    p.unlink()
        target.mkdir(parents=True, exist_ok=True)
        for f in sub.files:
            (target / safe_name(f.name)).write_bytes(f.data)
        return "updated" if existed else "new"

    def log(self, message: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with (self.dir / config.LOG_FILE).open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}  {message}\n")


def _fingerprint(folder: Path) -> str:
    files = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name)
    return hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in files)).hexdigest()
