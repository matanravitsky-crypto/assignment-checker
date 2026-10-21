import tempfile
from pathlib import Path

from moodle.status import status, unsafe_names


def test_unsafe_names_flags_what_onedrive_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for name in ["0001.pdf", "mapping.csv", "הגשה 0.pdf", "‎⁨הגשה⁩.pdf", "a�.pdf"]:
            (folder / name).write_bytes(b"")

        assert unsafe_names(folder) == sorted(["‎⁨הגשה⁩.pdf", "a�.pdf"])


def test_status_counts_each_stage():
    with tempfile.TemporaryDirectory() as tmp:
        assignment = Path(tmp)
        (assignment / "anon").mkdir()
        (assignment / "anon" / "0001.pdf").write_bytes(b"")
        (assignment / "anon" / "0002.pdf").write_bytes(b"")
        (assignment / "mapping.csv").write_text("number,participant_id\n0001,1\n0002,2\n", encoding="utf-8")

        report = status(assignment)

        assert report["anon_files"] == 2
        assert report["mapping_rows"] == 2
        assert report["results_rows"] is None
        assert report["marked_files"] == 0
        assert report["unsafe_names"] == []


if __name__ == "__main__":
    test_unsafe_names_flags_what_onedrive_refuses()
    test_status_counts_each_stage()
    print("All tests passed.")
