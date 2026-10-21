import csv
import tempfile
from pathlib import Path

from prepare_submissions import parse_folder, prepare


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
        assignment = Path(tmp)
        original = assignment / "original"
        # Odd characters phones put in Hebrew file names must not matter
        make_submission(original, "בת_200_assignsubmission_file", {"‎⁨הגשה⁩.PDF": "b"})
        make_submission(original, "אב_100_assignsubmission_file", {"a.pdf": "a", "b.pdf": "a2"})

        rows = prepare(assignment)

        assert [row["anon_file"] for row in rows] == ["0001.pdf", "0001-2.pdf", "0002.pdf"]
        assert [row["participant_id"] for row in rows] == ["100", "100", "200"]
        assert (assignment / "anon" / "0002.pdf").read_text(encoding="utf-8") == "b"
        with open(assignment / "mapping.csv", encoding="utf-8-sig") as f:
            saved = list(csv.DictReader(f))
        assert saved[2]["original_folder"] == "בת_200_assignsubmission_file"


if __name__ == "__main__":
    test_parse_folder()
    test_parse_folder_rejects_other_names()
    test_prepare_numbers_by_participant_id()
    print("All tests passed.")
