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
        return self.details().get("title") or self.dir.name

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
        d = self.dir / GRADED
        return {p.stem.split("-")[0] for p in d.glob("*.pdf")} if d.is_dir() else set()


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
