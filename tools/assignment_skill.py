"""A grading skill per rubric: the grading skeleton with one assignment's rubric dressed on it.

    skeleton (grading/skill/SKILL.md + the grading engine, the same in every grading skill)
  + rubric of assignment X (frozen when the TA approved it)
  = grade-<course>-<N>: a self-contained skill that grades only X

The skeleton is what tools/extract_skill.py builds for exercise-grader: the steps of SKILL.md and the system's own
grading code (grading/ and the core it needs). Its SKILL.md marks the places that belong to the rubric with
<!-- rubric-slot: <name> --> ... <!-- /rubric-slot -->; exercise-grader keeps what is there (the user brings a rubric in
any format), a skill for rubric X gets SLOTS below (the rubric is built in). Everything else is the skeleton, word for
word, so a lesson learned in grading reaches every rubric's skill.

Two halves, kept apart on purpose:
  the rubric package   <course>/Grading skills/<name>/ in the shared folder: assignment/ (a frozen copy of exactly what
                       grading reads from the assignment folder: Assignment details.json, the פדגוגי files grading sends,
                       the official key, Official solution.pdf) and MANIFEST.json (name, version, who, when, triggers,
                       sha256 per file). Written only by `build`, after the TA's "מאושר" (the rubric-to-grader-factory skill)
  the skill            ~/.claude/skills/<name>/ on each computer: assembled there from that computer's skeleton and the
                       package (`install`, also by the dashboard at every start). A newer skeleton (a fix in marking, a
                       new rule of the grader) reaches every rubric's skill by itself; the rubric changes only by `build`

    python tools/assignment_skill.py build <moodle id> [--draft] [--name grade-linear-1] [--by <who>] [--triggers "..."]
    python tools/assignment_skill.py check <moodle id>     the rubric changed since the package was built?
    python tools/assignment_skill.py list                  every package, its version, up to date or behind
    python tools/assignment_skill.py install               assemble every package into ~/.claude/skills (new or changed)

Never in a package or a skill: a submission, a grade, a name or the key table.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):  # run as a script: python tools/assignment_skill.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grading import grade, one_submission  # noqa: E402
from moodle import paths  # noqa: E402
from tools import extract_skill  # noqa: E402

KIND = "assignment-grading-skill"   # the MANIFEST mark: install and replace only what carries it
MANIFEST = "MANIFEST.json"
SNAPSHOT = "assignment"             # the rubric, inside the package and inside the skill
SKELETON = "grading"                # the part whose skill is the skeleton (exercise-grader)
COURSE_SHORT = {"Linear Algebra": "linear", "Discrete Mathematics": "discrete"}
COURSE_HE = {"Linear Algebra": "אלגברה לינארית", "Discrete Mathematics": "מתמטיקה בדידה"}
_SLOT = re.compile(r"<!-- rubric-slot: ([a-z-]+) -->\n(.*?)\n<!-- /rubric-slot -->\n?", re.S)

# What a rubric's skill says in each slot of the skeleton (grading/skill/SKILL.md). {id} is the Moodle id
SLOTS = {
    "install": "",
    "ask": ("2. **The rubric is built into this skill:** `<skill>\\" + SNAPSHOT + "`, the assignment's approved rubric, "
            "frozen when it was approved (with the official key and the solutions, if the assignment has them). Never "
            "ask for a rubric. If the user attaches another one, say that this assignment has an approved rubric in "
            "the skill and ask which to grade by; grade by another only on their word, then as exercise-grader does.\n"
            "3. **The work is of this assignment.** If its pages plainly answer other questions, say so before grading."),
    "rubric": ("The rubric is the folder `<skill>\\" + SNAPSHOT + "` (use its absolute path): an assignment folder with "
               "`Assignment details.json` and `פדגוגי\\`, read exactly as the system reads the real one. Wherever a "
               "command below takes the rubric (`rubric`, `mark`), pass that folder. Never write a `rubric.json` by hand."),
    "current": ("## Keeping it current\n\n"
                "This skill = the grading skeleton of this computer + the rubric package "
                "`<course>\\" + paths.GRADING_SKILLS + "\\<name>` in the shared folder. The system assembles it again at "
                "every start when either changed (`dashboard/skills.py`). A rubric that changed after approval is built "
                "again by the rubric team (`rubric-to-grader-factory`); in the repo, `python tools/assignment_skill.py check "
                "{id}` says whether it fell behind."),
}


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _slot(folder: Path) -> str | None:
    m = re.match(r"Assignment (\d+)\b", folder.name)
    return m.group(1) if m else None


def default_name(folder: Path) -> str:
    """grade-linear-1, grade-discrete-0: the course and the slot (הגשה N)."""
    course = folder.parent.name
    short = COURSE_SHORT.get(course) or re.sub(r"[^a-z0-9]+", "-", course.lower()).strip("-") or "course"
    slot = _slot(folder)
    if slot is None:
        raise SystemExit(f"{folder.name}: not an \"Assignment N\" folder; give the skill a name with --name")
    return f"grade-{short}-{slot}"


def sources(folder: Path) -> dict[str, Path]:
    """What the system's grading reads from the assignment folder, by its path inside the snapshot."""
    folder = Path(folder)
    out: dict[str, Path] = {}
    if (folder / paths.INFO).is_file():
        out[paths.INFO] = folder / paths.INFO
    for f in grade.pedagogy_files(folder):
        out[f"{f.parent.name}/{f.name}"] = f
    key = folder / paths.OFFICIAL_KEY
    if key.is_dir():
        for f in sorted(key.iterdir()):
            if f.is_file():
                out[f"{paths.OFFICIAL_KEY}/{f.name}"] = f
    for name in (paths.OFFICIAL_KEY_TEXT, grade.SOLUTION):
        if (folder / name).is_file():
            out[name] = folder / name
    return out


def packages_dir_of(folder: Path) -> Path:
    return Path(folder).parent / paths.GRADING_SKILLS


def _approved(folder: Path) -> bool | None:
    """Does the rubric's changelog say מאושר? None when there is no changelog (a rubric not built by rubric-builder)."""
    for name in paths.PEDAGOGY:
        log = Path(folder) / name / paths.RUBRIC_NOTES / paths.RUBRIC_LOG
        if log.is_file():
            return "מאושר" in log.read_text(encoding="utf-8-sig", errors="replace")
    return None


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def _manifest(folder: Path) -> dict | None:
    try:
        m = json.loads((Path(folder) / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m if isinstance(m, dict) and m.get("kind") == KIND else None


def _rmtree(folder: Path) -> None:
    """Removes a folder whose files may be read-only (OneDrive marks folders read-only)."""
    def writable(func, path, _exc):
        os.chmod(path, stat.S_IRWXU)
        func(path)
    shutil.rmtree(folder, onexc=writable) if sys.version_info >= (3, 12) else shutil.rmtree(folder, onerror=writable)


# ---------- the rubric package (shared folder) ----------
DRAFTS = Path.home() / ".grading-skill-drafts"  # a draft's package: this computer only, never the shared folder


def build(assignment_id: str, name: str | None = None, by: str | None = None, triggers: list[str] | None = None,
          install_to: Path | None = None, draft: bool = False, drafts: Path | None = None,
          source: Path | None = None) -> dict:
    """Freezes the assignment's rubric into <course>/Grading skills/<name>/ and assembles the skill on this computer
    (`install_to`, default ~/.claude/skills). Refuses a rubric without points for every question, and a copy that would
    not grade exactly like the assignment folder. `draft`: the package goes to ~/.grading-skill-drafts/ (this computer
    only), for the calibration round before the team gets it; the same build without it publishes."""
    home = paths.assignment_dir(assignment_id)  # the assignment the skill is for (its course, its slot, its works)
    # `source`: a rubric package someone brought (the pedagogical team's assignment folder: Assignment details.json and
    # פדגוגי/), dressed instead of the shared folder's own; a draft only, never published from here
    folder = Path(source) if source else home
    if source and not draft:
        raise SystemExit("a rubric brought from outside is built as a --draft; publish only from the assignment folder")
    name = name or default_name(home)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", name):
        raise SystemExit(f"{name}: a skill name is lowercase letters, digits and '-'")
    try:
        rubric = one_submission.rubric(folder)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001  (grade.load_context refuses an assignment without a rubric)
        raise SystemExit(f"the rubric of {folder.name} can't be read: {e}") from e
    missing = [q["label"] for q in rubric["questions"] if not q["points"]]
    if not rubric["questions"] or missing:
        raise SystemExit("no points for: " + (", ".join(missing) or "any question") + " (fix the rubric first)")
    info = paths.read_info(folder)
    files = sources(folder)
    dest = (Path(drafts) if drafts else DRAFTS) / name if draft else packages_dir_of(folder) / name
    old = _manifest(dest)
    if dest.exists() and any(dest.iterdir()) and old is None:
        raise SystemExit(f"{dest} exists and was not built by this tool: not touching it")
    slot = _slot(home)
    title = _clean(info.get("hebrew_title") or info.get("title") or home.name)
    course_he = COURSE_HE.get(home.parent.name, home.parent.name)
    phrases = ([f"תבדוק עבודה של הגשה {slot} ב{course_he}", f"תבדוק לפי המחוון של הגשה {slot}"] if slot is not None
               else []) + [f"בדיקה של {title}"]
    phrases += [t for t in (triggers or []) if t and t not in phrases]
    manifest = {"kind": KIND, "skill": name, "assignment_id": str(paths.read_info(home).get("id")),
                "assignment": f"{home.parent.name}/{home.name}", "title": title, "course": course_he,
                "source": str(Path(source).resolve()) if source else None,
                "triggers": phrases, "version": (old or {}).get("version", 0) + 1,
                "built_at": datetime.now().isoformat(timespec="seconds"),
                "built_by": by or os.environ.get("GRADER_NAME") or os.environ.get("USERNAME") or os.environ.get("USER") or "?",
                "approved": _approved(folder), "files": {rel: _sha(f) for rel, f in files.items()}}
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        _rmtree(tmp)
    for rel, f in files.items():
        target = tmp / SNAPSHOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())
    # grading takes the title and the course from the folder names when the details have none (grade.load_context);
    # inside the skill the folder is "assignment", so the copy carries them
    snap_info = tmp / SNAPSHOT / paths.INFO
    d = json.loads(snap_info.read_text(encoding="utf-8-sig"))
    d["title"] = d.get("title") or folder.name
    d["course_title"] = d.get("course_title") or folder.parent.name
    d.setdefault("id", manifest["assignment_id"])
    snap_info.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (tmp / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    same = one_submission.rubric(tmp / SNAPSHOT)
    if same["context"] != rubric["context"] or same["questions"] != rubric["questions"]:
        _rmtree(tmp)
        raise SystemExit("the copy does not grade like the assignment folder (context differs): nothing written")
    if dest.exists():
        _rmtree(dest)
    tmp.rename(dest)
    return {"skill": name, "package": str(dest), "version": manifest["version"], "files": len(files),
            "questions": rubric["questions"], "total_points": rubric["total_points"],
            "approved": manifest["approved"], "draft": draft, "installed": install_one(dest, install_to)}


def stale(package: Path) -> list[str]:
    """What changed in the assignment folder since the package was built: files whose bytes differ, are gone, or are
    new (a new file in פדגוגי, a key uploaded since). Empty = the package grades like the system does today."""
    m = _manifest(package)
    if m is None:
        raise SystemExit(f"{package} is not a rubric package")
    folder = Path(m["source"]) if m.get("source") else paths.assignment_dir(m["assignment_id"])
    now = {rel: _sha(f) for rel, f in sources(folder).items()}
    return sorted(rel for rel in set(now) | set(m["files"]) if now.get(rel) != m["files"].get(rel))


def all_packages(data: Path | None = None) -> list[Path]:
    root = Path(data) if data else paths.data_dir()
    return sorted(p.parent for p in root.glob(f"*/{paths.GRADING_SKILLS}/*/{MANIFEST}") if _manifest(p.parent))


# ---------- the skill (this computer) = skeleton + package ----------
def skeleton_md() -> str:
    return (extract_skill.skill_source(SKELETON) / "SKILL.md").read_text(encoding="utf-8")


def slots(text: str) -> list[str]:
    return [m.group(1) for m in _SLOT.finditer(text)]


def skill_md(package: Path) -> str:
    """The skill's SKILL.md: a header from the rubric, then the skeleton's own text with its rubric slots filled."""
    m = _manifest(package)
    body = skeleton_md()
    names = slots(body)
    if sorted(names) != sorted(SLOTS):
        raise SystemExit(f"the skeleton's rubric slots are {names}, this tool fills {sorted(SLOTS)}: update SLOTS")
    body = body.split("\n---\n", 1)[1] if body.startswith("---\n") else body  # the skeleton's own front matter goes
    body = _SLOT.sub(lambda s: (SLOTS[s.group(1)].format(id=m["assignment_id"]) + "\n") if SLOTS[s.group(1)] else "", body)
    body = re.sub(r"^# .*$", f"# בדיקת {m['title']} ({m['course']}): השלד של הבדיקה עם המחוון של המטלה", body, count=1,
                  flags=re.M)
    rubric = one_submission.rubric(Path(package) / SNAPSHOT)
    rows = "\n".join(f"| {q['label']} | {q['points']:g} |" for q in rubric["questions"])
    quoted = ", ".join(f'"{p}"' for p in m["triggers"])
    approved = {True: "approved (מאושר)", False: "NOT marked מאושר in the rubric's changelog", None: "no changelog"}[m["approved"]]
    description = (f"Grade a student's work of {m['course']}, {m['title']} (Moodle id {m['assignment_id']}), by this "
                   f"assignment's own rubric, built in, and return the marked PDF exactly like the system does. Use when "
                   f"someone sends a work of this assignment and says {quoted}, or names this assignment. Not for other "
                   f"assignments: each has its own grade-<course>-<N> skill; exercise-grader grades with a rubric the "
                   f"user brings.")
    head = (f"---\nname: {m['skill']}\ndescription: {json.dumps(description, ensure_ascii=False)}\nmodel: {grade.DEFAULT_MODEL}\neffort: {grade.EFFORT}\n---\n\n"
            f"> **The rubric of this skill:** {m['assignment']}, version {m['version']}, frozen {m['built_at'][:16].replace('T', ' ')} "
            f"by {m['built_by']} ({approved}). Total {rubric['total_points']:g} points, grade out of {rubric['max_grade']:g}.\n>\n"
            f"> | שאלה | נקודות |\n> |---|---|\n" + "\n".join("> " + r for r in rows.splitlines()) + "\n\n")
    return head + body.lstrip("\n")


def _ours(dest: Path) -> bool:
    return _manifest(dest) is not None


def up_to_date(package: Path, dest: Path) -> bool:
    """The skill holds this package's rubric and this computer's skeleton, as they are now."""
    there, mine = _manifest(dest), _manifest(package)
    if not there or not mine or {k: there.get(k) for k in ("version", "built_at", "files")} != \
            {k: mine.get(k) for k in ("version", "built_at", "files")}:
        return False
    try:
        if extract_skill.stale(dest) or (dest / "scripts" / "run.py").read_text(encoding="utf-8") != \
                extract_skill.RUN.format(part=SKELETON):
            return False
        return (dest / "SKILL.md").read_text(encoding="utf-8") == skill_md(package)
    except (OSError, ValueError, KeyError):
        return False


def install_one(package: Path, skills: Path | None = None) -> str:
    """Assembles one package into the skills folder: "installed", "updated", "up_to_date", or "kept" when a skill of
    that name there was not built by this tool (never touched)."""
    package = Path(package)
    skills = Path(skills) if skills else Path.home() / ".claude" / "skills"
    dest = skills / package.name
    if dest.exists() and any(dest.iterdir()) and not _ours(dest):
        return "kept"
    if dest.exists() and up_to_date(package, dest):
        return "up_to_date"
    action = "updated" if dest.exists() else "installed"
    tmp = skills / (package.name + ".tmp")
    if tmp.exists():
        _rmtree(tmp)
    skills.mkdir(parents=True, exist_ok=True)
    extract_skill.build(SKELETON, tmp)                     # the skeleton: SKILL.md's steps and the grading engine
    shutil.copytree(package / SNAPSHOT, tmp / SNAPSHOT, copy_function=shutil.copyfile)   # the rubric, frozen
    (tmp / MANIFEST).write_bytes((package / MANIFEST).read_bytes())
    (tmp / "SKILL.md").write_text(skill_md(package), encoding="utf-8")
    for extra in ("install.ps1",):                         # the skeleton's ZIP installer belongs to exercise-grader
        if (tmp / "scripts" / extra).is_file():
            (tmp / "scripts" / extra).unlink()
    if dest.exists():
        _rmtree(dest)
    tmp.rename(dest)
    return action


def install_all(skills: Path | None = None, data: Path | None = None) -> list[dict]:
    """Every rubric package of the data folder, assembled into ~/.claude/skills when new or changed."""
    out = []
    home = Path(skills) if skills else Path.home() / ".claude" / "skills"
    for package in all_packages(data):
        try:
            out.append({"skill": package.name, "action": install_one(package, skills), "path": str(home / package.name)})
        except (OSError, SystemExit) as e:
            out.append({"skill": package.name, "action": "error", "error": str(e)})
    return out


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    from moodle import shared_folder
    shared_folder.use_for_commands()  # the synced shared folder, like every other command (moodle, grading, copying)
    p = argparse.ArgumentParser(prog="python tools/assignment_skill.py", description="A grading skill per rubric")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("id")
    b.add_argument("--name")
    b.add_argument("--by")
    b.add_argument("--triggers", action="append", default=[], help="another phrase that starts the skill")
    b.add_argument("--draft", action="store_true", help="this computer only, for the calibration round")
    b.add_argument("--from", dest="source", type=Path, help="a rubric package brought from outside (with --draft)")
    c = sub.add_parser("check")
    c.add_argument("id")
    sub.add_parser("list")
    sub.add_parser("install")
    a = p.parse_args(argv)
    if a.cmd == "build":
        print(json.dumps(build(a.id, a.name, a.by, a.triggers, draft=a.draft, source=a.source), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "check":
        want = str(paths.read_info(paths.assignment_dir(a.id)).get("id"))
        found = [s for s in all_packages() if _manifest(s)["assignment_id"] == want]
        if not found:
            print("no grading skill for this assignment yet")
            return 1
        rc = 0
        for s in found:
            behind, m = stale(s), _manifest(s)
            print(f"{s.name}  v{m['version']}  built {m['built_at']} by {m['built_by']}: "
                  + ("up to date" if not behind else "the rubric changed since: " + ", ".join(behind)))
            rc = rc or (1 if behind else 0)
        return rc
    if a.cmd == "list":
        for s in all_packages():
            m = _manifest(s)
            try:
                state = "up to date" if not stale(s) else "behind the rubric"
            except (SystemExit, FileNotFoundError, paths.TwoFolders) as e:
                state = f"can't check: {e}"
            print(f"{s.name}  {m['assignment']}  v{m['version']}  {m['built_at'][:10]}  {state}")
        return 0
    for r in install_all():
        print(f"{r['skill']}: {r['action']}" + (f" ({r['error']})" if r.get("error") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
