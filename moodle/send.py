"""Decide what goes into the next upload to Moodle: only marked work that is new or changed.

`prepare_batch` looks at the marked files of an assignment and leaves out
    - numbers already returned: every marked file still equals what the log says was uploaded
    - numbers the student resubmitted after the work was marked (the marked file is of the old submission)
and packs the rest into ZIPs of at most `max_bytes` in "3 - Ready to upload to Moodle/", with
    Upload batch.json    which ZIP holds which files, with each file's hash (see upload_log.py)
    Upload steps.txt     the steps for whoever uploads by hand

It also reports what to know before uploading, by number only (no names): files too big for one
upload (their whole number stays out), resubmitted numbers, and numbers nobody approved yet in Grades.csv.
Unapproved work is still uploaded: that list is for the person who confirms the batch.

Nothing here talks to Moodle, and nothing here writes the log: a ZIP is logged by `upload_log.record_zip`
once someone has uploaded it.
"""

import csv
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from moodle import anonymize, paths, upload, upload_log


class BatchBlocked(ValueError):
    """The batch can't be prepared until someone fixes something. The message is in Hebrew, for the user."""


@dataclass
class BatchSummary:
    id: str
    assignment_id: str
    title: str
    students: int
    files: int
    zips: list[dict]  # {"name", "count", "mb"}
    too_big: list[str]
    resubmitted: list[str]
    not_approved: list[str]


def is_approved(row: dict | None) -> bool:
    """Same rule as grading.grade.is_approved (not imported: grading/ loads PyMuPDF, moodle/ must not)."""
    return bool(row) and (row.get("approved") or "").strip().lower() not in ("", "0", "no", "false", "לא")


def submission_files(assignment_dir: Path) -> dict[str, list[Path]]:
    """Number -> its submission files in "1 - Submissions to grade", by the key table (one row per file).

    Not anonymize.read_mapping: that keeps only a number's first row, and a number can have several files.
    """
    to_grade = assignment_dir / paths.TO_GRADE
    out: dict[str, list[Path]] = {}
    with open(assignment_dir / paths.KEY, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if (to_grade / row["anon_file"]).is_file():
                out.setdefault(row["number"], []).append(to_grade / row["anon_file"])
    return out


def newest(files: list[Path]) -> float:
    return max((p.stat().st_mtime for p in files), default=0.0)


def prepare_batch(assignment_dir: Path, max_bytes: int = upload.CLAUDE_MAX_ZIP_BYTES) -> BatchSummary:
    conflicts = upload_log.log_conflicts(assignment_dir)
    if conflicts:
        raise BatchBlocked(
            f"ב-OneDrive נוצר עותק כפול של יומן ההעלאה ({', '.join(conflicts)}). "
            f"צריך לאחד אותו עם `{upload_log.LOG_FILE}` ולמחוק את העותק לפני העלאה נוספת.")

    mapping = anonymize.read_mapping(assignment_dir)
    marked_dir = assignment_dir / paths.MARKED
    marked = paths.files_by_number(marked_dir)
    for number, files in marked.items():
        if number not in mapping:
            raise ValueError(f"{files[0].name}: המספר {number} לא בטבלת המפתח")

    returned = upload_log.returned_numbers(assignment_dir, marked)
    submissions = submission_files(assignment_dir)
    resubmitted = sorted(n for n, files in marked.items()
                         if n not in returned and newest(submissions.get(n, [])) > newest(files))
    going = {n for n in marked if n not in returned and n not in resubmitted}

    upload_dir = assignment_dir / paths.UPLOAD
    upload_dir.mkdir(parents=True, exist_ok=True)
    parts, too_big = upload.plan_parts(marked_dir, mapping, max_bytes, going)
    # Hash before zipping: if a file changes in between, the log then holds the older hash and the number goes up again
    hashes = {src: upload_log.file_hash(src) for part in parts for src, _ in part}
    zips = upload.write_zips(upload_dir, parts)

    info = paths.read_info(assignment_dir)
    created = datetime.now()
    batch = {
        "id": f"{created:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}",
        "assignment_id": str(info["id"]),
        "created_at": created.isoformat(timespec="seconds"),
        "zips": [{"name": z.name,
                  "files": [{"number": src.stem[:4], "file": src.name, "sha256": hashes[src]} for src, _ in part]}
                 for z, part in zip(zips, parts)],
    }
    upload_log.write_batch(assignment_dir, batch)

    grades = upload.read_results(assignment_dir) if (assignment_dir / paths.GRADES).exists() else {}
    in_batch = {f["number"] for z in batch["zips"] for f in z["files"]}
    upload.write_instructions(upload_dir / upload.INSTRUCTIONS_FILE, {
        "assignment_id": batch["assignment_id"],
        "submissions": len(mapping),
        "results": len(grades),
        "missing_results": sorted(set(mapping) - set(grades)),
        "grades_filled": None,
        "feedback_zips": zips,
        "too_big": too_big,
    }, max_bytes)

    return BatchSummary(
        id=batch["id"],
        assignment_id=batch["assignment_id"],
        title=info.get("title") or info.get("name", ""),
        students=len(in_batch),
        files=sum(len(z["files"]) for z in batch["zips"]),
        zips=[{"name": z.name, "count": len(part), "mb": round(z.stat().st_size / 1_000_000, 1)}
              for z, part in zip(zips, parts)],
        too_big=too_big,
        resubmitted=resubmitted,
        not_approved=sorted(n for n in in_batch if not is_approved(grades.get(n))),
    )
