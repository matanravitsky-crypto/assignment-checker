"""datastore/ledger.py (proposal A): the event ledger projects the same grade on every computer, a conflict copy of a log
is one event, a lost update is found and replayed into the original writer's file, and an edit that started and never
finished is visible. Numbers only."""
from __future__ import annotations

import csv
import json
import random
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import activity_log
from datastore import doctor, ledger
from datastore.__main__ import main
from moodle import grades, paths

NAMES = {"1001": "נועה כהן", "1002": "איתי לוי"}


@pytest.fixture
def a(tmp_path, monkeypatch) -> Path:
    r = tmp_path / "Exercise Checking System"
    a = r / "Linear Algebra" / "Assignment 3 - Determinants"
    for sub in (paths.TO_GRADE, paths.MARKED, paths.NOTES, paths.CLAIMS, paths.UPLOAD):
        (a / sub).mkdir(parents=True)
    (a / paths.INFO).write_text(json.dumps({"id": "777", "course": "Linear Algebra", "name": a.name, "max_grade": 100}, ensure_ascii=False), encoding="utf-8")
    with (a / paths.KEY).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["number", "anon_file", "participant_id", "original_folder", "original_file"])
        w.writeheader()
        for i, (pid, name) in enumerate(NAMES.items(), start=1):
            w.writerow({"number": f"{i:04d}", "anon_file": f"{i:04d}.pdf", "participant_id": pid, "original_folder": f"{name}_{pid}_assignsubmission_file", "original_file": "hw.pdf"})
            (a / paths.TO_GRADE / f"{i:04d}.pdf").write_bytes(b"%PDF")
    monkeypatch.setenv("ASSIGNMENT_DATA", str(r))
    monkeypatch.setenv("BODEK_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("GRADER_NAME", "אורי")
    return a


def raw(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def ev(action, by, at, number="0001", **d):
    return {"at": at, "action": action, "by": by, "pc": "PC", "number": number, **d}


# ---------- projection ----------
def test_projection_is_the_same_whatever_the_file_order_and_approval_beats_grading(a):
    log = a / paths.ACTIVITY_LOG
    events = [
        ev("grade_set", "אורי", "2026-11-08T10:00:00.000001+02:00", grade=70, points="30;40"),
        ev("grade_set", "מתן", "2026-11-08T10:00:00.000001+02:00", grade=75, points="35;40"),  # same instant: id decides
        ev("grade_set", "אורי", "2026-11-08T11:00:00.000000+02:00", grade=80, points="40;40"),
        ev("grade_edit", "דנה", "2026-11-08T09:00:00.000000+02:00", **{"from": "70", "to": "95"}, points_to="45;50", kind="review"),  # earlier, but approved
        ev("grade_set", "אורי", "2026-11-08T12:00:00.000000+02:00", number="0002", grade=50, points="20;30"),
        ev("grade_failed", "אורי", "2026-11-08T12:30:00.000000+02:00", number="0002", error="x"),
    ]
    for e in events:
        e["id"] = activity_log.event_id(e)
    seen = set()
    for trial in range(6):
        shutil.rmtree(log, ignore_errors=True)
        order = events[:]
        random.Random(trial).shuffle(order)
        for i, e in enumerate(order):  # spread over several writers' files, in a different split every time
            raw(log / f"w{i % 3}.jsonl", [e])
        p = ledger.projection(a)
        seen.add(json.dumps(p, sort_keys=True, ensure_ascii=False))
        assert p["0001"]["grade"] == "95" and p["0001"]["approved"] and p["0001"]["by"] == "דנה"
        assert p["0002"]["grade"] == "50" and not p["0002"]["approved"]  # a failure after a grade does not erase it
    assert len(seen) == 1, "the projection depended on the file order"


def test_at_equal_time_the_event_id_decides_the_same_way_everywhere(a):
    log = a / paths.ACTIVITY_LOG
    e1 = ev("grade_set", "אורי", "2026-11-08T10:00:00.000000+02:00", grade=70, points="30;40")
    e2 = ev("grade_set", "מתן", "2026-11-08T10:00:00.000000+02:00", grade=75, points="35;40")
    e1["id"], e2["id"] = activity_log.event_id(e1), activity_log.event_id(e2)
    raw(log / "a.jsonl", [e1])
    raw(log / "b.jsonl", [e2])
    first = ledger.projection(a)["0001"]
    shutil.rmtree(log)
    raw(log / "a.jsonl", [e2])
    raw(log / "b.jsonl", [e1])
    assert ledger.projection(a)["0001"] == first
    assert first["event"] == max(e1["id"], e2["id"])


def test_a_conflict_copy_of_a_log_file_is_one_event(a):
    e = activity_log.record(a, "grade_set", "אורי", number="0001", grade=88, points="44;44")
    mine = activity_log.file_for(a, "אורי")
    shutil.copy(mine, mine.with_name("אורי-DESKTOP-ABC.jsonl"))  # OneDrive kept both versions
    assert len(activity_log.read(a)) == 1
    assert [x["id"] for x in ledger.history(a, "1")] == [e["id"]]  # "1" and "0001" are the same work
    assert ledger.projection(a)["0001"]["grade"] == "88"


def test_old_entries_without_id_still_read_and_a_cut_line_is_skipped(a):
    log = a / paths.ACTIVITY_LOG
    raw(log / "old.jsonl", [ev("grade_set", "אורי", "2026-11-01T10:00:00", grade=60, points="30;30")])
    with (log / "old.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"at": "2026-11-01T11:00:00", "action": "grade_set", "by": "אורי", "number": "0001", "grade": 9')  # the PC went off here
    assert ledger.projection(a)["0001"]["grade"] == "60"


# ---------- compare / replay ----------
def test_a_lost_update_is_found_and_replayed_into_the_original_writers_file(a):
    activity_log.record(a, "grade_set", "אורי", number="0001", grade=85, points="40;45")
    activity_log.record(a, "grade_set", "מתן", number="0002", grade=60, points="30;30")
    # מתן's row made it to the files; אורי's file was overwritten before there were locks
    grades.write_file(a / paths.GRADES_BY.format("מתן"), {"0002": {"number": "0002", "grade": "60", "points": "30;30", "graded_at": "2026-11-08T13:00:00", "graded_by": "מתן", "feedback": "", "approved": "", "review": ""}})
    lost = ledger.compare(a)
    assert [(m["number"], m["ledger_grade"], m["file_grade"], m["by"]) for m in lost] == [("0001", "85", "", "אורי")]

    lines = ledger.replay(a, dry_run=True)
    assert len(lines) == 1 and "0001" in lines[0] and "85" in lines[0] and "אורי" in lines[0]
    assert not (a / paths.GRADES_BY.format("אורי")).exists(), "a dry run wrote"

    lines = ledger.replay(a, dry_run=False)
    assert len(lines) == 1
    mine = grades.read_file(a / paths.GRADES_BY.format("אורי"))
    assert mine["0001"]["grade"] == "85" and mine["0001"]["points"] == "40;45" and mine["0001"]["graded_by"] == "אורי"
    assert not grades.is_approved(mine["0001"])
    assert grades.read(a)["0001"]["grade"] == "85" and grades.read(a)["0002"]["grade"] == "60"
    assert ledger.compare(a) == [] and ledger.replay(a, dry_run=False) == []
    replayed = activity_log.read(a, "grade_replayed")
    assert len(replayed) == 1 and replayed[0]["number"] == "0001" and replayed[0]["grade"] == "85"
    for e in activity_log.read(a):  # numbers only, never the names from the key
        assert not any(name in json.dumps(e, ensure_ascii=False) for name in NAMES.values())


def test_an_approved_edit_lost_from_the_file_comes_back_approved(a):
    activity_log.record(a, "grade_set", "אורי", number="0001", grade=85, points="40;45")
    activity_log.record(a, "grade_edit", "דנה", number="0001", **{"from": "85", "to": "100"}, points_to="50;50", kind="review", reason="")
    grades.write_file(a / paths.GRADES_BY.format("אורי"), {"0001": {"number": "0001", "grade": "85", "points": "40;45", "graded_at": "2026-11-08T13:00:00", "graded_by": "אורי", "feedback": "", "approved": "", "review": ""}})
    (m,) = ledger.compare(a)
    assert m["ledger_grade"] == "100" and m["file_grade"] == "85" and m["approved"]
    ledger.replay(a, dry_run=False)
    row = grades.read(a)["0001"]
    assert row["grade"] == "100" and grades.is_approved(row) and "שוחזר מהיומן" in row["approved"]
    assert ledger.compare(a) == []


def test_a_hand_edit_newer_than_the_ledger_and_a_row_without_events_are_left_alone(a):
    activity_log.record(a, "grade_set", "אורי", number="0001", grade=85, points="40;45")
    grades.write_file(a / paths.GRADES_BY.format("אורי"), {
        "0001": {"number": "0001", "grade": "90", "points": "45;45", "graded_at": "2999-01-01T00:00:00", "graded_by": "אורי", "feedback": "", "approved": "", "review": ""},
        "0002": {"number": "0002", "grade": "40", "points": "20;20", "graded_at": "2026-11-01T00:00:00", "graded_by": "אורי", "feedback": "", "approved": "", "review": ""},
    })
    assert ledger.compare(a) == [] and ledger.replay(a, dry_run=False) == []
    assert grades.read(a)["0001"]["grade"] == "90" and grades.read(a)["0002"]["grade"] == "40"


def test_replay_refuses_a_grade_the_schema_rejects_and_touches_nothing_else(a):
    activity_log.record(a, "grade_set", "אורי", number="0001", grade=85, points="40;45")
    activity_log.record(a, "grade_set", "אורי", number="0002", grade="abc", points="x")  # a hostile line in the log
    with pytest.raises(Exception):
        ledger.replay(a, dry_run=False)
    mine = grades.read_file(a / paths.GRADES_BY.format("אורי"))
    assert mine.get("0001", {}).get("grade") == "85" and "0002" not in mine


# ---------- intent ----------
def test_an_edit_that_started_and_never_finished_is_an_incomplete_edit(a):
    edit = SimpleNamespace(assignment_dir=a, by="דנה", number="0001", old_grade="85", new_grade="100", kind="review")
    ledger.LedgerStore().save_grade(edit)
    assert [(e["number"], e["by"]) for e in ledger.incomplete_edits(a)] == [("0001", "דנה")]
    (e,) = activity_log.read(a, "grade_edit_intent")
    assert e["from"] == "85" and e["to"] == "100" and e["kind"] == "review"
    assert ledger.projection(a) == {}, "an intent is not a grade"
    activity_log.record(a, "grade_edit", "דנה", number="0001", **{"from": "85", "to": "100"}, kind="review")
    assert ledger.incomplete_edits(a) == []
    ledger.LedgerStore().save_grade(edit)
    activity_log.record(a, "grade_edit_failed", "דנה", number="0001", error="disk")
    assert ledger.incomplete_edits(a) == []


# ---------- doctor / CLI ----------
def test_doctor_reports_the_mismatch_and_the_incomplete_edit_and_fix_replays(a):
    activity_log.record(a, "grade_set", "אורי", number="0001", grade=85, points="40;45")
    ledger.LedgerStore().save_grade(SimpleNamespace(assignment_dir=a, by="דנה", number="0002", old_grade=None, new_grade="70", kind="first"))
    rep = doctor.check(a)
    kinds = {p.code: p.level for p in rep.problems}
    assert kinds.get("ledger_mismatch") == "warn" and kinds.get("incomplete_edit") == "info" and "ledger_mismatch" in rep.fixable
    assert all(name not in p.message for p in rep.problems for name in NAMES.values())
    doctor.fix(a, dry_run=True)
    assert not (a / paths.GRADES_BY.format("אורי")).exists()
    doctor.fix(a, dry_run=False)
    assert grades.read(a)["0001"]["grade"] == "85"
    assert "ledger_mismatch" not in {p.code for p in doctor.check(a).problems}


def test_cli_replay_and_history(a, capsys):
    activity_log.record(a, "grade_set", "אורי", number="0001", grade=85, points="40;45")
    assert main(["replay", "777"]) == 0
    out = capsys.readouterr().out
    assert "0001" in out and "בדיקה בלבד" in out
    assert main(["replay", "777", "--yes"]) == 0
    assert grades.read(a)["0001"]["grade"] == "85"
    assert main(["replay", "777"]) == 0 and "תואמים" in capsys.readouterr().out
    assert main(["history", "777", "1"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert [l.split()[1] for l in lines] == ["grade_set", "grade_replayed"]
    assert all(name not in l for l in lines for name in NAMES.values())
