"""הגדרות המערכת.

שני מקומות, בכוונה:
  * "הגדרות.json" בתיקיית OneDrive: קורסים, מטלות ומזהים במודל. משותף לכל הצוות,
    ולכן אסור שיהיו בו סודות.
  * ".env" בתיקיית הריפו במחשב: הטוקן של מודל ומפתח Claude. לא עולה ל-GitHub
    (מופיע ב-.gitignore) ולא ל-OneDrive.

דוגמה ל-הגדרות.json:
{
  "moodle_url": "https://moodle.bgu.ac.il",
  "courses": [
    {
      "name": "אלגברה לינארית 1",
      "moodle_course_id": 12345,
      "moodle_shortname": "ALG1",
      "assignments": [
        {"name": "תרגיל בית 1", "moodle_assign_id": 678, "due": "2026-11-05T23:59", "questions": 4}
      ]
    }
  ]
}
moodle_course_id: המספר שמופיע בכתובת של הקורס במודל (course/view.php?id=12345).
moodle_assign_id: מזהה המטלה. אם יש טוקן, המערכת ממלאת אותו לבד מתוך מודל.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

SETTINGS_FILE = "הגדרות.json"
REPO_DIR = Path(__file__).resolve().parent.parent


@dataclass
class AssignmentCfg:
    name: str
    moodle_assign_id: int | None = None
    moodle_cmid: int | None = None
    due: str | None = None
    questions: int = 4
    last_pulled: str | None = None  # מתי לחצו "משוך הגשות" בפעם האחרונה

    @property
    def due_dt(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.due) if self.due else None
        except ValueError:
            return None


@dataclass
class CourseCfg:
    name: str
    moodle_course_id: int | None = None
    moodle_shortname: str | None = None
    assignments: list[AssignmentCfg] = field(default_factory=list)

    def assignment(self, name: str) -> AssignmentCfg | None:
        return next((a for a in self.assignments if a.name == name), None)


@dataclass
class Settings:
    moodle_url: str = "https://moodle.bgu.ac.il"
    courses: list[CourseCfg] = field(default_factory=list)

    def course(self, name: str) -> CourseCfg | None:
        return next((c for c in self.courses if c.name == name), None)

    def ensure_course(self, name: str) -> CourseCfg:
        c = self.course(name)
        if not c:
            c = CourseCfg(name=name)
            self.courses.append(c)
        return c


def default_settings() -> Settings:
    return Settings(courses=[
        CourseCfg(name="אלגברה לינארית 1", assignments=[AssignmentCfg(name=f"תרגיל בית {i}") for i in range(1, 5)]),
    ])


def load(root: Path) -> Settings:
    path = root / SETTINGS_FILE
    if not path.exists():
        return default_settings()
    raw = json.loads(path.read_text(encoding="utf-8"))
    courses = [
        CourseCfg(
            name=c["name"],
            moodle_course_id=c.get("moodle_course_id"),
            moodle_shortname=c.get("moodle_shortname"),
            assignments=[AssignmentCfg(**{k: v for k, v in a.items() if k in AssignmentCfg.__dataclass_fields__}) for a in c.get("assignments", [])],
        )
        for c in raw.get("courses", [])
    ]
    return Settings(moodle_url=raw.get("moodle_url", Settings.moodle_url), courses=courses)


def save(root: Path, s: Settings) -> None:
    path = root / SETTINGS_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------- סודות (במחשב בלבד) ----------
def load_env() -> None:
    """טוען את .env מתיקיית הריפו לתוך משתני הסביבה, בלי לדרוס משתנים שכבר מוגדרים."""
    env = REPO_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def moodle_token() -> str | None:
    return os.environ.get("MOODLE_TOKEN") or None


def claude_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None
