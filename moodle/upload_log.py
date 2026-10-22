"""The record of what was uploaded to Moodle, by number: no names, only numbers and hashes.

In "3 - Ready to upload to Moodle/":
    Upload batch.json   the batch being uploaded: its folder, its ZIPs with the hash of each ZIP, and for
                        each ZIP the files in it with the hash of each marked file as it was put into the ZIP
    Upload batch <id>/  the ZIPs of that batch (Graded - part 01.zip ...), apart from the ZIPs that the manual
                        "Prepare return" (upload.prepare_upload) writes straight into the upload folder
    Upload log.csv      one row per file per upload: number, file, sha256, zip, uploaded_at, by

A number counts as returned when every one of its marked files still has the hash it had in its
latest upload. If the grader changes a file after that, the number is no longer returned.

OneDrive may make a conflict copy of the log (`Upload log-DESKTOP.csv`) or of the batch list
(`Upload batch-DESKTOP.json`) when two people write it at once; `log_conflicts` and `batch_conflicts` find
them so someone merges them by hand, as with the key table. Nothing here deletes them.
Nothing here talks to Moodle.
"""

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from moodle import paths, upload

LOG_FILE = "Upload log.csv"
BATCH_FILE = "Upload batch.json"
LOG_FIELDS = ["number", "file", "sha256", "zip", "uploaded_at", "by"]
BATCH_DIR_PREFIX = "Upload batch "
# Only folders with exactly this name are ours: the batch id is "<date>-<time>-<8 hex>" (see send.prepare_batch)
BATCH_DIR_NAME = re.compile(re.escape(BATCH_DIR_PREFIX) + r"\d{8}-\d{6}-[0-9a-f]{8}")
ZIP_CHANGED = "קובץ ה-ZIP {name} השתנה או חסר מאז ההכנה. צריך להכין שוב."

HASH_CHUNK = 1 << 20  # marked PDFs are 1-2 MB, scans up to tens of MB: don't read a file whole


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


# ---------- הרשימה של האצווה ----------
def write_batch(assignment_dir: Path, batch: dict) -> None:
    """batch: {"id", "assignment_id", "created_at", "folder",
               "zips": [{"name", "sha256", "files": [{"number", "file", "sha256"}]}]}."""
    folder = assignment_dir / paths.UPLOAD
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / BATCH_FILE, "w", encoding="utf-8-sig") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)


def read_batch(assignment_dir: Path) -> dict | None:
    path = assignment_dir / paths.UPLOAD / BATCH_FILE
    if not path.exists():
        return None
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def batch_dir_name(batch_id: str) -> str:
    return f"{BATCH_DIR_PREFIX}{batch_id}"


def batch_folder(assignment_dir: Path, batch: dict) -> Path | None:
    """The folder of the batch's ZIPs, or None for a batch list without a valid one (an older list, or a bad name)."""
    name = batch.get("folder")
    if not isinstance(name, str) or not BATCH_DIR_NAME.fullmatch(name):
        return None
    return assignment_dir / paths.UPLOAD / name


def zip_hash(path: Path) -> str | None:
    """The hash of a ZIP, or None when it is not there."""
    try:
        return file_hash(path)
    except OSError:
        return None


def batch_zip(assignment_dir: Path, zip_name: str) -> Path:
    """The ZIP `zip_name` of the current batch, in the batch's folder, still exactly as it was prepared.

    Raises ValueError (Hebrew) when the batch doesn't list it, or the file is missing or changed.
    """
    batch = read_batch(assignment_dir) or {}
    name = Path(zip_name).name  # "Upload batch <id>/Graded - part 01.zip" works too
    entry = next((z for z in batch.get("zips", []) if z["name"] == name), None)
    if entry is None:
        raise ValueError(f"ה-ZIP {name} לא ברשימת האצווה")
    folder = batch_folder(assignment_dir, batch)
    if folder is None or not entry.get("sha256") or zip_hash(folder / name) != entry["sha256"]:
        raise ValueError(ZIP_CHANGED.format(name=name))
    return folder / name


def remove_old_batch_folders(assignment_dir: Path, keep: str) -> None:
    """Delete the ZIP folders of earlier batches: only folders named like ours, and in them only the ZIPs we wrote.

    Anything else in such a folder (an OneDrive conflict copy, a file someone put there) stays, and so does the folder.
    """
    folder = assignment_dir / paths.UPLOAD
    for old in folder.iterdir() if folder.is_dir() else []:
        if not old.is_dir() or old.name == keep or not BATCH_DIR_NAME.fullmatch(old.name):
            continue
        for item in old.iterdir():
            if upload.is_zip_we_wrote(item):
                item.unlink()
        try:
            old.rmdir()
        except OSError:  # not empty: what is left was not ours to delete
            pass


# ---------- היומן ----------
def read_log(assignment_dir: Path) -> list[dict]:
    path = assignment_dir / paths.UPLOAD / LOG_FILE
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def last_hashes(assignment_dir: Path) -> dict[str, str]:
    """File name ("0001-2.pdf") -> its hash in the latest upload of that file (the log is in upload order)."""
    return {row["file"]: row["sha256"] for row in read_log(assignment_dir)}


def returned_numbers(assignment_dir: Path, marked: dict[str, list[Path]]) -> set[str]:
    """Numbers whose marked files all match their latest upload. `marked` is paths.files_by_number of the marked folder."""
    uploaded = last_hashes(assignment_dir)
    return {number for number, files in marked.items()
            if files and all(p.name in uploaded and file_hash(p) == uploaded[p.name] for p in files)}


def log_conflicts(assignment_dir: Path) -> list[str]:
    """Conflict copies of the log that OneDrive makes (e.g. "Upload log-DESKTOP.csv")."""
    folder = assignment_dir / paths.UPLOAD
    return sorted(p.name for p in folder.glob(f"{Path(LOG_FILE).stem}*.csv") if p.name != LOG_FILE)


def batch_conflicts(assignment_dir: Path) -> list[str]:
    """Conflict copies of the batch list that OneDrive makes (e.g. "Upload batch-DESKTOP.json"). Never deleted here."""
    folder = assignment_dir / paths.UPLOAD
    stem, suffix = Path(BATCH_FILE).stem, Path(BATCH_FILE).suffix
    return sorted(p.name for p in folder.glob(f"{stem}*{suffix}") if p.name != BATCH_FILE and p.is_file())


def record_zip(assignment_dir: Path, zip_name: str, by: str, now: datetime | None = None) -> int:
    """Add a log row for every file of `zip_name`, as the batch lists it. Returns how many rows were written."""
    batch = read_batch(assignment_dir)
    zips = {z["name"]: z for z in (batch or {}).get("zips", [])}
    if zip_name not in zips:
        raise ValueError(f"ה-ZIP {zip_name} לא ברשימת האצווה")
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    rows = [{"number": f["number"], "file": f["file"], "sha256": f["sha256"],
             "zip": zip_name, "uploaded_at": stamp, "by": by} for f in zips[zip_name]["files"]]
    path = assignment_dir / paths.UPLOAD / LOG_FILE
    is_new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)
