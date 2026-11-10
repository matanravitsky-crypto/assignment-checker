"""Grades for Moodle.csv: each grade next to the Moodle participant id, only when it is safe, and the upload uses it."""
import csv
from pathlib import Path

from moodle import moodle_table, paths
from moodle.upload import GRADES_FOR_MOODLE, prepare_upload

KEY = [
    ["number", "anon_file", "participant_id", "original_folder", "original_file"],
    ["0001", "0001.pdf", "100", "אב_100_assignsubmission_file", "a.pdf"],
    ["0002", "0002.pdf", "200", "בת_200_assignsubmission_file", "b.pdf"],
    ["0003", "0003.pdf", "300", "גד_300_assignsubmission_file", "c.pdf"],
]


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)


def table(a: Path) -> dict[str, dict]:
    return {r["number"]: r for r in moodle_table.read(a)}


def test_each_grade_sits_next_to_its_moodle_participant(tmp_path):
    write_csv(tmp_path / paths.KEY, KEY)
    write_csv(tmp_path / paths.GRADES, [["number", "grade", "feedback", "approved"],
                                        ["2", "90", "טוב", "dana 2026-11-10 10:00"], ["0001", "70.5", "", ""]])
    rep = moodle_table.build(tmp_path)
    assert rep["rows"] == 2 and rep["left_out"] == {} and rep["written"]
    t = table(tmp_path)
    assert t["0002"]["participant_id"] == "200" and t["0002"]["moodle_identifier"] == "Participant 200"
    assert (t["0002"]["grade"], t["0002"]["feedback"], t["0002"]["max_grade"]) == ("90", "טוב", "100")
    assert t["0002"]["approved"].startswith("dana") and t["0001"]["grade"] == "70.5"
    assert "0003" not in t  # not graded yet
    # nothing changed: the file is not written again
    assert not moodle_table.build(tmp_path)["written"]


def test_the_table_follows_the_merged_grades_an_edit_wins(tmp_path):
    write_csv(tmp_path / paths.KEY, KEY)
    write_csv(tmp_path / paths.GRADES_BY.format("a"), [["number", "grade", "graded_at"], ["0001", "60", "2026-11-10T10:00:00"]])
    write_csv(tmp_path / paths.GRADES_BY.format("b"), [["number", "grade", "graded_at", "approved"],
                                                       ["0001", "95", "2026-11-10T11:00:00", "b 2026-11-10 11:00"]])
    moodle_table.build(tmp_path)
    assert table(tmp_path)["0001"]["grade"] == "95"


def test_what_cannot_be_tied_to_one_student_never_goes_in(tmp_path):
    bad_key = KEY + [["0002", "0002-2.pdf", "999", "בת_999_assignsubmission_file", "b2.pdf"]]  # 0002 with two participants
    write_csv(tmp_path / paths.KEY, bad_key)
    write_csv(tmp_path / paths.GRADES, [["number", "grade"], ["0001", "80"], ["0002", "90"], ["0003", "130"], ["0009", "50"]])
    rep = moodle_table.build(tmp_path)
    assert set(table(tmp_path)) == {"0001"}
    assert rep["left_out"] == {"key_problem": ["0002"], "invalid_grade": ["0003"], "no_participant": ["0009"]}


def test_the_max_grade_comes_from_the_assignment(tmp_path):
    write_csv(tmp_path / paths.KEY, KEY)
    (tmp_path / paths.INFO).write_text('{"max_grade": 10}', encoding="utf-8")
    write_csv(tmp_path / paths.GRADES, [["number", "grade"], ["0001", "9"], ["0002", "11"]])
    rep = moodle_table.build(tmp_path)
    assert table(tmp_path)["0001"]["max_grade"] == "10" and rep["left_out"] == {"invalid_grade": ["0002"]}


def test_a_conflict_copy_of_the_table_is_removed(tmp_path):
    write_csv(tmp_path / paths.KEY, KEY)
    write_csv(tmp_path / paths.GRADES, [["number", "grade"], ["0001", "80"]])
    (tmp_path / "Grades for Moodle-DESKTOP-ABC.csv").write_text("old", encoding="utf-8")
    moodle_table.build(tmp_path)
    assert not (tmp_path / "Grades for Moodle-DESKTOP-ABC.csv").exists() and (tmp_path / paths.MOODLE_TABLE).exists()


def test_the_upload_fills_moodles_worksheet_from_the_table(tmp_path):
    write_csv(tmp_path / paths.KEY, KEY)
    write_csv(tmp_path / paths.GRADES, [["number", "grade", "feedback"], ["0001", "70", "א"], ["0002", "90", "ב"], ["0003", "150", ""]])
    write_csv(tmp_path / "worksheet.csv", [["מזהה", "שם מלא", "ציון", "ציון מירבי", "הערות למשוב"],
                                           ["משתתף 200", "x", "", "100", ""], ["משתתף 300", "y", "", "100", ""],
                                           ["משתתף 100", "z", "", "100", ""]])
    rep = prepare_upload(tmp_path, tmp_path / "worksheet.csv")
    assert rep["moodle_table"]["rows"] == 2 and rep["grades_filled"] == 2 and rep["grades_skipped_invalid"] == ["0003"]
    with open(tmp_path / paths.UPLOAD / GRADES_FOR_MOODLE, encoding="utf-8-sig") as f:
        rows = {r[0]: r for r in csv.reader(f)}
    assert rows["משתתף 200"][2:5:2] == ["90", "ב"] and rows["משתתף 100"][2] == "70" and rows["משתתף 300"][2] == ""
    assert table(tmp_path)["0002"]["grade"] == "90"  # the table was built by the upload
