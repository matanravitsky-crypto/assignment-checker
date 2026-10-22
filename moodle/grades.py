"""The grades of an assignment, which may be split over several files while several computers grade at once.

Grading splits an assignment into fifths by number: fifth 1 is 0001, 0006, 0011 ..., fifth 2 is 0002, 0007 ...
(by number and not by position, so the split stays the same when more submissions are pulled later). A computer
grades one fifth at a time, under that fifth's lock ("Grading part 3 in progress.txt"), and writes only that
fifth's file ("Grades - part 3.csv"). So two computers never write the same file, and OneDrive has nothing to
make a conflict copy of. When no fifth is being graded any more, grading merges the fifths into Grades.csv.

Everything that reads grades reads them through here: Grades.csv first, then each fifth's file on top of it. A row
that someone approved (the "approved" column) is never replaced by a row that was not approved.
"""

import csv
import re
from pathlib import Path

from moodle import paths

PARTS = 5
PART_FILE = re.compile(r"Grades - part (\d+)\.csv")


def part_of(number: str) -> int:
    """Which fifth a submission number belongs to: 0001 -> 1, 0005 -> 5, 0006 -> 1."""
    return (int(number) - 1) % PARTS + 1


def part_file(assignment_dir: Path, part: int) -> Path:
    return assignment_dir / paths.GRADES_PART.format(part)


def part_lock(part: int) -> str:
    return paths.GRADING_LOCK.format(part)


def part_files(assignment_dir: Path) -> list[Path]:
    """The fifths' grade files that exist now, by part. OneDrive's conflict copies ("...-DESKTOP.csv") don't match."""
    found = [p for p in assignment_dir.glob("Grades - part *.csv") if PART_FILE.fullmatch(p.name)]
    return sorted(found, key=lambda p: int(PART_FILE.fullmatch(p.name).group(1)))


def files(assignment_dir: Path) -> list[Path]:
    """Every file that holds grades of this assignment: Grades.csv (if there is one), then the fifths."""
    main = assignment_dir / paths.GRADES
    return ([main] if main.exists() else []) + part_files(assignment_dir)


def number_key(n: str, width: int = 4) -> str:
    n = str(n).strip()
    return n.zfill(width) if n.isdigit() else n


def is_approved(row: dict | None) -> bool:
    return bool(row) and (row.get("approved") or "").strip().lower() not in ("", "0", "no", "false", "לא")


def read_file(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {number_key(r["number"]): r for r in csv.DictReader(fh) if (r.get("number") or "").strip()}


def read(assignment_dir: Path) -> dict[str, dict]:
    """{number: row} from all the grade files: Grades.csv, then each fifth on top, never replacing an approved row."""
    rows: dict[str, dict] = {}
    for path in files(assignment_dir):
        for n, row in read_file(path).items():
            if is_approved(rows.get(n)) and not is_approved(row):
                continue
            rows[n] = row
    return rows


def last_modified(assignment_dir: Path) -> float | None:
    """When grades last changed (the newest of the files), or None if there are none."""
    return max((p.stat().st_mtime for p in files(assignment_dir)), default=None)
