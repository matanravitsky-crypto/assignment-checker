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

`run_batch` then hands each ZIP to a driver, which does the upload in Moodle (the driver of Claude in Chrome
comes separately; `SimulatedDriver` stands in for it in tests and in the site's demo). A ZIP goes into the log
(`upload_log.record_zip`) only when the driver's answer matches the number of files in it. A stopped run resumes
where it stopped: ZIPs whose files are all in the log with the same hash are skipped. While it runs, the
assignment has `Upload in progress.txt` (see lock.py), so two people don't upload the same assignment at once.

Nothing in `prepare_batch` talks to Moodle or writes the log.
"""

import csv
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from moodle import anonymize, lock, paths, upload, upload_log

UPLOAD_LOCK = "Upload in progress.txt"
STALE_MESSAGE = "הקבצים השתנו מאז ההכנה. צריך להכין שוב."


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


# ---------- העלאה ----------
@dataclass
class UploadResult:
    """What the driver saw in Moodle for one ZIP.

    status: "imported" | "dry_run_ok" | "needs_login" | "mismatch" | "error"
    rows: how many files Moodle processed (imported + skipped), or the expected count in a dry run (nothing is imported);
    imported / skipped: how many files Moodle imported / left as they were.
    """
    status: str
    rows: int | None = None
    imported: int | None = None
    skipped: int | None = None
    message: str = ""


class MoodleDriver(Protocol):
    def upload_zip(self, info: dict, zip_path: Path, expected: int, dry_run: bool) -> UploadResult:
        """Upload one ZIP of `expected` files (or, with dry_run, check the page and attach the file, then cancel: nothing is imported)."""
        ...


class SimulatedDriver:
    """A driver that never touches Moodle: gives `results` one by one, then says every ZIP went through.

    For tests, and for the site with MOODLE_DRIVER=simulate. `delay` seconds per ZIP make progress visible.
    """

    def __init__(self, results: list[UploadResult] | None = None, delay: float = 0.0):
        self.results = list(results or [])
        self.delay = delay
        self.calls: list[str] = []  # names of the ZIPs it was given

    def upload_zip(self, info: dict, zip_path: Path, expected: int, dry_run: bool) -> UploadResult:
        self.calls.append(zip_path.name)
        if self.delay:
            time.sleep(self.delay)
        if self.results:
            return self.results.pop(0)
        if dry_run:
            return UploadResult("dry_run_ok", rows=expected)
        return UploadResult("imported", rows=expected, imported=expected)


@dataclass
class RunReport:
    """How a run ended. `done_zips`: every ZIP of the batch that is finished, in this run or an earlier one.
    `recorded`: log rows this run wrote. `stopped`: None when all went through, else why it stopped:
    "user" | "needs_login" | "mismatch" | "error" | "stale" | "locked"."""
    total_zips: int
    done_zips: list[str] = field(default_factory=list)
    recorded: int = 0
    stopped: str | None = None
    message: str = ""


def current_batch(assignment_dir: Path, batch_id: str) -> dict | None:
    """The batch list, if it is still the one the person confirmed (a new prepare changes the id)."""
    batch = upload_log.read_batch(assignment_dir)
    return batch if batch and batch["id"] == batch_id else None


def counts_match(result: UploadResult, expected: int) -> bool:
    return result.rows == expected and (result.imported or 0) + (result.skipped or 0) == expected


def run_batch(
    assignment_dir: Path,
    batch_id: str,
    driver: MoodleDriver,
    *,
    dry_run: bool = False,
    should_stop: Callable[[], bool] = lambda: False,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> RunReport:
    """Upload the ZIPs of the prepared batch `batch_id` one by one, and log each one Moodle accepted.

    `should_stop` is asked before every ZIP that is still to upload; `on_progress(index, total, zip_name)` is
    called after each ZIP this run finished (index counts from 1 in the batch). With `dry_run` only the first ZIP
    that is still to upload is checked as far as attaching the file (Moodle imports at once, so it never imports), and nothing is logged.
    """
    batch = current_batch(assignment_dir, batch_id)
    if batch is None:
        return RunReport(0, stopped="stale", message=STALE_MESSAGE)
    try:
        lock_file = lock.take(assignment_dir, UPLOAD_LOCK)
    except lock.Locked as busy:
        return RunReport(len(batch["zips"]), stopped="locked",
                         message=f"{busy.who} מעלה את המטלה הזו עכשיו (מ-{busy.since:%H:%M}).")
    try:
        return upload_zips(assignment_dir, batch_id, batch["zips"], driver, dry_run, should_stop, on_progress, lock_file)
    finally:
        lock_file.unlink(missing_ok=True)


def upload_zips(
    assignment_dir: Path,
    batch_id: str,
    zips: list[dict],
    driver: MoodleDriver,
    dry_run: bool,
    should_stop: Callable[[], bool],
    on_progress: Callable[[int, int, str], None] | None,
    lock_file: Path,
) -> RunReport:
    """The loop of run_batch, with the lock already taken."""
    report = RunReport(len(zips))
    info = paths.read_info(assignment_dir)
    uploaded = upload_log.last_hashes(assignment_dir)

    def stop(why: str, message: str) -> RunReport:
        report.stopped, report.message = why, message
        return report

    def finished(index: int, name: str) -> None:
        lock.refresh(lock_file)  # a long run keeps its lock alive
        if on_progress:
            on_progress(index, report.total_zips, name)

    for index, entry in enumerate(zips, 1):
        name, files = entry["name"], entry["files"]
        if all(uploaded.get(f["file"]) == f["sha256"] for f in files):
            report.done_zips.append(name)  # an earlier run did this one: that is how a stopped batch resumes
            continue
        if should_stop():
            return stop("user", f"נעצר לבקשתך אחרי {len(report.done_zips)} מתוך {report.total_zips} קבצי ZIP.")
        if current_batch(assignment_dir, batch_id) is None:  # prepared again meanwhile: these ZIPs are not the ones confirmed
            return stop("stale", STALE_MESSAGE)

        expected = len(files)
        result = driver.upload_zip(info, assignment_dir / paths.UPLOAD / name, expected, dry_run)
        if dry_run and result.status == "dry_run_ok" and result.rows == expected:
            report.message = f"בדיקה יבשה עברה: הדף והקובץ נבדקו ({result.rows} קבצים ב-ZIP), שום דבר לא יובא"
            finished(index, name)
            return report
        if not dry_run and result.status == "imported" and counts_match(result, expected):
            # An upload takes minutes: if the batch was prepared again meanwhile, the list now on disk is not the
            # one this ZIP was built from, and record_zip would log the wrong hashes (or fail after Moodle imported).
            # Record nothing; uploading the ZIP again later is safe.
            if current_batch(assignment_dir, batch_id) is None:
                return stop("stale", STALE_MESSAGE)
            report.recorded += upload_log.record_zip(assignment_dir, name, by=lock.me())
            report.done_zips.append(name)
            finished(index, name)
            continue

        # Anything else stops the run; a result that says imported (or checked) but fails the numbers is an error
        detail = result.message
        if not detail and result.status in ("imported", "dry_run_ok"):
            detail = (f"קבצים צפויים: {expected}, קבצים ש-Moodle עיבד: {result.rows}, "
                      f"יובאו: {result.imported or 0}, דולגו: {result.skipped or 0}")
        why = result.status if result.status in ("needs_login", "mismatch", "error") else "error"
        return stop(why, f"{name}: {detail}")

    if dry_run or report.recorded == 0:
        report.message = "אין מה להעלות: כל קבצי ה-ZIP כבר הועלו."
    else:
        report.message = (f"הסתיים: {len(report.done_zips)} מתוך {report.total_zips} קבצי ZIP הועלו, "
                          f"{report.recorded} קבצים נרשמו ביומן.")
    return report
