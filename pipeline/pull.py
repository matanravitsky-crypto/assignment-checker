"""שלב 1: משיכת הגשות לתיקיית OneDrive.

מה קורה בכל משיכה:
  1. קוראים את ההגשות מהמקור: קובץ ZIP שהורד ממודל, או הגשות הדגמה.
  2. כל הגשה נשמרת בתיקייה משלה ב-"1-הגשות". הגשה שלא השתנתה לא נכתבת שוב.
  3. בודקים שכל קובץ תקין: נפתח, לא ריק, ומסוג שאפשר לבדוק.
  4. מעדכנים את ציונים.xlsx: שורה חדשה לכל סטודנט חדש, בלי לגעת במה שהצוות כתב.
  5. כותבים ליומן מה נעשה.
OneDrive מעלה את כל השינויים לענן לבד.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pymupdf

from . import config
from .gradebook import GradeBook, fmt_time
from .moodle_zip import read_zip
from .workspace import Submission, Workspace

CHECKABLE = {".pdf", ".jpg", ".jpeg", ".png", ".heic"}


@dataclass
class PullResult:
    total: int = 0
    new: int = 0
    updated: int = 0
    same: int = 0
    problems: list[str] = field(default_factory=list)
    zips: list[str] = field(default_factory=list)

    def summary(self) -> str:
        def count(n, one, many):
            return one if n == 1 else f"{n} {many}"
        if not self.total:
            return "לא נמצאו הגשות"
        parts = [count(self.total, "הגשה אחת", "הגשות")]
        if self.new:
            parts.append(count(self.new, "חדשה אחת", "חדשות"))
        if self.updated:
            parts.append(count(self.updated, "אחת עודכנה", "עודכנו"))
        if self.same and (self.new or self.updated):
            parts.append(count(self.same, "אחת בלי שינוי", "בלי שינוי"))
        if self.problems:
            parts.append(count(len(self.problems), "אחת דורשת טיפול", "דורשות טיפול"))
        return ", ".join(parts)


def inspect(sub: Submission, due: datetime | None) -> None:
    """ממלא את מספר העמודים ואת רשימת הבעיות של ההגשה."""
    sub.pages, sub.issues = 0, []
    if not sub.files:
        sub.issues.append("אין קבצים בהגשה")
    for f in sub.files:
        ext = Path(f.name).suffix.lower()
        if not f.data:
            sub.issues.append(f"הקובץ {f.name} ריק")
        elif ext == ".pdf":
            try:
                with pymupdf.open(stream=f.data, filetype="pdf") as doc:
                    if doc.page_count == 0:
                        sub.issues.append(f"הקובץ {f.name} ריק")
                    sub.pages += doc.page_count
            except Exception:
                sub.issues.append(f"הקובץ {f.name} לא נפתח")
        elif ext in CHECKABLE:
            sub.pages += 1
        elif ext not in {".html", ".txt"}:
            sub.issues.append(f"סוג קובץ שאי אפשר לבדוק: {f.name}")
    if due and sub.submitted_at and sub.submitted_at > due:
        sub.issues.append("הוגשה באיחור")


def import_submissions(ws: Workspace, subs: list[Submission], due: datetime | None = None, questions: int = 4) -> PullResult:
    ws.ensure()
    book = GradeBook(ws.grades_path, questions)
    res = PullResult(total=len(subs))
    for sub in subs:
        inspect(sub, due)
        change = ws.store(sub)
        setattr(res, change, getattr(res, change) + 1)
        blocking = [i for i in sub.issues if i != "הוגשה באיחור"]
        if blocking:
            res.problems.append(f"{sub.name}: {'; '.join(blocking)}")
        book.upsert(sub.moodle_id, {
            "שם מלא": sub.name,
            "ת״ז": sub.student_id or None,
            "מייל": sub.email or None,
            "הוגשה": fmt_time(sub.submitted_at),
            "קבצים": ", ".join(f.name for f in sub.files),
            "עמודים": sub.pages,
            "הערות מערכת": "; ".join(sub.issues) or None,
        }, change, problem=bool(blocking))
    book.save()
    return res


def pull_zip(ws: Workspace, zip_path: Path, due: datetime | None = None, questions: int = 4, move: bool = False) -> PullResult:
    """קולט ZIP אחד של מודל. move=True מעביר אותו אחר כך ל-"0-קליטה/נקלטו"."""
    subs = read_zip(zip_path)
    res = import_submissions(ws, subs, due, questions)
    res.zips.append(zip_path.name)
    ws.log(f"נקלט {zip_path.name}: {res.summary()}")
    for p in res.problems:
        ws.log(f"  דורשת טיפול: {p}")
    if move:
        done = ws.inbox / config.INBOX_DONE
        done.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        shutil.move(str(zip_path), str(done / f"{stamp} {zip_path.name}"))
    return res


def pull_inbox(ws: Workspace, due: datetime | None = None, questions: int = 4) -> PullResult:
    """קולט את כל קובצי ה-ZIP שמחכים בתיקייה "0-קליטה"."""
    ws.ensure()
    total = PullResult()
    for zip_path in sorted(ws.inbox.glob("*.zip")):
        r = pull_zip(ws, zip_path, due, questions, move=True)
        for k in ("total", "new", "updated", "same"):
            setattr(total, k, getattr(total, k) + getattr(r, k))
        total.problems += r.problems
        total.zips += r.zips
    if not total.zips:
        ws.log("משיכה: אין קובצי ZIP חדשים בתיקיית הקליטה")
    return total
