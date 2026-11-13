"""Takes one part of the system out to a Claude skill, from the code as it is: nothing is copied or rewritten by hand.

    python tools/extract_skill.py copying                  builds ~/.claude/skills/<the skill's name>/
    python tools/extract_skill.py copying <folder>         builds it there
    python tools/extract_skill.py copying --list           only lists the files it would take
    python tools/extract_skill.py --stale <skill folder>   which files of a built skill no longer match the repo
    python tools/extract_skill.py grading --install        builds ~/.claude/skills/<name>/ only if it is missing or fell
                                                           behind; a skill there that this tool did not build (an older
                                                           copy from a ZIP) is first copied to ~/.claude/skill-backups/.
                                                           The dashboard runs this at every start (dashboard/skills.py)
    python tools/extract_skill.py --remove <skill folder>  removes a skill this tool built (never one it did not build)

The skill gets:
  SKILL.md               from <part>/skill/SKILL.md (the part owns its text; its `name:` is the skill's name), and
                         anything else in <part>/skill/
  scripts/run.py         runs `python -m <part>` from the skill's own copy, so the repo is not needed
  scripts/<the code>     the part and every module of the repo it needs (tools/modules.closure): the part itself and
                         the core it uses, never a part above it (tests/test_modularity.py keeps that true)
  scripts/MANIFEST.json  the commit it came from and every file's sha256, so a copy that fell behind is found, and
                         "team": true when the dashboard installed it as one of the team's skills, so the dashboard
                         also removes it once it is no longer on its list (retire)
A part can go out this way only because it uses nothing but the core and the parts below it (docs/Modularity.md).
Every part with a <part>/skill/SKILL.md is built and run alone by tests/integration/test_every_skill.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):  # run as a script: python tools/extract_skill.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import modules as M  # noqa: E402

MANIFEST = "MANIFEST.json"
# what is left of a removed skill when Windows keeps its folder (Claude Code holds it): no SKILL.md, so it is no skill;
# the next retire removes the folder, and an install over it takes the folder back
REMOVED = "REMOVED by Bodek Hacham.txt"
RUN ='''"""Runs `python -m {part}` of Bodek Hacham from this skill's own copy of the code (built by tools/extract_skill.py).

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


# Files that are not modules but that a part reads, at the same path relative to the repo (so the code finds them in
# the skill as in the repo). 2026-11-13: exercise-grader graded without "כללים לכל מחוון" (grade.UNIVERSAL_RULES)
DATA = {"grading": [".claude/skills/rubric-builder/assets/universal-rules.json"]}


def data_for(part: str) -> list[Path]:
    return [M.REPO / rel for rel in DATA.get(part, []) if (M.REPO / rel).is_file()]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=M.REPO, capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _empty(folder: Path) -> None:
    """Removes everything in the folder but keeps the folder: Claude Code watches its skills folders, and Windows refuses
    to remove one it holds. Read-only files and folders too (OneDrive marks folders read-only, and an older build copied
    that attribute)."""
    def writable(path: str | Path) -> None:
        folder_ = os.path.isdir(path) and not os.path.islink(path)
        os.chmod(path, stat.S_IRWXU if folder_ else stat.S_IREAD | stat.S_IWRITE)

    for child in list(folder.iterdir()):
        writable(child)
        if child.is_dir() and not child.is_symlink():
            for root, dirs, names in os.walk(child):  # top down: a folder is writable before it is walked into
                for name in dirs + names:
                    writable(os.path.join(root, name))
            shutil.rmtree(child)
        else:
            child.unlink()


def build(part: str, dest: Path | None = None, team: bool = False) -> Path:
    """Builds the skill and returns its folder. A folder that is there already is replaced only if this tool built it.
    `team`: the dashboard installs it as one of the team's skills (dashboard/skills.py), and may remove it later."""
    src = skill_source(part)
    dest = Path(dest) if dest else Path.home() / ".claude" / "skills" / skill_name(part)
    if dest.exists() and any(dest.iterdir()):
        if not (dest / "scripts" / MANIFEST).is_file():
            raise SystemExit(f"{dest} exists and was not built by this tool: not touching it")
        _empty(dest)
    for rel, data in _skill_files(part).items():  # files only: copytree's copystat made OneDrive's read-only folders
        target = dest / rel                         # read-only here, and the next rebuild could not remove them
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    scripts = dest / "scripts"
    scripts.mkdir(exist_ok=True)
    files = {}
    for f in files_for(part) + data_for(part):
        rel = f.relative_to(M.REPO).as_posix()
        target = scripts / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        files[rel] = _sha(f)
    (scripts / "run.py").write_text(RUN.format(part=part), encoding="utf-8")
    manifest = {"part": part, "skill": skill_name(part), "commit": _commit(),
                "built_at": datetime.now().isoformat(timespec="seconds"), "team": team, "files": files}
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
    current = {f.relative_to(M.REPO).as_posix() for f in files_for(manifest["part"]) + data_for(manifest["part"])}
    return sorted(set(out) | (current - set(manifest["files"])))


def _skill_files(part: str) -> dict[str, bytes]:
    """The files the skill takes from <part>/skill/ (SKILL.md and the rest), by their path in the skill."""
    src = skill_source(part)
    return {f.relative_to(src).as_posix(): f.read_bytes() for f in sorted(src.rglob("*"))
            if f.is_file() and "__pycache__" not in f.parts}


def up_to_date(part: str, dest: Path) -> bool:
    """True when `dest` was built by this tool from this part and nothing in it differs from the repo now: the code
    (stale), SKILL.md and the other files of <part>/skill/, and run.py."""
    dest = Path(dest)
    try:
        manifest = json.loads((dest / "scripts" / MANIFEST).read_text(encoding="utf-8"))
        if manifest.get("part") != part or stale(dest):
            return False
        if (dest / "scripts" / "run.py").read_text(encoding="utf-8") != RUN.format(part=part):
            return False
        return all((dest / rel).is_file() and (dest / rel).read_bytes() == data
                   for rel, data in _skill_files(part).items())
    except (OSError, ValueError, KeyError):
        return False


def _manifest(skill_dir: Path) -> dict | None:
    """The MANIFEST.json of a skill this tool built, or None (no skill there, or one it did not build)."""
    try:
        m = json.loads((Path(skill_dir) / "scripts" / MANIFEST).read_text(encoding="utf-8"))
        return m if isinstance(m, dict) else None
    except (OSError, ValueError):
        return None


def _removed_earlier(folder: Path) -> bool:
    """A skill folder that remove() emptied and Windows kept: nothing in it but the REMOVED note."""
    try:
        return folder.is_dir() and [c.name for c in folder.iterdir()] == [REMOVED]
    except OSError:
        return False


def _remove_folder(folder: Path) -> None:
    folder.rmdir()


def _skills_dir(skills: Path | None) -> Path:
    return Path(skills) if skills else Path.home() / ".claude" / "skills"


def install(part: str, skills: Path | None = None, backups: Path | None = None, team: bool = False) -> dict:
    """Keeps the part's skill current in a skills folder (default ~/.claude/skills), the way a teammate's computer gets
    it: nothing is done when it is up to date; a copy this tool built is built again; a copy it did not build (the
    hand-made exercise-grader that went round as a ZIP) is first copied whole to `backups` (default
    ~/.claude/skill-backups, outside the skills folder, so it is not a second skill with the same name), and only then
    replaced. `team` (the dashboard, dashboard/skills.py) marks it as one of the team's skills, which retire() removes
    once it is off the list; a mark that is there stays.
    Returns {"skill", "path", "action": "up_to_date" | "installed" | "updated" | "replaced", "backup"}."""
    name = skill_name(part)
    skills = _skills_dir(skills)
    dest = skills / name
    out = {"skill": name, "path": str(dest), "action": "up_to_date", "backup": None}
    if _removed_earlier(dest):  # the folder of a skill removed earlier: it is ours again
        (dest / REMOVED).unlink()
    there = dest.is_dir() and any(dest.iterdir())
    old = _manifest(dest) if there else None
    team = team or bool(old and old.get("team"))
    if there and old is not None and bool(old.get("team")) == team and up_to_date(part, dest):
        return out
    if there and not (dest / "scripts" / MANIFEST).is_file():
        backups = Path(backups) if backups else skills.parent / "skill-backups"
        backup = backups / f"{name}-{datetime.now():%Y%m%d-%H%M%S}"
        n = 2
        while backup.exists():
            backup = backups / f"{name}-{datetime.now():%Y%m%d-%H%M%S}-{n}"
            n += 1
        shutil.copytree(dest, backup)
        _empty(dest)  # in place: build() replaces only what it built itself
        out.update(action="replaced", backup=str(backup))
    else:
        out["action"] = "updated" if there else "installed"
    skills.mkdir(parents=True, exist_ok=True)
    build(part, dest, team=team)
    return out


def remove(skill_dir: Path) -> None:
    """Removes a skill this tool built; one it did not build is never touched. On Windows Claude Code may hold the
    folder, so it is emptied and then removed; when Windows keeps it, a note (REMOVED) is all that stays, which is no
    skill, and the next retire() removes the folder."""
    skill_dir = Path(skill_dir)
    if _manifest(skill_dir) is None:
        raise SystemExit(f"{skill_dir} was not built by this tool: not touching it")
    _empty(skill_dir)
    try:
        _remove_folder(skill_dir)
    except OSError:
        (skill_dir / REMOVED).write_text("This skill was removed by Bodek Hacham (tools/extract_skill.py). The folder "
                                         "goes at the dashboard's next start.\n", encoding="utf-8")


def retire(keep: list[str], skills: Path | None = None) -> list[dict]:
    """Removes from a skills folder (default ~/.claude/skills) every team skill (installed with team=True, by the
    dashboard) whose name is not in `keep`: a part taken off dashboard/skills.TEAM_SKILLS, or a skill whose name changed.
    A skill built by hand (`extract_skill.py <part>`, `--install`) or made by hand is never touched. Also removes the
    folders that an earlier remove() could only empty. Returns [{"skill", "path", "action": "removed"}]."""
    skills = _skills_dir(skills)
    out = []
    if not skills.is_dir():
        return out
    for folder in sorted(skills.iterdir()):
        if not folder.is_dir() or folder.is_symlink():
            continue
        if _removed_earlier(folder):
            try:
                (folder / REMOVED).unlink()
                _remove_folder(folder)
            except OSError:
                (folder / REMOVED).touch()  # Windows still holds it: the note stays for the next start
            continue
        m = _manifest(folder)
        if m is None or not m.get("team") or folder.name in keep:
            continue
        remove(folder)
        out.append({"skill": folder.name, "path": str(folder), "action": "removed", "backup": None})
    return out


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python tools/extract_skill.py", description="Take one part of the system out to a skill")
    p.add_argument("part", nargs="?", help="the part's folder, e.g. copying")
    p.add_argument("dest", nargs="?", type=Path, help="where to build it (default ~/.claude/skills/<name>)")
    p.add_argument("--list", action="store_true", help="only list the files it would take")
    p.add_argument("--stale", type=Path, metavar="SKILL_DIR", help="which files of a built skill fell behind the repo")
    p.add_argument("--install", action="store_true",
                   help="build it in ~/.claude/skills only if missing or behind; back up a hand-made one first")
    p.add_argument("--remove", type=Path, metavar="SKILL_DIR", help="remove a skill this tool built")
    args = p.parse_args(argv)
    if args.remove:
        remove(args.remove)
        print(f"removed {args.remove}")
        return 0
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
    if args.install:
        done = install(args.part)
        print(f"{done['skill']}: {done['action']}  {done['path']}"
              + (f"  (the earlier one: {done['backup']})" if done["backup"] else ""))
        return 0
    dest = build(args.part, args.dest)
    n = len(json.loads((dest / "scripts" / MANIFEST).read_text(encoding="utf-8"))["files"])
    print(f"{dest}  ({n} files of the repo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
