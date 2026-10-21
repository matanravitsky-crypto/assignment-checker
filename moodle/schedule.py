"""Which assignments to download now.

assignments.json (repo root) lists the team's assignments and their due dates.
It holds no student data, so everyone shares it through git. An assignment is
pending once its due date has passed and this computer has no download from
after that date. The scheduled download task asks this, then checks Moodle
itself before downloading: the due date here is a hint, Moodle has the truth.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from moodle import paths

ASSIGNMENTS_FILE = Path(__file__).resolve().parent.parent / "assignments.json"


def load_assignments(path: Path = ASSIGNMENTS_FILE) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        assignments = json.load(f)
    for assignment in assignments:
        assignment["due"] = datetime.fromisoformat(assignment["due"])
    return assignments


def last_download(assignment_id: str, raw_dir: Path) -> datetime | None:
    """When this computer last downloaded the assignment (the ZIP's own time)."""
    zips = list(raw_dir.glob(f"{assignment_id}-*.zip")) if raw_dir.exists() else []
    if not zips:
        return None
    newest = max(z.stat().st_mtime for z in zips)
    return datetime.fromtimestamp(newest, timezone.utc)


def pending(assignments: list[dict], now: datetime | None = None, raw_dir: Path | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    raw_dir = raw_dir or paths.raw_dir()
    due_now = []
    for assignment in assignments:
        if now < assignment["due"]:
            continue
        downloaded = last_download(assignment["id"], raw_dir)
        if downloaded is None or downloaded < assignment["due"]:
            due_now.append(assignment)
    return due_now
