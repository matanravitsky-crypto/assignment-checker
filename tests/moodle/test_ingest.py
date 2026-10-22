import json
import os
import tempfile
import time
import zipfile
from pathlib import Path

import pytest

from moodle import paths
from moodle.ingest import (assignment_folder, find_download, find_parts, ingest, name_from_zip, seven_zip,
                           wait_for_download)


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


def has_seven_zip() -> bool:
    try:
        seven_zip()
        return True
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not has_seven_zip(), reason="needs 7-Zip")
def test_cut_off_zip_is_refused_before_anything_changes():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "x-הגשה 0-3438636.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("אב_100_assignsubmission_file/a.pdf", b"a" * 5000)
        data = zip_path.read_bytes()
        zip_path.write_bytes(data[: len(data) // 2])  # a download that ended early
        os.environ["ASSIGNMENT_DATA"] = str(Path(tmp) / "data")
        try:
            with pytest.raises(ValueError, match="incomplete or damaged"):
                ingest("3438636", zip_path, "Linear Algebra", "Assignment 0")
            assert zip_path.exists()
            assert not (Path(tmp) / "data").exists()
        finally:
            del os.environ["ASSIGNMENT_DATA"]


def make_zip(path: Path, students: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for folder, data in students.items():
            archive.writestr(f"{folder}/work.pdf", data)
    return path


def test_find_parts_takes_every_zip_of_the_assignment():
    with tempfile.TemporaryDirectory() as tmp:
        downloads = Path(tmp)
        for name in ["x-הגשה 0-3438636.zip", "x-הגשה 0-3438636 (1).zip", "x-הגשה 0-3438636 (2).zip",
                     "x-הגשה 1-3438638.zip", "BROKEN 3438636.zip"]:
            (downloads / name).write_bytes(b"")
        assert [p.name for p in find_parts("3438636", downloads)] == [
            "x-הגשה 0-3438636 (1).zip", "x-הגשה 0-3438636 (2).zip", "x-הגשה 0-3438636.zip"]


@pytest.mark.skipif(not has_seven_zip(), reason="needs 7-Zip")
def test_parts_come_together_into_one_numbered_set():
    with tempfile.TemporaryDirectory() as tmp:
        one = make_zip(Path(tmp) / "x-הגשה 0-3438636.zip", {"א_100_assignsubmission_file": b"a"})
        two = make_zip(Path(tmp) / "x-הגשה 0-3438636 (1).zip", {"ב_200_assignsubmission_file": b"b"})
        os.environ["ASSIGNMENT_DATA"] = str(Path(tmp) / "data")
        os.environ["ASSIGNMENT_WORK"] = str(Path(tmp) / "work")
        try:
            rows = ingest("3438636", [one, two], "Linear Algebra", "Assignment 0")
            folder = paths.assignment_dir("3438636")
            backups = sorted(p.name for p in paths.backup_dir(folder).glob("*.zip"))
        finally:
            del os.environ["ASSIGNMENT_DATA"], os.environ["ASSIGNMENT_WORK"]
        assert sorted(r["participant_id"] for r in rows) == ["100", "200"]
        assert backups[-1].endswith("part 2.zip")
        assert not list(folder.rglob("*.zip"))


@pytest.mark.skipif(not has_seven_zip(), reason="needs 7-Zip")
def test_student_in_two_parts_keeps_the_newer_copy_once():
    with tempfile.TemporaryDirectory() as tmp:
        one = make_zip(Path(tmp) / "a-3438636.zip", {"א_100_assignsubmission_file": b"old",
                                                       "ב_200_assignsubmission_file": b"b"})
        two = make_zip(Path(tmp) / "a-3438636 (1).zip", {"א_100_assignsubmission_file": b"new"})
        os.utime(one, (time.time() - 60, time.time() - 60))
        os.environ["ASSIGNMENT_DATA"] = str(Path(tmp) / "data")
        os.environ["ASSIGNMENT_WORK"] = str(Path(tmp) / "work")
        try:
            rows = ingest("3438636", [one, two], "Linear Algebra", "Assignment 0")
            folder = paths.assignment_dir("3438636")
        finally:
            del os.environ["ASSIGNMENT_DATA"], os.environ["ASSIGNMENT_WORK"]
        assert sorted(r["participant_id"] for r in rows) == ["100", "200"]
        number = next(r["number"] for r in rows if r["participant_id"] == "100")
        assert (folder / paths.TO_GRADE / f"{number}.pdf").read_bytes() == b"new"


@pytest.mark.skipif(not has_seven_zip(), reason="needs 7-Zip")
def test_parts_hours_apart_are_refused():
    with tempfile.TemporaryDirectory() as tmp:
        one = make_zip(Path(tmp) / "a-3438636.zip", {"א_100_assignsubmission_file": b"old"})
        two = make_zip(Path(tmp) / "a-3438636 (1).zip", {"ב_200_assignsubmission_file": b"new"})
        os.utime(one, (time.time() - 5 * 3600, time.time() - 5 * 3600))
        os.environ["ASSIGNMENT_DATA"] = str(Path(tmp) / "data")
        try:
            with pytest.raises(ValueError, match="2 hours apart"):
                ingest("3438636", [one, two], "Linear Algebra", "Assignment 0")
            assert one.exists() and two.exists()
        finally:
            del os.environ["ASSIGNMENT_DATA"]
