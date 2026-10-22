"""קריאה של המבנה בתיקייה "Exercise Checking System", לתצוגה באתר.

המבנה והשמות מוגדרים במקום אחד, ב-`moodle/paths.py` (הקוד של אורי). כאן רק קוראים:
קורסים, מטלות, פרטי מטלה, טבלת המפתח (רק המספרים) והעבודות המסומנות.
הכתיבה לתיקייה נעשית רק דרך `moodle/` (ingest ו-upload).
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from moodle import paths

SUBMISSIONS = paths.TO_GRADE
GRADED = paths.MARKED
READY = paths.UPLOAD

COURSE_TITLES = {"Linear Algebra": "אלגברה לינארית", "Discrete Mathematics": "מתמטיקה בדידה"}
SLOTS = 10  # בכל קורס עשר הגשות: הגשה 0 עד הגשה 9. מטלה שעוד לא נמשכה מוצגת כמקום ריק


def slot(dir_name: str) -> int | None:
    """"Assignment 3 - Vectors" → 3. תיקייה בלי מספר כזה לא תופסת מקום מהעשרה."""
    m = re.match(r"Assignment (\d+)(?: - |$)", dir_name)
    return int(m.group(1)) if m else None


def slot_folder(n: int) -> str:
    """שם התיקייה של הגשה n שעוד לא נמשכה (באנגלית, כמו כל התיקיות)."""
    return f"Assignment {n}"


def slot_title(n: int) -> str:
    return f"הגשה {n}"


@dataclass
class Assignment:
    dir: Path

    @property
    def submissions(self) -> Path:
        return self.dir / SUBMISSIONS

    def details(self) -> dict:
        path = self.dir / paths.INFO
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return {}

    @property
    def title(self) -> str:
        n = slot(self.dir.name)
        return self.details().get("title") or (slot_title(n) if n is not None else self.dir.name)

    def question_labels(self) -> list[str]:
        out = []
        for q in self.details().get("questions") or []:
            if isinstance(q, dict):
                for num in q.get("numbers") or []:
                    out.append(f"{q.get('sheet', '')} {num}".strip())
        return out

    def question_count(self) -> int:
        return len(self.question_labels()) or 4

    def key_rows(self) -> list[dict]:
        """טבלת המפתח. האתר משתמש רק ב-number וב-anon_file, אף פעם לא בשמות."""
        path = self.dir / paths.KEY
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    def graded_numbers(self) -> set[str]:
        """מספרי ההגשות שיש להן עבודה מסומנת (0001.pdf, וגם 0001-2.pdf שייך ל-0001)."""
        return set(self.marked_files())

    def marked_files(self) -> dict[str, list[Path]]:
        """מספר → הקבצים המסומנים שלו ב-"2 - Graded with comments", לפי הסדר."""
        return files_by_number(self.dir / GRADED, "*.pdf")

    def submission_files(self) -> dict[str, list[Path]]:
        """מספר → הקבצים שהסטודנט הגיש ב-"1 - Submissions to grade": 0001.pdf, 0001-2.jpg..."""
        return files_by_number(self.submissions, "*")


def files_by_number(folder: Path, pattern: str) -> dict[str, list[Path]]:
    """קבצים בשם 0001 או 0001-2 (קובץ נוסף של אותה הגשה), מקובצים לפי המספר ולפי הסדר."""
    out: dict[str, list[tuple[int, Path]]] = {}
    for p in folder.glob(pattern) if folder.is_dir() else []:
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", p.stem)
        if p.is_file() and m:
            out.setdefault(m.group(1), []).append((int(m.group(2) or 1), p))
    return {n: [p for _, p in sorted(files)] for n, files in sorted(out.items())}


def courses(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def assignments(course_dir: Path) -> list[Assignment]:
    return sorted(
        (Assignment(p) for p in course_dir.iterdir() if p.is_dir() and (p / paths.INFO).exists()),
        key=lambda a: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", a.dir.name)],
    )


def course_title(course_dir: Path) -> str:
    for a in assignments(course_dir):
        t = a.details().get("course_title")
        if t:
            return t
    return COURSE_TITLES.get(course_dir.name, course_dir.name)
