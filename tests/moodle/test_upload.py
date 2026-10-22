import csv
import tempfile
import zipfile
from pathlib import Path

from moodle import paths
from moodle.upload import (GRADES_FOR_MOODLE, INSTRUCTIONS_FILE, build_feedback_zips, participant_from_identifier,
                           plan_parts, prepare_upload, write_zips)

MAPPING = [
    ["number", "anon_file", "participant_id", "original_folder", "original_file"],
    ["0001", "0001.pdf", "100", "אב_100_assignsubmission_file", "a.pdf"],
    ["0002", "0002.pdf", "200", "בת_200_assignsubmission_file", "b.pdf"],
]

WORKSHEET = [
    ["מזהה", "שם מלא", "ציון", "ציון מירבי", "הערות למשוב"],
    ["משתתף 200", "בת", "", "100", ""],
    ["משתתף 100", "אב", "", "100", ""],
    ["משתתף 300", "לא הגיש", "", "100", ""],
]


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)


def test_participant_from_identifier():
    assert participant_from_identifier("Participant 13464355") == "13464355"
    assert participant_from_identifier("משתתף 13464355") == "13464355"


def test_prepare_upload_matches_by_number_not_order():
    with tempfile.TemporaryDirectory() as tmp:
        assignment = Path(tmp)
        write_csv(assignment / paths.KEY, MAPPING)
        write_csv(assignment / paths.GRADES, [["number", "grade", "feedback"], ["2", "90", "טוב"], ["0001", "70", ""]])
        write_csv(assignment / "worksheet.csv", WORKSHEET)
        (assignment / paths.MARKED).mkdir()
        (assignment / paths.MARKED / "0002.pdf").write_bytes(b"marked")

        report = prepare_upload(assignment, assignment / "worksheet.csv")

        upload = assignment / paths.UPLOAD
        assert report["grades_filled"] == 2
        assert report["missing_results"] == []
        with open(upload / GRADES_FOR_MOODLE, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        assert rows[1][2:5:2] == ["90", "טוב"]
        assert rows[2][2] == "70"
        assert rows[3][2] == ""
        assert [z.name for z in report["feedback_zips"]] == ["Graded - part 01.zip"]
        instructions = (upload / INSTRUCTIONS_FILE).read_text(encoding="utf-8-sig")
        assert "Graded - part 01.zip" in instructions
        assert f"\"{GRADES_FOR_MOODLE}\" מוכן (2 ציונים)" in instructions
        with zipfile.ZipFile(report["feedback_zips"][0]) as archive:
            assert archive.namelist() == ["בת_200_assignsubmission_file/feedback.pdf"]


def test_feedback_zips_split_under_the_size_limit():
    with tempfile.TemporaryDirectory() as tmp:
        assignment = Path(tmp)
        marked = assignment / paths.MARKED
        marked.mkdir()
        (marked / "0001.pdf").write_bytes(b"x" * 600)
        (marked / "0002.pdf").write_bytes(b"y" * 600)
        (marked / "0002-2.pdf").write_bytes(b"z" * 2000)
        mapping = {row[0]: dict(zip(MAPPING[0], row)) for row in MAPPING[1:]}

        zips, too_big = build_feedback_zips(marked, assignment, mapping, max_bytes=1000)

        # A number goes whole or not at all: 0002-2 is too big, so 0002 stays out too
        assert [z.name for z in zips] == ["Graded - part 01.zip"]
        assert too_big == ["0002-2.pdf"]
        with zipfile.ZipFile(zips[0]) as archive:
            assert archive.namelist() == ["אב_100_assignsubmission_file/feedback.pdf"]


def test_plan_parts_limits_to_the_given_numbers_and_names_extra_files():
    with tempfile.TemporaryDirectory() as tmp:
        marked = Path(tmp)
        (marked / "0001.pdf").write_bytes(b"x" * 10)
        (marked / "0002.pdf").write_bytes(b"y" * 10)
        (marked / "0002-2.pdf").write_bytes(b"z" * 10)
        (marked / "README.txt").write_bytes(b"not a marked file")
        mapping = {row[0]: dict(zip(MAPPING[0], row)) for row in MAPPING[1:]}

        parts, too_big = plan_parts(marked, mapping, 1000, numbers={"0002"})

        assert too_big == []
        assert [[(src.name, arc) for src, arc in part] for part in parts] == [[
            ("0002.pdf", "בת_200_assignsubmission_file/feedback.pdf"),
            ("0002-2.pdf", "בת_200_assignsubmission_file/feedback-2.pdf")]]
        assert plan_parts(marked, mapping, 1000, numbers=set()) == ([], [])


def test_plan_parts_starts_a_new_part_when_the_next_file_does_not_fit():
    with tempfile.TemporaryDirectory() as tmp:
        marked = Path(tmp)
        (marked / "0001.pdf").write_bytes(b"x" * 600)
        (marked / "0002.pdf").write_bytes(b"y" * 600)
        mapping = {row[0]: dict(zip(MAPPING[0], row)) for row in MAPPING[1:]}

        parts, too_big = plan_parts(marked, mapping, 1000)

        assert [[src.name for src, _ in part] for part in parts] == [["0001.pdf"], ["0002.pdf"]]
        assert too_big == []


def test_write_zips_replaces_the_earlier_zips_and_leaves_other_files():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "Graded - part 01.zip").write_bytes(b"old")
        (folder / "Graded - part 02.zip").write_bytes(b"old")
        (folder / "Upload log.csv").write_bytes(b"keep")
        (folder / "a.pdf").write_bytes(b"marked")

        zips = write_zips(folder, [[(folder / "a.pdf", "f/feedback.pdf")]])

        assert [z.name for z in zips] == ["Graded - part 01.zip"]
        assert sorted(p.name for p in folder.glob("Graded - part *.zip")) == ["Graded - part 01.zip"]
        assert (folder / "Upload log.csv").read_bytes() == b"keep"
        with zipfile.ZipFile(zips[0]) as archive:
            assert archive.namelist() == ["f/feedback.pdf"]
        assert write_zips(folder, []) == []
        assert list(folder.glob("Graded - part *.zip")) == []


def test_prepare_upload_reports_missing_results():
    with tempfile.TemporaryDirectory() as tmp:
        assignment = Path(tmp)
        write_csv(assignment / paths.KEY, MAPPING)
        write_csv(assignment / paths.GRADES, [["number", "grade", "feedback"], ["0001", "70", ""], ["0009", "50", ""]])

        report = prepare_upload(assignment)

        assert report["missing_results"] == ["0002"]
        assert report["unknown_numbers"] == ["0009"]
        assert report["grades_filled"] is None


if __name__ == "__main__":
    test_participant_from_identifier()
    test_prepare_upload_matches_by_number_not_order()
    test_prepare_upload_reports_missing_results()
    test_feedback_zips_split_under_the_size_limit()
    test_plan_parts_limits_to_the_given_numbers_and_names_extra_files()
    test_plan_parts_starts_a_new_part_when_the_next_file_does_not_fit()
    test_write_zips_replaces_the_earlier_zips_and_leaves_other_files()
    print("All tests passed.")
