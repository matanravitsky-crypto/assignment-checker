"""שלב 1: קליטת הגשות למבנה של הצוות, ממוספרות ובלי שמות.

לכל הגשה:
  1. כל הקבצים של הסטודנט מאוחדים ל-PDF אחד (תמונות של דפים נהפכות לעמודים).
  2. סטודנט שכבר יש לו מספר בטבלת המפתח שומר עליו. סטודנט חדש מקבל את המספר הבא.
  3. הקובץ נשמר ב-"1 - Submissions to grade" בשם <מספר>.pdf, ושורה נכתבת לטבלת המפתח.
  4. הגשה שלא השתנתה לא נכתבת שוב. הגשה שהשתנתה אחרי שכבר נבדקה מסומנת.
  5. קובץ ריק או פגום לא מקבל מספר, ומדווח (לפי מזהה המשתתף, בלי שם).
"""
from __future__ import annotations

import hashlib
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pymupdf

from .moodle_zip import read_zip
from .team import HASH_COLUMN, INBOX_DONE, SUBMISSIONS, Assignment
from .types import Submission

IMAGES = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".heic": "heic", ".bmp": "bmp", ".tif": "tiff", ".tiff": "tiff"}


@dataclass
class PullResult:
    total: int = 0
    new: int = 0
    updated: int = 0
    same: int = 0
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    zips: list[str] = field(default_factory=list)

    def add(self, other: "PullResult") -> None:
        for k in ("total", "new", "updated", "same"):
            setattr(self, k, getattr(self, k) + getattr(other, k))
        self.problems += other.problems
        self.notes += other.notes
        self.zips += other.zips

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


def single_pdf(sub: Submission) -> tuple[bytes | None, list[str]]:
    """מאחד את כל הקבצים של ההגשה ל-PDF אחד. מחזיר (None, בעיות) אם אין מה לבדוק."""
    issues: list[str] = []
    usable = []
    for f in sub.files:
        ext = Path(f.name).suffix.lower()
        data = f.content()  # נקרא עכשיו ומשתחרר בסוף הפונקציה, לא נשמר על ההגשה
        if not data:
            issues.append(f"קובץ ריק ({f.name})")
        elif ext == ".pdf":
            try:
                with pymupdf.open(stream=data, filetype="pdf") as d:
                    if d.page_count:
                        usable.append(("pdf", f.name, data))
                    else:
                        issues.append(f"PDF בלי עמודים ({f.name})")
            except Exception:
                issues.append(f"PDF פגום ({f.name})")
        elif ext in IMAGES:
            usable.append(("img", f.name, data))
        elif ext in (".html", ".txt"):
            issues.append("טקסט מקוון לא נקלט, רק קבצים")
        else:
            issues.append(f"סוג קובץ שאי אפשר לבדוק ({f.name})")
    if not usable:
        return None, issues or ["אין קבצים בהגשה"]
    if len(usable) == 1 and usable[0][0] == "pdf":
        return usable[0][2], issues  # PDF יחיד נשמר בדיוק כפי שהוגש
    out = pymupdf.open()
    for kind, name, data in sorted(usable, key=lambda x: x[1]):
        try:
            if kind == "pdf":
                with pymupdf.open(stream=data, filetype="pdf") as d:
                    out.insert_pdf(d)
            else:
                with pymupdf.open(stream=data, filetype=IMAGES[Path(name).suffix.lower()]) as img:
                    with pymupdf.open("pdf", img.convert_to_pdf()) as d:
                        out.insert_pdf(d)
        except Exception:
            issues.append(f"לא הצלחתי לצרף את {name}")
    if not out.page_count:
        return None, issues
    merged = out.tobytes(garbage=3, deflate=True)
    out.close()
    return merged, issues


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def import_submissions(asg: Assignment, subs: list[Submission]) -> PullResult:
    asg.submissions.mkdir(parents=True, exist_ok=True)
    rows = asg.key_rows()
    by_pid = {r.get("participant_id"): r for r in rows}
    width = asg.number_width(rows)
    next_no = max((int(r["number"]) for r in rows if r.get("number", "").isdigit()), default=0) + 1
    graded = asg.graded_numbers()
    due = asg.due
    res = PullResult(total=len(subs))

    for sub in sorted(subs, key=lambda s: (s.submitted_at or datetime.min, s.moodle_id)):
        who = f"משתתף {sub.moodle_id}"
        pdf, issues = single_pdf(sub)
        if pdf is None:
            res.problems.append(f"{who}: {'; '.join(issues)}")
            continue
        late = bool(due and sub.submitted_at and sub.submitted_at > due)
        digest = _hash(pdf)
        row = by_pid.get(sub.moodle_id)
        original = ", ".join(f.name for f in sub.files)

        if row:
            target = asg.submissions / row["anon_file"]
            if _unchanged(target, row, pdf, digest):
                res.same += 1
                if not row.get(HASH_COLUMN):
                    row[HASH_COLUMN] = digest
                continue
            target.write_bytes(pdf)
            row.update({"original_file": original, HASH_COLUMN: digest})
            res.updated += 1
            if row["number"] in graded:
                res.notes.append(f"הגשה {row['number']} הוגשה מחדש אחרי שכבר נבדקה")
            label = row["number"]
        else:
            number = str(next_no).zfill(width)
            next_no += 1
            anon = f"{number}.pdf"
            (asg.submissions / anon).write_bytes(pdf)
            row = {"number": number, "anon_file": anon, "participant_id": sub.moodle_id,
                   "original_folder": sub.folder or f"{sub.name}_{sub.moodle_id}_assignsubmission_file",
                   "original_file": original, HASH_COLUMN: digest}
            rows.append(row)
            by_pid[sub.moodle_id] = row
            res.new += 1
            label = number
        if late:
            res.notes.append(f"הגשה {label} הוגשה באיחור")
        for issue in issues:
            res.notes.append(f"הגשה {label}: {issue}")

    asg.save_key(rows)
    return res


def _unchanged(target: Path, row: dict, pdf: bytes, digest: str) -> bool:
    if not target.exists():
        return False
    if row.get(HASH_COLUMN):
        return row[HASH_COLUMN] == digest  # בלי לפתוח את הקובץ (שאולי יושב רק בענן)
    if target.stat().st_size != len(pdf):
        return False
    return target.read_bytes() == pdf


def pull_zip(asg: Assignment, zip_path: Path, move: bool = True) -> PullResult:
    """קולט ZIP של "הורדת כל ההגשות". move=True מעביר אותו אחר כך ל-Imported."""
    with zipfile.ZipFile(zip_path) as zf:
        res = import_submissions(asg, read_zip(zf))
    res.zips.append(zip_path.name)
    asg.log(f"נקלט {zip_path.name}: {res.summary()}")
    for p in res.problems:
        asg.log(f"  דורשת טיפול: {p}")
    if move:
        done = asg.inbox / INBOX_DONE
        done.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        shutil.move(str(zip_path), str(done / f"{stamp} {zip_path.name}"))
    return res


def waiting_zips(asg: Assignment) -> list[Path]:
    """קובצי ZIP שמחכים בתיקייה "0 - Moodle download" של המטלה.

    רק שם. ZIP שמונח במקום אחר (למשל ההורדה המקורית של אורי בתיקיית המטלה) לא נקרא ולא זז.
    """
    return sorted(asg.inbox.glob("*.zip")) if asg.inbox.is_dir() else []


__all__ = ["PullResult", "import_submissions", "pull_zip", "single_pdf", "waiting_zips", "SUBMISSIONS"]
