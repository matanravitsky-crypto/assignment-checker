"""Number Moodle submissions 0001..N so grading never sees student names.

Reads the extracted ZIP (one folder per student, as Moodle's "Download all
submissions" gives them) and writes into the assignment folder:
    1 - עבודות לבדיקה/0001.pdf ...      the files the grader gets
    טבלת מפתח - מספר לסטודנט.csv        number -> Moodle participant id and
                                        original folder; used to rebuild
                                        Moodle's names for the upload
"""

import csv
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
    Nothing is deleted or written over: a file this download replaces moves to "Earlier versions/<date>/" first, the
    old key goes to "Key history/", a key that would lose or move a student is refused (KeyBroken) before anything
    changes, and a key that changes during the pull (another computer) puts every file back."""
    loose = [f.name for f in original.iterdir() if not f.is_dir()]
    if loose:  # Moodle's "download in folders" was off: a file without its folder has no participant id
        raise ValueError(f"{len(loose)} files in the download are not in a folder per student: "
                         "turn on the folders option in Moodle and pull again")
    folders = sorted(
        (f for f in original.iterdir() if f.is_dir()),
        key=lambda f: int(parse_folder(f.name)),
    )
    check_key(assignment_dir)
    key = assignment_dir / paths.KEY
    key_before = key.read_bytes() if key.exists() else None  # a key that changes under us: another computer pulled
    old_rows = existing_rows(assignment_dir)
    anon = assignment_dir / paths.TO_GRADE
    anon.mkdir(exist_ok=True)
    conflicts = submission_conflicts(assignment_dir)
    if conflicts:
        raise KeyBroken(f"OneDrive conflict copies in {paths.TO_GRADE}: {', '.join(conflicts[:10])}: nothing was changed")
    _restore_previous(assignment_dir, anon)
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

    # "1 - Submissions to grade" is updated in place, file by file, and only where something changed: a pull that
    # fails halfway leaves every file either as it was or as it is now (never half written), nothing of a student who
    # is not in this download is touched, and OneDrive uploads only what changed
    rows, wanted, first_file = [], {}, {}
    for folder in sorted(folders, key=numbers.get):
        number = numbers[folder]
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        for index, file in enumerate(files):
            # A second file from the same student becomes 0001-2.pdf
            suffix = "" if index == 0 else f"-{index + 1}"
            anon_name = f"{number:04d}{suffix}{file.suffix.lower()}"
            wanted[anon_name] = file
            first_file.setdefault(folder, anon_name)
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
    check_new_key(old_rows, rows)  # before any file is touched

    earlier = assignment_dir / paths.EARLIER / stamp
    done: list[tuple[Path, Path | None]] = []  # (a file this pull wrote or moved, where the old one went): to undo
    here_numbers = {f"{n:04d}" for n in numbers.values()}
    try:
        # a file of a student in this download that the download no longer has (they submitted fewer files)
        for old in sorted(anon.iterdir()):
            if (old.is_file() and old.name not in wanted and not old.name.endswith(".tmp")
                    and _number_of(old.name) in here_numbers):
                done.append((old, _set_aside(old, earlier)))
        starts = {name: i for i, name in enumerate(first_file.values())}
        for anon_name, file in wanted.items():
            if on_folder and anon_name in starts:
                on_folder(starts[anon_name], len(starts))
            changed = _put(file, anon / anon_name, earlier)
            if changed:
                done.append(changed)
        if (key.read_bytes() if key.exists() else None) != key_before:
            raise KeyBroken("the key changed during the pull (another computer pulled the same assignment?): "
                            "every file was put back and nothing was changed")
        _write_key(assignment_dir, rows, stamp)
    except BaseException:
        _undo(done)
        raise
    return rows


def _write_key(assignment_dir: Path, rows: list[dict], stamp: str) -> None:
    """The key last, and whole or not at all: written next to it, then put in its place in one step. The old one is
    kept in "Key history" first (not next to the key: there it would look like an OneDrive conflict copy)."""
    key = assignment_dir / paths.KEY
    tmp = key.with_name(key.name + ".tmp")
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


class KeyBroken(ValueError):
    """The new key would lose or move a student, or give a number to two; or it changed under the pull: nothing changed."""


def check_new_key(old_rows: list[dict], rows: list[dict]) -> None:
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


def _set_aside(path: Path, earlier: Path) -> Path:
    """Move a file to "Earlier versions/<date>/", under a free name, and say where."""
    earlier.mkdir(parents=True, exist_ok=True)
    target, n = earlier / path.name, 2
    while target.exists():
        target, n = earlier / f"{path.stem} ({n}){path.suffix}", n + 1
    path.rename(target)
    return target


def _undo(done: list[tuple[Path, Path | None]]) -> None:
    """Put "1 - Submissions to grade" back as it was: what this pull copied goes, and what it moved aside comes back."""
    for path, aside in reversed(done):
        path.unlink(missing_ok=True)  # only a file this pull wrote (or one it moved, which is gone already)
        if aside is not None:
            aside.rename(path)


def submission_conflicts(assignment_dir: Path) -> list[str]:
    """OneDrive conflict copies of submissions ("0571-DESKTOP-ABC.pdf"): two computers wrote the same number, and
    nobody knows whose file "0571.pdf" holds. Grading ignores such a name, but nothing may number or upload until a
    person checks them."""
    anon = assignment_dir / paths.TO_GRADE
    pattern = re.compile(r"\d{4}(?:-\d+)?-.*\D.*")
    return sorted(p.name for p in anon.iterdir() if p.is_file() and pattern.fullmatch(p.stem)) if anon.is_dir() else []


KEY_EMPTY = "the key table is empty or unreadable"


def check_key(assignment_dir: Path) -> None:
    """Refuse to number when the key is empty or unreadable while the assignment already has submissions: numbering
    from it would give every student a new number, and grades would reach the wrong student. Changes nothing."""
    anon = assignment_dir / paths.TO_GRADE
    has_submissions = anon.is_dir() and any(f.is_file() and not f.name.endswith(".tmp") for f in anon.iterdir())
    try:
        rows = existing_rows(assignment_dir)
        ok = all(row.get("participant_id", "").isdigit() and row.get("number", "").isdigit() for row in rows)
    except (OSError, UnicodeDecodeError, csv.Error):
        rows, ok = [], False
    if (has_submissions and not rows) or not ok:
        raise ValueError(f"{KEY_EMPTY}: {paths.KEY} has {len(rows)} usable rows"
                         f"{f' but {paths.TO_GRADE} has submissions' if has_submissions else ''}. Nothing was changed")


PREVIOUS = " (previous)"  # left by the old code when a pull failed halfway


def _number_of(anon_name: str) -> str:
    """"0012-2.pdf" -> "0012"."""
    return anon_name.split(".")[0].split("-")[0]


def _put(source: Path, dest: Path, earlier: Path) -> tuple[Path, Path | None] | None:
    """Copy source to dest unless dest already has exactly these bytes; the copy goes next to it first (.tmp, which
    the OneDrive sync skips), the old file moves to `earlier`, and the copy takes its place. None when nothing changed,
    else (dest, where the old file went or None) for _undo."""
    if dest.is_file() and dest.stat().st_size == source.stat().st_size and _same_bytes(source, dest):
        return None
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.copy2(source, tmp)
    aside = _set_aside(dest, earlier) if dest.exists() else None
    os.replace(tmp, dest)
    return dest, aside


def _same_bytes(a: Path, b: Path) -> bool:
    """Byte by byte (filecmp remembers earlier answers by size and time, and a resubmission can match both)."""
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            x, y = fa.read(1 << 20), fb.read(1 << 20)
            if x != y:
                return False
            if not x:
                return True


def _restore_previous(assignment_dir: Path, anon: Path) -> None:
    """The old code renamed the folder to "... (previous)" during a pull; one left by a pull that failed halfway has the
    files that were there before it. Put back what is missing, then remove it."""
    previous = assignment_dir / f"{paths.TO_GRADE}{PREVIOUS}"
    if not previous.is_dir():
        return
    for old in previous.iterdir():
        if old.is_file() and not (anon / old.name).exists():
            old.replace(anon / old.name)
    shutil.rmtree(previous)


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
