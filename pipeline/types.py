"""מבני הנתונים של הגשה, כפי שהיא מגיעה ממודל (לפני המספור)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


@dataclass
class SubmittedFile:
    name: str
    data: bytes | None = None
    read: Callable[[], bytes] | None = None  # קריאה מאוחרת מתוך ZIP גדול, סטודנט אחד בכל פעם

    def content(self) -> bytes:
        if self.data is None and self.read is not None:
            return self.read()
        return self.data or b""


@dataclass
class Submission:
    moodle_id: str              # מזהה המשתתף במודל
    name: str                   # השם נשמר רק בטבלת המפתח
    files: list[SubmittedFile]
    submitted_at: datetime | None = None
    folder: str = ""            # שם התיקייה המקורית ב-ZIP של מודל
    student_id: str = ""
    email: str = ""
    issues: list[str] = field(default_factory=list)
