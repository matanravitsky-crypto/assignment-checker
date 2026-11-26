"""A grading skill for one assignment, built from its approved rubric: the weekly step of the rubric team
(the skill .claude/skills/grading-skill-maker runs it; decided at the meeting of 2026-11-15: "a grading skill per assignment").

    python tools/assignment_skill.py build <moodle id> [--name grade-linear-1] [--by <who>] [--triggers "..."]
                                        builds <course>/Grading skills/<name>/ in the data folder and installs it here
    python tools/assignment_skill.py check <moodle id>     is its skill there, and does it still match the rubric?
    python tools/assignment_skill.py list                  every assignment's grading skill and whether it fell behind
    python tools/assignment_skill.py install               copies every assignment's skill from the data folder into
                                                           ~/.claude/skills (only new or changed ones; the dashboard
                                                           does this at every start, dashboard/skills.py)

What a skill holds (and nothing else; never a submission, a grade or the key):
  SKILL.md            the assignment's name, its questions and points, the phrases that start it, and the steps: grade
                      with exercise-grader (the system's own grading code, on every teammate's computer) with this
                      skill's copy of the grading material as the rubric
  assignment/         a frozen copy of exactly what the system's grading reads from the assignment folder:
                      Assignment details.json, the files of פדגוגי that grading sends (grade.pedagogy_files), the
                      official key (Official key/, Official key.txt) and Official solution.pdf
  MANIFEST.json       which assignment, who built it and when, and the sha256 of every copied file, so a skill whose
                      rubric changed since is found (`check`, `list`)

So the skill grades exactly like the system did on the day it was built, by anyone, without passing the rubric around;
when the rubric changes, the skill is built again (the same name, a new version). The rubric is the one source: a
grading instruction belongs in the rubric (rubric-builder), never only in the skill.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):  # run as a script: python tools/assignment_skill.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grading import grade, one_submission  # noqa: E402
from moodle import paths  # noqa: E402

KIND = "assignment-grading-skill"   # the MANIFEST mark: install and replace only skills that carry it
MANIFEST = "MANIFEST.json"
SNAPSHOT = "assignment"             # the copy of the grading material, inside the skill
GRADER = "exercise-grader"          # the skill that grades (grading/skill/SKILL.md), installed by the dashboard
COURSE_SHORT = {"Linear Algebra": "linear", "Discrete Mathematics": "discrete"}
COURSE_HE = {"Linear Algebra": "אלגברה לינארית", "Discrete Mathematics": "מתמטיקה בדידה"}


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


def skills_dir_of(folder: Path) -> Path:
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


def skill_md(name: str, folder: Path, rubric: dict, info: dict, triggers: list[str], built: dict) -> str:
    course = folder.parent.name
    course_he = COURSE_HE.get(course, course)
    slot = _slot(folder)
    title = _clean(info.get("hebrew_title") or info.get("title") or rubric.get("title") or folder.name)
    phrases = [f"תבדוק עבודה של הגשה {slot} ב{course_he}", f"בדיקה של {title}",
               f"תבדוק לפי המחוון של הגשה {slot}"] if slot is not None else [f"בדיקה של {title}"]
    phrases += [t for t in triggers if t not in phrases]
    quoted = ", ".join(f'"{p}"' for p in phrases)
    description = (f"Grade a student's submission of {course_he}, {title} (Moodle id {info.get('id')}), with this "
                   f"assignment's rubric already inside, and return the marked PDF like the system does. "
                   f"Use when someone sends a work of this assignment and says {quoted}, or a work and names this "
                   f"assignment. Needs the {GRADER} skill (every computer that runs the system has it). "
                   f"Not for other assignments: each one has its own grade-<course>-<N> skill.")
    rows = "\n".join(f"| {q['label']} | {q['points']:g} |" for q in rubric["questions"])
    approved = {True: "מאושר", False: "לא כתוב מאושר ביומן המחוון", None: "אין יומן מחוון"}[built["approved"]]
    return f"""---
name: {name}
description: {description}
model: {grade.DEFAULT_MODEL}
effort: {grade.EFFORT}
---

# בדיקת {title} ({course_he})

סקיל הבדיקה של המטלה הזאת בלבד. נבנה ב-{built['built_at'][:16].replace('T', ' ')} על ידי {built['built_by']} מהמחוון
של המטלה ({approved}), עם `tools/assignment_skill.py` של בודק חכם. אף אחד לא כותב את הקובץ הזה ביד: מחוון שהשתנה
= בונים את הסקיל שוב (הסקיל `grading-skill-maker`).

`<skill>` למטה היא התיקייה של הסקיל הזה, `<skill>\\{SNAPSHOT}` היא המחוון: עותק קפוא של כל מה שהמערכת קוראת מתיקיית
המטלה כשהיא בודקת (`Assignment details.json`, הקבצים של פדגוגי שנשלחים לבדיקה, המכוון והפתרון הרשמי). לכן לא מבקשים
מהמשתמש מחוון, ולא מחפשים מחוון אחר.

## השאלות והניקוד

| שאלה | נקודות |
|---|---|
{rows}

סה"כ {rubric['total_points']:g}, ציון מתוך {rubric['max_grade']:g}.

## איך בודקים

1. **מצא את סקיל הבדיקה של המערכת**: `<home>\\.claude\\skills\\{GRADER}\\SKILL.md` (`Path.home()`). אם הוא חסר, אמור
   למשתמש שצריך את המערכת פועלת במחשב (`start.bat`, היא מתקינה אותו בכל הפעלה) או את `{GRADER}.zip` מהצוות, ועצור.
2. **קרא את `{GRADER}\\SKILL.md` ועבוד לפיו, צעד אחרי צעד**, עם שני שינויים בלבד:
   - **המחוון** בכל מקום שבו הוא מבקש מחוון (`rubric`, `mark`) הוא התיקייה `<skill>\\{SNAPSHOT}`, כנתיב מלא. לא שואלים
     על מחוון, ולא כותבים `rubric.json` ביד. אם המשתמש צירף מחוון אחר, אמור שלמטלה הזאת יש מחוון מאושר בסקיל ושאל
     באיזה לבדוק.
   - **העבודה** היא של המטלה הזאת. אם ברור מהעמודים שזו מטלה אחרת (שאלות אחרות), אמור את זה לפני שבודקים.
3. כל השאר בדיוק כמו ב-`{GRADER}`: עברית, בלי שמות ות"ז, הפלט בתיקייה `עבודות בדוקות` בשולחן העבודה.

## הסקיל הזה עדכני?

בכל מחשב שמריץ את המערכת, השרת מעתיק בכל הפעלה את הסקילים של כל המטלות מהתיקייה המשותפת
(`<course>\\{paths.GRADING_SKILLS}\\`), ורק כשמשהו השתנה. בבדיקה ידנית, מתוך תיקיית הקוד:
`python tools/assignment_skill.py check {info.get('id')}` אומר אם המחוון השתנה מאז שהסקיל נבנה.
"""


def build(assignment_id: str, name: str | None = None, by: str | None = None, triggers: list[str] | None = None,
          install_to: Path | None = None) -> dict:
    """Builds the assignment's grading skill in <course>/Grading skills/<name>/ and installs it in `install_to`
    (default ~/.claude/skills). Refuses an assignment whose rubric is missing points for a question."""
    folder = paths.assignment_dir(assignment_id)
    name = name or default_name(folder)
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
    dest = skills_dir_of(folder) / name
    old = _manifest(dest)
    if dest.exists() and any(dest.iterdir()) and old is None:
        raise SystemExit(f"{dest} exists and was not built by this tool: not touching it")
    built = {"kind": KIND, "skill": name, "assignment_id": str(info.get("id")),
             "assignment": f"{folder.parent.name}/{folder.name}",
             "version": (old or {}).get("version", 0) + 1,
             "built_at": datetime.now().isoformat(timespec="seconds"),
             "built_by": by or os.environ.get("GRADER_NAME") or os.environ.get("USERNAME") or os.environ.get("USER") or "?",
             "approved": _approved(folder), "total_points": rubric["total_points"],
             "files": {rel: _sha(f) for rel, f in files.items()}}
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
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
    snap_info.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (tmp / "SKILL.md").write_text(skill_md(name, folder, rubric, info, triggers or [], built), encoding="utf-8")
    (tmp / MANIFEST).write_text(json.dumps(built, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    same = one_submission.rubric(tmp / SNAPSHOT)
    if same["context"] != rubric["context"] or same["questions"] != rubric["questions"]:
        shutil.rmtree(tmp)
        raise SystemExit("the copy does not grade like the assignment folder (context differs): nothing written")
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    out = {"skill": name, "path": str(dest), "version": built["version"], "files": len(files),
           "questions": rubric["questions"], "total_points": rubric["total_points"], "approved": built["approved"]}
    out["installed"] = install_one(dest, _skills_home(install_to))
    return out


def _manifest(skill_dir: Path) -> dict | None:
    try:
        m = json.loads((Path(skill_dir) / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m if isinstance(m, dict) and m.get("kind") == KIND else None


def stale(skill_dir: Path) -> list[str]:
    """What changed in the assignment folder since the skill was built: files whose bytes differ, are gone, or are new
    (a new file in פדגוגי, a key uploaded since). Empty = the skill grades like the system does today."""
    m = _manifest(skill_dir)
    if m is None:
        raise SystemExit(f"{skill_dir} is not an assignment grading skill")
    folder = paths.assignment_dir(m["assignment_id"])
    now = {rel: _sha(f) for rel, f in sources(folder).items()}
    return sorted(rel for rel in set(now) | set(m["files"]) if now.get(rel) != m["files"].get(rel))


def all_skills(data: Path | None = None) -> list[Path]:
    root = Path(data) if data else paths.data_dir()
    return sorted(p.parent for p in root.glob(f"*/{paths.GRADING_SKILLS}/*/{MANIFEST}") if _manifest(p.parent))


def _skills_home(skills: Path | None) -> Path:
    return Path(skills) if skills else Path.home() / ".claude" / "skills"


def install_one(src: Path, skills: Path | None = None) -> str:
    """Copies one built skill into the skills folder: "installed", "updated", "up_to_date", or "kept" when a skill of
    that name there was not built by this tool (never touched)."""
    src, skills = Path(src), _skills_home(skills)
    dest = skills / src.name
    there = _manifest(dest)
    if dest.exists() and any(dest.iterdir()) and there is None:
        return "kept"
    mine = _manifest(src)
    if there and mine and there.get("built_at") == mine.get("built_at") and there.get("files") == mine.get("files") \
            and (dest / "SKILL.md").is_file() and (dest / "SKILL.md").read_bytes() == (src / "SKILL.md").read_bytes():
        return "up_to_date"
    action = "updated" if dest.exists() else "installed"
    tmp = skills / (src.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(src, tmp, copy_function=shutil.copyfile)  # no copystat: OneDrive marks folders read-only
    if dest.exists():
        _clear(dest)
        dest.rmdir()
    tmp.rename(dest)
    return action


def _clear(folder: Path) -> None:
    import stat
    for root, dirs, names in os.walk(folder, topdown=False):
        for n in names:
            p = os.path.join(root, n)
            os.chmod(p, stat.S_IREAD | stat.S_IWRITE)
            os.unlink(p)
        for d in dirs:
            p = os.path.join(root, d)
            os.chmod(p, stat.S_IRWXU)
            os.rmdir(p)


def install_all(skills: Path | None = None, data: Path | None = None) -> list[dict]:
    """Every assignment's grading skill from the data folder into ~/.claude/skills, only when new or changed."""
    out = []
    for src in all_skills(data):
        try:
            out.append({"skill": src.name, "action": install_one(src, skills), "path": str(_skills_home(skills) / src.name)})
        except OSError as e:
            out.append({"skill": src.name, "action": "error", "error": str(e)})
    return out


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python tools/assignment_skill.py", description="A grading skill per assignment")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("id")
    b.add_argument("--name")
    b.add_argument("--by")
    b.add_argument("--triggers", action="append", default=[], help="another phrase that starts the skill")
    c = sub.add_parser("check")
    c.add_argument("id")
    sub.add_parser("list")
    sub.add_parser("install")
    a = p.parse_args(argv)
    if a.cmd == "build":
        print(json.dumps(build(a.id, a.name, a.by, a.triggers), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "check":
        folder = paths.assignment_dir(a.id)
        found = [s for s in all_skills() if _manifest(s)["assignment_id"] == str(paths.read_info(folder).get("id"))]
        if not found:
            print("no grading skill for this assignment yet")
            return 1
        rc = 0
        for s in found:
            behind = stale(s)
            m = _manifest(s)
            print(f"{s.name}  v{m['version']}  built {m['built_at']} by {m['built_by']}: "
                  + ("up to date" if not behind else "the rubric changed since: " + ", ".join(behind)))
            rc = rc or (1 if behind else 0)
        return rc
    if a.cmd == "list":
        for s in all_skills():
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
