"""Number Moodle submissions 0001..N so grading never sees student names.

Reads the extracted ZIP (one folder per student, as Moodle's "Download all
submissions" gives them) and writes into the assignment folder:
    1 - עבודות לבדיקה/0001.pdf ...      the files the grader gets
    טבלת מפתח - מספר לסטודנט.csv        number -> Moodle participant id and
                                        original folder; used to rebuild
                                        Moodle's names for the upload
"""

import csv
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


def prepare(original: Path, assignment_dir: Path) -> list[dict]:
    anon = assignment_dir / paths.TO_GRADE
    if anon.exists():
        shutil.rmtree(anon)
    anon.mkdir()

    folders = sorted(
        (f for f in original.iterdir() if f.is_dir()),
        key=lambda f: int(parse_folder(f.name)),
    )

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

    rows = []
    for folder in sorted(folders, key=numbers.get):
        number = numbers[folder]
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        for index, file in enumerate(files):
            # A second file from the same student becomes 0001-2.pdf
            suffix = "" if index == 0 else f"-{index + 1}"
            anon_name = f"{number:04d}{suffix}{file.suffix.lower()}"
            shutil.copy2(file, anon / anon_name)
            rows.append({
                "number": f"{number:04d}",
                "anon_file": anon_name,
                "participant_id": parse_folder(folder.name),
                "original_folder": folder.name,
                "original_file": str(file.relative_to(folder)),
            })

    with open(assignment_dir / paths.KEY, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=MAPPING_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def existing_numbers(assignment_dir: Path) -> dict[str, int]:
    """{participant id: number} from the key table, if the assignment has one."""
    if not (assignment_dir / paths.KEY).exists():
        return {}
    with open(assignment_dir / paths.KEY, encoding="utf-8-sig") as f:
        return {row["participant_id"]: int(row["number"]) for row in csv.DictReader(f)}


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
