"""copying/ taken out to a skill (tools/extract_skill.py, docs/Modularity.md): the skill holds the part and only the
core it needs, runs with no repo on the path, finds exactly what the system finds, and the system does not change."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from copying import check
from moodle import paths
from tests.copying.test_check import pdf_of, scan
from tools import extract_skill, modules as M


@pytest.fixture
def assignment(tmp_path):
    a = tmp_path / "data" / "Linear Algebra" / "Assignment 0"
    (a / paths.TO_GRADE).mkdir(parents=True)
    same = pdf_of(scan(1), scan(2))
    for name, data in {"0001.pdf": same, "0002.pdf": same,                               # the same file
                       "0003.pdf": pdf_of(scan(1, quality=50, dpi=90), scan(2, quality=45, dpi=80)),  # the same pages
                       "0004.pdf": pdf_of(scan(3), scan(4))}.items():                    # someone else's work
        (a / paths.TO_GRADE / name).write_bytes(data)
    return a


def run_skill(skill, *args, cwd, data):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "ASSIGNMENT_CHECKER_ROOT")}
    env["ASSIGNMENT_DATA"] = str(data)  # never the real shared folder of this computer
    env["PYTHONIOENCODING"] = "utf-8"
    # -I: no PYTHONPATH, no user site, no current folder: only the skill's own scripts/ (run.py puts it on the path)
    return subprocess.run([sys.executable, "-I", str(skill / "scripts" / "run.py"), *args], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)


def test_the_skill_takes_copying_and_only_the_core_it_needs():
    taken = {M.module_name(f) for f in extract_skill.files_for("copying")}
    assert {m for m in taken if M.part_of(m) == "copying"} == {"copying", "copying.__main__", "copying.check"}
    assert {m for m in taken if M.part_of(m) != "copying"} <= set(M.CORE)
    assert "moodle.paths" in taken


def test_the_skill_runs_alone_and_finds_what_the_system_finds(tmp_path, assignment):
    skill = extract_skill.build("copying", tmp_path / "skills" / "copying-check")
    assert (skill / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: copying-check\n")
    built = {p.relative_to(skill / "scripts").parts[0] for p in (skill / "scripts").rglob("*.py")}
    assert built == {"copying", "moodle", "run.py"}  # nothing of the dashboard, grading, stats, datastore...
    assert extract_skill.stale(skill) == []

    system_copy = tmp_path / "system" / assignment.name
    shutil.copytree(assignment, system_copy)

    # the skill, on an assignment folder and then by the assignment's Moodle id, from a folder that is not the repo
    out = run_skill(skill, str(assignment), cwd=tmp_path, data=tmp_path / "data")
    assert out.returncode == 0, out.stderr
    assert "0001 ↔ 0002" in out.stdout and "0004" not in out.stdout
    from_skill = json.loads((assignment / paths.COPYING).read_text(encoding="utf-8"))
    (assignment / paths.INFO).write_text(json.dumps({"id": "3438636"}), encoding="utf-8")
    again = run_skill(skill, "3438636", cwd=tmp_path, data=tmp_path / "data")
    assert again.returncode == 0 and "0001 ↔ 0002" in again.stdout, again.stderr

    # the system's own code, on a copy of the same submissions
    rep = check.check_assignment(system_copy)
    as_json = json.loads(json.dumps({"pairs": rep.pairs, "repeated": rep.repeated}))
    assert from_skill["pairs"] == as_json["pairs"] and from_skill["repeated"] == as_json["repeated"]
    assert {(p["a"], p["b"]) for p in rep.pairs} == {("0001", "0002"), ("0001", "0003"), ("0002", "0003")}


def test_the_skill_never_loads_code_from_the_repo(tmp_path):
    skill = extract_skill.build("copying", tmp_path / "copying-check")
    probe = ("import runpy, sys; sys.argv = ['run.py', '--help']\n"
             "try:\n    runpy.run_path(sys.argv_path, run_name='__main__')\nexcept SystemExit:\n    pass\n"
             "import json; print(json.dumps(sorted({m.__file__ for m in list(sys.modules.values())"
             " if getattr(m, '__file__', None) and m.__name__.split('.')[0] in ('copying', 'moodle')})))")
    probe = probe.replace("sys.argv_path", repr(str(skill / "scripts" / "run.py")))
    out = subprocess.run([sys.executable, "-I", "-c", probe], cwd=tmp_path, capture_output=True, text=True,
                         encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=120)
    loaded = json.loads(out.stdout.strip().splitlines()[-1])
    assert loaded and all(str(skill) in f for f in loaded), loaded


def test_a_skill_that_fell_behind_the_repo_is_found(tmp_path):
    skill = extract_skill.build("copying", tmp_path / "copying-check")
    (skill / "scripts" / "copying" / "check.py").write_text("# changed by hand\n", encoding="utf-8")
    assert extract_skill.stale(skill) == ["copying/check.py"]
    by_hand = tmp_path / "a skill made by hand"
    by_hand.mkdir()
    (by_hand / "SKILL.md").write_text("---
name: mine
---
", encoding="utf-8")
    with pytest.raises(SystemExit):  # a folder this tool did not build is never replaced
        extract_skill.build("copying", by_hand)
    assert (by_hand / "SKILL.md").read_text(encoding="utf-8").startswith("---
name: mine")
    # one it built is rebuilt in place (the folder stays: Windows refuses to remove a skills folder Claude Code holds)
    assert extract_skill.build("copying", skill) == skill and extract_skill.stale(skill) == []
