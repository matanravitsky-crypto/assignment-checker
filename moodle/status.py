"""Where an assignment stands, and whether its folder is safe to sync.

OneDrive refuses some names students' phones produce (invisible RTL marks,
emoji, broken characters), so anything in the shared folder should use plain
ASCII and Hebrew letters only.
"""

import csv
import re
from pathlib import Path

# Plain ASCII and Hebrew letters, minus what Windows and OneDrive forbid
SAFE_NAME = re.compile(r'^[\x20-\x7Eא-ת]+$')
FORBIDDEN = set('"*:<>?/\\|')


def unsafe_names(folder: Path) -> list[str]:
    """Paths under folder whose names OneDrive may refuse to sync."""
    bad = []
    for path in folder.rglob("*"):
        name = path.name
        if (not SAFE_NAME.match(name) or FORBIDDEN & set(name)
                or name != name.strip() or name.endswith(".")):
            bad.append(str(path.relative_to(folder)))
    return sorted(bad)


def count_files(folder: Path) -> int:
    return sum(1 for p in folder.iterdir() if p.is_file()) if folder.is_dir() else 0


def count_rows(path: Path) -> int | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))


def status(assignment_dir: Path) -> dict:
    return {
        "anon_files": count_files(assignment_dir / "anon"),
        "mapping_rows": count_rows(assignment_dir / "mapping.csv"),
        "results_rows": count_rows(assignment_dir / "results.csv"),
        "marked_files": count_files(assignment_dir / "marked"),
        "upload_files": count_files(assignment_dir / "upload"),
        "unsafe_names": unsafe_names(assignment_dir) if assignment_dir.exists() else [],
    }
