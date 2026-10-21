import os
import tempfile
import time
from pathlib import Path

from moodle.ingest import find_download


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


if __name__ == "__main__":
    test_find_download_picks_newest_zip_for_the_assignment()
    test_find_download_reports_missing_zip()
    print("All tests passed.")
