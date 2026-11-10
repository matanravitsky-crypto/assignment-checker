"""Grades for Moodle.csv: every grade of an assignment next to what Moodle needs to give it to the right student.

Moodle does not know our numbers (0001, 0002...) or ID numbers (ת"ז). It knows each student by the *participant id* of
the assignment: the number in the folder name of Moodle's download ("<name>_<participant id>_assignsubmission_file")
and in the "Identifier" column of its grading worksheet ("Participant 13464355", in Hebrew Moodle "משתתף 13464355").
The key table (Key - number to student.csv) links our number to it. This table puts them side by side, one row per
graded number:

    number, participant_id, moodle_identifier, grade, max_grade, feedback, approved, graded_by, graded_at

It lives in the assignment folder (next to the key, so it never widens who can link a grade to a student) and is
DERIVED: built again from the merged grades (moodle/grades.py) and the key on every grading, every grade edit and every
upload, so it can always be deleted and rebuilt, and an OneDrive conflict copy of it is simply removed. The upload
(`moodle upload`, `prepare_upload`) fills Moodle's own worksheet from this table, matching by participant id, so the
grade that goes to Moodle is exactly the one in the table, whatever language Moodle's headers are in.

A row goes in only when it is safe: its grade is a valid number (0..max grade), and the key gives its number exactly one
participant, who has no other number. Everything else is reported by number (never a name) and left out: a grade that
cannot be tied to one student for sure never reaches Moodle.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from datastore import atomic, schema

from . import anonymize, grades, paths

COLUMNS = ["number", "participant_id", "moodle_identifier", "grade", "max_grade", "feedback", "approved", "graded_by",
           "graded_at"]
IDENTIFIER = "Participant {}"   # what Moodle's English worksheet writes; the Hebrew one writes "משתתף {}"
DEFAULT_MAX = 100


def path(assignment_dir: Path) -> Path:
    return Path(assignment_dir) / paths.MOODLE_TABLE


def max_grade(assignment_dir: Path) -> float:
    try:
        d = json.loads((Path(assignment_dir) / paths.INFO).read_text(encoding="utf-8"))
        return float(d.get("max_grade") or DEFAULT_MAX)
    except (OSError, ValueError, TypeError, AttributeError):
        return float(DEFAULT_MAX)


def _pts(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def compute(assignment_dir: Path) -> tuple[list[dict], dict[str, list[str]]]:
    """The rows of the table, and what was left out: {"no_participant" | "key_problem" | "invalid_grade": numbers}."""
    a = Path(assignment_dir)
    top = max_grade(a)
    results = grades.read(a)
    has_key = (a / paths.KEY).is_file()
    mapping = anonymize.read_mapping(a) if has_key else {}
    bad_key = {n for found in (anonymize.key_problems(a) if has_key else {}).values() for n in found}
    rows: list[dict] = []
    left: dict[str, list[str]] = {"no_participant": [], "key_problem": [], "invalid_grade": []}
    for n in sorted(results):
        r = results[n]
        if not (r.get("grade") or "").strip():
            continue  # no grade yet (a failed grading): nothing to give
        g = schema.valid_grade(r, top)
        if g is None:
            left["invalid_grade"].append(n)
            continue
        if n in bad_key:
            left["key_problem"].append(n)
            continue
        pid = (mapping.get(n, {}).get("participant_id") or "").strip()
        if not pid:
            left["no_participant"].append(n)
            continue
        rows.append({"number": n, "participant_id": pid, "moodle_identifier": IDENTIFIER.format(pid), "grade": _pts(g),
                     "max_grade": _pts(top), "feedback": r.get("feedback") or "", "approved": r.get("approved") or "",
                     "graded_by": r.get("graded_by") or "", "graded_at": r.get("graded_at") or ""})
    return rows, {k: v for k, v in left.items() if v}


def _text(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\r\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def remove_conflict_copies(assignment_dir: Path) -> list[str]:
    """OneDrive's conflict copies of the table ("Grades for Moodle-DESKTOP-ABC.csv"): derived, so they just go."""
    stem = Path(paths.MOODLE_TABLE).stem
    gone = []
    for p in Path(assignment_dir).glob(f"{stem}-*.csv"):
        try:
            p.unlink()
            gone.append(p.name)
        except OSError:
            pass
    return gone


def build(assignment_dir: Path) -> dict:
    """Builds the table again and writes it (only when it changed). Returns {"rows", "left_out", "path", "written"}."""
    rows, left = compute(assignment_dir)
    out = path(assignment_dir)
    remove_conflict_copies(assignment_dir)
    text = _text(rows)
    try:
        same = out.read_bytes() == text.encode("utf-8-sig")
    except OSError:
        same = False
    if not same:
        atomic.write_atomic(out, text, encoding="utf-8-sig")  # BOM, so Excel shows Hebrew feedback
    return {"rows": len(rows), "left_out": left, "path": str(out), "written": not same}


def read(assignment_dir: Path) -> list[dict]:
    """The table as written (build it first to be sure it is current)."""
    p = path(assignment_dir)
    if not p.is_file():
        return []
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def by_participant(rows: list[dict]) -> dict[str, dict]:
    return {r["participant_id"]: r for r in rows if r.get("participant_id")}
