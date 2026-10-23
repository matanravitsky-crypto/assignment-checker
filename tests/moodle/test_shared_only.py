"""Pulls happen only in the course's synced OneDrive folder, where the one key of every assignment lives (2026-10-23):
a local copy's key would not see the numbers another computer gave, and two students would get one number."""
from __future__ import annotations

import sys

import pytest

from moodle import __main__ as cli, paths


@pytest.mark.parametrize("path, shared", [
    (r"C:\Users\PC\BGU\נדב מאיר - YallaLinearit\Exercise Checking System", True),  # OneDrive's name for the shortcut
    (r"C:\Users\yossi\OneDrive - BGU\YallaLinearit\Exercise Checking System", True),
    (r"C:\Users\ori34\Exercise Checking System", False),  # a local copy
    (r"C:\Users\ori34\YallaLinearitBackup\Exercise Checking System", False),
])
def test_only_the_course_folder_counts_as_shared(path, shared):
    assert paths.in_shared_folder(path) is shared


def test_ingest_refuses_a_local_copy(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASSIGNMENT_DATA", str(tmp_path / "Exercise Checking System"))
    monkeypatch.setattr(sys, "argv", ["moodle", "ingest", "3453769"])
    monkeypatch.setattr(cli.ingest, "ingest", lambda *a, **k: pytest.fail("a local copy must not ingest"))
    with pytest.raises(SystemExit, match="not in the course's synced OneDrive folder"):
        cli.main()
