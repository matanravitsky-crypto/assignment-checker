"""Every part that goes out to a skill is checked here with nothing written for it by hand: a new <part>/skill/SKILL.md
is tested the moment it is added (docs/Modularity.md, "סקיל: להוסיף, להוריד, לבדוק"). Each one must
  - have a SKILL.md that Claude Code can load: front matter with a `name:` (lowercase, digits, hyphens) and a description,
  - be a command (`python -m <part>`), since the skill's run.py runs it,
  - build (tools/extract_skill.py) from the part and only what is below it, and not be stale right after,
  - run alone: `run.py --help` with `python -I`, from a folder that is not the repo, loading code only from the skill.
What a skill does is tested by its own test (test_copying_skill.py, test_grading_skill.py)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

from tools import extract_skill, modules as M

WITH_SKILL = [p for p in M.LAYERS if (M.REPO / p / "skill" / "SKILL.md").is_file()]


def front_matter(part: str) -> dict:
    text = (M.REPO / part / "skill" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{part}/skill/SKILL.md must start with its front matter (---)"
    head, sep, _ = text[4:].partition("\n---")
    assert sep, f"{part}/skill/SKILL.md: the front matter has no closing ---"
    return {k.strip(): v.strip() for k, _, v in (line.partition(":") for line in head.splitlines()) if v.strip()}


def test_the_skills_are_found():
    assert {"copying", "grading"} <= set(WITH_SKILL)


@pytest.mark.parametrize("part", WITH_SKILL)
def test_skill_md_has_a_name_and_a_description(part):
    fm = front_matter(part)
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fm.get("name", "")), f"{part}: name: {fm.get('name')!r}"
    assert fm["name"] == extract_skill.skill_name(part)
    assert len(fm.get("description", "")) >= 40, f"{part}: a description says when Claude should use the skill"


def test_no_two_parts_give_a_skill_the_same_name():
    names = [extract_skill.skill_name(p) for p in WITH_SKILL]
    assert len(names) == len(set(names)), names


@pytest.mark.parametrize("part", WITH_SKILL)
def test_the_part_is_a_command(part):
    assert (M.REPO / part / "__main__.py").is_file(), f"run.py runs `python -m {part}`: {part}/__main__.py is missing"


@pytest.mark.parametrize("part", WITH_SKILL)
def test_the_skill_builds_runs_alone_and_loads_nothing_from_the_repo(part, tmp_path):
    skill = extract_skill.build(part, tmp_path / "skills" / extract_skill.skill_name(part))
    assert extract_skill.stale(skill) == [] and extract_skill.up_to_date(part, skill)

    below = set(M.LAYERS[: M.LAYERS.index(part) + 1])
    taken = {p.relative_to(skill / "scripts").parts[0] for p in (skill / "scripts").rglob("*.py")} - {"run.py"}
    assert taken <= below, f"{part} took parts above it: {sorted(taken - below)}"

    probe = ("import json, runpy, sys\n"
             "sys.argv = ['run.py', '--help']\n"
             "code = 0\n"
             "try:\n    runpy.run_path(RUN, run_name='__main__')\n"
             "except SystemExit as e:\n    code = e.code or 0\n"
             "print(json.dumps({'code': code, 'files': sorted({m.__file__ for m in list(sys.modules.values())"
             " if getattr(m, '__file__', None) and m.__name__.split('.')[0] in PARTS})}))\n")
    probe = probe.replace("RUN", repr(str(skill / "scripts" / "run.py"))).replace("PARTS", repr(tuple(M.LAYERS)))
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "ASSIGNMENT_CHECKER_ROOT")}
    env.update(PYTHONIOENCODING="utf-8", ASSIGNMENT_DATA=str(tmp_path / "data"))  # never the real shared folder
    out = subprocess.run([sys.executable, "-I", "-c", probe], cwd=tmp_path, capture_output=True, text=True,
                         encoding="utf-8", env=env, timeout=300)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["code"] == 0, out.stdout + out.stderr
    assert result["files"] and all(str(skill) in f for f in result["files"]), result["files"]
