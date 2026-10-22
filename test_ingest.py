import json
import os
import tempfile
import time
from pathlib import Path

from moodle import paths
from moodle.ingest import assignment_folder, find_download, name_from_zip


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
            folder = assignment_folder("3438638", zip_path, "אלגברה לינארית")

            assert folder == Path(tmp) / "אלגברה לינארית" / "הגשה 1 - וקטורים"
            info = json.loads((folder / paths.INFO).read_text(encoding="utf-8"))
            assert info == {"id": "3438638", "course": "אלגברה לינארית", "name": "הגשה 1 - וקטורים"}
            # The next download finds it by id, with no course needed
            assert assignment_folder("3438638", zip_path, None) == folder
        finally:
            del os.environ["ASSIGNMENT_DATA"]


if __name__ == "__main__":
    test_find_download_picks_newest_zip_for_the_assignment()
    test_find_download_reports_missing_zip()
    test_name_from_zip_keeps_dashes_in_the_assignment_name()
    test_new_assignment_gets_a_named_folder_and_is_found_again()
    print("All tests passed.")
