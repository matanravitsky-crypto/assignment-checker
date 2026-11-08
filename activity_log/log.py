"""The activity log: who did what and when, kept in the shared folder.

Any action can write to it: `record(folder, action, by, **details)`. The folder is usually the assignment folder, and
the log is `<folder>/Activity log/<who>.jsonl`: one JSON object per line, one file per writer, so two computers never
write the same file and OneDrive never keeps one of two versions as a conflict copy. `read` merges every file of the
folder (conflict copies too, without doubles) and returns the entries oldest first.

Every entry has `at` (local time with the zone offset, to the microsecond), `action`, `by`, `pc`, `seq` (this writer's
running number in this folder) and `id` (a sha256 of the entry's content: the same event written twice, or read from a
conflict copy, is one event); the rest is the action's own details. Older entries without `id`/`seq` still read fine.
Lines are only ever added, never changed or removed. Numbers only: never a student's name, ID or email.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
from datetime import datetime
from pathlib import Path

from moodle import claims, paths

FOLDER = paths.ACTIVITY_LOG
_lock = threading.Lock()
_BASE = ("at", "action", "by", "pc", "seq", "id")
_seq: dict[str, int] = {}  # per file, in this process; the first write of a file counts its lines


def _next_seq(path: Path) -> int:
    key = str(path)
    if key not in _seq:
        try:
            _seq[key] = sum(1 for _ in path.open(encoding="utf-8", errors="replace")) if path.exists() else 0
        except OSError:
            _seq[key] = 0
    _seq[key] += 1
    return _seq[key]


def event_id(entry: dict) -> str:
    """A deterministic id for an entry: the same content gives the same id, on any computer."""
    payload = json.dumps({k: v for k, v in entry.items() if k != "id"}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def file_for(folder: Path, by: str) -> Path:
    """The writer's own log file in this folder."""
    return Path(folder) / FOLDER / f"{claims.file_name(by)}.jsonl"


def record(folder: Path, action: str, by: str, **details) -> dict:
    """Adds one entry to the writer's log file and returns it. Raises OSError when it could not be written."""
    if not action or not isinstance(action, str):
        raise ValueError("action is required")
    path = file_for(folder, by)
    with _lock:
        entry = {"at": datetime.now().astimezone().isoformat(timespec="microseconds"), "action": action, "by": by,
                 "pc": socket.gethostname(), "seq": _next_seq(path), **{k: v for k, v in details.items() if k not in _BASE}}
        entry["id"] = event_id(entry)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
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
            key = str(entry["id"]) if entry.get("id") else raw  # the same event in a conflict copy counts once
            if key in seen:
                continue
            seen.add(key)
            if action and entry.get("action") != action:
                continue
            if any(entry.get(k) != v for k, v in match.items()):
                continue
            out.append(entry)
    out.sort(key=lambda e: str(e.get("at") or ""))
    return out
