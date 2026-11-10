"""The grades upload (moodle/send_grades.py) with a fake driver: nothing here opens Chrome or Moodle."""
import csv
import json
import subprocess

import pytest

from moodle import claude_driver, paths, send_grades, upload
from moodle.lock import me
from moodle.send import UPLOAD_LOCK, prepare_batch
from moodle.send_grades import GradesResult, pending, read_log, send_grades as run
from moodle.upload_log import record_zip
from tests.fakes import FakeGradesDriver
from test_send_prepare import assignment, write_grades  # noqa: F401  (assignment: the fixture)

# The worksheet as Moodle gives it (fictional names; rows not in the key order on purpose)
HEADER = ["מזהה", "שם מלא", "כתובת דואר אלקטרוני", "ציון", "ציון מירבי", "שינוי אחרון (ציון)", "הערות למשוב"]
SHEET = [HEADER,
         ["משתתף 200", "איתי לוי", "x@example.com", "", "100", "", ""],
         ["משתתף 300", "מאיה מזרחי", "y@example.com", "", "100", "", ""],
         ["משתתף 100", "נועה כהן", "z@example.com", "", "100", "", ""]]


def rows_of(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


@pytest.fixture
def returned(assignment):
    """0001 and 0002 graded, their marked files already uploaded (in Upload log.csv); 0003 has no marked file."""
    write_grades(assignment, [("0001", "80", "yes"), ("0002", "95", ""), ("0003", "50", "")])
    prepare_batch(assignment, max_bytes=10_000_000)
    record_zip(assignment, "Graded - part 01.zip", by="me (PC)")
    return assignment


@pytest.fixture
def downloads(tmp_path):
    d = tmp_path / "Downloads"
    d.mkdir()
    return d


def go(a, driver, downloads, **kw):
    return run(a, driver, downloads=downloads, wait_s=0, sleep=lambda s: None, **kw)


# ---------- filling the worksheet ----------
def test_fill_for_upload_fills_only_the_given_numbers_by_participant(returned, tmp_path):
    sheet = tmp_path / "sheet.csv"
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([*SHEET[:2], ["משתתף 300", "מאיה מזרחי", "y", "70.00", "100", "", "ישן"], SHEET[3]])
    results = {"0002": {"number": "0002", "grade": "95", "feedback": "טוב"},
               "0003": {"number": "0003", "grade": "70", "feedback": "ישן"}}
    out = tmp_path / "out.csv"
    got = upload.fill_for_upload(sheet, out, results, {"0002": {"participant_id": "200"}, "0003": {"participant_id": "300"}})
    assert got == {"filled": ["0002", "0003"], "grade_changes": 1, "changed_rows": 1}  # 0003 already has 70 and the same feedback
    rows = rows_of(out)
    assert rows[1][3] == "95" and rows[1][6] == "טוב"
    assert rows[3][3] == "" and rows[3][6] == ""  # 0001 was not asked for: untouched
    assert rows[0] == HEADER


def test_fill_for_upload_without_a_feedback_column(tmp_path):
    sheet = tmp_path / "sheet.csv"
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([["Identifier", "Grade"], ["Participant 100", "-"]])
    got = upload.fill_for_upload(sheet, tmp_path / "out.csv", {"0001": {"grade": "60"}}, {"0001": {"participant_id": "100"}})
    assert got["grade_changes"] == 1 and rows_of(tmp_path / "out.csv")[1] == ["Participant 100", "60"]


def test_fill_for_upload_leaves_out_a_grade_above_the_maximum(tmp_path):
    sheet = tmp_path / "sheet.csv"
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([["Identifier", "Grade"], ["Participant 100", ""]])
    got = upload.fill_for_upload(sheet, tmp_path / "o.csv", {"0001": {"grade": "120"}}, {"0001": {"participant_id": "100"}}, 100)
    assert got["filled"] == [] and rows_of(tmp_path / "o.csv")[1][1] == ""


# ---------- what goes up ----------
def test_pending_is_returned_numbers_with_a_valid_grade_not_yet_sent(returned):
    assert sorted(pending(returned)) == ["0001", "0002"]  # 0003 has no marked file in Moodle


def test_nothing_pending_without_grades(assignment):
    assert pending(assignment) == {}


# ---------- the run ----------
def test_grades_go_up_and_are_logged_by_number(returned, downloads):
    d = FakeGradesDriver(downloads, SHEET)
    r = go(returned, d, downloads)
    assert (r.status, r.sent, r.changes) == ("done", 2, 2)
    sheet, expected, dry = d.uploaded[0]
    assert (expected, dry) == (2, False)
    by_id = {row[0]: row[3] for row in sheet[1:]}
    assert by_id == {"משתתף 100": "80", "משתתף 200": "95", "משתתף 300": ""}  # by participant, not by row
    assert [(row["number"], row["grade"], row["by"]) for row in read_log(returned)] == [("0001", "80", me()), ("0002", "95", me())]
    assert not list(downloads.iterdir())  # Moodle's sheet (names, emails) does not stay in Downloads
    assert (returned / paths.UPLOAD / upload.GRADES_FOR_MOODLE).is_file()
    assert not (returned / UPLOAD_LOCK).exists()
    assert pending(returned) == {}
    assert go(returned, d, downloads).status == "nothing" and len(d.uploaded) == 1


def test_a_changed_grade_goes_up_again(returned, downloads):
    go(returned, FakeGradesDriver(downloads, SHEET), downloads)
    write_grades(returned, [("0001", "85", "yes"), ("0002", "95", ""), ("0003", "50", "")])
    assert sorted(pending(returned)) == ["0001"]


def test_worksheet_not_enabled_changes_nothing(returned, downloads):
    d = FakeGradesDriver(downloads, SHEET, download_status="not_enabled")
    r = go(returned, d, downloads)
    assert r.status == "not_enabled" and "Offline grading worksheet" in r.message
    assert d.uploaded == [] and read_log(returned) == []


def test_no_worksheet_in_downloads_is_an_error(returned, downloads):
    class NoFile(FakeGradesDriver):
        def download_worksheet(self, info):
            return {"status": "started", "message": ""}
    r = go(returned, NoFile(downloads, SHEET), downloads)
    assert r.status == "error" and r.message == send_grades.NO_WORKSHEET


def test_a_preview_that_does_not_match_logs_nothing(returned, downloads):
    d = FakeGradesDriver(downloads, SHEET, grades_result=GradesResult("mismatch", preview=1, skipped=0))
    r = go(returned, d, downloads)
    assert r.status == "mismatch" and "בוטלה" in r.message
    assert read_log(returned) == []


def test_imported_with_a_wrong_preview_count_is_not_logged(returned, downloads):
    d = FakeGradesDriver(downloads, SHEET, grades_result=GradesResult("imported", preview=1, skipped=0, updated=1))
    assert go(returned, d, downloads).status == "mismatch" and read_log(returned) == []


def test_dry_run_uploads_to_the_preview_only_and_logs_nothing(returned, downloads):
    d = FakeGradesDriver(downloads, SHEET)
    r = go(returned, d, downloads, dry_run=True)
    assert r.status == "dry_run_ok" and d.uploaded[0][2] is True
    assert read_log(returned) == []


def test_grades_moodle_already_has_are_only_logged(returned, downloads):
    sheet = [HEADER, ["משתתף 100", "נ", "z", "80.00", "100", "", ""], ["משתתף 200", "א", "x", "95", "100", "", ""]]
    d = FakeGradesDriver(downloads, sheet)
    r = go(returned, d, downloads)
    assert (r.status, r.sent) == ("done", 2) and d.uploaded == []


def test_refused_while_someone_else_uploads(returned, downloads):
    (returned / UPLOAD_LOCK).write_text("other (PC2)", encoding="utf-8")
    assert go(returned, FakeGradesDriver(downloads, SHEET), downloads).status == "locked"


def test_wait_for_worksheet_takes_chromes_renamed_copy(downloads):
    (downloads / "Grading worksheet-555 (1).csv").write_text("a,b\n", encoding="utf-8")
    (downloads / "Grading worksheet-5550.csv").write_text("a,b\n", encoding="utf-8")
    got = send_grades.wait_for_worksheet("555", 0, downloads, 0, sleep=lambda s: None)
    assert got.name == "Grading worksheet-555 (1).csv"


# ---------- the Claude in Chrome side (a fake subprocess.run) ----------
INFO = {"id": "3438636", "title": "הגשה 0"}


def cli(answer):
    return json.dumps({"type": "result", "is_error": False, "structured_output": answer})


class Run:
    def __init__(self, answer):
        self.answer, self.calls, self.seen = answer, [], []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        self.seen.append(sorted(p.name for p in __import__("pathlib").Path(kw["cwd"]).iterdir()))
        return subprocess.CompletedProcess(cmd, 0, stdout=cli(self.answer), stderr="")


def test_worksheet_script_is_checked_and_saves_to_the_name_python_waits_for():
    p = claude_driver.worksheet_prompt(INFO)
    assert "pluginaction=downloadgrades" in p and "Grading worksheet-3438636.csv" in p
    assert send_grades.worksheet_pattern("3438636").fullmatch("Grading worksheet-3438636.csv")
    assert "never click anything" in p and "settings" in p


def test_grades_prompt_confirms_only_a_matching_preview():
    real = claude_driver.grades_prompt(INFO, "C:/t/Grades for Moodle worksheet.csv", 7, dry_run=False)
    dry = claude_driver.grades_prompt(INFO, "C:/t/Grades for Moodle worksheet.csv", 7, dry_run=True)
    assert "pluginaction=uploadgrades" in real and "preview is 7 and skipped is 0" in real
    assert "Never click the confirm button" in dry and "Never click the confirm button" not in real


def test_download_worksheet_runs_without_tools(tmp_path):
    fake = Run({"status": "not_enabled", "message": "off"})
    r = claude_driver.ClaudeChromeDriver(run=fake, claude="claude", sleep=lambda s: None).download_worksheet(INFO)
    assert r["status"] == "not_enabled"
    cmd = fake.calls[0]
    assert cmd[cmd.index("--tools") + 1] == "" and fake.seen == [[]]


def test_upload_grades_gets_only_a_copy_of_the_csv(tmp_path):
    csv_path = tmp_path / "Grades for Moodle worksheet.csv"
    csv_path.write_text("a,b\n", encoding="utf-8")
    fake = Run({"status": "imported", "preview": 3, "skipped": 0, "updated": 3, "message": "3"})
    d = claude_driver.ClaudeChromeDriver(run=fake, claude="claude")
    r = d.upload_grades(INFO, csv_path, 3, False, sha256=claude_driver.upload_log.file_hash(csv_path))
    assert (r.status, r.preview, r.skipped, r.updated) == ("imported", 3, 0, 3)
    cmd = fake.calls[0]
    assert cmd[cmd.index("--tools") + 1] == "Read" and fake.seen == [["Grades for Moodle worksheet.csv"]]
    assert d.upload_grades(INFO, csv_path, 3, False, sha256="0" * 64).status == "error"  # changed since it was filled
