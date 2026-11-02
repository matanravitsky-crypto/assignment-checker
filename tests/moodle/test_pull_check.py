"""The check at the end of every pull (moodle/pull_check.py): it looks at the disk again, and a pull that would lose,
miss, double or change something it should not is undone. Fake students only (participant ids, no names)."""
import csv
import os

import pytest

from moodle import anonymize, paths, pull_check


def _folder(original, pid, files):
    d = original / f"s_{pid}_assignsubmission_file"
    d.mkdir(parents=True)
    for i, data in enumerate(files):
        (d / f"scan {i + 1}.pdf").write_bytes(data)


def _key(assignment):
    with open(assignment / paths.KEY, encoding="utf-8-sig") as f:
        return {r["participant_id"]: r["number"] for r in csv.DictReader(f)}


def _state(assignment):
    anon = assignment / paths.TO_GRADE
    return _key(assignment), {p.name: p.read_bytes() for p in anon.iterdir()}


@pytest.fixture
def pulled(tmp_path):
    """An assignment pulled once: students 11, 22, 33 (22 with two files)."""
    a, first = tmp_path / "a", tmp_path / "first"
    a.mkdir()
    _folder(first, "11", [b"%PDF 11"])
    _folder(first, "22", [b"%PDF 22", b"%PDF 22b"])
    _folder(first, "33", [b"%PDF 33"])
    anonymize.prepare(first, a)
    return a


def test_a_good_pull_is_counted(pulled, tmp_path):
    later = tmp_path / "later"
    _folder(later, "11", [b"%PDF 11 again"])  # resubmitted
    _folder(later, "44", [b"%PDF 44"])        # new; 22 and 33 are not in this download
    check = {}
    anonymize.prepare(later, pulled, check=check)
    assert check == {"students_before": 3, "students_after": 4, "new_students": 1, "in_this_download": 2,
                     "files_unchanged": 3, "files_written": 2, "files_moved_to_earlier": 1, "files_in_folder": 5}
    assert (pulled / paths.TO_GRADE / "0002-2.pdf").read_bytes() == b"%PDF 22b"


def test_a_copy_that_writes_other_bytes_undoes_the_pull(pulled, tmp_path, monkeypatch):
    before = _state(pulled)
    later = tmp_path / "later"
    _folder(later, "11", [b"%PDF 11 again"])
    _folder(later, "44", [b"%PDF 44"])
    real = anonymize._copy

    def wrong(source, target):
        real(source, target)
        target.write_bytes(b"not what came")  # a disk or a sync program that changed it on the way
    monkeypatch.setattr(anonymize, "_copy", wrong)
    with pytest.raises(pull_check.PullCheckFailed, match="not what the download brought"):
        anonymize.prepare(later, pulled)
    assert _state(pulled) == before  # every file back, the key as it was


def test_a_file_of_a_student_not_in_the_download_that_changes_undoes_the_pull(pulled, tmp_path, monkeypatch):
    before = _state(pulled)
    later = tmp_path / "later"
    _folder(later, "44", [b"%PDF 44"])
    real = anonymize._copy

    def and_another(source, target):
        real(source, target)
        other = pulled / paths.TO_GRADE / "0003.pdf"
        other.write_bytes(b"%PDF 33 changed")
        os.utime(other, ns=(1, 1))
    monkeypatch.setattr(anonymize, "_copy", and_another)
    with pytest.raises(pull_check.PullCheckFailed, match="0003.pdf changed or vanished"):
        anonymize.prepare(later, pulled)
    assert _key(pulled) == before[0]


def test_a_file_that_vanishes_during_the_pull_undoes_it(pulled, tmp_path, monkeypatch):
    later = tmp_path / "later"
    _folder(later, "44", [b"%PDF 44"])
    real = anonymize._copy

    def and_lose_one(source, target):
        real(source, target)
        (pulled / paths.TO_GRADE / "0001.pdf").unlink()
    monkeypatch.setattr(anonymize, "_copy", and_lose_one)
    with pytest.raises(pull_check.PullCheckFailed, match="0001.pdf"):
        anonymize.prepare(later, pulled)
    assert "44" not in _key(pulled)


def test_a_student_in_two_folders_is_refused_before_anything(pulled, tmp_path):
    before = _state(pulled)
    later = tmp_path / "later"
    _folder(later, "44", [b"%PDF 44"])
    (later / "x_44_assignsubmission_file").mkdir()
    (later / "x_44_assignsubmission_file" / "a.pdf").write_bytes(b"%PDF 44 other")
    with pytest.raises(pull_check.PullCheckFailed, match="two folders"):
        anonymize.prepare(later, pulled)
    assert _state(pulled) == before


def test_moodle_side_counts_what_came_and_what_did_not():
    # the table's ids (user ids) are not the ZIP's (participant ids): only the counts compare
    listing = {"users": 5, "files": [{"ids": ["11", "22"]}, {"ids": ["33", "11"]}], "with_date": ["901", "902", "903", "904"]}
    counts, problems = pull_check.moodle_side(listing, {"11", "22", "33"})
    assert problems == []
    assert counts == {"moodle_students": 5, "came_from_moodle": 3, "with_date_no_file": 1}
    _, problems = pull_check.moodle_side(listing, {"11", "22"})
    assert problems == ["1 students came from Moodle but their folder was not extracted"]
    _, problems = pull_check.moodle_side(listing, {"11", "22", "33", "99"})
    assert problems == ["1 student folders were extracted that Moodle did not list"]
    assert pull_check.moodle_side({}, {"11"})[1] == []  # an older list without ids: nothing to compare
    assert pull_check.moodle_side({**listing, "with_date": ["901"]}, {"11", "22", "33"})[0]["with_date_no_file"] == 0


def test_the_check_is_written_with_numbers_only(pulled):
    pull_check.write(pulled, {"ok": True, "students_after": 3})
    got = pull_check.read(pulled)
    assert got["ok"] is True and got["students_after"] == 3 and "checked_at" in got
