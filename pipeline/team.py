"""המבנה של הצוות בתיקייה "Exercise Checking System" (כפי שאורי הגדיר).

    Exercise Checking System/
      README.txt                         הסבר וכללים (לא נוגעים)
      <קורס, באנגלית>/                  למשל "Linear Algebra"
        README.txt                       רשימת המטלות בקורס (המערכת מעדכנת את המספרים)
        <מטלה>/                          למשל "Assignment 0 - Sets and Complex Numbers"
          Assignment details.json        מזהה במודל, מזהה קורס, מועד הגשה, שאלות, שם בעברית
          Key - number to student.csv    טבלת המפתח: מספר ↔ סטודנט. רק כאן יש שמות
          0 - Moodle download/           ZIP של "הורדת כל ההגשות" ממודל (המערכת מוסיפה)
          1 - Submissions to grade/      0001.pdf, 0002.pdf... ממוספרות, בלי שמות
          2 - Graded with comments/      אותו מספר, עם ההערות (שלב הבדיקה)
          3 - Ready to upload to Moodle/ מה שמוכן להעלאה (שלב ההחזרה)
          System log.txt                 מה המערכת עשתה ומתי (בלי שמות)

הכלל החשוב: שמות של סטודנטים מופיעים רק בטבלת המפתח. כל השאר ממוספר.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SUBMISSIONS = "1 - Submissions to grade"
GRADED = "2 - Graded with comments"
READY = "3 - Ready to upload to Moodle"
INBOX = "0 - Moodle download"
INBOX_DONE = "Imported"
DETAILS = "Assignment details.json"
KEY = "Key - number to student.csv"
LOG = "System log.txt"
KEY_COLUMNS = ["number", "anon_file", "participant_id", "original_folder", "original_file"]
HASH_COLUMN = "content_hash"  # עמודה נוספת של המערכת: מזהה תוכן, כדי לא להוריד קבצים רק כדי להשוות

COURSE_TITLES = {"Linear Algebra": "אלגברה לינארית", "Discrete Mathematics": "מתמטיקה בדידה"}

README_GRADED = ("כאן שמים את העבודות אחרי הבדיקה: העבודה של הסטודנט עם ההערות עליה,\n"
                 "באותו מספר כמו ב\"1 - Submissions to grade\" (למשל 0023.pdf). עד 1-2 MB לקובץ.\n")
README_READY = ("התיקייה מתמלאת אוטומטית כשמכינים העלאה למודל.\n"
                "ההוראות יופיעו כאן בקובץ \"הוראות העלאה.txt\".\n")

_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str) -> str:
    """שם שמותר בתיקיות של Windows ו-OneDrive."""
    return _BAD_CHARS.sub("_", name).strip().rstrip(".") or "ללא שם"


def _write_text(path: Path, text: str, bom: bool = False) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8-sig" if bom else "utf-8")
    tmp.replace(path)


# ---------- מטלה ----------
@dataclass
class Assignment:
    dir: Path

    @property
    def course_dir(self) -> Path:
        return self.dir.parent

    @property
    def submissions(self) -> Path:
        return self.dir / SUBMISSIONS

    @property
    def inbox(self) -> Path:
        return self.dir / INBOX

    # ---- פרטי המטלה ----
    def details(self) -> dict:
        path = self.dir / DETAILS
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return {}

    def save_details(self, data: dict) -> None:
        _write_text(self.dir / DETAILS, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    @property
    def title(self) -> str:
        return self.details().get("title") or self.dir.name

    @property
    def due(self) -> datetime | None:
        raw = self.details().get("due")
        try:
            dt = datetime.fromisoformat(raw) if raw else None
        except ValueError:
            return None
        # השוואה מול זמני הגשה מקומיים (בלי אזור זמן)
        return dt.astimezone().replace(tzinfo=None) if dt and dt.tzinfo else dt

    def question_count(self) -> int:
        qs = self.details().get("questions") or []
        n = sum(len(q.get("numbers") or [None]) for q in qs if isinstance(q, dict))
        return n or 4

    def question_labels(self) -> list[str]:
        out = []
        for q in self.details().get("questions") or []:
            if isinstance(q, dict):
                for num in q.get("numbers") or []:
                    out.append(f"{q.get('sheet', '')} {num}".strip())
        return out

    # ---- טבלת המפתח ----
    def key_rows(self) -> list[dict]:
        path = self.dir / KEY
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    def save_key(self, rows: list[dict]) -> None:
        cols = list(KEY_COLUMNS)
        for r in rows:
            for c in r:
                if c not in cols:
                    cols.append(c)
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\r\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        _write_text(self.dir / KEY, buf.getvalue(), bom=True)

    def number_width(self, rows: list[dict]) -> int:
        return max((len(r["number"]) for r in rows if r.get("number")), default=4)

    # ---- מצב של כל הגשה ----
    def graded_numbers(self) -> set[str]:
        d = self.dir / GRADED
        return {p.stem for p in d.glob("*.pdf")} if d.is_dir() else set()

    def ready_numbers(self) -> set[str]:
        d = self.dir / READY
        return {p.stem for p in d.glob("*.pdf")} if d.is_dir() else set()

    # ---- יומן ----
    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with (self.dir / LOG).open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}  {message}\n")

    def log_lines(self, limit: int = 40) -> list[dict]:
        path = self.dir / LOG
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            stamp, _, text = line.partition("  ")
            try:
                at = datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M").isoformat()
            except ValueError:
                continue
            text = text.strip()
            kind = "error" if ("נכשל" in text or "דורשת טיפול" in text) else "pull"
            out.append({"at": at, "kind": kind, "text": text})
        return out


# ---------- קורסים ומטלות ----------
def courses(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "0 - ")))


def assignments(course_dir: Path) -> list[Assignment]:
    return sorted(
        (Assignment(p) for p in course_dir.iterdir()
         if p.is_dir() and ((p / DETAILS).exists() or (p / SUBMISSIONS).is_dir())),
        key=lambda a: _natural(a.dir.name),
    )


def course_title(course_dir: Path) -> str:
    for a in assignments(course_dir):
        t = a.details().get("course_title")
        if t:
            return t
    return COURSE_TITLES.get(course_dir.name, course_dir.name)


def course_id(course_dir: Path) -> str | None:
    for a in assignments(course_dir):
        cid = a.details().get("course_id")
        if cid:
            return str(cid)
    return None


def _natural(name: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


def create_assignment(course_dir: Path, folder_name: str, details: dict) -> Assignment:
    """מטלה חדשה, באותו מבנה בדיוק כמו המטלות הקיימות."""
    a = Assignment(course_dir / safe_name(folder_name))
    for sub in (SUBMISSIONS, GRADED, READY):
        (a.dir / sub).mkdir(parents=True, exist_ok=True)
    if not (a.dir / GRADED / "README.txt").exists():
        _write_text(a.dir / GRADED / "README.txt", README_GRADED, bom=True)
    if not (a.dir / READY / "README.txt").exists():
        _write_text(a.dir / READY / "README.txt", README_READY, bom=True)
    if not (a.dir / DETAILS).exists():
        a.save_details({
            "id": details.get("id"), "course": course_dir.name, "course_id": details.get("course_id"),
            "name": a.dir.name, "due": details.get("due"), "questions": [], "submission_rules": [],
            "max_grade": None, "rubric": None, "notes": details.get("notes", ""),
            "title": details.get("title") or a.dir.name, "course_title": details.get("course_title") or course_title(course_dir),
        })
    if not (a.dir / KEY).exists():
        a.save_key([])
    return a


def update_course_readme(course_dir: Path) -> None:
    """מעדכן את רשימת המטלות ומספר ההגשות ב-README של הקורס, באותו פורמט."""
    items = assignments(course_dir)
    lines = [course_dir.name, "=" * len(course_dir.name), "", "המטלות בקורס:"]
    if items:
        for a in items:
            n = len(a.key_rows())
            title = a.details().get("title")
            lines.append(f"  - {a.dir.name}" + (f"  ({title})" if title else "") + f": {n} הגשות")
    else:
        lines.append("  עוד אין. כל מטלה שתורד ממודל תקבל כאן תיקייה משלה, באותו מבנה כמו בשאר הקורסים.")
    lines += ["", "בכל תיקיית מטלה יש קובץ README.txt עם הפרטים.", ""]
    _write_text(course_dir / "README.txt", "\n".join(lines), bom=True)
