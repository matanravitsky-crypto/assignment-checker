"""The grades of an assignment: Grades.csv plus one file per grader, "Grades by <name>.csv".

Two people grading at once on two computers would both rewrite Grades.csv, and OneDrive would keep one version as a
conflict copy, so grades would disappear. So grading writes only the grader's own file, and every reader merges them
all, number by number:
- an approved row wins (a person checked it),
- otherwise the row graded last (its graded_at),
- a row without graded_at (Grades.csv from before the split) loses to one that has it.
Grades.csv stays for older grades and for approvals typed in by hand.
"""

import csv
import io
from pathlib import Path

from datastore import atomic, schema

from datastore import atomic, schema

from . import claims, paths

# number, grade, feedback are what the return step reads. The rest are the system's:
#   points      points per question, in order, separated by ";"
#   approved    empty until someone approves the grade. An approved row is never overwritten
#   review      why Claude asked a person to check the work (empty if it didn't)
#   graded_at   when it was graded, graded_by  who graded it (the merge above uses graded_at)
COLUMNS = ["number", "grade", "feedback", "points", "approved", "review", "graded_at", "graded_by"]


def number_key(n: str, width: int = 4) -> str:
    n = str(n).strip()
    return n.zfill(width) if n.isdigit() else n


def files(assignment_dir: Path) -> list[Path]:
    """Every grades file of the assignment: Grades.csv first, then the graders' files."""
    main = assignment_dir / paths.GRADES
    by = sorted(p for p in assignment_dir.glob(paths.GRADES_BY.format("*")) if p.is_file())
    return ([main] if main.is_file() else []) + by


def own_file(assignment_dir: Path, who: str | None = None) -> Path:
    return assignment_dir / paths.GRADES_BY.format(claims.file_name(who or claims.me()))


def is_approved(row: dict | None) -> bool:
    return bool(row) and (row.get("approved") or "").strip().lower() not in ("", "0", "no", "false", "לא")


def read_file(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    # errors="replace": a grades file that is not UTF-8 (a hand edit in Excel) must not stop every reader (the site, the upload)
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        return {number_key(r["number"]): r for r in csv.DictReader(fh) if (r.get("number") or "").strip()}


def _rank(row: dict) -> tuple[bool, str]:
    return is_approved(row), (row.get("graded_at") or "").strip()


def read(assignment_dir: Path) -> dict[str, dict]:
    """number -> its row, merged from all the grades files (see the top of this file)."""
    best: dict[str, dict] = {}
    for path in files(assignment_dir):
        for n, row in read_file(path).items():
            if n not in best or _rank(row) >= _rank(best[n]):
                best[n] = row
    return best


def write_file(path: Path, rows: dict[str, dict]) -> None:
    cols = list(COLUMNS)
    for r in rows.values():
        cols += [c for c in r if c and c not in cols]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\r\n", extrasaction="ignore")
    w.writeheader()
    for n in sorted(rows):
        w.writerow({**rows[n], "number": n})
    # BOM so Excel shows Hebrew. Atomic: a unique temp file, fsync, replace, so a half-written file never stays behind
    atomic.write_atomic(path, buf.getvalue(), encoding="utf-8-sig")


def update_own(assignment_dir: Path, number: str, row: dict, *, who: str | None = None,
               max_grade: float | None = None, question_points: list[float] | None = None) -> dict:
    """Write one row into my own grades file: a process lock around the read-modify-write (the CLI and the dashboard
    of the same grader on one PC never overwrite each other), and the schema check first (an invalid row is refused
    with schema.Invalid, never written). Returns the row as written."""
    n = number_key(number)
    row = {**row, "number": n}
    mine = own_file(assignment_dir, who)
    schema.require(schema.check_grade_row(row, max_grade=max_grade, question_points=question_points, where=mine.name))
    with atomic.process_lock(str(mine.resolve())):
        own = read_file(mine)
        own[n] = row
        write_file(mine, own)
    return row
