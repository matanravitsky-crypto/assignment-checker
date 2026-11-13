"""Shared by the meta-evaluator scripts: where an assignment and a round live, and reading the grading output.
Numbers only: nothing here reads the key table, the originals or a name."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

HOME_WORK = Path.home() / ".meta-eval"


def assignment_dir(ident: str) -> Path:
    """A Moodle id (found through moodle.paths) or a folder path."""
    p = Path(ident)
    if p.is_dir():
        return p
    from moodle import paths
    return paths.assignment_dir(ident)


def assignment_id(a: Path) -> str:
    try:
        return str(json.loads((a / "Assignment details.json").read_text(encoding="utf-8-sig")).get("id") or a.name)
    except (OSError, ValueError):
        return a.name


def round_dir(a: Path, name: str, root: Path | None = None) -> Path:
    """The round's work folder: ~/.meta-eval/<id>/<round>. Never inside the repo or OneDrive (student pages)."""
    base = (root or HOME_WORK) / assignment_id(a) / name
    resolved = str(base.resolve()).lower()
    if str(REPO.resolve()).lower() in resolved or "onedrive" in resolved:
        raise SystemExit(f"תיקיית העבודה לא יכולה להיות בריפו או ב-OneDrive: {base}")
    base.mkdir(parents=True, exist_ok=True)
    return base


def labels(a: Path) -> tuple[list[str], list[float]]:
    """The graded sections in order and their points, as grading sees them."""
    from grading import grade
    ctx = grade.load_context(a, send_solution=False)
    return [q.label for q in ctx.questions], [q.points for q in ctx.questions]


def grades(a: Path) -> dict[str, dict]:
    """number -> merged grade row (approved first, then the latest graded_at), the way every reader merges them."""
    from moodle import grades as g
    return g.read(a)


def notes(a: Path, number: str) -> dict:
    f = a / "Grading notes" / f"{number}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}


def graded_numbers(a: Path) -> list[str]:
    return sorted(p.stem for p in (a / "Grading notes").glob("*.json") if "points" in notes(a, p.stem))


GRADER_WORDS = ["קריאה הנמוכה", "לא הורד", "unsure", "placeholder", "פליטת קולמוס", "לפי המחוון"]


def dump(obj, path: Path) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def say(*parts) -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        print(*parts)
    except UnicodeEncodeError:
        print(*(str(p).encode("ascii", "replace").decode() for p in parts))
