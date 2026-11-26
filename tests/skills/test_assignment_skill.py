"""A grading skill per assignment (tools/assignment_skill.py, the skill grading-skill-maker): built from the
assignment's rubric into <course>/Grading skills/<name>/, it grades exactly like the assignment folder (the same text
and points reach the grading), holds nothing of the students, finds out when the rubric changed, and every computer
copies it into its skills folder without touching a skill of the same name it did not build."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard import skills as team_skills
from grading import one_submission
from moodle import paths
from tools import assignment_skill as S

COURSE, HW = "Linear Algebra", "Assignment 1 - Vectors"
LABELS = ["דף וקטורים 8", "דף וקטורים 11"]


@pytest.fixture
def data(tmp_path, monkeypatch) -> Path:
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


def test_the_skill_holds_exactly_what_the_grading_reads(data, tmp_path):
    out = S.build("3438638", by="נועה", install_to=tmp_path / "skills")
    skill = Path(out["path"])
    assert skill == data / COURSE / paths.GRADING_SKILLS / "grade-linear-1"
    assert out["installed"] == "installed" and out["approved"] is True and out["version"] == 1
    files = sorted(p.relative_to(skill / S.SNAPSHOT).as_posix() for p in (skill / S.SNAPSHOT).rglob("*") if p.is_file())
    assert files == [paths.INFO, f"{paths.OFFICIAL_KEY}/key.png", "פדגוגי/Rubric.md", "פדגוגי/Solutions.md"]
    here, there = one_submission.rubric(assignment(data)), one_submission.rubric(skill / S.SNAPSHOT)
    assert there["context"] == here["context"] and there["questions"] == here["questions"]
    every = [p.name for p in skill.rglob("*")]
    assert "0001.pdf" not in every and paths.KEY not in every  # nothing of the students


def test_skill_md_names_the_assignment_its_points_and_the_grader(data, tmp_path):
    skill = Path(S.build("3438638", by="נועה", triggers=["דף וקטורים"], install_to=tmp_path / "skills")["path"])
    md = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert md.startswith("---\nname: grade-linear-1\n")
    assert "תבדוק עבודה של הגשה 1 באלגברה לינארית" in md and '"דף וקטורים"' in md
    assert "| דף וקטורים 8 | 50 |" in md and S.GRADER in md and "נועה" in md
    assert (tmp_path / "skills" / "grade-linear-1" / "SKILL.md").read_text(encoding="utf-8") == md


def test_a_rubric_change_makes_the_skill_stale_and_a_rebuild_is_the_next_version(data, tmp_path):
    skill = Path(S.build("3438638", install_to=tmp_path / "skills")["path"])
    assert S.stale(skill) == []
    (assignment(data) / "פדגוגי" / "Rubric.md").write_text("# מחוון\n\nשונה\n", encoding="utf-8")
    (assignment(data) / "פדגוגי" / "Manual review rules.md").write_text("חדש", encoding="utf-8")
    assert S.stale(skill) == ["פדגוגי/Manual review rules.md", "פדגוגי/Rubric.md"]
    again = S.build("3438638", install_to=tmp_path / "skills")
    assert again["version"] == 2 and again["installed"] == "updated" and S.stale(skill) == []


def test_no_skill_without_points_for_every_question(data, tmp_path):
    info = json.loads((assignment(data) / paths.INFO).read_text(encoding="utf-8"))
    info["rubric"] = None
    (assignment(data) / paths.INFO).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    (assignment(data) / "פדגוגי" / "Rubric.md").write_text("# מחוון בלי טבלת ניקוד\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        S.build("3438638", install_to=tmp_path / "skills")
    assert not (data / COURSE / paths.GRADING_SKILLS).exists()


def test_the_skills_folder_never_shows_as_an_assignment(data, tmp_path):
    S.build("3438638", install_to=tmp_path / "skills")
    assert paths.assignment_dirs() == [assignment(data)]
    assert paths.find_assignment("3438638") == assignment(data)


def test_every_computer_copies_new_and_changed_skills_only(data, tmp_path):
    S.build("3438638", install_to=tmp_path / "builder")
    home = tmp_path / "teammate"
    assert [r["action"] for r in team_skills.assignment_skills(home)] == ["installed"]
    assert [r["action"] for r in team_skills.assignment_skills(home)] == ["up_to_date"]
    (assignment(data) / "פדגוגי" / "Rubric.md").write_text("# מחוון\n\nשונה\n", encoding="utf-8")
    S.build("3438638", install_to=tmp_path / "builder")
    assert [r["action"] for r in team_skills.assignment_skills(home)] == ["updated"]
    assert "שונה" in (home / "grade-linear-1" / S.SNAPSHOT / "פדגוגי" / "Rubric.md").read_text(encoding="utf-8")


def test_a_hand_made_skill_of_the_same_name_is_never_touched(data, tmp_path):
    home = tmp_path / "skills"
    (home / "grade-linear-1").mkdir(parents=True)
    (home / "grade-linear-1" / "SKILL.md").write_text("mine", encoding="utf-8")
    assert S.build("3438638", install_to=home)["installed"] == "kept"
    assert (home / "grade-linear-1" / "SKILL.md").read_text(encoding="utf-8") == "mine"
