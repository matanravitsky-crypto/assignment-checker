"""python -m moodle | grading | copying work in the same folder as the site.

Until 2026-11-03 they looked only in ASSIGNMENT_DATA (default ~/Exercise Checking System) and never for the synced
OneDrive folder, which only the site's server found. So on a teammate's computer, where the data is only in OneDrive,
"python -m grading <id>" said the assignment does not exist, and a teammate's Claude concluded that the system works
only on the computers of the people who set it up.
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from copying import __main__ as copying_cli
from moodle import settings, shared_folder
from grading import __main__ as grading_cli
from moodle import __main__ as moodle_cli, paths

MID = "3438636"


def _assignment(system, course="Linear Algebra", name="Assignment 0"):
    a = system / course / name
    a.mkdir(parents=True)
    (a / paths.INFO).write_text(json.dumps({"id": MID}), encoding="utf-8")
    return a


@pytest.fixture
def synced(tmp_path, monkeypatch):
    """A computer whose only copy of the data is the synced course folder, and no .env."""
    monkeypatch.delenv("ASSIGNMENT_DATA", raising=False)
    monkeypatch.delenv("ASSIGNMENT_CHECKER_ROOT", raising=False)
    monkeypatch.setattr(settings, "REPO_DIR", tmp_path / "repo")  # never the real .env (Ori's names a real folder)
    monkeypatch.setattr(shared_folder, "onedrive_roots", lambda: [])
    monkeypatch.setattr(shared_folder.Path, "home", staticmethod(lambda: tmp_path))
    return _assignment(tmp_path / "BGU" / "נדב מאיר - YallaLinearit" / "Exercise Checking System")


def test_moodle_status_finds_the_synced_folder(synced, monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "argv", ["moodle", "status", MID])
    monkeypatch.setattr(moodle_cli.status, "status", lambda target: seen.append(target) or {
        "key_rows": None, "grades_rows": None, "downloads": [], "to_grade": 0, "marked": 0, "upload_files": 0,
        "unsafe_names": []})
    moodle_cli.main()
    assert seen == [synced]


def test_grading_finds_the_synced_folder(synced, monkeypatch):
    seen = []
    monkeypatch.setattr(grading_cli.grade, "grade_assignment", lambda folder, *a, **k: seen.append(folder) or
                        SimpleNamespace(summary=lambda: "", notes=[], failed={}, review=[]))
    assert grading_cli.main([MID]) == 0
    assert seen == [synced]


def test_copying_finds_the_synced_folder(synced, monkeypatch):
    seen = []
    monkeypatch.setattr(copying_cli.check, "check_assignment", lambda folder, **k: seen.append(folder) or
                        SimpleNamespace(summary=lambda: "", pairs=[], repeated=[]))
    assert copying_cli.main([MID]) == 0
    assert seen == [synced]


def test_assignment_data_set_by_hand_still_wins(synced, tmp_path, monkeypatch):
    other = _assignment(tmp_path / "elsewhere")
    monkeypatch.setenv("ASSIGNMENT_DATA", str(tmp_path / "elsewhere"))
    seen = []
    monkeypatch.setattr(copying_cli.check, "check_assignment", lambda folder, **k: seen.append(folder) or
                        SimpleNamespace(summary=lambda: "", pairs=[], repeated=[]))
    assert copying_cli.main([MID]) == 0
    assert seen == [other]


def test_the_root_in_env_file_counts_for_the_commands_too(synced, tmp_path, monkeypatch):
    """Ori keeps a local copy and names it in the repo's .env (ASSIGNMENT_CHECKER_ROOT), as the site reads it."""
    local = _assignment(tmp_path / "Local copy" / "Exercise Checking System")
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / ".env").write_text(f"ASSIGNMENT_CHECKER_ROOT={local.parent.parent}\n", encoding="utf-8")
    seen = []
    monkeypatch.setattr(copying_cli.check, "check_assignment", lambda folder, **k: seen.append(folder) or
                        SimpleNamespace(summary=lambda: "", pairs=[], repeated=[]))
    assert copying_cli.main([MID]) == 0
    assert seen == [local]
