"""Who grades which submissions, so the team can split an assignment between them.

Every grader has one file in the assignment's "Who grades what" folder, "<name>.json", and only that grader writes it:
    {"name": "מתן", "numbers": {"0001": "2026-10-23T10:00:00", ...}}    number -> when they took it
One writer per file means OneDrive never has two versions of a file to merge. Everyone reads all the files, and
OneDrive brings a new claim to the others' computers within seconds to a minute.

If two people took the same number before their files synced, whoever took it first keeps it (then by name, so every
computer decides the same way). The other one's file still lists it, but it doesn't count as theirs.

Pulling and returning go by assignment, not by number, so their owner is kept per course, in the course's
"Who does what" folder, again one "<name>.json" per person:
    {"name": "מתן", "tasks": {"3:pull": {"at": "...", "taken": true}, "3:return": {"at": "...", "taken": false}}}
The key is the assignment's slot number ("Assignment 3 - ..." -> "3") and the stage. Every take and every release is
an event, and the latest event of a key, in anyone's file, decides: a take makes that person the owner (so someone
can take over from a teammate who is away), a release leaves it without an owner.

My name: GRADER_NAME (the site saves it in .env), otherwise the Windows user name.
"""

import getpass
import json
import os
import re
from datetime import datetime
from pathlib import Path

from . import paths

_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def me() -> str:
    return (os.environ.get("GRADER_NAME") or "").strip() or getpass.getuser()


def name_set() -> bool:
    """Did this computer get a grader name (and not just the Windows user name)?"""
    return bool((os.environ.get("GRADER_NAME") or "").strip())


def file_name(who: str) -> str:
    """The grader's name as a file name that works on Windows and in OneDrive."""
    return _BAD_CHARS.sub("_", who).strip(" .")[:60] or "grader"


def folder(assignment_dir: Path) -> Path:
    return assignment_dir / paths.CLAIMS


def _path(assignment_dir: Path, who: str) -> Path:
    return folder(assignment_dir) / f"{file_name(who)}.json"


def _read(path: Path) -> tuple[str, dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return str(data.get("name") or path.stem), {str(n): str(at) for n, at in (data.get("numbers") or {}).items()}


def read_all(assignment_dir: Path) -> dict[str, dict]:
    """number -> {"who": name, "at": when they took it}, for every number someone took."""
    held: dict[str, dict] = {}
    if not folder(assignment_dir).is_dir():
        return held
    for path in sorted(folder(assignment_dir).glob("*.json")):
        try:
            who, numbers = _read(path)
        except (OSError, ValueError, AttributeError):  # half-synced or broken: skip it until it is whole
            continue
        for n, at in numbers.items():
            old = held.get(n)
            if old is None or (at, who) < (old["at"], old["who"]):
                held[n] = {"who": who, "at": at}
    return held


def _own(assignment_dir: Path, who: str) -> dict[str, str]:
    """My file as it is. A file that can't be read raises, so a broken read never wipes my claims."""
    path = _path(assignment_dir, who)
    return _read(path)[1] if path.exists() else {}


def _write(assignment_dir: Path, who: str, numbers: dict[str, str]) -> None:
    folder(assignment_dir).mkdir(exist_ok=True)
    path = _path(assignment_dir, who)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"name": who, "numbers": dict(sorted(numbers.items()))}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(path)


def take(assignment_dir: Path, numbers: list[str], who: str | None = None) -> dict:
    """Take the numbers nobody else holds. Returns {"taken": [...], "others": {number: who holds it}}."""
    who = who or me()
    held = read_all(assignment_dir)
    own = _own(assignment_dir, who)
    now = datetime.now().isoformat(timespec="seconds")
    taken, others = [], {}
    for n in numbers:
        holder = held.get(n)
        if holder and holder["who"] != who:
            others[n] = holder["who"]
            continue
        taken.append(n)
    if any(n not in own for n in taken):
        _write(assignment_dir, who, {**{n: now for n in taken}, **own})  # a number I already had keeps its time
    return {"taken": taken, "others": others}


def release(assignment_dir: Path, numbers: list[str], who: str | None = None) -> list[str]:
    """Give back numbers I took. Returns the ones that were mine."""
    who = who or me()
    own = _own(assignment_dir, who)
    dropped = [n for n in numbers if n in own]
    if dropped:
        _write(assignment_dir, who, {n: at for n, at in own.items() if n not in dropped})
    return dropped


# ---------- pull, return, rubric, review: an owner per assignment, kept in the course folder ----------
STAGES = ("pull", "return", "rubric", "review")


def task_key(assignment_folder: str, stage: str) -> str:
    """("Assignment 3 - Vectors", "pull") -> "3:pull". A folder without a slot number keeps its whole name."""
    m = re.match(r"Assignment (\d+)(?: - |$)", assignment_folder)
    return f"{m.group(1) if m else assignment_folder}:{stage}"


def _task_path(course_dir: Path, who: str) -> Path:
    return course_dir / paths.TASKS / f"{file_name(who)}.json"


def _read_tasks(path: Path) -> tuple[str, dict[str, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = {str(k): v for k, v in (data.get("tasks") or {}).items() if isinstance(v, dict) and v.get("at")}
    return str(data.get("name") or path.stem), tasks


def task_owners(course_dir: Path) -> dict[str, dict]:
    """key ("3:pull") -> {"who": name, "at": since when}, for every task that has an owner now."""
    latest: dict[str, tuple[str, str, bool]] = {}
    folder_ = course_dir / paths.TASKS
    for path in sorted(folder_.glob("*.json")) if folder_.is_dir() else []:
        try:
            who, tasks = _read_tasks(path)
        except (OSError, ValueError, AttributeError):
            continue
        for key, event in tasks.items():
            at = str(event["at"])
            if key not in latest or (at, who) > latest[key][:2]:
                latest[key] = (at, who, bool(event.get("taken")))
    return {key: {"who": who, "at": at} for key, (at, who, taken) in latest.items() if taken}


def set_task(course_dir: Path, key: str, taken: bool, who: str | None = None) -> dict | None:
    """Take (taken=True) or release a task as me. Returns its owner afterwards."""
    who = who or me()
    path = _task_path(course_dir, who)
    tasks = _read_tasks(path)[1] if path.exists() else {}
    tasks[key] = {"at": datetime.now().isoformat(timespec="seconds"), "taken": taken}
    _write_tasks(path, who, tasks)
    return task_owners(course_dir).get(key)


def _write_tasks(path: Path, who: str, tasks: dict[str, dict]) -> None:
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"name": who, "tasks": dict(sorted(tasks.items()))}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(path)


def rename_tasks(course_dir: Path, old: str, new: str) -> None:
    """Move my pull and return tasks to my new name."""
    old_path, new_path = _task_path(course_dir, old), _task_path(course_dir, new)
    if old == new or not old_path.exists():
        return
    tasks = _read_tasks(old_path)[1]
    if new_path != old_path and new_path.exists():
        for key, event in _read_tasks(new_path)[1].items():
            if key not in tasks or str(event["at"]) > str(tasks[key]["at"]):
                tasks[key] = event
    _write_tasks(new_path, new, tasks)
    if new_path != old_path:
        old_path.unlink()


def rename(assignment_dir: Path, old: str, new: str) -> None:
    """Move my claims to my new name (the site lets a grader change their name)."""
    old_path = _path(assignment_dir, old)
    if old == new or not old_path.exists():
        return
    same_file = old_path == _path(assignment_dir, new)
    own = _own(assignment_dir, old)
    _write(assignment_dir, new, own if same_file else {**own, **_own(assignment_dir, new)})
    if not same_file:
        old_path.unlink()
