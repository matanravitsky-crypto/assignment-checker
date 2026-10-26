import csv
import json
import os
import sys
import time

import pytest

from moodle import __main__ as cli
from moodle import claude_driver, paths
from moodle.paths import assignment_dir
from moodle.send import UploadResult, prepare_batch
from moodle.upload_log import read_log
from tests.fakes import FakeDriver

# Fictional names (from tests.sample_files.NAMES, copied so these tests don't load PyMuPDF)
STUDENTS = [("0001", "100", "נועה כהן"), ("0002", "200", "איתי לוי")]
ID = "3438636"


REAL_MAKE_DRIVER = cli.make_driver


@pytest.fixture(autouse=True)
def fake_moodle(monkeypatch):
    """No test reaches Moodle: the CLI's driver is the tests' fake one."""
    monkeypatch.setattr(cli, "make_driver", lambda: FakeDriver())


@pytest.fixture
def data(tmp_path, monkeypatch):
    """ASSIGNMENT_DATA with one assignment: 2 students, submissions older than the 2 small marked files."""
    monkeypatch.setenv("ASSIGNMENT_DATA", str(tmp_path))
    a = tmp_path / "Course" / "Assignment 1"
    for folder in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD):
        (a / folder).mkdir(parents=True)
    (a / paths.INFO).write_text(json.dumps({"id": ID, "title": "הגשה 1"}, ensure_ascii=False), encoding="utf-8")
    with open(a / paths.KEY, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(
            [["number", "anon_file", "participant_id", "original_folder", "original_file"],
             *[(n, f"{n}.pdf", p, f"{name}_{p}_assignsubmission_file", "work.pdf") for n, p, name in STUDENTS]])
    now = time.time()
    for n, _, _ in STUDENTS:
        (a / paths.TO_GRADE / f"{n}.pdf").write_bytes(b"submission " + n.encode())
        os.utime(a / paths.TO_GRADE / f"{n}.pdf", (now - 120, now - 120))
        (a / paths.MARKED / f"{n}.pdf").write_bytes(b"marked " + n.encode())
        os.utime(a / paths.MARKED / f"{n}.pdf", (now - 60, now - 60))
    return a


@pytest.fixture
def run_cli(monkeypatch):
    def run(args):
        """Runs main() and returns its exit code (0 when it simply returns)."""
        monkeypatch.setattr(sys, "argv", ["moodle", *args])
        try:
            cli.main()
        except SystemExit as stop:
            return stop.code or 0
        return 0
    return run


def test_send_with_yes_uploads_and_records(data, capsys, run_cli):
    assert run_cli(["send", ID, "--yes"]) == 0
    out = capsys.readouterr().out
    assert "2 סטודנטים" in out and "2 קבצים" in out and "1 ZIP" in out
    assert len(read_log(assignment_dir(ID))) == 2


def test_send_summary_has_numbers_only_no_names(data, capsys, run_cli):
    (data / paths.TO_GRADE / "0002.pdf").touch()  # resubmitted after marking: held back, by number
    run_cli(["send", ID, "--yes"])
    out = capsys.readouterr().out
    assert "0002" in out
    assert not any(name in out or p in out for _, p, name in STUDENTS)


def test_send_without_yes_and_answer_no_uploads_nothing(data, monkeypatch, run_cli):
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    assert run_cli(["send", ID]) == 0
    assert read_log(assignment_dir(ID)) == []


def test_send_without_yes_and_answer_y_uploads(data, monkeypatch, run_cli):
    asked = []
    monkeypatch.setattr("builtins.input", lambda prompt="": asked.append(prompt) or "y")
    assert run_cli(["send", ID]) == 0
    assert asked == ["להעלות למודל? (y/N) "]
    assert len(read_log(assignment_dir(ID))) == 2


def test_send_dry_run_logs_nothing(data, capsys, run_cli):
    assert run_cli(["send", ID, "--yes", "--dry-run"]) == 0
    assert read_log(assignment_dir(ID)) == []
    assert "ריצת ניסיון" in capsys.readouterr().out


def test_send_with_nothing_new_says_so_and_does_not_ask(data, capsys, monkeypatch, run_cli):
    run_cli(["send", ID, "--yes"])
    capsys.readouterr()
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("must not ask"))
    assert run_cli(["send", ID]) == 0
    assert "אין עבודות חדשות להעלאה" in capsys.readouterr().out


def test_send_blocked_prints_the_message_and_exits_1(data, capsys, run_cli):
    (data / paths.UPLOAD / "Upload log-PC2.csv").write_text("x", encoding="utf-8")
    assert run_cli(["send", ID, "--yes"]) == 1
    assert "Upload log-PC2.csv" in capsys.readouterr().out


def test_send_exits_1_when_the_run_stops(data, capsys, monkeypatch, run_cli):
    monkeypatch.setattr(cli, "make_driver", lambda: FakeDriver([UploadResult("needs_login", message="צריך להתחבר")]))
    assert run_cli(["send", ID, "--yes"]) == 1
    assert "צריך להתחבר" in capsys.readouterr().out
    assert read_log(assignment_dir(ID)) == []


def test_send_always_uses_the_real_claude_driver(data, monkeypatch, run_cli):
    built = []

    class Fake(FakeDriver):
        def __init__(self):
            super().__init__()
            built.append(1)

    monkeypatch.setattr(cli, "make_driver", REAL_MAKE_DRIVER)
    monkeypatch.setattr(claude_driver, "ClaudeChromeDriver", Fake)
    run_cli(["send", ID, "--yes"])
    assert built == [1]


def test_record_writes_the_log(data, capsys, run_cli):
    prepare_batch(assignment_dir(ID))
    assert run_cli(["record", ID, "Graded - part 01.zip"]) == 0
    assert "2 קבצים נרשמו" in capsys.readouterr().out
    assert len(read_log(assignment_dir(ID))) == 2


def test_record_of_an_unknown_zip_prints_the_message_and_exits_1(data, capsys, run_cli):
    prepare_batch(assignment_dir(ID))
    assert run_cli(["record", ID, "Nope.zip"]) == 1
    assert "Nope.zip" in capsys.readouterr().out


def test_record_finds_the_zip_in_the_batch_folder_and_refuses_a_changed_one(data, capsys, run_cli):
    from moodle.upload_log import batch_folder, read_batch
    a = assignment_dir(ID)
    prepare_batch(a)
    folder = batch_folder(a, read_batch(a))
    assert run_cli(["record", ID, f"{folder.name}/Graded - part 01.zip"]) == 0  # a path inside the folder works too
    (a / paths.UPLOAD / "Upload log.csv").unlink()
    (folder / "Graded - part 01.zip").write_bytes(b"not the ZIP that was prepared")
    capsys.readouterr()
    assert run_cli(["record", ID, "Graded - part 01.zip"]) == 1
    assert "השתנה" in capsys.readouterr().out
    assert read_log(a) == []


def test_send_is_refused_while_an_upload_runs(data, capsys, run_cli):
    (data / paths.UPLOAD_LOCK).write_text("uri (URI-LAPTOP) pid=4242", encoding="utf-8")
    assert run_cli(["send", ID, "--yes"]) == 1
    out = capsys.readouterr().out
    assert "uri (URI-LAPTOP) מעלה" in out and "pid" not in out
    assert read_log(data) == []
