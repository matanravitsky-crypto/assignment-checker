"""המשיכה בחלקים (dashboard/pull_parts.py): מחכים בתיקיית ההורדות לסיכום של הסקריפט שבלשונית של מודל, ולוקחים את החלקים שבו."""
from __future__ import annotations

import json
import os
import time

import pytest

from dashboard import pull_parts
from moodle import ingest

MID, RUN = "3453769", "12345678"


@pytest.fixture
def downloads():
    """תיקיית ההורדות הזמנית של הבדיקות (conftest)."""
    return ingest.downloads_dir()


def summary(d, parts, stage="done", error=None):
    (d / pull_parts.summary_name(MID, RUN)).write_text(json.dumps(
        {"cmid": MID, "run": RUN, "stage": stage, "users": 100, "error": error,
         "parts": [{"size": s, "students": 50, "asked": 50} for s in parts]}), encoding="utf-8")


def no_sleep(_):
    pass


def test_parts_are_matched_to_the_summary_by_exact_size(downloads):
    since = time.time() - 1
    a, b = downloads / f"x-{MID}.zip", downloads / f"x-{MID} (1).zip"
    a.write_bytes(b"1" * 10)
    b.write_bytes(b"2" * 20)
    (downloads / "x-999.zip").write_bytes(b"3" * 20)  # another assignment
    summary(downloads, [10, 20])
    zips, s = pull_parts.wait(MID, RUN, since, downloads, sleep=no_sleep)
    assert zips == [a, b] and s["users"] == 100
    assert not (downloads / pull_parts.summary_name(MID, RUN)).exists()


def test_waits_while_chrome_is_still_writing_a_part(downloads, monkeypatch):
    since = time.time() - 1
    (downloads / f"x-{MID}.zip").write_bytes(b"1" * 10)
    summary(downloads, [10, 20])
    calls = []

    def later(_):  # the second part lands while we wait
        calls.append(1)
        if len(calls) == 2:
            (downloads / f"x-{MID} (1).zip").write_bytes(b"2" * 20)
    zips, _ = pull_parts.wait(MID, RUN, since, downloads, sleep=later)
    assert len(zips) == 2 and len(calls) == 2


def test_an_old_zip_of_the_same_size_is_not_a_part(downloads, monkeypatch):
    old = downloads / f"x-{MID}.zip"
    old.write_bytes(b"1" * 10)
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    summary(downloads, [10])
    monkeypatch.setattr(pull_parts, "SETTLE_S", 0)
    with pytest.raises(pull_parts.PartsError, match="לא כל החלקים"):
        pull_parts.wait(MID, RUN, time.time() - 1, downloads, sleep=no_sleep)


@pytest.mark.parametrize("error, message", [("needs_login", "להתחבר מחדש"), ("no_submissions", "אין עדיין"),
                                            ("Moodle 503", "Moodle 503")])
def test_a_run_that_stopped_says_why(downloads, error, message):
    summary(downloads, [], stage="error", error=error)
    with pytest.raises(pull_parts.PartsError, match=message):
        pull_parts.wait(MID, RUN, time.time() - 1, downloads, sleep=no_sleep)


def test_gives_up_when_nothing_changes_and_keeps_the_lock_alive_meanwhile(downloads, monkeypatch):
    monkeypatch.setattr(pull_parts, "STALL_S", 0.2)
    alive = []
    with pytest.raises(pull_parts.PartsError, match="לא הסתיימה בזמן"):
        pull_parts.wait(MID, RUN, time.time() - 1, downloads, keep_alive=lambda: alive.append(1),
                        sleep=lambda s: time.sleep(0.05))
    assert len(alive) > 2


def test_run_ids_are_digits_only():
    assert all(pull_parts.new_run().isdigit() and len(pull_parts.new_run()) == 8 for _ in range(20))
