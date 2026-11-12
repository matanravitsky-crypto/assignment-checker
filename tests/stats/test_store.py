"""stats/store.py and the build/read/rebuild/export layer: a derived file that is fresh, never duplicated, never fought over."""
from __future__ import annotations

import csv
import json
import sqlite3
import time
from pathlib import Path

import pytest

from moodle import grades, paths
import stats
from stats import store
from stats.__main__ import main

NAMES = {"1001": "נועה כהן", "1002": "איתי לוי", "1003": "מאיה מזרחי"}


def make_assignment(root: Path, course: str, folder: str, moodle_id: str, grades_by: dict[str, dict[str, dict]],
                    notes: dict[str, dict] | None = None, points=(40, 60)) -> Path:
    a = root / course / folder
    for sub in (paths.TO_GRADE, paths.MARKED, paths.NOTES):
        (a / sub).mkdir(parents=True, exist_ok=True)
    (a / paths.INFO).write_text(json.dumps({
        "id": moodle_id, "course": course, "name": folder, "title": f"הגשה {folder[-1]}",
        "rubric": {"questions": [{"label": f"שאלה {i + 1}", "points": p} for i, p in enumerate(points)]}}, ensure_ascii=False), encoding="utf-8")
    rows = [{"number": f"{i:04d}", "anon_file": f"{i:04d}.pdf", "participant_id": pid, "original_folder": f"{name}_{pid}_assignsubmission_file",
             "original_file": "hw.pdf"} for i, (pid, name) in enumerate(NAMES.items(), start=1)]
    with (a / paths.KEY).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        (a / paths.TO_GRADE / r["anon_file"]).write_bytes(b"%PDF-1.4 fake")
    for who, rs in grades_by.items():
        grades.write_file(a / paths.GRADES_BY.format(who), rs)
    for n, d in (notes or {}).items():
        (a / paths.NOTES / f"{n}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return a


def row(n, grade, pts, by="אורי", at="2026-11-01T10:00:00", approved=""):
    return {"number": n, "grade": str(grade), "feedback": "", "points": ";".join(str(p) for p in pts), "approved": approved,
            "review": "", "graded_at": at, "graded_by": by}


@pytest.fixture
def root(tmp_path, monkeypatch):
    r = tmp_path / "Exercise Checking System"
    make_assignment(r, "Linear Algebra", "Assignment 2 - Matrices", "555",
                    {"אורי": {"0001": row("0001", 100, [40, 60]), "0002": row("0002", 70, [30, 40])}},
                    {"0002": {"mistakes": [["חסר נימוק"], ["טעות סימן"]], "unsure": [False, False]}})
    make_assignment(r, "Discrete Mathematics", "Assignment 1", "777", {"מתן": {"0001": row("0001", 50, [20, 30], by="מתן")}})
    monkeypatch.setenv("ASSIGNMENT_DATA", str(r))
    monkeypatch.setenv("GRADER_NAME", "אורי")
    return r


def la(root) -> Path:
    return root / "Linear Algebra" / "Assignment 2 - Matrices"


def test_build_writes_one_file_per_assignment_by_slot_and_a_readme(root):
    s = stats.build(la(root))
    f = root / paths.STATISTICS / "Linear Algebra" / "Assignment 2.json"
    assert f.is_file() and (root / paths.STATISTICS / paths.README).is_file()
    on_disk = json.loads(f.read_text(encoding="utf-8"))
    assert on_disk == s and on_disk["key"] == "Linear Algebra/Assignment 2" and on_disk["grade"]["mean"] == 85
    assert on_disk["computed_by"] == "אורי"
    # that the statistics folder is not a course on the site: tests/dashboard/test_stats_api.py


def test_read_uses_the_file_while_fresh_and_recomputes_when_the_grades_change(root):
    a = la(root)
    first = stats.build(a)
    f = stats.file_for(a)
    before = f.stat().st_mtime_ns
    time.sleep(0.02)
    assert stats.read(a) == first and f.stat().st_mtime_ns == before  # fresh: not rewritten
    # another grader's file arrives (OneDrive): the file is stale, read recomputes and saves
    grades.write_file(a / paths.GRADES_BY.format("מתן"), {"0003": row("0003", 40, [10, 30], by="מתן")})
    second = stats.read(a)
    assert second["counts"]["graded"] == 3 and second["grade"]["mean"] == 70
    assert json.loads(f.read_text(encoding="utf-8")) == second and f.stat().st_mtime_ns != before


def test_same_content_is_not_rewritten_even_with_a_new_time(root, monkeypatch):
    a = la(root)
    stats.build(a)
    f = stats.file_for(a)
    text = f.read_text(encoding="utf-8")
    time.sleep(0.02)
    again = stats.build(a, by="מתן")  # another computer computes the same thing
    assert f.read_text(encoding="utf-8") == text  # byte for byte: who computed first stays
    assert again["computed_by"] == "אורי"


def test_a_stale_file_from_another_computer_is_replaced_and_a_fresh_one_is_kept(root):
    a = la(root)
    f = stats.file_for(a)
    # a fresh file that another computer wrote: same sources, its name on it
    theirs = {**stats.compute_assignment(a), "computed_by": "מתן", "computed_at": "2026-11-07T20:00:00"}
    store.write(f, theirs)
    got = stats.read(a)
    assert got["computed_by"] == "מתן"  # kept as is
    # a stale one (fewer grades than the folder has now): recomputed
    stale = {**theirs, "sources": {**theirs["sources"], "grades": []}}
    f.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
    assert stats.read(a)["computed_by"] == "אורי" and stats.is_fresh(a, store.read_file(f))


def test_conflict_copies_of_the_statistics_are_removed_but_nothing_else(root):
    a = la(root)
    f = stats.file_for(a)
    f.parent.mkdir(parents=True)
    (f.parent / "Assignment 2-DESKTOP-ABC.json").write_text("{}", encoding="utf-8")
    (f.parent / "Assignment 20-DESKTOP-ABC.json").write_text("{}", encoding="utf-8")  # another assignment's copy
    key_copy = a / "Key - number to student-DESKTOP-ABC.csv"
    key_copy.write_text("number\n", encoding="utf-8")
    stats.build(a)
    assert not (f.parent / "Assignment 2-DESKTOP-ABC.json").exists()
    assert (f.parent / "Assignment 20-DESKTOP-ABC.json").exists() and key_copy.exists()


def test_a_corrupt_or_old_version_file_is_rebuilt(root):
    a = la(root)
    f = stats.file_for(a)
    f.parent.mkdir(parents=True)
    f.write_text("{broken", encoding="utf-8")
    assert stats.read(a)["grade"]["mean"] == 85
    f.write_text(json.dumps({**store.read_file(f), "version": 0}), encoding="utf-8")
    assert stats.read(a)["version"] == stats.compute.VERSION  # type: ignore[attr-defined]


def test_rebuild_writes_every_assignment_and_the_csv_with_unique_keys(root):
    out = stats.rebuild(root)
    assert [s["key"] for s in out] == ["Discrete Mathematics/Assignment 1", "Linear Algebra/Assignment 2"]
    assert (root / paths.STATISTICS / "Discrete Mathematics" / "Assignment 1.json").is_file()
    with (root / paths.STATISTICS / paths.STATS_EXPORT).open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2 + 2 + 2  # an assignment row and two question rows each
    keys = [(r["course"], r["slot"], r["question"]) for r in rows]
    assert len(set(keys)) == len(keys)
    la_row = next(r for r in rows if r["course"] == "Linear Algebra" and r["question"] == "")
    assert la_row["graded"] == "2" and la_row["mean"] == "85" and la_row["points"] == "100"
    q2 = next(r for r in rows if r["course"] == "Linear Algebra" and r["question"] == "2")
    assert q2["top_mistake"] == "טעות סימן" and q2["top_mistake_count"] == "1"
    text = (root / paths.STATISTICS / paths.STATS_EXPORT).read_text(encoding="utf-8-sig")
    for pid, name in NAMES.items():
        assert pid not in text and name not in text
    # rebuilding again changes nothing
    before = {p: p.read_bytes() for p in (root / paths.STATISTICS).rglob("*") if p.is_file()}
    stats.rebuild(root)
    assert {p: p.read_bytes() for p in (root / paths.STATISTICS).rglob("*") if p.is_file()} == before


def test_sqlite_export_has_unique_keys_and_no_duplicates_on_a_second_run(root, tmp_path):
    db = tmp_path / "local" / "stats.sqlite"
    stats.export_sqlite(root, db)
    stats.export_sqlite(root, db)  # twice: still one row per key
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 4
        assert con.execute("SELECT count FROM mistakes WHERE text = ?", ("טעות סימן",)).fetchone()[0] == 1
        assert con.execute("SELECT SUM(count) FROM histogram WHERE assignment_key = ?", ("Linear Algebra/Assignment 2",)).fetchone()[0] == 2
        assert con.execute("SELECT mean FROM assignments WHERE key = ?", ("Discrete Mathematics/Assignment 1",)).fetchone()[0] == 50
    finally:
        con.close()
    assert not (root / paths.STATISTICS).rglob("*.sqlite") or not list((root / paths.STATISTICS).rglob("*.sqlite"))


def test_cli_build_show_rebuild_export(root, capsys, tmp_path):
    assert main(["build", "555"]) == 0
    assert "Linear Algebra/Assignment 2: נבדקו 2/3, ממוצע 85" in capsys.readouterr().out
    assert main(["show", "555"]) == 0
    assert json.loads(capsys.readouterr().out)["key"] == "Linear Algebra/Assignment 2"
    assert main(["show", "--all", "--brief"]) == 0
    out = capsys.readouterr().out
    assert "Discrete Mathematics/Assignment 1" in out and "Linear Algebra/Assignment 2" in out
    assert main(["rebuild"]) == 0
    capsys.readouterr()
    db = tmp_path / "x.sqlite"
    assert main(["export", "--sqlite", str(db)]) == 0
    assert db.is_file() and "SQLite" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["show", "999"])
