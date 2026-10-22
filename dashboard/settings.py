"""הגדרות שנמצאות רק במחשב שמריץ את המערכת.

מפתח Claude נשמר בקובץ ".env" בתיקיית הריפו. הקובץ לא עולה ל-GitHub (הוא ב-.gitignore)
ולא ל-OneDrive:
    ANTHROPIC_API_KEY=...
למודל אין API: ההורדה וההעלאה נעשות בדפדפן (ראו CLAUDE.md).
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent


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


def claude_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None
