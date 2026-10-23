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
