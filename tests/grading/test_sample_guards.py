"""grading.sample never writes student pages into the repo, OneDrive or on top of another sample."""
from pathlib import Path

import pytest

from grading import sample


def test_an_out_folder_inside_the_repo_is_refused():
    repo = Path(sample.__file__).resolve().parent.parent
    with pytest.raises(sample.BadOut) as ex:
        sample.check_out(repo / "%USERPROFILE%" / ".rubric-work" / "1" / "inputs" / "submissions")
    assert "repo" in str(ex.value)


def test_an_out_folder_under_onedrive_is_refused(tmp_path):
    with pytest.raises(sample.BadOut):
        sample.check_out(tmp_path / "OneDrive - BGU" / "work")


def test_a_folder_that_already_holds_pages_is_refused(tmp_path):
    out = tmp_path / "subs"
    (out / "pages").mkdir(parents=True)
    (out / "pages" / "0001_p01.jpg").write_bytes(b"x")
    with pytest.raises(sample.BadOut) as ex:
        sample.check_out(out)
    assert "דגימה קודמת" in str(ex.value)


def test_an_empty_folder_outside_is_fine(tmp_path):
    sample.check_out(tmp_path / "fresh")
