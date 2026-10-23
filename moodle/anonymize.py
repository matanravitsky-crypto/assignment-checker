"""Number Moodle submissions 0001..N so grading never sees student names.

Reads the extracted ZIP (one folder per student, as Moodle's "Download all
submissions" gives them) and writes into the assignment folder:
    1 - עבודות לבדיקה/0001.pdf ...      the files the grader gets
    טבלת מפתח - מספר לסטודנט.csv        number -> Moodle participant id and
                                        original folder; used to rebuild
                                        Moodle's names for the upload
"""

import csv
import filecmp
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from moodle import paths

# Moodle names each folder "<full name>_<participant id>_assignsubmission_file"
FOLDER_PATTERN = re.compile(r"^(?P<name>.+)_(?P<participant>\d+)_assignsubmission_file_?$")

MAPPING_FIELDS = ["number", "anon_file", "participant_id", "original_folder", "original_file"]


def parse_folder(folder_name: str) -> str:
    """Return the Moodle participant id from a submission folder name."""
    match = FOLDER_PATTERN.match(folder_name)
    if not match:
        raise ValueError(f"Not a Moodle submission folder: {folder_name!r}")
    return match.group("participant")


def prepare(original: Path, assignment_dir: Path, on_folder=None) -> list[dict]:
    """`on_folder(done, total)` hears every student folder that was copied, for the dashboard's progress bar.

    The key never loses a student: one who is not in this download (a part that came without folders, a submission
    removed in Moodle) keeps their rows and their files in "1 - Submissions to grade" as they were. On 2026-10-23 a
    download with two parts without folders dropped 74 students from the key, and the key had to be rebuilt.
    Nothing is deleted: a file this download replaces moves to "Earlier versions/<date>/", the old key to
    "Key history/", and a key that would lose or move a student is refused (KeyBroken) before anything changes."""
    loose = [f.name for f in original.iterdir() if not f.is_dir()]
    if loose:  # Moodle's "download in folders" was off: a file without its folder has no participant id
        raise ValueError(f"{len(loose)} files in the download are not in a folder per student: "
                         "turn on the folders option in Moodle and pull again")
    folders = sorted(
        (f for f in original.iterdir() if f.is_dir()),
        key=lambda f: int(parse_folder(f.name)),
    )
    key = assignment_dir / paths.KEY
    key_before = key.read_bytes() if key.exists() else None  # a key that changes under us: another computer pulled
    old_rows = existing_rows(assignment_dir)
    stamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")

    # A student keeps their number across downloads, even after grading started;
    # students who submitted since the last download get the next free numbers
    known = existing_numbers(assignment_dir)
    next_number = max(known.values(), default=0) + 1
    numbers = {}
    for folder in folders:
        participant = parse_folder(folder.name)
        if participant in known:
            numbers[folder] = known[participant]
        else:
            numbers[folder] = next_number
            next_number += 1

    rows, sources = [], {}
    for folder in sorted(folders, key=numbers.get):
        number = numbers[folder]
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        for index, file in enumerate(files):
            # A second file from the same student becomes 0001-2.pdf
            suffix = "" if index == 0 else f"-{index + 1}"
            anon_name = f"{number:04d}{suffix}{file.suffix.lower()}"
            sources[anon_name] = file
            rows.append({
                "number": f"{number:04d}",
                "anon_file": anon_name,
                "participant_id": parse_folder(folder.name),
                "original_folder": folder.name,
                "original_file": str(file.relative_to(folder)),
            })

    # Students of the key who are not in this download: their rows stay, and so do their files
    here = {parse_folder(f.name) for f in folders}
    rows += [{k: row.get(k, "") for k in MAPPING_FIELDS} for row in old_rows if row["participant_id"] not in here]
    rows.sort(key=lambda r: r["number"])  # stable: a student's files stay in their order (0001.pdf, then 0001-2.pdf)
    check_key(old_rows, rows)  # before any file is touched

    # The files go in place: one that is the same stays as it is (nothing new for OneDrive to sync), and one that this
    # download replaces moves to "Earlier versions" first. Nothing in "1 - Submissions to grade" is ever deleted
    anon = assignment_dir / paths.TO_GRADE
    anon.mkdir(exist_ok=True)
    conflicts = submission_conflicts(assignment_dir)
    if conflicts:
        raise KeyBroken(f"OneDrive conflict copies in {paths.TO_GRADE}: {', '.join(conflicts[:10])}: nothing was changed")
    earlier = assignment_dir / paths.EARLIER / stamp
    done: list[tuple[Path, Path | None]] = []  # (a file this pull wrote or moved, where the old one went): to undo
    numbers_here = {r["number"] for r in rows if r["anon_file"] in sources}
    try:
        for old in sorted(anon.iterdir()):  # a file of a student in this download that the download no longer has
            if old.is_file() and old.name not in sources and old.name[:4] in numbers_here and old.name[4:5] in (".", "-"):
                done.append((old, _set_aside(old, earlier)))
        seen: set[str] = set()
        for anon_name, source in sources.items():
            if on_folder and anon_name[:4] not in seen:
                on_folder(len(seen), len(numbers_here))
            seen.add(anon_name[:4])
            target = anon / anon_name
            if target.is_file() and _same(source, target):
                continue
            aside = _set_aside(target, earlier) if target.exists() else None
            done.append((target, aside))
            shutil.copy2(source, target)
        if (key.read_bytes() if key.exists() else None) != key_before:
            raise KeyBroken("the key changed during the pull (another computer pulled the same assignment?): "
                            "every file was put back and nothing was changed")
        _write_key(assignment_dir, rows, stamp)
    except BaseException:
        _undo(done)
        raise
    return rows


def _undo(done: list[tuple[Path, Path | None]]) -> None:
    """Put "1 - Submissions to grade" back as it was: what this pull copied goes, and what it moved aside comes back."""
    for path, aside in reversed(done):
        if aside is None:
            path.unlink(missing_ok=True)  # a file this pull copied, where there was none
        else:
            path.unlink(missing_ok=True)
            aside.rename(path)


def submission_conflicts(assignment_dir: Path) -> list[str]:
    """OneDrive conflict copies of submissions ("0571-DESKTOP-ABC.pdf"): two computers wrote the same number, and
    nobody knows whose file "0571.pdf" holds. Grading ignores such a name, but nothing may number or upload until a
    person checks them."""
    anon = assignment_dir / paths.TO_GRADE
    pattern = re.compile(r"\d{4}(?:-\d+)?-.*\D.*")
    return sorted(p.name for p in anon.iterdir() if p.is_file() and pattern.fullmatch(p.stem)) if anon.is_dir() else []


def _same(a: Path, b: Path) -> bool:
    """The same bytes. Never by time: a ZIP's times can repeat, and a resubmission of the same size would be missed."""
    return a.stat().st_size == b.stat().st_size and filecmp.cmp(a, b, shallow=False)


def _set_aside(path: Path, earlier: Path) -> Path:
    """Move a file to "Earlier versions/<date>/", under a free name, and say where."""
    earlier.mkdir(parents=True, exist_ok=True)
    target, n = earlier / path.name, 2
    while target.exists():
        target, n = earlier / f"{path.stem} ({n}){path.suffix}", n + 1
    path.rename(target)
    return target


class KeyBroken(ValueError):
    """The new key would lose or move a student, or give a number to two: nothing was changed."""


def check_key(old_rows: list[dict], rows: list[dict]) -> None:
    """Every student of the old key is in the new one with the same number, and every number has one student."""
    old = {r["participant_id"]: r["number"] for r in old_rows}
    pid_number: dict[str, str] = {}
    number_pid: dict[str, str] = {}
    for r in rows:
        pid, number = r["participant_id"], r["number"]
        if pid_number.setdefault(pid, number) != number or number_pid.setdefault(number, pid) != pid:
            raise KeyBroken(f"number {number} would have two students, or a student two numbers: nothing was changed")
    lost = sorted(n for pid, n in old.items() if pid_number.get(pid) != n)
    if lost:
        raise KeyBroken(f"numbers {', '.join(lost[:10])} would change or go missing in the key: nothing was changed")


def _write_key(assignment_dir: Path, rows: list[dict], stamp: str) -> None:
    """The key, written whole or not at all (a temp file, then a rename), with the old one kept in "Key history"."""
    key = assignment_dir / paths.KEY
    tmp = assignment_dir / f"{paths.KEY}.writing"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=MAPPING_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    if key.exists():
        if key.read_bytes() == tmp.read_bytes():
            tmp.unlink()
            return
        history = assignment_dir / paths.KEY_HISTORY
        history.mkdir(exist_ok=True)
        shutil.copy2(key, history / f"Key {stamp}.csv")
    os.replace(tmp, key)


def existing_rows(assignment_dir: Path) -> list[dict]:
    """The rows of the key table, if the assignment has one."""
    if not (assignment_dir / paths.KEY).exists():
        return []
    with open(assignment_dir / paths.KEY, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def existing_numbers(assignment_dir: Path) -> dict[str, int]:
    """{participant id: number} from the key table, if the assignment has one."""
    return {row["participant_id"]: int(row["number"]) for row in existing_rows(assignment_dir)}


def key_conflicts(assignment_dir: Path) -> list[str]:
    """Conflict copies of the key that OneDrive makes when two computers write it at once ("...-DESKTOP-ABC.csv").

    While one exists, two students may share a number: nothing that numbers or uploads may go on until
    someone merges the copy into the main key and deletes it.
    """
    stem = Path(paths.KEY).stem
    return sorted(p.name for p in assignment_dir.glob(f"{stem}*.csv") if p.name != paths.KEY)


def key_problems(assignment_dir: Path) -> dict[str, list[str]]:
    """What is wrong in the key table, by number only (never names): {kind: sorted numbers}, empty when it is sound.

    "number_has_two_participants"  a number whose rows name more than one participant id
    "participant_has_two_numbers"  numbers that share a participant id
    "folder_does_not_match"        a number whose original folder does not carry its participant id
    """
    pids: dict[str, set[str]] = {}
    numbers: dict[str, set[str]] = {}
    bad_folder: set[str] = set()
    with open(assignment_dir / paths.KEY, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            number, pid = (row.get("number") or "").strip(), (row.get("participant_id") or "").strip()
            pids.setdefault(number, set()).add(pid)
            numbers.setdefault(pid, set()).add(number)
            match = FOLDER_PATTERN.match(row.get("original_folder") or "")
            if not pid or not match or match.group("participant") != pid:
                bad_folder.add(number)
    problems = {
        "number_has_two_participants": sorted(n for n, p in pids.items() if len(p) > 1),
        "participant_has_two_numbers": sorted({n for ns in numbers.values() if len(ns) > 1 for n in ns}),
        "folder_does_not_match": sorted(bad_folder),
    }
    return {kind: found for kind, found in problems.items() if found}


def read_mapping(assignment_dir: Path) -> dict[str, dict]:
    """Return the key as {number: first row for that number}."""
    with open(assignment_dir / paths.KEY, encoding="utf-8-sig") as f:
        mapping = {}
        for row in csv.DictReader(f):
            mapping.setdefault(row["number"], row)
        return mapping
