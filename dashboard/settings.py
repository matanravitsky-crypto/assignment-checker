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


def save_env(key: str, value: str) -> None:
    """כותב (או מחליף) שורה KEY=value ב-.env, ומעדכן גם את משתנה הסביבה בתהליך הזה."""
    env = REPO_DIR / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    lines = [ln for ln in lines if ln.split("=", 1)[0].strip() != key] + [f"{key}={value}"]
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value


def claude_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None
