"""Upload the grades to Moodle, only when someone asks for it (the site's "העלה ציונים" button, or `send-grades`):
Moodle's grading worksheet, filled in by number, for work whose marked files are already in Moodle.

Moodle has no API, and the only safe way to set many grades is its offline grading worksheet ("Offline grading
worksheet" must be on in the assignment's feedback settings; we never turn it on ourselves). So `send_grades`:
1. picks the numbers whose grade goes up (`pending`): their marked files are already in Moodle (`Upload log.csv`),
   they have a valid grade, and that grade and feedback are not yet in `Grades upload log.csv` exactly as they are now;
2. has the driver download a fresh worksheet in the user's Chrome (`download_worksheet`) and waits for it in Downloads;
3. fills in those numbers only, matched by participant id, never by row order (`upload.fill_for_upload`), into
   "3 - Ready to upload to Moodle/Grades for Moodle worksheet.csv", and counts how many grades really change;
4. has the driver upload it (`upload_grades`). Moodle then shows a preview of every change before it imports, so the
   driver confirms only when the preview's number of grade changes equals ours and nothing is skipped; otherwise it
   cancels and nothing changes in Moodle ("mismatch");
5. writes what went up to `Grades upload log.csv` (number, grade, a hash of the feedback, when, by whom: no names).

It runs under the assignment's upload lock (`Upload in progress.txt`), like the files. Uploading the same grades
again is harmless: Moodle changes only what differs. The downloaded worksheet (it has names and emails) is deleted
from Downloads once it was read; the filled copy stays in the upload folder, as the manual "Prepare return" leaves it.
"""

from __future__ import annotations

import csv
import hashlib
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from datastore import schema
from moodle import anonymize, lock, paths, upload, upload_log

UPLOAD_LOCK = paths.UPLOAD_LOCK  # the same lock as the files (moodle/send.py)

LOG_FILE = "Grades upload log.csv"
LOG_FIELDS = ["number", "grade", "feedback_sha256", "uploaded_at", "by"]
WORKSHEET_NAME = "Grading worksheet-{id}.csv"  # what the download script saves (Chrome adds " (1)" when it exists)
WORKSHEET_WAIT_S = 60

NOT_ENABLED = ('במטלה הזו "גיליון ציונים לא מקוון" (Offline grading worksheet) כבוי, ולכן אי אפשר להעלות ציונים. '
               "צריך לבקש מהמרצה להפעיל אותו בהגדרות המטלה (סוגי משוב), ואז ללחוץ שוב. הקבצים עצמם כבר עלו.")
NO_WORKSHEET = "גיליון הציונים לא הגיע להורדות תוך דקה. שום ציון לא עלה. אפשר לנסות שוב."


@dataclass
class GradesResult:
    """What the driver saw in Moodle for the worksheet.

    status: "imported" | "dry_run_ok" | "needs_login" | "mismatch" | "not_enabled" | "error"
    preview: how many grade changes Moodle's preview listed; skipped: how many rows it would skip (changed in Moodle
    after the download); updated: the number in Moodle's message after the import.
    """
    status: str
    preview: int | None = None
    skipped: int | None = None
    updated: int | None = None
    message: str = ""


class GradesDriver(Protocol):
    def download_worksheet(self, info: dict) -> dict:
        """Start the download of the grading worksheet in the user's Chrome. {"status": "started"|"not_enabled"|"needs_login"|"error", "message"}."""
        ...

    def upload_grades(self, info: dict, csv_path: Path, expected: int, dry_run: bool,
                      sha256: str | None = None) -> GradesResult:
        """Upload the filled worksheet, check Moodle's preview against `expected` grade changes, and confirm (not in a dry run)."""
        ...


@dataclass
class GradesReport:
    """How the grades upload ended. status: "done" | "nothing" | "dry_run_ok" | "not_enabled" | "needs_login" |
    "mismatch" | "error" | "locked". `sent`: numbers written to the log in this run."""
    status: str
    message: str = ""
    sent: int = 0
    changes: int = 0


# ---------- the log ----------
def log_path(assignment_dir: Path) -> Path:
    return assignment_dir / paths.UPLOAD / LOG_FILE


def feedback_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def read_log(assignment_dir: Path) -> list[dict]:
    path = log_path(assignment_dir)
    if not path.is_file():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("number")]


def last_sent(assignment_dir: Path) -> dict[str, tuple[str, str]]:
    """Number -> (grade, feedback hash) of its last upload."""
    return {row["number"]: (row.get("grade") or "", row.get("feedback_sha256") or "") for row in read_log(assignment_dir)}


def append_log(assignment_dir: Path, rows: list[dict]) -> None:
    path = log_path(assignment_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file()
    with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            writer.writeheader()
        writer.writerows(rows)


def same_grade(a: str, b: str) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return (a or "").strip() == (b or "").strip()


# ---------- what goes up ----------
def pending(assignment_dir: Path, results: dict | None = None, returned: set[str] | None = None) -> dict[str, dict]:
    """Number -> its grade row, for every number whose grade should go up now: its marked files are in Moodle
    (`returned`, by default from `Upload log.csv`), its grade is valid, and the log doesn't have it as it is now."""
    if results is None:
        if not upload.grades.files(assignment_dir):
            return {}
        results = upload.read_results(assignment_dir)
    if returned is None:
        returned = upload_log.returned_numbers(assignment_dir, paths.files_by_number(assignment_dir / paths.MARKED))
    max_grade = paths.read_info(assignment_dir).get("max_grade")
    sent = last_sent(assignment_dir)
    out = {}
    for number in returned:
        row = results.get(number)
        if not row or schema.valid_grade(row, max_grade) is None:
            continue
        before = sent.get(number)
        if before and same_grade(before[0], str(row["grade"])) and before[1] == feedback_hash(row.get("feedback")):
            continue
        out[number] = row
    return out


def worksheet_pattern(mid: str) -> re.Pattern:
    stem = re.escape(WORKSHEET_NAME.format(id=mid)[:-4])
    return re.compile(rf"{stem}(?: \(\d+\))?\.csv", re.IGNORECASE)


def wait_for_worksheet(mid: str, since: float, downloads: Path | None = None, timeout_s: float = WORKSHEET_WAIT_S,
                       sleep=time.sleep, clock=time.time) -> Path | None:
    """The worksheet the download script saved in Downloads at or after `since`, or None after `timeout_s`."""
    if downloads is None:
        from moodle import ingest  # loads 7-Zip helpers: only when a worksheet is awaited
        downloads = ingest.downloads_dir()
    pattern = worksheet_pattern(mid)
    end = clock() + timeout_s
    while True:
        found = [p for p in downloads.glob("*.csv") if pattern.fullmatch(p.name) and p.stat().st_mtime >= since - 2]
        if found:
            newest = max(found, key=lambda p: p.stat().st_mtime)
            size = newest.stat().st_size
            sleep(0.5)  # Chrome may still be writing it
            if newest.stat().st_size == size and size > 0:
                return newest
        if clock() >= end:
            return None
        sleep(1)


# ---------- the run ----------
def send_grades(assignment_dir: Path, driver: GradesDriver, *, dry_run: bool = False,
                downloads: Path | None = None, wait_s: float = WORKSHEET_WAIT_S, sleep=time.sleep,
                clock=time.time) -> GradesReport:
    """Upload the pending grades of the assignment (see the module docstring). Never raises for Moodle's answers;
    a broken worksheet (no identifier or grade column) comes back as "error"."""
    todo = pending(assignment_dir)
    if not todo:
        return GradesReport("nothing", "אין ציונים חדשים להעלאה.")
    try:
        lock_file = lock.take(assignment_dir, UPLOAD_LOCK)
    except lock.Locked as busy:
        return GradesReport("locked", f"{busy.who} מעלה את המטלה הזו עכשיו (מ-{busy.since:%H:%M}).")
    try:
        return _send(assignment_dir, driver, todo, dry_run, downloads, wait_s, sleep, clock, lock_file)
    finally:
        lock_file.unlink(missing_ok=True)


def _send(assignment_dir, driver, todo, dry_run, downloads, wait_s, sleep, clock, lock_file) -> GradesReport:
    info = paths.read_info(assignment_dir)
    mid = str(info["id"])
    started = clock()
    got = driver.download_worksheet(info)
    status = got.get("status")
    if status == "not_enabled":
        return GradesReport("not_enabled", NOT_ENABLED)
    if status != "started":
        return GradesReport(status if status in ("needs_login", "error") else "error",
                            "הורדת גיליון הציונים נכשלה: " + (got.get("message") or "Claude לא פירט מה השתבש."))
    worksheet = wait_for_worksheet(mid, started, downloads, wait_s, sleep, clock)
    if worksheet is None:
        return GradesReport("error", NO_WORKSHEET)
    lock.refresh(lock_file)

    out = assignment_dir / paths.UPLOAD / upload.GRADES_FOR_MOODLE
    try:
        filled = upload.fill_for_upload(worksheet, out, todo, anonymize.read_mapping(assignment_dir),
                                        info.get("max_grade"))
    except ValueError as e:
        return GradesReport("error", f"גיליון הציונים ממודל לא במבנה הצפוי: {e}")
    finally:
        worksheet.unlink(missing_ok=True)  # Moodle's sheet has names and emails: it doesn't stay in Downloads

    in_sheet = [n for n in todo if n in filled["filled"]]
    missing = sorted(set(todo) - set(in_sheet))
    note = f" {len(missing)} מספרים לא נמצאו בגיליון של מודל: {', '.join(missing[:10])}." if missing else ""
    if not in_sheet:
        return GradesReport("error", "אף אחד מהמספרים לא נמצא בגיליון הציונים של מודל, ולכן שום ציון לא עלה." + note)

    def record() -> int:
        now = datetime.now().isoformat(timespec="seconds")
        append_log(assignment_dir, [{"number": n, "grade": str(todo[n]["grade"]),
                                     "feedback_sha256": feedback_hash(todo[n].get("feedback")),
                                     "uploaded_at": now, "by": lock.me()} for n in sorted(in_sheet)])
        return len(in_sheet)

    if filled["changed_rows"] == 0:
        # Moodle already has exactly these grades and feedback: nothing to upload, only the log was behind
        sent = 0 if dry_run else record()
        return GradesReport("done" if not dry_run else "dry_run_ok",
                            f"הציונים במודל כבר מעודכנים ({len(in_sheet)} מספרים).{note}", sent=sent)

    expected = filled["grade_changes"]
    result = driver.upload_grades(info, out, expected, dry_run, sha256=upload_log.file_hash(out))
    numbers = (f"שינויי ציון צפויים: {expected}, בתצוגה המקדימה של מודל: {result.preview}, "
               f"דולגו: {result.skipped or 0}")
    if dry_run:
        if result.status == "dry_run_ok" and result.preview == expected and not result.skipped:
            return GradesReport("dry_run_ok", f"בדיקה יבשה של הציונים עברה ({numbers}). שום ציון לא השתנה.{note}",
                                changes=expected)
        return GradesReport(result.status if result.status != "dry_run_ok" else "mismatch",
                            (result.message or numbers) + note)
    if result.status == "imported" and result.preview == expected and not result.skipped:
        sent = record()
        moodle_says = f" מודל: עודכנו {result.updated}." if result.updated is not None else ""
        return GradesReport("done", f"{sent} ציונים עלו למודל ({expected} מהם השתנו).{moodle_says}{note}",
                            sent=sent, changes=expected)
    if result.status == "imported":
        # Moodle imported although the preview did not match (should not happen: the prompt cancels then)
        return GradesReport("mismatch", f"מודל עדכן ציונים, אבל המספרים לא תואמים ({numbers}). צריך לבדוק במודל.{note}")
    if result.status == "not_enabled":
        return GradesReport("not_enabled", NOT_ENABLED)
    why = result.status if result.status in ("needs_login", "mismatch", "error") else "error"
    detail = result.message or numbers
    if why == "mismatch":
        detail = f"התצוגה המקדימה של מודל לא תאמה ({numbers}), ולכן ההעלאה בוטלה ושום ציון לא השתנה."
    return GradesReport(why, detail + note)
