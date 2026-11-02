"""paths.in_shared_folder tells the course's synced OneDrive folder from a local copy. Since 2026-10-29 a local copy
may pull too (Ori, the pull owner, pulls from his laptop), so this is information only, nothing refuses by it."""
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


def test_ingest_runs_from_a_local_copy_too(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASSIGNMENT_DATA", str(tmp_path / "Exercise Checking System"))
    monkeypatch.setattr(sys, "argv", ["moodle", "ingest", "3453769"])
    seen = []
    monkeypatch.setattr(cli.ingest, "ingest", lambda *a, **k: seen.append(a) or [])
    monkeypatch.setattr(cli.paths, "assignment_dir", lambda _id: tmp_path / "x")
    cli.main()
    assert seen and seen[0][0] == "3453769"
