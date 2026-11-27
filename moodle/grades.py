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
import json
import re
import math
from pathlib import Path

from . import atomic, claims, paths, schema

# number, grade, feedback are what the return step reads. The rest are the system's:
#   points      points per question, in order, separated by ";"
#   approved    empty until someone approves the grade. An approved row is never overwritten
#   review      why Claude asked a person to check the work (empty if it didn't)
#   graded_at   when it was graded, graded_by  who graded it (the merge above uses graded_at)
#   course_grade  what Moodle gets when the assignment's grade counts what was handed in (course_policy), not the rubric
COLUMNS = ["number", "grade", "feedback", "points", "approved", "review", "graded_at", "graded_by", "course_grade"]


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


def rank(row: dict) -> tuple[bool, str]:
    """Which of two rows of one number wins the merge: the higher rank (approved first, then the later graded_at)."""
    return is_approved(row), (row.get("graded_at") or "").strip()


_rank = rank  # the older private name, for code that still uses it


def read(assignment_dir: Path) -> dict[str, dict]:
    """number -> its row, merged from all the grades files (see the top of this file)."""
    best: dict[str, dict] = {}
    for path in files(assignment_dir):
        for n, row in read_file(path).items():
            if n not in best or rank(row) >= rank(best[n]):
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


def course_policy(details: dict | None) -> dict | None:
    """The assignment's course-grade policy, or None when Moodle gets the rubric's grade. `moodle_grade.basis =
    "submission"` in Assignment details.json: Moodle measures what was handed in, not how right it is (the assignment's
    "מדיניות ציון - PDF ומודל" document, Matan 2026-11-18): every question weighs the same, a question counts by the
    share of its parts that were handed in, and a typed submission or one identical to another's gets 0. The rubric's
    grade stays in the marked PDF, so the student sees how the work would be graded in an exam. (From 2026-11-15 to
    11-18 this basis meant the full grade for any submission.)"""
    policy = details.get("moodle_grade") if isinstance(details, dict) else None
    if isinstance(policy, dict) and str(policy.get("basis") or "").strip().lower() == "submission":
        return policy
    return None


def _question(label: str) -> str:
    """The question a part belongs to: "קבוצות 12ב" and "שאלה 3 (ב)" -> "קבוצות 12", "שאלה 3"."""
    s = " ".join(str(label).split())
    return re.sub(r"(?<=\d)\s*(?:\(\s*[א-ת]['׳]?\s*\)|[א-ת]['׳]?)$", "", s).strip() or s


def course_grade(labels: list[str], submitted: list[bool], max_grade: float = 100, zero: bool = False,
                 per_question: str = "share") -> float:
    """What Moodle gets under course_policy: max_grade / (number of questions) for each question, times the share of
    its parts handed in (`per_question` "share", the default: LA Assignment 0), or all of it when at least one part was
    handed in (`"any"`: `moodle_grade.per_question` in Assignment details.json, the pedagogical team on 2026-11-27, from
    LA Assignment 1 on), rounded to a whole number (a half up). 0 when `zero` (typed, identical to another's)."""
    if zero or not labels:
        return 0
    groups: dict[str, list[bool]] = {}
    for label, done in zip(labels, list(submitted) + [False] * (len(labels) - len(submitted))):
        groups.setdefault(_question(label), []).append(bool(done))
    share = (lambda g: 1 if any(g) else 0) if per_question == "any" else (lambda g: sum(g) / len(g))
    total = sum(max_grade / len(groups) * share(g) for g in groups.values())
    return math.floor(total + 0.5 + 1e-9)


# the copying check's kinds (copying/check.py, STRONG) that mean the same work: the same file, the same PDF document,
# at least two identical page images, or typed pages that share the rare text
IDENTICAL = {"file", "doc_id", "page", "text"}


def identical(assignment_dir: Path) -> dict[str, list[str]]:
    """number -> the numbers whose work is the same (Copying check.json, written by the copying check, no tokens).
    Under course_policy each of them gets 0 in Moodle (Matan, 2026-11-18). {} when the check has not run."""
    try:
        report = json.loads((Path(assignment_dir) / paths.COPYING).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, list[str]] = {}
    for pair in report.get("pairs") or []:
        kinds = {r.get("kind") for r in pair.get("reasons") or [] if isinstance(r, dict)}
        if pair.get("level") == "strong" and kinds & IDENTICAL:
            a, b = number_key(str(pair.get("a"))), number_key(str(pair.get("b")))
            out.setdefault(a, []).append(b)
            out.setdefault(b, []).append(a)
    return out


def for_moodle(row: dict, policy: dict | None, copies: dict[str, list[str]]) -> str:
    """The grade that goes to Moodle for one row: the rubric's grade, or under course_policy the row's course_grade
    (0 for a work identical to another's). "" when the policy applies and the row has no course_grade (graded before
    it): such a row is left out, never sent with the rubric's grade."""
    if policy is None:
        return (row.get("grade") or "").strip()
    if not (row.get("grade") or "").strip():
        return ""
    if number_key(str(row.get("number") or "")) in copies:
        return "0"
    return (row.get("course_grade") or "").strip()


def to_moodle(assignment_dir: Path, rows: dict[str, dict]) -> dict[str, dict]:
    """`rows` (number -> row, as read() gives them) with each graded row's "grade" replaced by the one that goes to
    Moodle (for_moodle) when the assignment has a course_policy; unchanged without one. Every path to Moodle reads
    grades through this (the table, the worksheet, the automatic upload, the return check), so none sends the rubric's
    grade under the policy (until 2026-11-18 none of them called for_moodle). The grades files keep the rubric's grade."""
    policy = course_policy(details(assignment_dir))
    if policy is None:
        return rows
    copies = identical(assignment_dir)
    return {n: ({**r, "grade": for_moodle({**r, "number": n}, policy, copies)} if (r.get("grade") or "").strip() else r)
            for n, r in rows.items()}


def details(assignment_dir: Path) -> dict:
    """Assignment details.json, or {} when it is missing or broken."""
    try:
        data = json.loads((Path(assignment_dir) / paths.INFO).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}
