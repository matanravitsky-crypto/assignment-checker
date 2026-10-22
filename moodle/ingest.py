"""Turn a "Download all submissions" ZIP into numbered files ready for grading.

Moodle names the ZIP "<course>-<assignment name>-<assignment id>.zip" and asks
for 7-Zip to open it (Python's zipfile garbles some Hebrew names), so this uses
7-Zip.
"""

import json
import os
import re
import shutil
import stat
import subprocess
from datetime import datetime
from pathlib import Path

from moodle import anonymize, guide, paths

SEVEN_ZIP_PATHS = [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]


def find_download(assignment_id: str, downloads: Path | None = None) -> Path:
    """Return the newest finished ZIP for this assignment in Downloads."""
    downloads = downloads or Path.home() / "Downloads"
    zips = [p for p in downloads.glob("*.zip") if p.stem.endswith(f"-{assignment_id}")]
    if not zips:
        raise FileNotFoundError(f"No ZIP ending in -{assignment_id}.zip in {downloads}")
    return max(zips, key=lambda p: p.stat().st_mtime)


def find_parts(assignment_id: str, downloads: Path | None = None) -> list[Path]:
    """Every ZIP of this assignment in Downloads, for an assignment downloaded in parts.

    A big assignment is too much for one Moodle ZIP (at ~2 GB it comes out cut off), so it is
    downloaded 100 submissions at a time. Chrome names the repeats "<name> (1).zip", "(2)" ...
    """
    downloads = downloads or Path.home() / "Downloads"
    pattern = re.compile(rf"-{assignment_id}( \(\d+\))?$")
    zips = sorted(p for p in downloads.glob("*.zip") if pattern.search(p.stem))
    if not zips:
        raise FileNotFoundError(f"No ZIP ending in -{assignment_id}.zip in {downloads}")
    return zips


def participants_in(zip_path: Path) -> set[str]:
    """Moodle participant ids of the student folders in a ZIP."""
    listing = subprocess.run([seven_zip(), "l", "-slt", "-sccUTF-8", str(zip_path)],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return set(re.findall(r"^Path = [^\r\n]*?_(\d+)_assignsubmission_", listing, re.M))


# Parts of one download are minutes apart; an older ZIP left in Downloads would be hours or days older
PARTS_WINDOW_SECONDS = 2 * 60 * 60


def check_parts_belong_together(zips: list[Path]) -> None:
    """Parts must come from one sitting, so a student in two of them has the same submission in both.

    While pages are downloaded one by one, new submissions shift Moodle's table, so a student at a
    page edge can land in two parts (and another can be skipped: compare the total with Moodle).
    """
    times = [p.stat().st_mtime for p in zips]
    if max(times) - min(times) > PARTS_WINDOW_SECONDS:
        raise ValueError("These ZIPs were downloaded more than 2 hours apart, so they are not parts of one "
                         "download. Keep only this download's parts in Downloads. Nothing was changed.")


def extract_parts(zips: list[Path], original: Path) -> None:
    """Extract parts into one folder per student; a student in two parts keeps the newer part's copy."""
    for index, part in enumerate(sorted(zips, key=lambda p: p.stat().st_mtime)):
        staging = original / f"_part {index}"
        subprocess.run([seven_zip(), "x", str(part), f"-o{staging}", "-y", "-bso0", "-bsp0"], check=True)
        for student in staging.iterdir():
            if (original / student.name).exists():
                remove_tree(original / student.name)
            shutil.move(student, original / student.name)
        staging.rmdir()


def seven_zip() -> str:
    found = shutil.which("7z") or next((p for p in SEVEN_ZIP_PATHS if Path(p).exists()), None)
    if not found:
        raise FileNotFoundError("7-Zip is not installed (winget install 7zip.7zip)")
    return found


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


def check_zip(zip_path: Path) -> None:
    """Refuse a ZIP that is cut off or damaged, before anything is moved or deleted.

    A big download can end early (on 22/10 a 1.8 GB one did) and still look finished.
    """
    test = subprocess.run([seven_zip(), "t", str(zip_path), "-bso0", "-bsp0"], capture_output=True)
    if test.returncode != 0:
        raise ValueError(f"{zip_path.name} is incomplete or damaged; download it again from Moodle. "
                         f"Nothing was changed.")


def ingest(assignment_id: str, zip_path: Path | list[Path] | None = None,
           course: str | None = None, name: str | None = None) -> list[dict]:
    """zip_path is one ZIP of the whole assignment, or the list of its parts (see find_parts)."""
    zips = zip_path if isinstance(zip_path, list) else [zip_path or find_download(assignment_id)]
    for part in zips:
        check_zip(part)
    if len(zips) > 1:
        check_parts_belong_together(zips)
    target = assignment_folder(assignment_id, zips[0], course, name)

    # Keep every download: a later one (after the due date) must not erase the first
    stamp = datetime.now().strftime("%Y-%m-%d %H-%M")
    paths.backup_dir(target).mkdir(parents=True, exist_ok=True)
    kept = []
    # Oldest first, so "part 1" is the first page downloaded (shutil.move keeps the file times)
    zips = sorted(zips, key=lambda p: p.stat().st_mtime)
    for index, part in enumerate(zips, start=1):
        suffix = f" part {index}" if len(zips) > 1 else ""
        kept.append(paths.backup_dir(target) / f"{paths.DOWNLOAD_PREFIX} {stamp}{suffix}.zip")
        shutil.move(part, kept[-1])

    original = paths.original_dir(target)
    if original.exists():
        remove_tree(original)
    original.mkdir(parents=True)
    extract_parts(kept, original)

    rows = anonymize.prepare(original, target)
    guide.write_guides(paths.data_dir())
    return rows
