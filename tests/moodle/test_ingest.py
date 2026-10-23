import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from moodle import paths
from moodle.ingest import assignment_folder, find_download, name_from_zip, wait_for_download


def test_find_download_picks_newest_zip_for_the_assignment():
    with tempfile.TemporaryDirectory() as tmp:
        downloads = Path(tmp)
        old = downloads / "קורס-הגשה 0-3438636.zip"
        new = downloads / "קורס-הגשה 0-3438636 (1).zip"
        other = downloads / "קורס-הגשה 1-3453769.zip"
        partial = downloads / "לא מאושר 877766.crdownload"
        for path in (old, new, other, partial):
            path.write_bytes(b"")
        # "(1)" copies do not end in the id, so they are not picked by mistake
        os.utime(old, (time.time() - 60, time.time() - 60))

        assert find_download("3438636", downloads) == old


def test_find_download_reports_missing_zip():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            find_download("3438636", Path(tmp))
        except FileNotFoundError:
            return
    raise AssertionError("expected FileNotFoundError")


def test_name_from_zip_keeps_dashes_in_the_assignment_name():
    zip_path = Path("214193210120271-הגשה 0 - קבוצות ומרוכבים-3438636.zip")
    assert name_from_zip(zip_path, "3438636") == "הגשה 0 - קבוצות ומרוכבים"


def test_new_assignment_gets_a_named_folder_and_is_found_again():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ASSIGNMENT_DATA"] = tmp
        try:
            zip_path = Path("214193210120271-הגשה 1 - וקטורים-3438638.zip")
            folder = assignment_folder("3438638", zip_path, "Linear Algebra", "Assignment 1 - Vectors")

            assert folder == Path(tmp) / "Linear Algebra" / "Assignment 1 - Vectors"
            info = json.loads((folder / paths.INFO).read_text(encoding="utf-8"))
            assert info == {"id": "3438638", "course": "Linear Algebra", "name": "Assignment 1 - Vectors",
                            "title": "הגשה 1 - וקטורים"}
            # The next download finds it by id, with no names needed
            assert assignment_folder("3438638", zip_path, None, None) == folder
        finally:
            del os.environ["ASSIGNMENT_DATA"]


def test_new_assignment_needs_english_names():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ASSIGNMENT_DATA"] = tmp
        try:
            assignment_folder("3438638", Path("x-הגשה 1-3438638.zip"), "Linear Algebra", None)
        except ValueError:
            return
        finally:
            del os.environ["ASSIGNMENT_DATA"]
    raise AssertionError("expected ValueError")



class Clock:
    """A fake clock for wait_for_download: every sleep moves time forward and may run a step (Chrome at work)."""

    def __init__(self, steps=()):
        self.now, self.steps = 0.0, list(steps)

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.steps:
            self.steps.pop(0)()


def test_wait_for_download_returns_the_new_zip_once_it_is_whole(tmp_path):
    since = time.time()
    old = tmp_path / "קורס-הגשה 0-3438636.zip"
    old.write_bytes(b"an old download")
    os.utime(old, (since - 600, since - 600))  # was there before the download was asked for: not it
    new = tmp_path / "קורס-הגשה 0-3438636.zip"
    partial = tmp_path / "Unconfirmed 1.crdownload"
    steps = [lambda: partial.write_bytes(b"PK"),
             # Chrome renames it when done (the old one was moved away by an earlier ingest)
             lambda: (partial.unlink(), old.unlink(), new.write_bytes(b"PK whole"))]
    clock = Clock(steps)
    got = wait_for_download("3438636", since, tmp_path, poll_s=1, clock=clock, sleep=clock.sleep)
    assert got == new and got.read_bytes() == b"PK whole"


def test_wait_for_download_gives_up_when_nothing_starts(tmp_path):
    clock = Clock()
    with pytest.raises(TimeoutError, match="did not start"):
        wait_for_download("3438636", time.time(), tmp_path, start_s=10, poll_s=1, clock=clock, sleep=clock.sleep)
    assert clock.now <= 12


def test_wait_for_download_keeps_waiting_while_chrome_downloads(tmp_path):
    (tmp_path / "x-3438636.zip.crdownload").write_bytes(b"PK")
    clock = Clock()
    with pytest.raises(TimeoutError, match="did not finish"):
        wait_for_download("3438636", time.time(), tmp_path, start_s=10, total_s=100, poll_s=5, clock=clock, sleep=clock.sleep)
    assert clock.now > 100


if __name__ == "__main__":
    test_find_download_picks_newest_zip_for_the_assignment()
    test_find_download_reports_missing_zip()
    test_name_from_zip_keeps_dashes_in_the_assignment_name()
    test_new_assignment_gets_a_named_folder_and_is_found_again()
    test_new_assignment_needs_english_names()
    print("All tests passed.")


def test_ingest_refuses_on_another_computer_than_the_named_one(tmp_path, monkeypatch):
    from moodle import ingest as ingest_module, lock
    monkeypatch.setenv("ASSIGNMENT_DATA", str(tmp_path))
    (tmp_path / paths.PULL_FROM).write_text("ori34 (OriLaptop)", encoding="utf-8")
    monkeypatch.setattr(lock, "me", lambda: "noa (OTHER-PC)")
    zip_path = tmp_path / "x-3438636.zip"
    zip_path.write_bytes(b"PK")
    with pytest.raises(lock.NotThePuller):
        ingest_module.ingest("3438636", zip_path)
    assert zip_path.exists()  # לא נגעו בכלום
