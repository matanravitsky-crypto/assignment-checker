"""The team's skills on every computer that runs the system (dashboard/skills.py): built at the server's start from
this computer's code, never stopping the server, and off with INSTALL_SKILLS=off."""
from __future__ import annotations

import pytest

from dashboard import skills
from tools import extract_skill


@pytest.fixture(autouse=True)
def no_git(monkeypatch):
    monkeypatch.setattr(extract_skill, "_commit", lambda: "abc1234")  # the dashboard tests start no real process


def test_the_server_start_builds_the_teams_skills(tmp_path):
    out = skills.refresh(tmp_path / "skills", tmp_path / "backups")
    assert [(r["skill"], r["action"]) for r in out] == [("exercise-grader", "installed")]
    assert extract_skill.up_to_date("grading", tmp_path / "skills" / "exercise-grader")
    assert [r["action"] for r in skills.refresh(tmp_path / "skills", tmp_path / "backups")] == ["up_to_date"]


def test_a_skill_that_cannot_be_built_never_stops_the_server(tmp_path, monkeypatch):
    def refuse(*a, **k):
        raise SystemExit("grading needs parts above it")
    monkeypatch.setattr(extract_skill, "install", refuse)
    (r,) = skills.refresh(tmp_path / "skills")
    assert r["action"] == "error" and "parts above" in r["error"]
    skills._run()  # prints, does not raise


def test_install_skills_off_turns_it_off(monkeypatch):
    monkeypatch.setenv("INSTALL_SKILLS", "off")
    assert not skills.enabled()
    monkeypatch.setenv("INSTALL_SKILLS", "on")
    assert skills.enabled()
    monkeypatch.delenv("INSTALL_SKILLS")
    assert skills.enabled()
