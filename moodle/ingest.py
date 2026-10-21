"""Turn a "Download all submissions" ZIP into numbered files ready for grading.

Moodle names the ZIP "<course>-<assignment name>-<assignment id>.zip" and asks
for 7-Zip to open it (Python's zipfile garbles some Hebrew names), so this uses
7-Zip.
"""

import os
import shutil
import stat
import subprocess
from datetime import datetime
from pathlib import Path

from moodle import anonymize, paths

SEVEN_ZIP_PATHS = [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]


def find_download(assignment_id: str, downloads: Path | None = None) -> Path:
    """Return the newest finished ZIP for this assignment in Downloads."""
    downloads = downloads or Path.home() / "Downloads"
    zips = [p for p in downloads.glob("*.zip") if p.stem.endswith(f"-{assignment_id}")]
    if not zips:
        raise FileNotFoundError(f"No ZIP ending in -{assignment_id}.zip in {downloads}")
    return max(zips, key=lambda p: p.stat().st_mtime)


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


def ingest(assignment_id: str, zip_path: Path | None = None) -> list[dict]:
    zip_path = zip_path or find_download(assignment_id)

    # Keep every download: a later one (after the due date) must not erase the first
    paths.raw_dir().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    kept = paths.raw_dir() / f"{assignment_id}-{stamp}.zip"
    shutil.move(zip_path, kept)

    target = paths.assignment_dir(assignment_id)
    original = target / "original"
    if original.exists():
        remove_tree(original)
    original.mkdir(parents=True)
    subprocess.run([seven_zip(), "x", str(kept), f"-o{original}", "-y", "-bso0", "-bsp0"], check=True)

    return anonymize.prepare(target)
