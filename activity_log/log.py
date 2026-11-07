"""The activity log: who did what and when, kept in the shared folder.

Any action can write to it: `record(folder, action, by, **details)`. The folder is usually the assignment folder, and
the log is `<folder>/Activity log/<who>.jsonl`: one JSON object per line, one file per writer, so two computers never
write the same file and OneDrive never keeps one of two versions as a conflict copy. `read` merges every file of the
folder (conflict copies too, without doubles) and returns the entries oldest first.

Every entry has `at` (local time, to the second), `action`, `by` and `pc`; the rest is the action's own details.
Lines are only ever added, never changed or removed. Numbers only: never a student's name, ID or email.
"""
from __future__ import annotations

import json
import os
import socket
import threading
from datetime import datetime
from pathlib import Path

from moodle import claims, paths

FOLDER = paths.ACTIVITY_LOG
_lock = threading.Lock()
_BASE = ("at", "action", "by", "pc")


def file_for(folder: Path, by: str) -> Path:
    """The writer's own log file in this folder."""
    return Path(folder) / FOLDER / f"{claims.file_name(by)}.jsonl"


def record(folder: Path, action: str, by: str, **details) -> dict:
    """Adds one entry to the writer's log file and returns it. Raises OSError when it could not be written."""
    if not action or not isinstance(action, str):
        raise ValueError("action is required")
    entry = {"at": datetime.now().isoformat(timespec="seconds"), "action": action, "by": by,
             "pc": socket.gethostname(), **{k: v for k, v in details.items() if k not in _BASE}}
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    path = file_for(folder, by)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
    return entry


def _lines(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):  # OneDrive in the middle of a sync: the next read gets it
        return
    for raw in text.splitlines():
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:  # a line cut in the middle (the computer went off while writing)
            continue
        if isinstance(entry, dict) and entry.get("action"):
            yield raw, entry


def read(folder: Path, action: str | None = None, **match) -> list[dict]:
    """Every entry of the folder's log, oldest first. `action` and `match` (field=value) filter them."""
    seen: set[str] = set()
    out: list[dict] = []
    for path in sorted((Path(folder) / FOLDER).glob("*.jsonl")):
        for raw, entry in _lines(path):
            if raw in seen:
                continue
            seen.add(raw)
            if action and entry.get("action") != action:
                continue
            if any(entry.get(k) != v for k, v in match.items()):
                continue
            out.append(entry)
    out.sort(key=lambda e: str(e.get("at") or ""))
    return out
