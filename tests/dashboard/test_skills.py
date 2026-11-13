"""The team's skills on every computer that runs the system (dashboard/skills.py): built at the server's start from
this computer's code, removed from every computer once taken off the list (only the ones the server installed),
never stopping the server, and off with INSTALL_SKILLS=off."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard import skills
from tools import extract_skill


@pytest.fixture(autouse=True)
def no_git(monkeypatch, tmp_path):
    monkeypatch.setattr(extract_skill, "_commit", lambda: "abc1234")  # the dashboard tests start no real process
    home = tmp_path / "home"  # never this computer's own ~/.claude/skills
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))


def team(skill: Path) -> bool:
    return json.loads((skill / "scripts" / extract_skill.MANIFEST).read_text(encoding="utf-8"))["team"]


def test_every_team_skill_has_a_skill_of_its_own():
    for part in skills.TEAM_SKILLS:
        assert (extract_skill.M.REPO / part / "skill" / "SKILL.md").is_file(), part


def test_the_server_start_builds_the_teams_skills(tmp_path):
    out = skills.refresh(tmp_path / "skills", tmp_path / "backups")
    assert [(r["skill"], r["action"]) for r in out] == [("exercise-grader", "installed")]
    assert extract_skill.up_to_date("grading", tmp_path / "skills" / "exercise-grader")
    assert team(tmp_path / "skills" / "exercise-grader")
    assert [r["action"] for r in skills.refresh(tmp_path / "skills", tmp_path / "backups")] == ["up_to_date"]


def test_a_skill_taken_off_the_list_is_removed_from_every_computer(tmp_path, monkeypatch):
    installed = tmp_path / "skills" / "exercise-grader"
    skills.refresh(tmp_path / "skills")
    assert installed.is_dir()
    monkeypatch.setattr(skills, "TEAM_SKILLS", [])
    out = skills.refresh(tmp_path / "skills")
    assert [(r["skill"], r["action"]) for r in out] == [("exercise-grader", "removed")]
    assert not installed.exists()
    assert skills.refresh(tmp_path / "skills") == []  # nothing left to do


def test_only_what_the_server_installed_is_ever_removed(tmp_path, monkeypatch):
    s = tmp_path / "skills"
    by_hand = extract_skill.build("copying", s / "copying-check")              # extract_skill.py copying
    with_install = extract_skill.install("grading", s)["path"]                 # extract_skill.py grading --install
    mine = s / "my-own-skill"                                                  # nothing to do with this tool
    mine.mkdir()
    (mine / "SKILL.md").write_text("---\nname: my-own-skill\n---\n", encoding="utf-8")
    monkeypatch.setattr(skills, "TEAM_SKILLS", [])
    assert skills.refresh(s) == []
    assert (by_hand / "SKILL.md").is_file() and (Path(with_install) / "SKILL.md").is_file()
    assert (mine / "SKILL.md").is_file()


def test_a_skill_installed_before_the_team_mark_gets_it_and_can_be_removed(tmp_path, monkeypatch):
    """exercise-grader went to every computer with PR #103, before MANIFEST had "team": the next start marks it."""
    s = tmp_path / "skills"
    old = extract_skill.build("grading", s / "exercise-grader")
    manifest = json.loads((old / "scripts" / extract_skill.MANIFEST).read_text(encoding="utf-8"))
    del manifest["team"]
    (old / "scripts" / extract_skill.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    assert [r["action"] for r in skills.refresh(s)] == ["updated"] and team(old)
    monkeypatch.setattr(skills, "TEAM_SKILLS", [])
    assert [r["action"] for r in skills.refresh(s)] == ["removed"] and not old.exists()


def test_a_hand_install_never_takes_the_team_mark_away(tmp_path):
    s = tmp_path / "skills"
    skills.refresh(s)
    (s / "exercise-grader" / "SKILL.md").write_text("---\nname: exercise-grader\n---\nolder\n", encoding="utf-8")
    assert extract_skill.install("grading", s)["action"] == "updated"  # by hand, with no team=True
    assert team(s / "exercise-grader")


def test_a_renamed_skill_goes_under_its_old_name_and_comes_under_the_new_one(tmp_path):
    s = tmp_path / "skills"
    extract_skill.build("grading", s / "grader-old-name", team=True)  # what `name:` used to be
    out = skills.refresh(s)
    assert [(r["skill"], r["action"]) for r in out] == [("grader-old-name", "removed"), ("exercise-grader", "installed")]
    assert not (s / "grader-old-name").exists() and (s / "exercise-grader" / "SKILL.md").is_file()


def test_a_folder_windows_keeps_is_no_skill_and_goes_at_the_next_start(tmp_path, monkeypatch):
    """Claude Code holds the skills folders it watches, and Windows then refuses to remove one (WinError 5)."""
    s = tmp_path / "skills"
    skills.refresh(s)
    held = s / "exercise-grader"
    free = extract_skill._remove_folder

    def refuse(folder):
        raise PermissionError(5, "Access is denied")
    monkeypatch.setattr(extract_skill, "_remove_folder", refuse)
    monkeypatch.setattr(skills, "TEAM_SKILLS", [])
    assert [r["action"] for r in skills.refresh(s)] == ["removed"]
    assert [c.name for c in held.iterdir()] == [extract_skill.REMOVED]  # no SKILL.md: Claude Code sees no skill
    assert skills.refresh(s) == [] and held.is_dir()                    # still held: the note stays

    monkeypatch.setattr(extract_skill, "_remove_folder", free)  # Claude Code let go of it
    assert skills.refresh(s) == [] and not held.exists()


def test_a_skill_back_on_the_list_takes_its_kept_folder_back(tmp_path, monkeypatch):
    s = tmp_path / "skills"
    skills.refresh(s)
    monkeypatch.setattr(extract_skill, "_remove_folder", lambda folder: (_ for _ in ()).throw(PermissionError(5, "")))
    monkeypatch.setattr(skills, "TEAM_SKILLS", [])
    skills.refresh(s)
    monkeypatch.setattr(skills, "TEAM_SKILLS", ["grading"])
    (r,) = skills.refresh(s, tmp_path / "backups")
    assert r["action"] == "installed" and r["backup"] is None  # not mistaken for a hand-made skill to back up
    assert extract_skill.up_to_date("grading", s / "exercise-grader") and not (tmp_path / "backups").exists()


def test_a_skill_that_cannot_be_built_never_stops_the_server(tmp_path, monkeypatch):
    def refuse(*a, **k):
        raise SystemExit("grading needs parts above it")
    monkeypatch.setattr(extract_skill, "install", refuse)
    (r,) = skills.refresh(tmp_path / "skills")
    assert r["action"] == "error" and "parts above" in r["error"]
    monkeypatch.setattr(extract_skill, "retire", refuse)
    assert [r["action"] for r in skills.refresh(tmp_path / "skills")] == ["error", "error"]
    skills._run()  # prints, does not raise


def test_a_list_it_cannot_read_removes_nothing(tmp_path, monkeypatch):
    s = tmp_path / "skills"
    skills.refresh(s)
    monkeypatch.setattr(skills, "TEAM_SKILLS", ["grading", "no_such_part"])
    out = skills.refresh(s)
    assert out[0]["skill"] == "retire" and out[0]["action"] == "error"
    assert (s / "exercise-grader" / "SKILL.md").is_file()


def test_install_skills_off_turns_it_off(monkeypatch):
    monkeypatch.setenv("INSTALL_SKILLS", "off")
    assert not skills.enabled()
    monkeypatch.setenv("INSTALL_SKILLS", "on")
    assert skills.enabled()
    monkeypatch.delenv("INSTALL_SKILLS")
    assert skills.enabled()
