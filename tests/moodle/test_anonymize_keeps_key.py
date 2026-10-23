"""The key never loses a student (on 2026-10-23 a download with two parts without folders dropped 74 of them)."""
import csv

import pytest

from moodle import anonymize, paths


def _folder(original, name, pid, data=b"%PDF"):
    d = original / f"{name}_{pid}_assignsubmission_file"
    d.mkdir(parents=True)
    (d / "hw.pdf").write_bytes(data)


def _key(assignment):
    with open(assignment / paths.KEY, encoding="utf-8-sig") as f:
        return {r["participant_id"]: r["number"] for r in csv.DictReader(f)}


def test_a_student_missing_from_a_later_download_keeps_number_and_file(tmp_path):
    assignment, first, later = tmp_path / "a", tmp_path / "first", tmp_path / "later"
    assignment.mkdir()
    for pid in ("11", "22", "33"):
        _folder(first, "s", pid, b"%PDF " + pid.encode())
    anonymize.prepare(first, assignment)
    assert _key(assignment) == {"11": "0001", "22": "0002", "33": "0003"}

    _folder(later, "s", "11")
    _folder(later, "s", "44")  # new since then; 22 and 33 are not in this download
    rows = anonymize.prepare(later, assignment)
    assert _key(assignment) == {"11": "0001", "22": "0002", "33": "0003", "44": "0004"}
    assert len(rows) == 4
    files = sorted(p.name for p in (assignment / paths.TO_GRADE).iterdir())
    assert files == ["0001.pdf", "0002.pdf", "0003.pdf", "0004.pdf"]
    assert (assignment / paths.TO_GRADE / "0002.pdf").read_bytes() == b"%PDF 22"  # the file kept, as it was
    assert not (assignment / f"{paths.TO_GRADE} (previous)").exists()


def test_loose_files_are_refused_before_anything_changes(tmp_path):
    assignment, first, flat = tmp_path / "a", tmp_path / "first", tmp_path / "flat"
    assignment.mkdir()
    _folder(first, "s", "11")
    anonymize.prepare(first, assignment)
    flat.mkdir()
    (flat / "s_22_assignsubmission_file_hw.pdf").write_bytes(b"%PDF")
    with pytest.raises(ValueError, match="not in a folder per student"):
        anonymize.prepare(flat, assignment)
    assert _key(assignment) == {"11": "0001"}
    assert [p.name for p in (assignment / paths.TO_GRADE).iterdir()] == ["0001.pdf"]


def _files(folder):
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_nothing_is_deleted_or_overwritten(tmp_path):
    """A resubmission replaces the file only after the old one moved to "Earlier versions"; a file that is the same
    stays as it was (OneDrive syncs nothing new), and a second file that is gone moves aside too."""
    assignment, first, later = tmp_path / "a", tmp_path / "first", tmp_path / "later"
    assignment.mkdir()
    _folder(first, "s", "11", b"%PDF old 11")
    _folder(first, "s", "22", b"%PDF 22")
    (first / "s_22_assignsubmission_file" / "page2.pdf").write_bytes(b"%PDF 22 page 2")
    anonymize.prepare(first, assignment)
    anon = assignment / paths.TO_GRADE
    assert _files(anon) == ["0001.pdf", "0002-2.pdf", "0002.pdf"]
    kept_time = (anon / "0002.pdf").stat().st_mtime_ns

    _folder(later, "s", "11", b"%PDF new 11")  # resubmitted: the same size, maybe the same second
    _folder(later, "s", "22", b"%PDF 22")      # the same file, without its second page
    anonymize.prepare(later, assignment)

    assert (anon / "0001.pdf").read_bytes() == b"%PDF new 11"
    assert (anon / "0002.pdf").stat().st_mtime_ns == kept_time  # not copied again
    assert _files(anon) == ["0001.pdf", "0002.pdf"]
    [earlier] = (assignment / paths.EARLIER).iterdir()
    assert (earlier / "0001.pdf").read_bytes() == b"%PDF old 11"
    assert (earlier / "0002-2.pdf").read_bytes() == b"%PDF 22 page 2"
    assert _key(assignment) == {"11": "0001", "22": "0002"}


def test_the_old_key_is_kept_before_every_change(tmp_path):
    assignment, first, later = tmp_path / "a", tmp_path / "first", tmp_path / "later"
    assignment.mkdir()
    _folder(first, "s", "11")
    anonymize.prepare(first, assignment)
    anonymize.prepare(first, assignment)  # nothing changed: no history
    assert _files(assignment / paths.KEY_HISTORY) == []
    _folder(later, "s", "22")
    anonymize.prepare(later, assignment)
    [old] = (assignment / paths.KEY_HISTORY).iterdir()
    with open(old, encoding="utf-8-sig") as f:
        assert {r["participant_id"]: r["number"] for r in csv.DictReader(f)} == {"11": "0001"}
    assert _key(assignment) == {"11": "0001", "22": "0002"}
    assert anonymize.key_conflicts(assignment) == []  # the history is no OneDrive conflict copy
    assert not list(assignment.glob("*.writing"))


def test_a_broken_key_is_refused_before_anything_changes(tmp_path):
    assignment, first, later = tmp_path / "a", tmp_path / "first", tmp_path / "later"
    assignment.mkdir()
    _folder(first, "s", "11")
    _folder(first, "s", "22")
    anonymize.prepare(first, assignment)
    key = assignment / paths.KEY
    key.write_text(key.read_text(encoding="utf-8-sig").replace(",22,", ",11,"), encoding="utf-8-sig")  # 11 twice
    before = key.read_bytes()
    _folder(later, "s", "33")
    with pytest.raises(anonymize.KeyBroken):
        anonymize.prepare(later, assignment)
    assert key.read_bytes() == before
    assert _files(assignment / paths.TO_GRADE) == ["0001.pdf", "0002.pdf"]


def test_check_key_catches_a_moved_or_lost_student():
    old = [{"participant_id": "11", "number": "0001"}, {"participant_id": "22", "number": "0002"}]
    anonymize.check_new_key(old, old + [{"participant_id": "33", "number": "0003"}])
    with pytest.raises(anonymize.KeyBroken, match="0002"):
        anonymize.check_new_key(old, old[:1])
    with pytest.raises(anonymize.KeyBroken):
        anonymize.check_new_key(old, old + [{"participant_id": "33", "number": "0002"}])


def test_a_key_that_changes_during_the_pull_puts_every_file_back(tmp_path, monkeypatch):
    """Another computer pulled the same assignment and OneDrive brought its key in the middle: this pull undoes
    itself, so no number points at another student's file."""
    assignment, first, later = tmp_path / "a", tmp_path / "first", tmp_path / "later"
    assignment.mkdir()
    _folder(first, "s", "11", b"%PDF old 11")
    anonymize.prepare(first, assignment)
    _folder(later, "s", "11", b"%PDF new 11")
    _folder(later, "s", "22", b"%PDF 22")
    key = assignment / paths.KEY
    real_copy = anonymize.shutil.copy2

    def copy_while_the_key_changes(src, dst):
        real_copy(src, dst)
        if not key.read_text(encoding="utf-8-sig").endswith("other\n"):
            key.write_text(key.read_text(encoding="utf-8-sig") + "other\n", encoding="utf-8-sig")
    monkeypatch.setattr(anonymize.shutil, "copy2", copy_while_the_key_changes)
    with pytest.raises(anonymize.KeyBroken, match="changed during the pull"):
        anonymize.prepare(later, assignment)
    assert _files(assignment / paths.TO_GRADE) == ["0001.pdf"]
    assert (assignment / paths.TO_GRADE / "0001.pdf").read_bytes() == b"%PDF old 11"
    assert key.read_text(encoding="utf-8-sig").endswith("other\n")  # the other computer's key, untouched


def test_onedrive_conflict_copies_of_submissions_stop_the_pull(tmp_path):
    assignment, first = tmp_path / "a", tmp_path / "first"
    assignment.mkdir()
    _folder(first, "s", "11")
    anonymize.prepare(first, assignment)
    (assignment / paths.TO_GRADE / "0001-2.pdf").write_bytes(b"%PDF")  # a second file: no conflict
    assert anonymize.submission_conflicts(assignment) == []
    (assignment / paths.TO_GRADE / "0001-DESKTOP-AB12.pdf").write_bytes(b"%PDF")
    assert anonymize.submission_conflicts(assignment) == ["0001-DESKTOP-AB12.pdf"]
    before = (assignment / paths.KEY).read_bytes()
    with pytest.raises(anonymize.KeyBroken, match="conflict copies"):
        anonymize.prepare(first, assignment)
    assert (assignment / paths.KEY).read_bytes() == before
