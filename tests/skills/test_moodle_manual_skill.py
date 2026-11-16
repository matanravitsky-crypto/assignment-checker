"""The moodle-manual skill (.claude/skills/moodle-manual/SKILL.md) and the team's guide (docs/Protocol - manual pull and
return.md) must stay runnable and honest: every command they name exists, they never send Claude into Moodle, and they
say where the data folder comes from (the shared OneDrive folder) so the skill works on any teammate's computer."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / ".claude" / "skills" / "moodle-manual" / "SKILL.md"
GUIDE = REPO / "docs" / "Protocol - manual pull and return.md"
CLI = REPO / "moodle" / "__main__.py"


def commands_in_cli() -> set[str]:
    return set(re.findall(r'commands\.add_parser\("([a-z-]+)"', CLI.read_text(encoding="utf-8")))


def front_matter(text: str) -> dict:
    assert text.startswith("---\n")
    head, sep, _ = text[4:].partition("\n---")
    assert sep
    return {k.strip(): v.strip() for k, _, v in (line.partition(":") for line in head.splitlines()) if v.strip()}


@pytest.fixture(scope="module")
def skill() -> str:
    return SKILL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def test_skill_has_a_name_and_a_description_that_says_when(skill):
    fm = front_matter(skill)
    assert fm["name"] == "moodle-manual"
    assert len(fm["description"]) > 80 and "Moodle" in fm["description"]


@pytest.mark.parametrize("doc", [SKILL, GUIDE])
def test_every_command_named_exists_in_the_cli(doc):
    text = doc.read_text(encoding="utf-8")
    named = set(re.findall(r"python -m moodle ([a-z-]+)", text))
    assert named, f"{doc.name} names no command"
    assert named <= commands_in_cli(), f"{doc.name} names commands the CLI does not have: {named - commands_in_cli()}"


@pytest.mark.parametrize("doc", [SKILL, GUIDE])
def test_claude_is_never_sent_into_moodle(doc):
    text = doc.read_text(encoding="utf-8")
    for forbidden in ("claude-in-chrome", "--chrome", "javascript_tool", "python -m moodle send"):
        assert forbidden not in text, f"{doc.name} mentions {forbidden}"
    assert "לא ניגש למודל" in text or "לא נוגע במודל" in text


def test_skill_says_where_the_data_folder_comes_from(skill):
    assert "OneDrive" in skill and "ASSIGNMENT_DATA" in skill
    assert "python -m moodle list" in skill  # the first thing it runs: which folder, which assignments


def test_skill_names_the_three_steps_and_the_reports(skill):
    for word in ("ingest", "upload", "record", "Pull report.txt", "Return check.txt", "Upload steps.txt"):
        assert word in skill, word


def test_skill_is_short_enough_to_be_light(skill):
    assert len(skill) < 12_000, "the skill is meant to be light: a script, not a manual (the guide is the manual)"
