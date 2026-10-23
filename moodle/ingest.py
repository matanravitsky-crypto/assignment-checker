"""Turn a "Download all submissions" ZIP into numbered files ready for grading.

Moodle names the ZIP "<course>-<assignment name>-<assignment id>.zip" and asks
for 7-Zip to open it (Python's zipfile garbles some Hebrew names), so this uses
7-Zip.
"""

import csv
import json
import os
import re
import shutil
import stat
import subprocess
import time
import zipfile
from datetime import datetime
from pathlib import Path

from moodle import anonymize, guide, lock, paths

SEVEN_ZIP_PATHS = [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]


# What Moodle gives: one ZIP of all submissions, or the list "<name>-<id>.json" that moodle/download_parts.js saves
# last, after its parts "<name>-<id> part 003 of 015.zip" (Moodle cuts a big ZIP early, so the dashboard downloads in parts)
LIST = ".json"
ARCHIVES = (".zip", LIST)


def _archives(downloads: Path, assignment_id: str) -> list[Path]:
    return [p for p in downloads.iterdir()
            if p.suffix.lower() in ARCHIVES and p.stem.endswith(f"-{assignment_id}") and p.is_file()]


def find_download(assignment_id: str, downloads: Path | None = None) -> Path:
    """Return the newest finished ZIP (or list of parts) for this assignment in Downloads."""
    downloads = downloads or downloads_dir()
    zips = _archives(downloads, assignment_id)
    if not zips:
        raise FileNotFoundError(f"No ZIP ending in -{assignment_id}.zip in {downloads}")
    return max(zips, key=lambda p: p.stat().st_mtime)


def downloads_dir() -> Path:
    return Path.home() / "Downloads"


def wait_for_download(assignment_id: str, since: float, downloads: Path | None = None, *,
                      start_s: float = 180, total_s: float = 1800, poll_s: float = 2.0,
                      clock=time.monotonic, sleep=time.sleep, on_size=None) -> Path:
    """Wait for the ZIP that Chrome is downloading to Downloads, and return it once it is whole.

    `since` is a time.time() from before the download was asked for: only a ZIP modified after it counts.
    Chrome writes "<name>.crdownload" (or "Unconfirmed <n>.crdownload") while it downloads, and renames it
    when it is done. Nothing at all within `start_s` means the download never started (say, Chrome asks where to
    save); a ZIP whose size holds still for two polls is done. Raises TimeoutError with the reason in English.
    `on_size(bytes)` hears how much has arrived so far, on every poll.
    """
    downloads = downloads or downloads_dir()
    started = clock()
    seen_partial = False
    last_size = None
    while True:
        zips = [p for p in _archives(downloads, assignment_id) if _mtime(p) >= since - 2]
        newest = max(zips, key=_mtime, default=None)
        if on_size:
            partial = [p for p in downloads.glob("*.crdownload") if _mtime(p) >= since - 2]
            on_size(_size(newest) if newest is not None else max(map(_size, partial), default=0))
        if newest is not None:
            size = _size(newest)
            if size and size == last_size:
                return newest
            last_size = size
        else:
            last_size = None
            seen_partial = seen_partial or any(_mtime(p) >= since - 2 for p in downloads.glob("*.crdownload"))
        waited = clock() - started
        if newest is None and not seen_partial and waited > start_s:
            raise TimeoutError("The download did not start in Chrome")
        if waited > total_s:
            raise TimeoutError("The download did not finish in time")
        sleep(poll_s)


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:  # Chrome renamed or removed it between glob and stat
        return 0.0


def _size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def seven_zip() -> str:
    found = shutil.which("7z") or next((p for p in SEVEN_ZIP_PATHS if Path(p).exists()), None)
    if not found:
        raise FileNotFoundError("7-Zip is not installed (winget install 7zip.7zip)")
    return found


def run_7z(args: list[str], on_percent=None) -> int:
    """Run 7-Zip and return its exit code. With `on_percent`, 7-Zip prints its progress ("-bsp1") and every new
    percent is passed on, so a big ZIP (2 GB and more) does not look stuck."""
    if not on_percent:
        return subprocess.run([seven_zip(), *args, "-bsp0"]).returncode
    proc = subprocess.Popen([seven_zip(), *args, "-bsp1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    last = None
    while chunk := proc.stdout.read1(4096):
        found = re.findall(rb"(\d{1,3})%", chunk)
        if found and int(found[-1]) != last:
            last = int(found[-1])
            on_percent(last)
    return proc.wait()


def remove_tree(path: Path) -> None:
    """Delete a folder even when 7-Zip extracted parts of it as read-only."""
    def make_writable_and_retry(function, target, _error):
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onexc=make_writable_and_retry)


def name_from_zip(zip_path: Path, assignment_id: str) -> str:
    """'214193210120271-הגשה 0 - קבוצות ומרוכבים-3438636.zip' -> 'הגשה 0 - קבוצות ומרוכבים'."""
    stem = zip_path.stem.removesuffix(f"-{assignment_id}")
    _course_code, _, name = stem.partition("-")
    return name.strip() or stem


def assignment_folder(assignment_id: str, zip_path: Path, course: str | None, name: str | None) -> Path:
    """The assignment's folder: the existing one, or a new <course>/<name>.

    Folder names are in English, so a new assignment needs both, e.g.
    --course "Linear Algebra" --name "Assignment 1 - Vectors". Its Hebrew
    title, as Moodle shows it, comes from the ZIP's file name.
    """
    existing = paths.find_assignment(assignment_id)
    if existing:
        return existing
    if not course or not name:
        raise ValueError(f"New assignment {assignment_id}: give --course and --name in English, "
                         f"e.g. --course \"Linear Algebra\" --name \"Assignment 1 - Vectors\"")
    folder = paths.data_dir() / course / name
    folder.mkdir(parents=True, exist_ok=True)
    info = {"id": str(assignment_id), "course": course, "name": name,
            "title": name_from_zip(zip_path, assignment_id)}
    (folder / paths.INFO).write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return folder


INCOMPLETE = "incomplete"


def _set_aside(download: Path, why: str) -> None:
    """Rename a broken download to "<name> (incomplete).<ext>", so the next pull does not take it again."""
    aside = download.with_name(f"{download.stem} ({INCOMPLETE}){download.suffix}")
    download.replace(aside)
    raise ValueError(f"The download is {INCOMPLETE} or broken ({why}); renamed to {aside.name}")


def _part_pattern(name: str) -> re.Pattern:
    """A part's file name as the list has it, or as Chrome renames it when the name is taken ("... of 015 (1).zip")."""
    stem = name.removesuffix(".zip")
    return re.compile(re.escape(stem) + r"(?: \(\d+\))?\.zip", re.IGNORECASE)


def parts_progress(assignment_id: str, since: float, downloads: Path | None = None) -> tuple[int, int]:
    """(how many parts of a download in parts are already in Downloads, how many are planned) for the progress bar.

    The page names each part "part 003 of 015": the planned count is the highest "of" so far (a part Moodle cut is
    asked for again in two halves, so it can grow), 0 when no part has come yet."""
    downloads = downloads or downloads_dir()
    pattern = re.compile(rf".*-{assignment_id} part \d{{3}}(?: of (\d{{3}}))?(?: \(\d+\))?\.zip", re.IGNORECASE)
    arrived, planned = 0, 0
    for p in downloads.iterdir():
        m = pattern.fullmatch(p.name)
        if m and _mtime(p) >= since - 2:
            arrived += 1
            planned = max(planned, int(m.group(1) or 0))
    return arrived, max(planned, arrived) if planned else 0


def parts_arrived(assignment_id: str, since: float, downloads: Path | None = None) -> int:
    """How many parts of a download in parts are already in Downloads (for the progress bar)."""
    return parts_progress(assignment_id, since, downloads)[0]


def gather_parts(list_path: Path) -> list[Path]:
    """The parts in Downloads that the list from moodle/download_parts.js names, in order.

    Each part must be there with exactly the size the page saved (the page checked it is a whole ZIP), as a file
    that is not older than an hour before the list. A part that Moodle cut every time is under "failed".
    Anything missing sets the list aside as "(incomplete)", and the next pull downloads again.
    """
    try:
        listed = json.loads(list_path.read_text(encoding="utf-8"))
        files = listed["files"]
        assert isinstance(files, list) and all(isinstance(f.get("name"), str) and isinstance(f.get("size"), int)
                                               for f in files)
    except (OSError, ValueError, KeyError, AssertionError, AttributeError):
        _set_aside(list_path, "not a list of parts")
    if listed.get("failed"):
        _set_aside(list_path, f"parts Moodle cut every time: {listed['failed']}")
    if not files:
        _set_aside(list_path, "no parts")
    newer_than = _mtime(list_path) - 3600
    parts = []
    for f in files:
        pattern = _part_pattern(Path(f["name"]).name)  # a name only: never a path out of Downloads
        found = [p for p in list_path.parent.iterdir()
                 if pattern.fullmatch(p.name) and _size(p) == f["size"] and _mtime(p) >= newer_than]
        if not found:
            _set_aside(list_path, f"missing part {f['name']}")
        parts.append(max(found, key=_mtime))
    return parts


def check_whole(zip_path: Path, on_percent=None, download: Path | None = None) -> None:
    """7-Zip tests every file in the ZIP before anything is moved or deleted.

    Moodle can end a big download early and Chrome still saves it as a finished .zip (on 2026-10-23: 356, 913 and
    889 MB of about 2.4 GB). Then the download (`download`, or the ZIP itself) is set aside as "(incomplete)".
    """
    if run_7z(["t", str(zip_path), "-bso0", "-bse0"], on_percent) != 0:
        _set_aside(download or zip_path, "7-Zip test failed")
    loose = files_without_folder(zip_path)
    if loose:
        _set_aside(download or zip_path, f"{NO_FOLDERS}: {loose} files")


# Moodle's "download in folders" is a personal option for every assignment, and it was off for two parts on
# 2026-10-23 (two pulls at once, each clicking it): a file without its "<name>_<participant id>_assignsubmission_..."
# folder has no participant id, and numbering would have dropped those students
NO_FOLDERS = "not in a folder per student"
IN_FOLDER = re.compile(r"[^/\\]+_\d+_assignsubmission_[a-z]+[/\\].+")


def files_without_folder(zip_path: Path) -> int:
    """How many files in the ZIP are not inside a student's folder. Only the structure is read (zipfile may garble a
    Hebrew name, never a slash or the digits of the participant id)."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            return sum(1 for n in z.namelist() if not n.endswith("/") and not IN_FOLDER.fullmatch(n))
    except (zipfile.BadZipFile, OSError):
        return 0  # 7-Zip already tested it: a ZIP that zipfile cannot read is left to the extraction


def _free_stamp(target: Path) -> str:
    """"2026-10-23 11-15-07" for the kept download, with " (2)" ... when a download of that second is already kept."""
    stamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    taken = lambda s: any((target / f"{paths.DOWNLOAD_PREFIX} {s}{ext}").exists() for ext in ("", ".zip"))
    n, free = 1, stamp
    while taken(free):
        n += 1
        free = f"{stamp} ({n})"
    return free


def _in_steps(report, phase: str, i: int, n: int):
    """A percent of one of n parts → a percent of all of them."""
    return lambda pct: report(phase, (i * 100 + pct) // n, 100)


def ingest(assignment_id: str, zip_path: Path | None = None,
           course: str | None = None, name: str | None = None, on_progress=None) -> list[dict]:
    """`on_progress(phase, done, total)` tells the dashboard where it is: "check" and "extract" in percent (of 100),
    "number" in student folders.

    `zip_path` is one ZIP of all submissions, or the list of parts from moodle/download_parts.js (each part is a
    ZIP of some of the students, all in Moodle's folder per student), which are extracted into the same folder.
    A list of only what changed (its "since") holds only those students: everyone else keeps what they have."""
    report = on_progress or (lambda *_: None)
    zip_path = zip_path or find_download(assignment_id)
    in_parts = zip_path.suffix.lower() == LIST
    if in_parts and nothing_changed(zip_path):
        return _log_unchanged(assignment_id, zip_path, course, name)
    zips = gather_parts(zip_path) if in_parts else [zip_path]
    report("check", 0, 100)
    for i, z in enumerate(zips):
        check_whole(z, on_percent=on_progress and _in_steps(report, "check", i, len(zips)), download=zip_path)
    target = assignment_folder(assignment_id, zip_path, course, name)
    anonymize.check_key(target)  # before anything moves: a broken key must leave the folder as it is

    # Keep every download: a later one (after the due date) must not erase the first, even a minute later. Parts go
    # together in a folder. On this computer only, never in the shared folder (names; GBs)
    backup = paths.backup_dir(target)
    backup.mkdir(parents=True, exist_ok=True)
    stamp = _free_stamp(backup)
    if in_parts:
        kept_dir = backup / f"{paths.DOWNLOAD_PREFIX} {stamp}"
        kept_dir.mkdir()
        moved = []
        for i, z in enumerate(zips, 1):
            moved.append(kept_dir / f"part {i:03}.zip")
            shutil.move(z, moved[-1])
        shutil.move(zip_path, kept_dir / "parts.json")
        zips = moved
    else:
        kept = backup / f"{paths.DOWNLOAD_PREFIX} {stamp}.zip"
        shutil.move(zip_path, kept)
        zips = [kept]

    original = paths.original_dir(target)
    if original.exists():
        remove_tree(original)
    original.mkdir(parents=True)
    report("extract", 0, 100)
    for i, z in enumerate(zips):
        args = ["x", str(z), f"-o{original}", "-y", "-bso0"]
        code = run_7z(args, on_percent=on_progress and _in_steps(report, "extract", i, len(zips)))
        if code:
            raise subprocess.CalledProcessError(code, ["7z", *args])

    before = set(anonymize.existing_numbers(target).values())
    rows = anonymize.prepare(original, target, on_folder=on_progress and (lambda done, total: report("number", done, total)))
    log_pull(target, rows, before, len(zips))
    guide.write_guides(paths.data_dir())
    return rows


def nothing_changed(list_path: Path) -> bool:
    """A list from download_parts.js that asked only for what changed since the last pull, and nothing had."""
    try:
        listed = json.loads(list_path.read_text(encoding="utf-8"))
        return int(listed.get("since") or 0) > 0 and listed.get("files") == [] and not listed.get("failed")
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def _log_unchanged(assignment_id: str, list_path: Path, course: str | None, name: str | None) -> list[dict]:
    """Nothing changed in Moodle: no file is touched, the list is kept with the other downloads, and the pull is logged
    (the next one asks only for what changes after it)."""
    target = assignment_folder(assignment_id, list_path, course, name)
    anonymize.check_key(target)
    backup = paths.backup_dir(target)
    backup.mkdir(parents=True, exist_ok=True)
    shutil.move(list_path, backup / f"{paths.DOWNLOAD_PREFIX} {_free_stamp(backup)} (no changes).json")
    rows = anonymize.existing_rows(target)
    log_pull(target, rows, {int(r["number"]) for r in rows}, 0)
    return rows


PULL_LOG_FIELDS = ["pulled_at", "by", "students", "new", "files", "parts"]


def log_pull(target: Path, rows: list[dict], before: set[int], parts: int) -> None:
    """One row in the assignment's "Pull log.csv": when, who (as in the lock files), and how many. Numbers only."""
    numbers = {int(r["number"]) for r in rows}
    log = target / paths.PULL_LOG
    new_file = not log.exists()
    with open(log, "a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PULL_LOG_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow({"pulled_at": datetime.now().isoformat(timespec="seconds"), "by": lock.me(),
                         "students": len(numbers), "new": len(numbers - before), "files": len(rows), "parts": parts})


def pulls(target: Path) -> list[str]:
    """When the assignment was pulled (pulled_at of every row in "Pull log.csv"), oldest first."""
    try:
        with open(target / paths.PULL_LOG, encoding="utf-8-sig", newline="") as f:
            return sorted(r["pulled_at"] for r in csv.DictReader(f) if r.get("pulled_at"))
    except (OSError, csv.Error):
        return []
