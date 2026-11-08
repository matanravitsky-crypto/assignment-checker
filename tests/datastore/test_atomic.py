"""datastore/atomic.py: atomic writes, O_EXCL lock files and the local process lock, including real processes."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from datastore import atomic
from datastore.schema import Problem

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _own_lock_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BODEK_LOCK_DIR", str(tmp_path / "locks"))


def test_write_atomic_writes_and_leaves_no_temp_file(tmp_path):
    f = tmp_path / "deep" / "er" / "a.txt"
    atomic.write_atomic(f, "שלום\r\nעולם")
    assert f.read_bytes() == "שלום\r\nעולם".encode("utf-8")  # bytes: read_text would translate the line ending
    assert [p.name for p in f.parent.iterdir()] == ["a.txt"]
    atomic.write_atomic(f, b"\xef\xbb\xbfbytes")
    assert f.read_bytes() == b"\xef\xbb\xbfbytes"


def test_a_failure_before_the_replace_keeps_the_old_file_and_cleans_up(tmp_path, monkeypatch):
    f = tmp_path / "a.json"
    atomic.write_json_atomic(f, {"v": 1})

    def boom(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(atomic.os, "replace", boom)
    with pytest.raises(OSError):
        atomic.write_json_atomic(f, {"v": 2})
    assert json.loads(f.read_text(encoding="utf-8")) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]  # no temp file left behind


def test_temp_names_are_short_for_long_windows_paths(tmp_path):
    f = tmp_path / ("x" * 60) / "README.txt"
    tmp = atomic._tmp_name(f)
    assert tmp.parent == f.parent and len(tmp.name) <= 12 and tmp.name.endswith(".tmp")


def test_write_json_atomic_with_bom_and_read_json_tolerance(tmp_path):
    f = tmp_path / "b.json"
    atomic.write_json_atomic(f, {"א": [1, 2]}, bom=True)
    assert f.read_bytes().startswith(b"\xef\xbb\xbf")
    assert atomic.read_json(f) == {"א": [1, 2]}
    problems: list[Problem] = []
    assert atomic.read_json(tmp_path / "missing.json", default="d", problems=problems) == "d" and problems == []
    (tmp_path / "broken.json").write_text("{nope", encoding="utf-8")
    (tmp_path / "bad-bytes.json").write_bytes(b"\xff\xfe\x00zz")
    assert atomic.read_json(tmp_path / "broken.json", default=None, problems=problems) is None
    assert atomic.read_json(tmp_path / "bad-bytes.json", default=None, problems=problems) is None
    assert [p.code for p in problems] == ["unreadable_json", "unreadable_json"]
    assert all("broken.json" in p.message or "bad-bytes.json" in p.message for p in problems)
    with pytest.raises(ValueError):
        atomic.write_json_atomic(f, {"x": float("nan")})  # never NaN in a file
    assert atomic.read_json(f) == {"א": [1, 2]}


def test_create_exclusive_lets_exactly_one_writer_in(tmp_path):
    lock = tmp_path / "lock.txt"
    assert atomic.create_exclusive(lock, "me") is True
    assert atomic.create_exclusive(lock, "you") is False
    assert lock.read_text(encoding="utf-8") == "me"


def test_process_lock_serializes_threads(tmp_path):
    counter = tmp_path / "n.txt"
    counter.write_text("0")
    errors = []

    def bump():
        try:
            for _ in range(40):
                with atomic.process_lock("counter"):
                    v = int(counter.read_text())
                    time.sleep(0.0005)
                    counter.write_text(str(v + 1))
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=bump) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and counter.read_text() == "200"


HOLDER = """
import os, sys, time
sys.path.insert(0, sys.argv[1])
from datastore import atomic
with atomic.process_lock("held"):
    print("held", flush=True)
    time.sleep(float(sys.argv[2]))
"""


def test_process_lock_blocks_another_real_process_and_times_out(tmp_path):
    env = {**os.environ, "BODEK_LOCK_DIR": str(tmp_path / "locks"), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(REPO), "2.5"], env=env, stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "held"
        t = time.perf_counter()
        with pytest.raises(atomic.LockTimeout):
            with atomic.process_lock("held", timeout=0.4):
                pass
        assert 0.3 < time.perf_counter() - t < 6.0  # loose upper bound: the machine may be busy with another test run
    finally:
        proc.wait(timeout=10)
    # once the holder exits, the lock is free again
    with atomic.process_lock("held", timeout=1):
        pass


WORKER = """
import csv, os, sys
sys.path.insert(0, sys.argv[1])
from datastore import atomic
path, tag, n = sys.argv[2], sys.argv[3], int(sys.argv[4])
for i in range(n):
    with atomic.process_lock(path):
        rows = []
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))
        rows.append([tag, str(i)])
        atomic.write_atomic(path, "".join(",".join(r) + "\\r\\n" for r in rows))
print("done")
"""


def test_three_real_processes_read_modify_write_one_file_without_losing_a_row(tmp_path):
    path = tmp_path / "shared.csv"
    env = {**os.environ, "BODEK_LOCK_DIR": str(tmp_path / "locks"), "PYTHONIOENCODING": "utf-8"}
    procs = [subprocess.Popen([sys.executable, "-c", WORKER, str(REPO), str(path), tag, "30"], env=env, stdout=subprocess.PIPE, text=True)
             for tag in ("A", "B", "C")]
    for p in procs:
        out, _ = p.communicate(timeout=120)
        assert p.returncode == 0 and "done" in out
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 90 and sorted(r[0] for r in rows).count("A") == 30
    assert sorted(int(r[1]) for r in rows if r[0] == "B") == list(range(30))
