"""For every test: never the real Claude Code of this computer.

grading finds Claude Code through the core (moodle/claude_code.py), and a computer of the team has it installed and signed
in, so a test that grades without its own fake Claude would run the real one. Here it is "not installed" for everyone;
a test that needs it says so with its own monkeypatch (tests/grading/test_claude_cli.py). The site's readiness check
goes through moodle/claude_driver.py, which the dashboard's tests fake on their own (tests/dashboard/conftest.py).
"""
import pytest

from moodle import claude_code


@pytest.fixture(autouse=True)
def no_claude_code_of_this_computer(monkeypatch):
    monkeypatch.setattr(claude_code, "find_claude", lambda: None)
