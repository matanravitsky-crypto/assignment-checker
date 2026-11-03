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


def test_words_after_the_extension_do_not_reach_the_number(tmp_path):
    """Discrete 2026-11-03: "<x>.pdf דיסקרטית מתוקן" became "0044.pdf דיסקרטית מתוקן", which grading can't open as a PDF."""
    assignment, original = tmp_path / "assignment", tmp_path / "original"
    assignment.mkdir()
    for pid, name, data in [("100", "hw.pdf דיסקרטית מתוקן", b"%PDF-1.7 a"), ("200", "scan.jpg (1)", b"\xff\xd8\xff b"),
                            ("300", "notes.txt final", b"text"), ("400", "page.png", b"\x89PNG d")]:
        folder = original / f"s_{pid}_assignsubmission_file"
        folder.mkdir(parents=True)
        (folder / name).write_bytes(data)

    rows = prepare(original, assignment)

    assert [row["anon_file"] for row in rows] == ["0001.pdf", "0002.jpg", "0003.txt", "0004.png"]
    assert rows[0]["original_file"] == "hw.pdf דיסקרטית מתוקן"
    assert (assignment / paths.TO_GRADE / "0001.pdf").read_bytes() == b"%PDF-1.7 a"


def test_a_later_pull_fixes_a_file_named_with_words_after_the_extension(tmp_path):
    """What the bad names left in the folder ("0001.pdf דיסקרטית", and "0002" from a name with no extension at all):
    the next pull of those students writes 0001.pdf and 0002.pdf and moves the old files aside."""
    assignment, original = tmp_path / "assignment", tmp_path / "original"
    anon = assignment / paths.TO_GRADE
    anon.mkdir(parents=True)
    (anon / "0001.pdf דיסקרטית").write_bytes(b"%PDF a")
    (anon / "0002").write_bytes(b"%PDF b")
    with open(assignment / paths.KEY, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([["number", "anon_file", "participant_id", "original_folder", "original_file"],
                                 ["0001", "0001.pdf דיסקרטית", "100", "s_100_assignsubmission_file", "hw.pdf דיסקרטית"],
                                 ["0002", "0002", "200", "s_200_assignsubmission_file", "hw"]])
    for pid, name, data in [("100", "hw.pdf דיסקרטית", b"%PDF a"), ("200", "hw", b"%PDF b")]:
        folder = original / f"s_{pid}_assignsubmission_file"
        folder.mkdir(parents=True)
        (folder / name).write_bytes(data)

    rows = prepare(original, assignment)

    assert [row["anon_file"] for row in rows] == ["0001.pdf", "0002.pdf"]
    assert sorted(p.name for p in anon.iterdir()) == ["0001.pdf", "0002.pdf"]
    [earlier] = (assignment / paths.EARLIER).iterdir()
    assert sorted(p.name for p in earlier.iterdir()) == ["0001.pdf דיסקרטית", "0002"]
    assert {n: r["participant_id"] for n, r in read_mapping(assignment).items()} == {"0001": "100", "0002": "200"}


if __name__ == "__main__":
    test_numbers_stay_when_new_students_submit()
    test_parse_folder()
    test_parse_folder_rejects_other_names()
    test_prepare_numbers_by_participant_id()
    print("All tests passed.")
