import csv
import hashlib
from datetime import datetime

import pytest

from moodle import paths
from moodle.upload_log import (BATCH_FILE, LOG_FIELDS, LOG_FILE, file_hash, last_hashes, log_conflicts,
                               read_batch, read_log, record_zip, returned_numbers, write_batch)

ZIP = "Graded - part 01.zip"
FILES = ["0001.pdf", "0002.pdf", "0002-2.pdf"]


def make_assignment(tmp_path):
    """An assignment with its marked files and a batch of one ZIP holding them (hashes of the files as they are now)."""
    a = tmp_path / "Course" / "Assignment"
    (a / paths.MARKED).mkdir(parents=True)
    (a / paths.UPLOAD).mkdir()
    entries = []
    for name in FILES:
        p = a / paths.MARKED / name
        p.write_bytes(f"marked {name}".encode())
        entries.append({"number": name[:4], "file": name, "sha256": file_hash(p)})
    write_batch(a, {"id": "batch-1", "assignment_id": "123", "created_at": "2026-10-22T10:00:00",
                    "zips": [{"name": ZIP, "files": entries}]})
    return a


def marked(a):
    return paths.files_by_number(a / paths.MARKED, "*.pdf")


def test_files_by_number_groups_and_orders_the_files(tmp_path):
    for name in ["0002-2.pdf", "0001.pdf", "0002.pdf", "0010.pdf", "notes.pdf", "0003-x.pdf", "readme.txt"]:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "0004.pdf").mkdir()  # a folder named like a file is skipped
    found = paths.files_by_number(tmp_path, "*.pdf")
    assert {n: [p.name for p in files] for n, files in found.items()} == {
        "0001": ["0001.pdf"], "0002": ["0002.pdf", "0002-2.pdf"], "0010": ["0010.pdf"]}
    assert list(found) == ["0001", "0002", "0010"]
    assert paths.files_by_number(tmp_path / "missing") == {}


def test_files_by_number_orders_extra_files_by_their_number_not_alphabetically(tmp_path):
    for name in ["0001.pdf", "0001-10.pdf", "0001-2.pdf"]:
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in paths.files_by_number(tmp_path)["0001"]] == ["0001.pdf", "0001-2.pdf", "0001-10.pdf"]


def test_file_hash_is_sha256_hex(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"x" * 3_000_000)  # more than one read chunk
    assert file_hash(p) == hashlib.sha256(b"x" * 3_000_000).hexdigest()


def test_batch_round_trip_and_missing_batch(tmp_path):
    a = make_assignment(tmp_path)
    batch = read_batch(a)
    assert batch["zips"][0]["name"] == ZIP
    assert [f["file"] for f in batch["zips"][0]["files"]] == FILES
    assert (a / paths.UPLOAD / BATCH_FILE).read_bytes().startswith(b"\xef\xbb\xbf")  # utf-8-sig like the CSVs
    assert read_batch(tmp_path / "no assignment here") is None


def test_record_zip_appends_rows_from_the_batch(tmp_path):
    a = make_assignment(tmp_path)
    assert record_zip(a, "Graded - part 01.zip", by="me (PC)") == 3
    rows = read_log(a)
    assert [r["file"] for r in rows] == ["0001.pdf", "0002.pdf", "0002-2.pdf"]
    assert set(rows[0]) == set(LOG_FIELDS)


def test_record_zip_row_content(tmp_path):
    a = make_assignment(tmp_path)
    record_zip(a, ZIP, by="me (PC)", now=datetime(2026, 10, 22, 11, 30, 5))
    row = read_log(a)[2]
    assert row == {"number": "0002", "file": "0002-2.pdf", "sha256": file_hash(a / paths.MARKED / "0002-2.pdf"),
                   "zip": ZIP, "uploaded_at": "2026-10-22T11:30:05", "by": "me (PC)"}


def test_log_has_one_header_and_one_bom_however_many_times_it_is_appended(tmp_path):
    a = make_assignment(tmp_path)
    record_zip(a, ZIP, by="me (PC)")
    record_zip(a, ZIP, by="me (PC)")
    raw = (a / paths.UPLOAD / LOG_FILE).read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and raw.count(b"\xef\xbb\xbf") == 1
    with open(a / paths.UPLOAD / LOG_FILE, encoding="utf-8-sig", newline="") as f:
        lines = list(csv.reader(f))
    assert lines[0] == LOG_FIELDS
    assert len(lines) == 1 + 6


def test_record_unknown_zip_is_refused(tmp_path):
    a = make_assignment(tmp_path)
    with pytest.raises(ValueError):
        record_zip(a, "Graded - part 09.zip", by="me (PC)")
    assert read_log(a) == []


def test_record_without_a_batch_is_refused(tmp_path):
    a = tmp_path / "Course" / "Assignment"
    (a / paths.UPLOAD).mkdir(parents=True)
    with pytest.raises(ValueError):
        record_zip(a, ZIP, by="me (PC)")


def test_read_log_and_last_hashes_are_empty_without_a_log(tmp_path):
    a = make_assignment(tmp_path)
    assert read_log(a) == []
    assert last_hashes(a) == {}


def test_last_hashes_takes_the_latest_upload_of_each_file(tmp_path):
    a = make_assignment(tmp_path)
    record_zip(a, ZIP, by="me (PC)")
    first = last_hashes(a)
    assert set(first) == set(FILES)
    batch = read_batch(a)
    batch["zips"][0]["files"][0]["sha256"] = "new-hash"  # 0001.pdf was fixed and uploaded again
    write_batch(a, batch)
    record_zip(a, ZIP, by="me (PC)")
    second = last_hashes(a)
    assert second["0001.pdf"] == "new-hash"
    assert second["0002.pdf"] == first["0002.pdf"]


def test_returned_only_when_every_file_matches_its_last_upload(tmp_path):
    a = make_assignment(tmp_path)   # writes the marked files and hashes them into the batch
    record_zip(a, "Graded - part 01.zip", by="me (PC)")
    marked = paths.files_by_number(a / paths.MARKED, "*.pdf")
    assert returned_numbers(a, marked) == {"0001", "0002"}
    (a / paths.MARKED / "0002-2.pdf").write_bytes(b"changed")
    assert returned_numbers(a, paths.files_by_number(a / paths.MARKED, "*.pdf")) == {"0001"}


def test_nothing_is_returned_before_anything_was_recorded(tmp_path):
    a = make_assignment(tmp_path)
    assert returned_numbers(a, marked(a)) == set()


def test_a_number_with_a_file_that_was_never_uploaded_is_not_returned(tmp_path):
    a = make_assignment(tmp_path)
    record_zip(a, ZIP, by="me (PC)")
    (a / paths.MARKED / "0001-2.pdf").write_bytes(b"added after the upload")
    (a / paths.MARKED / "0003.pdf").write_bytes(b"graded later")
    assert returned_numbers(a, marked(a)) == {"0002"}


def test_log_conflict_copies_are_found(tmp_path):
    a = make_assignment(tmp_path)
    (a / paths.UPLOAD / "Upload log-DESKTOP-1.csv").write_text("x", encoding="utf-8")
    assert log_conflicts(a) == ["Upload log-DESKTOP-1.csv"]


def test_log_conflicts_ignore_the_log_itself_and_are_sorted(tmp_path):
    a = make_assignment(tmp_path)
    record_zip(a, ZIP, by="me (PC)")
    for name in ["Upload log-PC2.csv", "Upload log-DESKTOP.csv"]:
        (a / paths.UPLOAD / name).write_text("x", encoding="utf-8")
    assert log_conflicts(a) == ["Upload log-DESKTOP.csv", "Upload log-PC2.csv"]
    assert log_conflicts(tmp_path / "no assignment here") == []
