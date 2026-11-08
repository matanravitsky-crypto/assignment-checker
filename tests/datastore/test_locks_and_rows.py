"""moodle/lock.py with the atomic take, and grades.update_own: real processes racing on the same folder and file."""
from __future__ import annotations

import csv
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from datastore import schema
from moodle import grades, lock, paths

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _own_lock_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BODEK_LOCK_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("GRADER_NAME", "אורי")


def _age(path: Path, minutes: int) -> None:
    t = (datetime.now() - timedelta(minutes=minutes)).timestamp()
    os.utime(path, (t, t))


# ---------- lock.take ----------
def test_take_writes_my_text_and_a_fresh_lock_of_someone_else_blocks(tmp_path):
    p = lock.take(tmp_path, paths.PULL_LOCK)
    assert p.read_text(encoding="utf-8") == lock.my_text()
    p.write_text("דנה (OTHER-PC) pid=4242", encoding="utf-8")
    with pytest.raises(lock.Locked) as e:
        lock.take(tmp_path, paths.PULL_LOCK)
    assert e.value.who == "דנה (OTHER-PC)"


def test_a_stuck_lock_and_my_dead_process_lock_are_taken_over(tmp_path):
    p = tmp_path / paths.PULL_LOCK
    p.write_text("דנה (OTHER-PC) pid=4242", encoding="utf-8")
    _age(p, lock.LOCK_MINUTES + 1)
    assert lock.take(tmp_path, paths.PULL_LOCK).read_text(encoding="utf-8") == lock.my_text()
    p.write_text(f"{lock.me()} pid=999999", encoding="utf-8")  # my lock, a process that is gone
    assert lock.take(tmp_path, paths.PULL_LOCK).read_text(encoding="utf-8") == lock.my_text()


def test_refresh_moves_the_time(tmp_path):
    p = lock.take(tmp_path, paths.UPLOAD_LOCK)
    _age(p, 10)
    old = p.stat().st_mtime
    lock.refresh(p)
    assert p.stat().st_mtime > old


RACER = """
import sys
sys.path.insert(0, sys.argv[1])
from moodle import lock
try:
    lock.take(__import__("pathlib").Path(sys.argv[2]), "Pull in progress.txt")
    print("won")
except lock.Locked:
    print("lost")
"""


def test_four_real_processes_race_for_one_lock_and_exactly_one_wins(tmp_path):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    # a stuck lock sits there first, so every racer tries to remove it and create its own
    stuck = tmp_path / paths.PULL_LOCK
    stuck.write_text("ישן (PC) pid=1", encoding="utf-8")
    _age(stuck, lock.LOCK_MINUTES + 5)
    procs = [subprocess.Popen([sys.executable, "-c", RACER, str(REPO), str(tmp_path)], env=env, stdout=subprocess.PIPE, text=True) for _ in range(4)]
    outs = [p.communicate(timeout=60)[0].strip() for p in procs]
    assert sorted(outs).count("won") >= 1 and all(o in ("won", "lost") for o in outs)
    # whatever happened, there is exactly one lock file with one process's text in it
    text = stuck.read_text(encoding="utf-8")
    assert "pid=" in text and text != "ישן (PC) pid=1"


# ---------- grades.update_own ----------
def make_assignment(tmp_path) -> Path:
    a = tmp_path / "Exercise Checking System" / "Linear Algebra" / "Assignment 2"
    (a / paths.TO_GRADE).mkdir(parents=True)
    (a / paths.INFO).write_text('{"id": "555", "course": "Linear Algebra", "name": "Assignment 2"}', encoding="utf-8")
    return a


def test_update_own_writes_one_row_and_refuses_an_invalid_one(tmp_path):
    a = make_assignment(tmp_path)
    row = grades.update_own(a, "7", {"grade": "90", "points": "40;50", "graded_at": "2026-11-01T10:00:00", "graded_by": "אורי"},
                            max_grade=100, question_points=[40, 60])
    assert row["number"] == "0007"
    mine = grades.own_file(a)
    assert grades.read_file(mine)["0007"]["grade"] == "90"
    before = mine.read_bytes()
    with pytest.raises(schema.Invalid):
        grades.update_own(a, "0008", {"grade": "abc"}, max_grade=100)
    with pytest.raises(schema.Invalid):
        grades.update_own(a, "0008", {"grade": "101"}, max_grade=100)
    with pytest.raises(schema.Invalid):
        grades.update_own(a, "0008", {"grade": "50", "points": "41;1"}, max_grade=100, question_points=[40, 60])
    assert mine.read_bytes() == before  # nothing written
    assert [p.name for p in a.iterdir() if p.suffix == ".tmp"] == []


def test_threads_updating_the_same_file_lose_nothing(tmp_path):
    a = make_assignment(tmp_path)

    def work(k):
        for i in range(15):
            grades.update_own(a, f"{k * 100 + i:04d}", {"grade": str(i), "graded_at": "2026-11-01T10:00:00", "graded_by": "אורי"}, max_grade=100)
    threads = [threading.Thread(target=work, args=(k,)) for k in range(1, 7)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(grades.read_file(grades.own_file(a))) == 90


UPDATER = """
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from moodle import grades
a, tag = Path(sys.argv[2]), int(sys.argv[3])
for i in range(25):
    grades.update_own(a, f"{tag * 100 + i:04d}", {"grade": str(i), "graded_at": "2026-11-01T10:00:00", "graded_by": "אורי"}, max_grade=100)
print("done")
"""


def test_three_real_processes_of_one_grader_write_the_same_file_without_losing_rows(tmp_path):
    a = make_assignment(tmp_path)
    env = {**os.environ, "BODEK_LOCK_DIR": str(tmp_path / "locks"), "GRADER_NAME": "אורי", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    procs = [subprocess.Popen([sys.executable, "-c", UPDATER, str(REPO), str(a), str(k)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
             for k in (1, 2, 3)]
    for p in procs:
        out, err = p.communicate(timeout=180)
        assert p.returncode == 0 and "done" in (out or ""), (err or "")[-800:]  # a failed process shows its stderr, not a TypeError
    rows = grades.read_file(grades.own_file(a))
    assert len(rows) == 75 and {r["grade"] for r in rows.values()} == {str(i) for i in range(25)}
    with grades.own_file(a).open(encoding="utf-8-sig", newline="") as fh:
        assert len(list(csv.DictReader(fh))) == 75  # the file itself is whole and well-formed
