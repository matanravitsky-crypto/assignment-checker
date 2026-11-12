"""Takes one part of the system out to a Claude skill, from the code as it is: nothing is copied or rewritten by hand.

    python tools/extract_skill.py copying                  builds ~/.claude/skills/<the skill's name>/
    python tools/extract_skill.py copying <folder>         builds it there
    python tools/extract_skill.py copying --list           only lists the files it would take
    python tools/extract_skill.py --stale <skill folder>   which files of a built skill no longer match the repo

The skill gets:
  SKILL.md               from <part>/skill/SKILL.md (the part owns its text; its `name:` is the skill's name), and
                         anything else in <part>/skill/
  scripts/run.py         runs `python -m <part>` from the skill's own copy, so the repo is not needed
  scripts/<the code>     the part and every module of the repo it needs (tools/modules.closure): the part itself and
                         the core it uses, never a part above it (tests/test_modularity.py keeps that true)
  scripts/MANIFEST.json  the commit it came from and every file's sha256, so a copy that fell behind is found
A part can go out this way only because it uses nothing but the core and the parts below it (docs/Modularity.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):  # run as a script: python tools/extract_skill.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import modules as M  # noqa: E402

MANIFEST = "MANIFEST.json"
RUN = '''"""Runs `python -m {part}` of Bodek Hacham from this skill's own copy of the code (built by tools/extract_skill.py).

    python run.py <arguments of python -m {part}>
"""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
runpy.run_module("{part}", run_name="__main__", alter_sys=True)
'''


def skill_source(part: str) -> Path:
    src = M.REPO / part / "skill"
    if not (src / "SKILL.md").is_file():
        raise SystemExit(f"{part}/skill/SKILL.md is missing: a part needs its own SKILL.md before it can go out as a skill")
    return src


def skill_name(part: str) -> str:
    for line in (skill_source(part) / "SKILL.md").read_text(encoding="utf-8").splitlines()[1:]:
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
        if line.strip() == "---":
            break
    raise SystemExit(f"{part}/skill/SKILL.md has no `name:` in its front matter")


def files_for(part: str) -> list[Path]:
    """The part's own modules and every module of the repo they need."""
    if part not in M.LAYERS:
        raise SystemExit(f"{part} is not a part (tools/modules.py, LAYERS)")
    start = [M.module_name(f) for f in M.part_files(part)]
    needed = M.closure(start)
    above = sorted(m for m in needed if M.LAYERS.index(M.part_of(m)) > M.LAYERS.index(part))
    if above:
        raise SystemExit(f"{part} needs parts above it ({', '.join(above)}): fix that first (tests/test_modularity.py)")
    return sorted({M.module_file(m) for m in needed} - {M.module_file(a) for a in M.ALIASES})


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=M.REPO, capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build(part: str, dest: Path | None = None) -> Path:
    """Builds the skill and returns its folder. A folder that is there already is replaced only if this tool built it."""
    src = skill_source(part)
    dest = Path(dest) if dest else Path.home() / ".claude" / "skills" / skill_name(part)
    if dest.exists() and any(dest.iterdir()):
        if not (dest / "scripts" / MANIFEST).is_file():
            raise SystemExit(f"{dest} exists and was not built by this tool: not touching it")
        # empty it but keep the folder: Claude Code watches its skills folders, and Windows refuses to remove one it holds
        for child in dest.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    scripts = dest / "scripts"
    scripts.mkdir(exist_ok=True)
    files = {}
    for f in files_for(part):
        rel = f.relative_to(M.REPO).as_posix()
        target = scripts / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        files[rel] = _sha(f)
    (scripts / "run.py").write_text(RUN.format(part=part), encoding="utf-8")
    manifest = {"part": part, "skill": skill_name(part), "commit": _commit(),
                "built_at": datetime.now().isoformat(timespec="seconds"), "files": files}
    (scripts / MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return dest


def stale(skill_dir: Path) -> list[str]:
    """The skill's files that differ from the repo now (or are gone from it): rebuild when this is not empty."""
    manifest = json.loads((Path(skill_dir) / "scripts" / MANIFEST).read_text(encoding="utf-8"))
    out = []
    for rel, sha in manifest["files"].items():
        here, there = M.REPO / rel, Path(skill_dir) / "scripts" / rel
        if not here.is_file() or not there.is_file() or _sha(here) != sha or _sha(there) != sha:
            out.append(rel)
    current = {f.relative_to(M.REPO).as_posix() for f in files_for(manifest["part"])}
    return sorted(set(out) | (current - set(manifest["files"])))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python tools/extract_skill.py", description="Take one part of the system out to a skill")
    p.add_argument("part", nargs="?", help="the part's folder, e.g. copying")
    p.add_argument("dest", nargs="?", type=Path, help="where to build it (default ~/.claude/skills/<name>)")
    p.add_argument("--list", action="store_true", help="only list the files it would take")
    p.add_argument("--stale", type=Path, metavar="SKILL_DIR", help="which files of a built skill fell behind the repo")
    args = p.parse_args(argv)
    if args.stale:
        behind = stale(args.stale)
        print("\n".join(behind) if behind else "up to date")
        return 1 if behind else 0
    if not args.part:
        p.error("which part?")
    if args.list:
        for f in files_for(args.part):
            print(f.relative_to(M.REPO).as_posix())
        return 0
    dest = build(args.part, args.dest)
    n = len(json.loads((dest / "scripts" / MANIFEST).read_text(encoding="utf-8"))["files"])
    print(f"{dest}  ({n} files of the repo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
