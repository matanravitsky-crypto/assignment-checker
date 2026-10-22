import csv
import tempfile
from pathlib import Path

from moodle import paths
from moodle.anonymize import parse_folder, prepare, read_mapping


def make_submission(original: Path, folder: str, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = original / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_parse_folder():
    assert parse_folder("ישראל ישראלי_13464355_assignsubmission_file") == "13464355"


def test_parse_folder_rejects_other_names():
    try:
        parse_folder("random folder")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_prepare_numbers_by_participant_id():
    with tempfile.TemporaryDirectory() as tmp:
        assignment = Path(tmp) / "assignment"
        assignment.mkdir()
        original = Path(tmp) / "original"
        # Odd characters phones put in Hebrew file names must not matter
        make_submission(original, "בת_200_assignsubmission_file", {"‎⁨הגשה⁩.PDF": "b"})
        make_submission(original, "אב_100_assignsubmission_file", {"a.pdf": "a", "b.pdf": "a2"})

        rows = prepare(original, assignment)

        assert [row["anon_file"] for row in rows] == ["0001.pdf", "0001-2.pdf", "0002.pdf"]
        assert [row["participant_id"] for row in rows] == ["100", "100", "200"]
        assert (assignment / paths.TO_GRADE / "0002.pdf").read_text(encoding="utf-8") == "b"
        with open(assignment / paths.KEY, encoding="utf-8-sig") as f:
            saved = list(csv.DictReader(f))
        assert saved[2]["original_folder"] == "בת_200_assignsubmission_file"
        assert read_mapping(assignment)["0001"]["anon_file"] == "0001.pdf"


def test_numbers_stay_when_new_students_submit():
    with tempfile.TemporaryDirectory() as tmp:
        assignment = Path(tmp) / "assignment"
        assignment.mkdir()
        original = Path(tmp) / "original"
        make_submission(original, "ב_200_assignsubmission_file", {"b.pdf": "b"})
        make_submission(original, "ד_400_assignsubmission_file", {"d.pdf": "d"})
        prepare(original, assignment)

        # Two more students submit, with ids before and between the first two
        make_submission(original, "א_100_assignsubmission_file", {"a.pdf": "a"})
        make_submission(original, "ג_300_assignsubmission_file", {"c.pdf": "c"})
        rows = prepare(original, assignment)

        by_id = {row["participant_id"]: row["number"] for row in rows}
        assert by_id == {"200": "0001", "400": "0002", "100": "0003", "300": "0004"}
        assert (assignment / paths.TO_GRADE / "0002.pdf").read_text(encoding="utf-8") == "d"


if __name__ == "__main__":
    test_numbers_stay_when_new_students_submit()
    test_parse_folder()
    test_parse_folder_rejects_other_names()
    test_prepare_numbers_by_participant_id()
    print("All tests passed.")
