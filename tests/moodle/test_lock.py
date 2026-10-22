import os
import time
from datetime import datetime

import pytest

from moodle import lock
from moodle.lock import Locked, holder, me, my_text, parse, pid_alive, refresh, take


def test_take_writes_me_and_refuses_a_fresh_lock_of_someone_else(tmp_path):
    lock_path = take(tmp_path, "Upload in progress.txt")
    assert lock_path.read_text(encoding="utf-8") == my_text() == f"{me()} pid={os.getpid()}"
    lock_path.write_text("other (PC2)", encoding="utf-8")
    with pytest.raises(Locked) as e:
        take(tmp_path, "Upload in progress.txt")
    assert e.value.who == "other (PC2)"
    assert isinstance(e.value.since, datetime)


def test_old_lock_is_ignored(tmp_path):
    p = tmp_path / "Upload in progress.txt"
    p.write_text("other (PC2)", encoding="utf-8")
    old = time.time() - 31 * 60
    os.utime(p, (old, old))
    assert take(tmp_path, p.name) == p
    assert p.read_text(encoding="utf-8") == my_text()


def test_my_own_lock_does_not_block_me(tmp_path):
    take(tmp_path, "x.txt")
    assert take(tmp_path, "x.txt").read_text(encoding="utf-8") == my_text()


def test_an_empty_lock_file_still_blocks(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("", encoding="utf-8")
    with pytest.raises(Locked) as e:
        take(tmp_path, "x.txt")
    assert e.value.who  # someone is shown even when the file says nothing


def test_refresh_moves_the_clock(tmp_path):
    p = take(tmp_path, "x.txt")
    old = time.time() - 29 * 60
    os.utime(p, (old, old))
    refresh(p)
    assert time.time() - p.stat().st_mtime < 5


# ---------- the pid: two programs of the same person on the same computer ----------
OTHER_PID = 0x7FFFFFFC  # no real process has it


def test_my_lock_held_by_another_live_process_blocks_me(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text(f"{me()} pid={OTHER_PID}", encoding="utf-8")
    monkeypatch.setattr(lock, "pid_alive", lambda pid: pid == OTHER_PID)  # say the CLI is still uploading
    with pytest.raises(Locked) as e:
        take(tmp_path, "x.txt")
    assert e.value.who == me()  # shown without the pid
    assert p.read_text(encoding="utf-8") == f"{me()} pid={OTHER_PID}"  # not taken over


def test_my_lock_of_a_process_that_is_gone_does_not_block_me(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text(f"{me()} pid={OTHER_PID}", encoding="utf-8")
    monkeypatch.setattr(lock, "pid_alive", lambda pid: False)  # it crashed
    assert take(tmp_path, "x.txt").read_text(encoding="utf-8") == my_text()


def test_my_old_lock_without_a_pid_still_lets_me_in(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text(me(), encoding="utf-8")  # written before the pid was added
    assert take(tmp_path, "x.txt").read_text(encoding="utf-8") == my_text()


def test_someone_elses_lock_with_a_pid_blocks_and_shows_who_without_it(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text(f"other (PC2) pid={OTHER_PID}", encoding="utf-8")
    monkeypatch.setattr(lock, "pid_alive", lambda pid: pytest.fail("another computer's pid means nothing here"))
    with pytest.raises(Locked) as e:
        take(tmp_path, "x.txt")
    assert e.value.who == "other (PC2)"
    assert holder(p)[0] == "other (PC2)"


def test_parse_reads_old_and_new_lock_text():
    assert parse("uri (URI-LAPTOP) pid=1234 ") == ("uri (URI-LAPTOP)", 1234)
    assert parse("uri (URI-LAPTOP)") == ("uri (URI-LAPTOP)", None)
    assert parse("  ")[0] == lock.SOMEONE_ELSE


def test_holder_ignores_stuck_locks_and_my_own_process(tmp_path):
    p = tmp_path / "x.txt"
    assert holder(p) is None  # no lock
    take(tmp_path, "x.txt")
    assert holder(p) is None  # this process's own lock
    p.write_text("other (PC2)", encoding="utf-8")
    assert holder(p)[0] == "other (PC2)"
    old = time.time() - 31 * 60
    os.utime(p, (old, old))
    assert holder(p) is None


def test_pid_alive_knows_this_process():
    assert pid_alive(os.getpid()) is True
    assert pid_alive(0) is False
    assert pid_alive(OTHER_PID) is False
