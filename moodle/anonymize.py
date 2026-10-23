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
    download with two parts without folders dropped 74 students from the key, and the key had to be rebuilt."""
    loose = [f.name for f in original.iterdir() if not f.is_dir()]
    if loose:  # Moodle's "download in folders" was off: a file without its folder has no participant id
        raise ValueError(f"{len(loose)} files in the download are not in a folder per student: "
                         "turn on the folders option in Moodle and pull again")
    folders = sorted(
        (f for f in original.iterdir() if f.is_dir()),
        key=lambda f: int(parse_folder(f.name)),
    )
    check_key(assignment_dir)
    old_rows = existing_rows(assignment_dir)
    anon = assignment_dir / paths.TO_GRADE
    anon.mkdir(exist_ok=True)
    _restore_previous(assignment_dir, anon)

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
    rows, wanted = [], {}
    for done, folder in enumerate(sorted(folders, key=numbers.get)):
        if on_folder:
            on_folder(done, len(folders))
        number = numbers[folder]
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        for index, file in enumerate(files):
            # A second file from the same student becomes 0001-2.pdf
            suffix = "" if index == 0 else f"-{index + 1}"
            anon_name = f"{number:04d}{suffix}{file.suffix.lower()}"
            wanted[anon_name] = file
            rows.append({
                "number": f"{number:04d}",
                "anon_file": anon_name,
                "participant_id": parse_folder(folder.name),
                "original_folder": folder.name,
                "original_file": str(file.relative_to(folder)),
            })
    for anon_name, file in wanted.items():
        _put(file, anon / anon_name)
    # a file of a student in this download that the download no longer has (they submitted fewer files)
    here_numbers = {f"{n:04d}" for n in numbers.values()}
    for old in anon.iterdir():
        if old.is_file() and old.name not in wanted and _number_of(old.name) in here_numbers:
            old.unlink()

    # Students of the key who are not in this download: their rows stay, and so do their files
    here = {parse_folder(f.name) for f in folders}
    rows += [{k: row.get(k, "") for k in MAPPING_FIELDS} for row in old_rows if row["participant_id"] not in here]
    rows.sort(key=lambda r: r["number"])  # stable: a student's files stay in their order (0001.pdf, then 0001-2.pdf)

    # The key last, and whole or not at all: written next to it, then put in its place in one step
    key = assignment_dir / paths.KEY
    tmp = key.with_name(key.name + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=MAPPING_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, key)
    return rows


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


def _put(source: Path, dest: Path) -> None:
    """Copy source to dest unless dest already has exactly these bytes; the copy goes next to it first (.tmp, which
    the OneDrive sync skips), then replaces it in one step."""
    if dest.is_file() and dest.stat().st_size == source.stat().st_size and _same_bytes(source, dest):
        return
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.copy2(source, tmp)
    os.replace(tmp, dest)


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
