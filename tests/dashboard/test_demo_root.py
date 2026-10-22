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


def test_demo_root_refuses_to_wipe_a_folder_that_is_not_a_demo(tmp_path):
    (tmp_path / "something else").mkdir()
    with pytest.raises(SystemExit):
        make_demo_root.build(tmp_path)
    assert (tmp_path / "something else").is_dir()
