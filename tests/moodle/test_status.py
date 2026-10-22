import tempfile
from pathlib import Path

from moodle import paths
from moodle.status import status, unsafe_names


def test_unsafe_names_flags_what_onedrive_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for name in ["0001.pdf", paths.KEY, "הגשה 0.pdf", "‎⁨הגשה⁩.pdf", "a�.pdf"]:
            (folder / name).write_bytes(b"")

        assert unsafe_names(folder) == sorted(["‎⁨הגשה⁩.pdf", "a�.pdf"])


def test_status_counts_each_stage():
    with tempfile.TemporaryDirectory() as tmp:
        assignment = Path(tmp)
        (assignment / paths.TO_GRADE).mkdir()
        (assignment / paths.TO_GRADE / "0001.pdf").write_bytes(b"")
        (assignment / paths.TO_GRADE / "0002.pdf").write_bytes(b"")
        (assignment / paths.KEY).write_text("number,participant_id\n0001,1\n0002,2\n", encoding="utf-8")
        (assignment / paths.BACKUP).mkdir()
        (assignment / paths.BACKUP / f"{paths.DOWNLOAD_PREFIX} 2026-10-21 16-28.zip").write_bytes(b"")

        report = status(assignment)

        assert report["to_grade"] == 2
        assert report["key_rows"] == 2
        assert report["grades_rows"] is None
        assert report["marked"] == 0
        assert report["downloads"] == [f"{paths.DOWNLOAD_PREFIX} 2026-10-21 16-28.zip"]
        assert report["unsafe_names"] == []


if __name__ == "__main__":
    test_unsafe_names_flags_what_onedrive_refuses()
    test_status_counts_each_stage()
    print("All tests passed.")
