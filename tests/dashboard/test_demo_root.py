"""The fictional demo folder (tests/make_demo_root.py) works with the dashboard's upload flow."""
from __future__ import annotations

import pytest

from dashboard import actions
from tests import make_demo_root


def test_demo_root_prepares_two_zips_and_is_rebuilt_in_place(tmp_path):
    root = tmp_path / "demo-root"
    make_demo_root.build(root, pad_mb=0.1)
    rep = actions.prepare_send(root, make_demo_root.COURSE, make_demo_root.ASSIGNMENT)
    assert rep["assignment_id"] == make_demo_root.MOODLE_ID
    assert (rep["students"], rep["files"]) == (2, 2)
    assert rep["not_approved"] == ["0002"] and rep["too_big"] == [] and rep["resubmitted"] == []
    make_demo_root.build(root, pad_mb=0.1)  # an earlier demo there is replaced


def test_demo_root_refuses_to_wipe_a_folder_without_its_marker(tmp_path):
    (tmp_path / "something else").mkdir()
    with pytest.raises(SystemExit):
        make_demo_root.build(tmp_path)
    assert (tmp_path / "something else").is_dir()
    # even a folder that looks like a demo (the course folder is there) is left alone without the marker it wrote
    (tmp_path / make_demo_root.COURSE).mkdir()
    (tmp_path / "something else").rmdir()
    with pytest.raises(SystemExit):
        make_demo_root.build(tmp_path)
    assert (tmp_path / make_demo_root.COURSE).is_dir()


def test_demo_root_builds_into_an_empty_or_new_folder_and_writes_its_marker(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    make_demo_root.build(empty, pad_mb=0.01)
    assert (empty / make_demo_root.MARKER).is_file()
    make_demo_root.build(tmp_path / "new" / "deeper", pad_mb=0.01)
    assert (tmp_path / "new" / "deeper" / make_demo_root.MARKER).is_file()
