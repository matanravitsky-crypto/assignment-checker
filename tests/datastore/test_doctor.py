"""datastore/doctor.py: every kind of problem is found with numbers only, and fix repairs exactly what is safe."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from datastore import doctor, schema
from datastore.__main__ import main
from moodle import grades, lock, paths

NAMES = {"1001": "נועה כהן", "1002": "איתי לוי", "1003": "מאיה מזרחי"}


def row(n, grade, pts="40;60", by="אורי", at="2026-11-01T10:00:00", approved=""):
    return {"number": n, "grade": grade, "feedback": "", "points": pts, "approved": approved, "review": "", "graded_at": at, "graded_by": by}


@pytest.fixture
def root(tmp_path, monkeypatch):
    r = tmp_path / "Exercise Checking System"
    a = r / "Linear Algebra" / "Assignment 2 - Matrices"
    for sub in (paths.TO_GRADE, paths.MARKED, paths.NOTES, paths.CLAIMS, paths.UPLOAD):
        (a / sub).mkdir(parents=True)
    (a / paths.INFO).write_text(json.dumps({"id": "555", "course": "Linear Algebra", "name": a.name, "max_grade": 100,
                                            "rubric": {"questions": [{"label": "א", "points": 40}, {"label": "ב", "points": 60}]}}, ensure_ascii=False), encoding="utf-8")
    with (a / paths.KEY).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["number", "anon_file", "participant_id", "original_folder", "original_file"])
        w.writeheader()
        for i, (pid, name) in enumerate(NAMES.items(), start=1):
            w.writerow({"number": f"{i:04d}", "anon_file": f"{i:04d}.pdf", "participant_id": pid, "original_folder": f"{name}_{pid}_assignsubmission_file", "original_file": "hw.pdf"})
            (a / paths.TO_GRADE / f"{i:04d}.pdf").write_bytes(b"%PDF")
    monkeypatch.setenv("ASSIGNMENT_DATA", str(r))
    monkeypatch.setenv("BODEK_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("GRADER_NAME", "אורי")
    return r


def a_of(root) -> Path:
    return root / "Linear Algebra" / "Assignment 2 - Matrices"


def test_a_sound_assignment_has_no_problems(root):
    a = a_of(root)
    grades.write_file(a / paths.GRADES_BY.format("אורי"), {"0001": row("0001", "100"), "0002": row("0002", "70", "30;40")})
    (a / paths.NOTES / "0001.json").write_text(json.dumps({"mistakes": [[], []], "unsure": [False, False]}), encoding="utf-8")
    (a / paths.MARKED / "0001.pdf").write_bytes(b"%PDF")
    rep = doctor.check(a)
    assert rep.problems == [] and rep.fixable == [] and rep.moodle_id == "555"
    d = rep.as_dict()
    assert d["summary"] == {"reject": 0, "warn": 0, "info": 0} and d["checked_at"]


def _age(path: Path, minutes: int) -> None:
    t = (datetime.now() - timedelta(minutes=minutes)).timestamp()
    os.utime(path, (t, t))


def break_everything(a: Path) -> None:
    # grades: a bad grade, an out-of-range one, wrong points length, a duplicate number in one file, the same number in two files
    with (a / paths.GRADES_BY.format("אורי")).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=grades.COLUMNS, lineterminator="\r\n")
        w.writeheader()
        w.writerow(row("0001", "abc"))
        w.writerow(row("0002", "150"))
        w.writerow(row("0003", "50", "10;20;30"))
        w.writerow(row("0003", "60", "20;40"))
    grades.write_file(a / paths.GRADES_BY.format("מתן"), {"0002": row("0002", "80", by="מתן", at="2026-11-02T10:00:00")})
    # notes: broken json, a list, an unknown kind
    (a / paths.NOTES / "0001.json").write_text("{nope", encoding="utf-8")
    (a / paths.NOTES / "0002.json").write_text("[1]", encoding="utf-8")
    (a / paths.NOTES / "0003.json").write_text(json.dumps({"mistakes": [[], []], "review_kind": "weird"}), encoding="utf-8")
    (a / paths.NOTES / "0004-DESKTOP-ABC.json").write_text("{}", encoding="utf-8")
    (a / paths.NOTES / "0004.json").write_text("{}", encoding="utf-8")
    # a marked PDF without any grade row
    (a / paths.MARKED / "0003.pdf").write_bytes(b"%PDF")  # 0003 has rows; 0009 does not
    (a / paths.MARKED / "0009.pdf").write_bytes(b"%PDF")
    # locks: a stuck one and a dead one of this computer
    stuck = a / paths.PULL_LOCK
    stuck.write_text("דנה (OTHER) pid=5", encoding="utf-8")
    _age(stuck, lock.LOCK_MINUTES + 2)
    (a / paths.UPLOAD_LOCK).write_text(f"{lock.me()} pid=999999", encoding="utf-8")
    # conflict copies: key (manual), grades (fixable), claims (fixable), statistics (fixable)
    (a / "Key - number to student-DESKTOP-ABC.csv").write_text("number\n", encoding="utf-8")
    grades.write_file(a / "Grades by אורי-DESKTOP-ABC.csv", {"0005": row("0005", "95", at="2026-11-03T10:00:00"), "0002": row("0002", "77", at="2026-10-01T10:00:00")})
    (a / paths.CLAIMS / "אורי.json").write_text(json.dumps({"0001": "2026-11-01T10:00:00"}), encoding="utf-8")
    (a / paths.CLAIMS / "אורי-DESKTOP-ABC.json").write_text(json.dumps({"0001": "2026-11-01T09:00:00", "0006": "2026-11-01T11:00:00"}), encoding="utf-8")
    stats_dir = a.parent.parent / paths.STATISTICS / a.parent.name
    stats_dir.mkdir(parents=True, exist_ok=True)
    (stats_dir / "Assignment 2.json").write_text("{}", encoding="utf-8")
    (stats_dir / "Assignment 2-DESKTOP-ABC.json").write_text("{}", encoding="utf-8")
    # a broken batch file
    (a / paths.UPLOAD / "Upload batch.json").write_text("{broken", encoding="utf-8")


def test_every_kind_of_problem_is_found_and_no_name_leaks(root):
    a = a_of(root)
    break_everything(a)
    rep = doctor.check(a)
    codes = {p.code for p in rep.problems}
    assert {"grade_not_numeric", "grade_out_of_range", "points_length", "duplicate_in_file", "graded_in_several_files",
            "unreadable_json", "notes_not_object", "notes_review_kind", "conflict_copy_notes", "marked_without_grade",
            "stale_lock", "dead_lock", "conflict_copy_key", "conflict_copy_grades", "conflict_copy_claims", "conflict_copy_stats"} <= codes
    by_code = {p.code: p for p in rep.problems}
    assert by_code["marked_without_grade"].number == "0009" and by_code["conflict_copy_key"].level == schema.REJECT
    assert by_code["graded_in_several_files"].level == schema.INFO
    assert sorted(set(rep.fixable)) == ["conflict_copy_claims", "conflict_copy_grades", "conflict_copy_stats", "dead_lock", "stale_lock"]
    text = json.dumps(rep.as_dict(), ensure_ascii=False)
    for pid, name in NAMES.items():
        assert pid not in text and name not in text
    # the batch problem names its file
    assert any("Upload batch.json" in p.message for p in rep.problems if p.code == "unreadable_json")


def test_fix_dry_run_changes_nothing_and_fix_repairs_only_what_is_safe(root):
    a = a_of(root)
    break_everything(a)
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    plan = doctor.fix(a, dry_run=True)
    assert len(plan) == 5 and all("היה" in line for line in plan)
    assert {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before

    done = doctor.fix(a, dry_run=False)
    assert len(done) == 5
    assert not (a / paths.PULL_LOCK).exists() and not (a / paths.UPLOAD_LOCK).exists()
    # the graders' copy was merged by the rules: the newer 0005 came in, the older 0002 did not win
    mine = grades.read_file(a / paths.GRADES_BY.format("אורי"))
    assert mine["0005"]["grade"] == "95" and mine["0002"]["grade"] == "150"
    assert not (a / "Grades by אורי-DESKTOP-ABC.csv").exists()
    kept = list((a / paths.EARLIER / doctor.CONFLICT_DIR).iterdir())
    assert sorted(p.name.split(" ", 2)[-1] for p in kept) == ["Grades by אורי-DESKTOP-ABC.csv", "אורי-DESKTOP-ABC.json"]
    # claims: union, the earlier time wins
    claims = json.loads((a / paths.CLAIMS / "אורי.json").read_text(encoding="utf-8"))
    assert claims == {"0001": "2026-11-01T09:00:00", "0006": "2026-11-01T11:00:00"}
    # statistics copy gone, key copy untouched, notes copy untouched
    assert not (a.parent.parent / paths.STATISTICS / a.parent.name / "Assignment 2-DESKTOP-ABC.json").exists()
    assert (a / "Key - number to student-DESKTOP-ABC.csv").exists() and (a / paths.NOTES / "0004-DESKTOP-ABC.json").exists()
    rep = doctor.check(a)
    assert rep.fixable == [] and "conflict_copy_key" in {p.code for p in rep.problems}
    assert doctor.fix(a, dry_run=False) == []  # nothing left to do


def test_a_fresh_lock_of_a_live_process_is_not_reported_or_removed(root):
    a = a_of(root)
    lock.take(a, paths.PULL_LOCK)  # mine, this process, alive
    rep = doctor.check(a)
    assert not {p.code for p in rep.problems} & {"stale_lock", "dead_lock"}
    assert doctor.fix(a, dry_run=False) == [] and (a / paths.PULL_LOCK).exists()


def test_conflict_copies_matches_only_onedrive_style_names(tmp_path):
    (tmp_path / "Grades by אורי.csv").write_text("", encoding="utf-8")
    (tmp_path / "Grades by אורי-DESKTOP-ABC.csv").write_text("", encoding="utf-8")
    (tmp_path / "Grades by אורי-LAPTOP-1.csv").write_text("", encoding="utf-8")
    (tmp_path / "Grades by דנה-כהן.csv").write_text("", encoding="utf-8")  # a hyphen in a name, no original: not a copy
    (tmp_path / "Assignment 2-x.json").write_text("", encoding="utf-8")   # no "Assignment 2.json" here either
    copies = sorted(c.name for c, _ in doctor.conflict_copies(tmp_path))
    assert copies == ["Grades by אורי-DESKTOP-ABC.csv", "Grades by אורי-LAPTOP-1.csv"]
    assert doctor.conflict_copies(tmp_path / "missing") == []


def test_broken_details_and_missing_key_are_reported_not_raised(root):
    a = a_of(root)
    (a / paths.INFO).write_text("{broken", encoding="utf-8")
    (a / paths.KEY).unlink()
    rep = doctor.check(a)
    assert "unreadable_json" in {p.code for p in rep.problems} and rep.moodle_id is None
    (a / paths.INFO).unlink()
    assert "details_missing" in {p.code for p in doctor.check(a).problems}


def test_check_all_skips_the_statistics_folder_and_cli_exit_codes(root, capsys):
    a = a_of(root)
    s = root / paths.STATISTICS / "Linear Algebra"
    s.mkdir(parents=True, exist_ok=True)
    (s / paths.INFO).write_text("{}", encoding="utf-8")
    assert [r.folder for r in doctor.check_all(root)] == [a.name]
    assert main(["check", "--all"]) == 0
    break_everything(a)
    assert main(["check", "555"]) == 1
    out = capsys.readouterr().out
    assert "שגיאה" in out and "אפשר לתקן לבד" in out
    assert main(["fix", "555"]) == 0 and "בדיקה בלבד" in capsys.readouterr().out
    assert (a / paths.PULL_LOCK).exists()
    assert main(["fix", "555", "--yes"]) == 0 and not (a / paths.PULL_LOCK).exists()
    with pytest.raises(SystemExit):
        main(["check", "999"])
