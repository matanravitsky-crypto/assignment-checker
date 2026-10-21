import csv
import tempfile
import zipfile
from pathlib import Path

from moodle.upload import INSTRUCTIONS_FILE, build_feedback_zips, participant_from_identifier, prepare_upload

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
        write_csv(assignment / "mapping.csv", MAPPING)
        write_csv(assignment / "results.csv", [["number", "grade", "feedback"], ["2", "90", "טוב"], ["0001", "70", ""]])
        write_csv(assignment / "worksheet.csv", WORKSHEET)
        (assignment / "marked").mkdir()
        (assignment / "marked" / "0002.pdf").write_bytes(b"marked")

        report = prepare_upload(assignment, assignment / "worksheet.csv")

        assert report["grades_filled"] == 2
        assert report["missing_results"] == []
        with open(assignment / "upload" / "grades.csv", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        assert rows[1][2:5:2] == ["90", "טוב"]
        assert rows[2][2] == "70"
        assert rows[3][2] == ""
        assert [z.name for z in report["feedback_zips"]] == ["feedback-1.zip"]
        instructions = (assignment / "upload" / INSTRUCTIONS_FILE).read_text(encoding="utf-8-sig")
        assert "feedback-1.zip" in instructions
        assert "grades.csv מוכן (2 ציונים)" in instructions
        with zipfile.ZipFile(assignment / "upload" / "feedback-1.zip") as archive:
            assert archive.namelist() == ["בת_200_assignsubmission_file/feedback.pdf"]


def test_feedback_zips_split_under_the_size_limit():
    with tempfile.TemporaryDirectory() as tmp:
        assignment = Path(tmp)
        marked = assignment / "marked"
        marked.mkdir()
        (marked / "0001.pdf").write_bytes(b"x" * 600)
        (marked / "0002.pdf").write_bytes(b"y" * 600)
        (marked / "0002-2.pdf").write_bytes(b"z" * 2000)
        mapping = {row[0]: dict(zip(MAPPING[0], row)) for row in MAPPING[1:]}

        zips, too_big = build_feedback_zips(marked, assignment, mapping, max_bytes=1000)

        assert [z.name for z in zips] == ["feedback-1.zip", "feedback-2.zip"]
        assert too_big == ["0002-2.pdf"]
        with zipfile.ZipFile(zips[1]) as archive:
            assert archive.namelist() == ["בת_200_assignsubmission_file/feedback.pdf"]


def test_prepare_upload_reports_missing_results():
    with tempfile.TemporaryDirectory() as tmp:
        assignment = Path(tmp)
        write_csv(assignment / "mapping.csv", MAPPING)
        write_csv(assignment / "results.csv", [["number", "grade", "feedback"], ["0001", "70", ""], ["0009", "50", ""]])

        report = prepare_upload(assignment)

        assert report["missing_results"] == ["0002"]
        assert report["unknown_numbers"] == ["0009"]
        assert report["grades_filled"] is None


if __name__ == "__main__":
    test_participant_from_identifier()
    test_prepare_upload_matches_by_number_not_order()
    test_prepare_upload_reports_missing_results()
    test_feedback_zips_split_under_the_size_limit()
    print("All tests passed.")
