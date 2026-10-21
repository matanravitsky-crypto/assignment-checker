"""קריאת קובץ ה-ZIP שמודל מוריד ב-"הורדת כל ההגשות" (Download all submissions).

מודל שם כל הגשה באחת משתי צורות, תלוי באפשרות "הורדת הגשות בתיקיות":
  בתיקיות:   "נועה כהן_123456_assignsubmission_file/hw3.pdf"
  בלי:       "נועה כהן_123456_assignsubmission_file_hw3.pdf"
המספר (123456) הוא מזהה המשתתף במודל, והוא המפתח של הסטודנט אצלנו.
הגשת טקסט מקוון מגיעה כ-"..._assignsubmission_onlinetext/onlinetext.html".
"""
from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

from .workspace import Submission, SubmittedFile

_ENTRY = re.compile(r"^(?P<name>.+?)_(?P<pid>\d+)_assignsubmission_(?P<plugin>file|onlinetext)(?:_(?P<fname>.+))?$")


def _decode(info: zipfile.ZipInfo) -> str:
    """שמות בעברית: אם הקובץ לא סומן כ-UTF-8, Python מפענח אותם כ-cp437 ומקבלים ג'יבריש."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def read_zip(path: Path) -> list[Submission]:
    by_id: dict[str, Submission] = {}
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = _decode(info).replace("\\", "/").split("/")
            # הרכיב הראשון בנתיב שנראה כמו הגשה של מודל (לפעמים הכל עטוף בתיקייה נוספת)
            hit = next(((i, m) for i, p in enumerate(parts) if (m := _ENTRY.match(p))), None)
            if not hit:
                continue
            i, m = hit
            rest = parts[i + 1:]
            file_name = "_".join(rest) if rest else (m.group("fname") or "onlinetext.html")
            sub = by_id.setdefault(m.group("pid"), Submission(moodle_id=m.group("pid"), name=m.group("name").strip(), files=[]))
            sub.files.append(SubmittedFile(name=file_name, data=zf.read(info)))
            stamp = datetime(*info.date_time)
            if sub.submitted_at is None or stamp > sub.submitted_at:
                sub.submitted_at = stamp
    return sorted(by_id.values(), key=lambda s: s.name)
