"""A grading skill per rubric (tools/assignment_skill.py, the skill grading-skill-maker): the skeleton (exercise-grader:
grading/skill/SKILL.md and the grading engine) with one assignment's frozen rubric dressed on it.
The rubric package in <course>/Grading skills/<name>/ grades exactly like the assignment folder and holds nothing of the
students; every computer assembles the skill from its own skeleton, so a newer skeleton reaches every rubric's skill,
while the rubric changes only when it is built again; a skill of the same name built by hand is never touched."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard import skills as team_skills
from grading import one_submission
from moodle import paths
from tools import assignment_skill as S
from tools import extract_skill

COURSE, HW = "Linear Algebra", "Assignment 1 - Vectors"
LABELS = ["דף וקטורים 8", "דף וקטורים 11"]


@pytest.fixture
def data(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(extract_skill, "_commit", lambda: "abc1234")
    root = tmp_path / "Exercise Checking System"
    a = root / COURSE / HW
    (a / paths.TO_GRADE).mkdir(parents=True)
    (a / paths.TO_GRADE / "0001.pdf").write_bytes(b"%PDF-1.4 a student's work")
    (a / paths.KEY).write_text("number,participant_id\n0001,123456\n", encoding="utf-8")
    (a / paths.INFO).write_text(json.dumps({
        "id": "3438638", "course": COURSE, "name": HW, "title": "הגשה 1 - וקטורים",
        "questions": [{"sheet": "דף וקטורים", "numbers": [8, 11]}], "max_grade": 100,
        "rubric": {"questions": [{"label": l, "points": 50} for l in LABELS]}}, ensure_ascii=False), encoding="utf-8")
    ped = a / "פדגוגי"
    (ped / paths.RUBRIC_NOTES).mkdir(parents=True)
    (ped / "Rubric.md").write_text("# מחוון\n\nבשאלה 8 מקבלים גם וקטור מנורמל.\n", encoding="utf-8")
    (ped / "Solutions.md").write_text("# פתרונות\n", encoding="utf-8")
    (ped / "Rubric old.md").write_text("ישן: לא נשלח לבדיקה", encoding="utf-8")
    (ped / paths.RUBRIC_NOTES / paths.RUBRIC_LOG).write_text("- round 2: מאושר\n", encoding="utf-8")
    (a / paths.OFFICIAL_KEY).mkdir()
    (a / paths.OFFICIAL_KEY / "key.png").write_bytes(b"\x89PNG key")
    monkeypatch.setenv("ASSIGNMENT_DATA", str(root))
    return root


def assignment(data: Path) -> Path:
    return data / COURSE / HW


def test_the_package_holds_exactly_what_the_grading_reads(data, tmp_path):
    out = S.build("3438638", by="נועה", install_to=tmp_path / "skills")
    package = Path(out["package"])
    assert package == data / COURSE / paths.GRADING_SKILLS / "grade-linear-1"
    assert out["installed"] == "installed" and out["approved"] is True and out["version"] == 1
    files = sorted(p.relative_to(package / S.SNAPSHOT).as_posix() for p in (package / S.SNAPSHOT).rglob("*") if p.is_file())
    assert files == [paths.INFO, f"{paths.OFFICIAL_KEY}/key.png", "פדגוגי/Rubric.md", "פדגוגי/Solutions.md"]
    here, there = one_submission.rubric(assignment(data)), one_submission.rubric(package / S.SNAPSHOT)
    assert there["context"] == here["context"] and there["questions"] == here["questions"]
    for folder in (package, tmp_path / "skills" / "grade-linear-1"):
        every = [p.name for p in folder.rglob("*")]
        assert "0001.pdf" not in every and paths.KEY not in every  # nothing of the students


def test_the_skill_is_the_skeleton_with_the_rubric_dressed_on(data, tmp_path):
    S.build("3438638", by="נועה", triggers=["דף וקטורים"], install_to=tmp_path / "skills")
    skill = tmp_path / "skills" / "grade-linear-1"
    md = (skill / "SKILL.md").read_text(encoding="utf-8")
    skeleton = S.skeleton_md()
    assert md.startswith("---\nname: grade-linear-1\n")
    assert '"תבדוק עבודה של הגשה 1 באלגברה לינארית"' in md and '"דף וקטורים"' in md
    assert "| דף וקטורים 8 | 50 |" in md and "נועה" in md
    assert "rubric-slot" not in md and "Never ask for a rubric" in md
    # every line of the skeleton outside its rubric slots is in the skill, word for word
    outside = S._SLOT.sub("", skeleton.split("\n---\n", 1)[1])
    lines = [l for l in outside.splitlines() if l.strip() and not l.startswith("# ")]
    assert lines and all(l in md for l in lines)
    # the engine is the skeleton's own code, and it runs from the skill
    assert not extract_skill.stale(skill) and (skill / "scripts" / "grading" / "grade.py").is_file()
    assert (skill / S.SNAPSHOT / "פדגוגי" / "Rubric.md").is_file()
    assert not (skill / "scripts" / "install.ps1").exists()


def test_the_skeleton_has_exactly_the_slots_this_tool_fills():
    assert sorted(S.slots(S.skeleton_md())) == sorted(S.SLOTS)


def test_a_rubric_change_makes_the_package_stale_and_a_rebuild_is_the_next_version(data, tmp_path):
    package = Path(S.build("3438638", install_to=tmp_path / "skills")["package"])
    assert S.stale(package) == []
    (assignment(data) / "פדגוגי" / "Rubric.md").write_text("# מחוון\n\nשונה\n", encoding="utf-8")
    (assignment(data) / "פדגוגי" / "Manual review rules.md").write_text("חדש", encoding="utf-8")
    assert S.stale(package) == ["פדגוגי/Manual review rules.md", "פדגוגי/Rubric.md"]
    again = S.build("3438638", install_to=tmp_path / "skills")
    assert again["version"] == 2 and again["installed"] == "updated" and S.stale(package) == []


def test_no_skill_without_points_for_every_question(data, tmp_path):
    info = json.loads((assignment(data) / paths.INFO).read_text(encoding="utf-8"))
    info["rubric"] = None
    (assignment(data) / paths.INFO).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    (assignment(data) / "פדגוגי" / "Rubric.md").write_text("# מחוון בלי טבלת ניקוד\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        S.build("3438638", install_to=tmp_path / "skills")
    assert not (data / COURSE / paths.GRADING_SKILLS).exists()


def test_the_packages_folder_never_shows_as_an_assignment(data, tmp_path):
    S.build("3438638", install_to=tmp_path / "skills")
    assert paths.assignment_dirs() == [assignment(data)]
    assert paths.find_assignment("3438638") == assignment(data)


def test_every_computer_assembles_new_and_changed_ones_only(data, tmp_path, monkeypatch):
    S.build("3438638", install_to=tmp_path / "builder")
    home = tmp_path / "teammate"
    assert [r["action"] for r in team_skills.assignment_skills(home)] == ["installed"]
    assert [r["action"] for r in team_skills.assignment_skills(home)] == ["up_to_date"]
    # a newer rubric (built again) reaches the teammate
    (assignment(data) / "פדגוגי" / "Rubric.md").write_text("# מחוון\n\nשונה\n", encoding="utf-8")
    S.build("3438638", install_to=tmp_path / "builder")
    assert [r["action"] for r in team_skills.assignment_skills(home)] == ["updated"]
    assert "שונה" in (home / "grade-linear-1" / S.SNAPSHOT / "פדגוגי" / "Rubric.md").read_text(encoding="utf-8")
    # a newer skeleton (the steps of SKILL.md changed) reaches it too, with the rubric unchanged
    monkeypatch.setattr(S, "skeleton_md", lambda real=S.skeleton_md: real() + "\nשורה חדשה בשלד\n")
    assert [r["action"] for r in team_skills.assignment_skills(home)] == ["updated"]
    assert "שורה חדשה בשלד" in (home / "grade-linear-1" / "SKILL.md").read_text(encoding="utf-8")


def test_a_hand_made_skill_of_the_same_name_is_never_touched(data, tmp_path):
    home = tmp_path / "skills"
    (home / "grade-linear-1").mkdir(parents=True)
    (home / "grade-linear-1" / "SKILL.md").write_text("mine", encoding="utf-8")
    assert S.build("3438638", install_to=home)["installed"] == "kept"
    assert (home / "grade-linear-1" / "SKILL.md").read_text(encoding="utf-8") == "mine"


def test_the_team_retire_never_removes_a_rubric_skill(data, tmp_path):
    home = tmp_path / "skills"
    S.build("3438638", install_to=home)
    extract_skill.retire(["exercise-grader"], home)
    assert (home / "grade-linear-1" / "SKILL.md").is_file()


def test_a_draft_stays_on_this_computer_until_published(data, tmp_path):
    out = S.build("3438638", install_to=tmp_path / "skills", draft=True, drafts=tmp_path / "drafts")
    assert out["draft"] and Path(out["package"]) == tmp_path / "drafts" / "grade-linear-1"
    assert (tmp_path / "skills" / "grade-linear-1" / "SKILL.md").is_file()
    assert not (data / COURSE / paths.GRADING_SKILLS).exists() and S.all_packages() == []
    published = S.build("3438638", install_to=tmp_path / "skills")
    assert S.all_packages() == [Path(published["package"])]
