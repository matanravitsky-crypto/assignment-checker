import os
import time
from datetime import datetime

import pytest

from moodle.lock import Locked, me, refresh, take


def test_take_writes_me_and_refuses_a_fresh_lock_of_someone_else(tmp_path):
    lock_path = take(tmp_path, "Upload in progress.txt")
    assert lock_path.read_text(encoding="utf-8") == me()
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
    assert p.read_text(encoding="utf-8") == me()


def test_my_own_lock_does_not_block_me(tmp_path):
    take(tmp_path, "x.txt")
    assert take(tmp_path, "x.txt").read_text(encoding="utf-8") == me()


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
