"""A lock file in the shared folder, so two people don't run the same step on one assignment at once.

The lock is a small text file that says who took it. Its modification time says since when: a lock
that was not refreshed for LOCK_MINUTES counts as stuck (a crashed run) and is ignored. Pull and
upload use it, each with its own file name.
"""

import getpass
import socket
from datetime import datetime, timedelta
from pathlib import Path

LOCK_MINUTES = 30
SOMEONE_ELSE = "מישהו אחר"  # shown when the lock file is empty


class Locked(Exception):
    """Someone else holds a fresh lock. `who` is what their lock file says, `since` its last update."""

    def __init__(self, who: str, since: datetime):
        super().__init__(f"locked by {who} since {since:%H:%M}")
        self.who = who
        self.since = since


def me() -> str:
    return f"{getpass.getuser()} ({socket.gethostname()})"


def take(folder: Path, name: str, minutes: int = LOCK_MINUTES) -> Path:
    """Write my lock into folder/name. Raises Locked if someone else's lock is fresher than `minutes`."""
    lock = folder / name
    if lock.exists():
        since = datetime.fromtimestamp(lock.stat().st_mtime)
        who = lock.read_text(encoding="utf-8").strip() or SOMEONE_ELSE
        if datetime.now() - since < timedelta(minutes=minutes) and who != me():
            raise Locked(who, since)
    lock.write_text(me(), encoding="utf-8")
    return lock


def refresh(lock: Path) -> None:
    """Write my name again so the lock's modification time moves (a long run keeps its lock alive)."""
    lock.write_text(me(), encoding="utf-8")
