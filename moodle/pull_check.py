"""The check at the end of every pull: nothing lost, nothing forgotten, nothing taken twice, nothing changed that the
download did not bring. Anyone on the team may pull, so this does not trust the code that numbered and copied: it
looks again at the disk, independently, before the new key is written (`anonymize.prepare` calls `verify`; a
failure puts every file back and writes no key) and against what Moodle said it sent (`moodle_side`, from the list
of parts of moodle/download_parts.js).

What it checks, by number and participant id only (never a name):
- The key: every student who was in it keeps their number; no number has two students; no student has two numbers.
- Nothing lost: every numbered file that was in "1 - Submissions to grade" is still there as it was, or, for a student
  in this download whose file the download replaced, its old version is in "Earlier versions" (same size).
- Nothing changed that shouldn't: a file of a student who is not in this download is exactly as it was (size and
  modification time). A file that changed belongs to a student in this download and has exactly the bytes of the
  download.
- Nothing forgotten: every file of the download is in the folder, with its bytes. Every row of the key has its file.
- Nothing twice: no file name and no student folder is taken twice.
- Moodle's side: every student whose ZIP came is in the extracted folder, and none that did not come; if fewer came
  than Moodle's table shows with a submission date, the difference is counted, so a person can look.

The result goes into "Pull check.json" in the assignment folder (numbers only) and into the pull's report.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from moodle import paths

CHECK_FILE = paths.PULL_CHECK


class PullCheckFailed(Exception):
    """The pull would have lost, missed, doubled or changed something: nothing is written."""


def snapshot(anon: Path, is_numbered) -> dict[str, tuple[int, int]]:
    """{file name: (size, modification time in ns)} of every numbered file in "1 - Submissions to grade"."""
    if not anon.is_dir():
        return {}
    out = {}
    for f in anon.iterdir():
        if is_numbered(f):
            st = f.stat()
            out[f.name] = (st.st_size, st.st_mtime_ns)
    return out


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _same_bytes(a: Path, b: Path) -> bool:
    return a.stat().st_size == b.stat().st_size and _digest(a) == _digest(b)


def verify(before_files: dict[str, tuple[int, int]], old_rows: list[dict], rows: list[dict],
           sources: dict[str, Path], anon: Path, moved_aside: dict[str, Path], is_numbered) -> dict:
    """Look at the disk after the files were copied and before the key is written. `moved_aside`: file name → where
    the pull moved its old version (in "Earlier versions"). Raises PullCheckFailed with what went wrong (numbers
    only); returns the counts for the report."""
    problems: list[str] = []
    here = {name[:4] for name in sources}  # the numbers of the students in this download

    # The key
    old_number = {r["participant_id"]: r["number"] for r in old_rows}
    new_number: dict[str, set[str]] = {}
    owner: dict[str, set[str]] = {}
    for r in rows:
        new_number.setdefault(r["participant_id"], set()).add(r["number"])
        owner.setdefault(r["number"], set()).add(r["participant_id"])
    for pid, number in old_number.items():
        if new_number.get(pid) != {number}:
            problems.append(f"student {number} would lose or change their number")
    problems += [f"number {n} would have {len(p)} students" for n, p in owner.items() if len(p) > 1]
    problems += [f"a student would have numbers {sorted(n)}" for n in new_number.values() if len(n) > 1]

    # Nothing taken twice
    names = [r["anon_file"] for r in rows]
    problems += [f"file {n} is in the key twice" for n in sorted({n for n in names if names.count(n) > 1})]
    used = [str(s) for s in sources.values()]
    if len(used) != len(set(used)):
        problems.append("a file of the download was copied under two names")

    now = snapshot(anon, is_numbered)
    aside = {name: p.stat().st_size for name, p in moved_aside.items() if p.is_file()}
    kept = changed = moved = 0
    # Nothing lost, nothing changed that shouldn't
    for name, (size, mtime) in before_files.items():
        if now.get(name) == (size, mtime):
            kept += 1
            continue
        if name[:4] not in here:
            problems.append(f"{name} changed or vanished, and its student is not in this download")
        elif aside.get(name) != size:
            problems.append(f"{name} was replaced, but its old version is not in {paths.EARLIER}")
        else:
            moved += 1
    # Nothing forgotten, and every change is exactly the download
    for name, source in sources.items():
        target = anon / name
        if name not in now:
            problems.append(f"{name} of the download is not in the folder")
        elif before_files.get(name) != now[name]:
            if not _same_bytes(source, target):
                problems.append(f"{name} in the folder is not what the download brought")
            changed += 1
    for name in now:
        if name not in before_files and name not in sources:
            problems.append(f"{name} appeared, but it is not in the download")
    missing = sorted(r["anon_file"] for r in rows if r["anon_file"] not in now)
    problems += [f"{n} is in the key but not in the folder" for n in missing[:20]]

    if problems:
        raise PullCheckFailed("; ".join(problems[:20]) + (f" (and {len(problems) - 20} more)" if len(problems) > 20 else ""))
    return {"students_before": len(old_number), "students_after": len(new_number),
            "new_students": len(set(new_number) - set(old_number)), "in_this_download": len(here),
            "files_unchanged": kept, "files_written": changed, "files_moved_to_earlier": moved,
            "files_in_folder": len(now)}


def moodle_side(listing: dict, extracted: set[str]) -> tuple[dict, list[str]]:
    """What Moodle said it sent (the list of download_parts.js) against the student folders that were extracted.
    Returns (the counts, problems). A problem stops the pull (all or nothing); students with a submission date and no
    file are only counted: Moodle shows a date for a text-only submission too, and a person looks."""
    came: set[str] = set()
    for f in listing.get("files") or []:
        came |= {str(i) for i in f.get("ids") or []}
    problems = []
    if came:  # lists from before this check have no ids
        if extracted - came:
            problems.append(f"{len(extracted - came)} student folders were extracted that Moodle did not list")
        if came - extracted:
            problems.append(f"{len(came - extracted)} students came from Moodle but their folder was not extracted")
    # The grading table knows students by their user id and the ZIP by their participant id (seen on Discrete 3453769,
    # 2026-11-02: no id in common), so the two sides are compared by count, not by id
    with_date = len(set(listing.get("with_date") or []))
    counts = {"moodle_students": int(listing.get("users") or 0), "came_from_moodle": len(came or extracted),
              "with_date_no_file": max(0, with_date - len(came or extracted)) if "with_date" in listing else 0}
    return counts, problems


def write(assignment_dir: Path, report: dict) -> None:
    """"Pull check.json": the last pull's check, numbers only, written whole through a temp file."""
    report = {"checked_at": datetime.now().isoformat(timespec="seconds"), **report}
    tmp = assignment_dir / (CHECK_FILE + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, assignment_dir / CHECK_FILE)


def read(assignment_dir: Path) -> dict | None:
    try:
        return json.loads((assignment_dir / CHECK_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
