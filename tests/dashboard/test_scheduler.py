"""Scheduled pull: the day is the due date, a warning half an hour before, the pull at 00:05 the night after, then a pull
of what changed every night for a week; only on the computer of whoever took the assignment's pull; a failed pull
tries again half an hour later, three times a night."""
import json
import shutil
from datetime import datetime

import pytest

from dashboard import scheduler
from moodle import claims, paths

from tests.dashboard.helpers import COURSE, HW

TITLE = "בודק חכם: הגשה 0 - קבוצות ומרוכבים"


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(scheduler, "notify", lambda t, m: sent.append(t))
    monkeypatch.setattr(scheduler, "_save", lambda state: None)
    monkeypatch.setenv("SCHEDULE_PULL_TIME", "00:05")
    monkeypatch.setenv("SCHEDULE_WARN_MIN", "30")
    monkeypatch.setenv("SCHEDULE_REPULL_DAYS", "7")
    return sent


def _due(root, iso, owner="מתן"):
    f = root / COURSE / HW / paths.INFO
    d = json.loads(f.read_text(encoding="utf-8"))
    d["due"] = iso
    f.write_text(json.dumps(d), encoding="utf-8")
    if owner:
        claims.set_task(root / COURSE, claims.task_key(HW, "pull"), True, who=owner)


def _ok(pulls, new=0):
    return lambda c, a, full: pulls.append((c, a, full)) or {"text": "ok", "new": new}


def _fails(tries):
    def boom(c, a, full):
        tries.append(1)
        raise RuntimeError("Moodle 404")
    return boom


def test_warns_then_pulls_everyone_once(root, quiet):
    _due(root, "2026-10-24T23:59:00")
    pulls, state = [], {}
    run = _ok(pulls)

    assert scheduler.tick(root, datetime(2026, 10, 24, 22, 0), state, run) is False   # too early
    assert scheduler.tick(root, datetime(2026, 10, 24, 23, 35), state, run) is True   # warning, stays awake
    assert quiet == ["בודק חכם: משיכה ב-00:05"] and not pulls
    scheduler.tick(root, datetime(2026, 10, 24, 23, 50), state, run)
    assert len(quiet) == 1                                                            # warned once
    scheduler.tick(root, datetime(2026, 10, 25, 0, 5), state, run)
    assert pulls == [(COURSE, HW, True)]                                              # the first night: everyone
    scheduler.tick(root, datetime(2026, 10, 25, 0, 6), state, run)
    assert len(pulls) == 1                                                            # once


def test_outside_the_window_does_nothing(root):
    _due(root, "2026-10-24T23:59:00")
    pulls = []
    run = _ok(pulls)
    scheduler.tick(root, datetime(2026, 10, 24, 12, 0), {}, run)    # before the window
    scheduler.tick(root, datetime(2026, 10, 25, 3, 30), {}, run)    # more than 3 hours late
    assert not pulls
    scheduler.tick(root, datetime(2026, 10, 25, 2, 0), {}, run)     # PC started late, inside catch-up: pulls
    assert len(pulls) == 1


def test_every_night_for_a_week_only_what_changed_quietly(root, quiet):
    _due(root, "2026-10-24T23:59:00")
    pulls, state = [], {}
    for day in range(25, 32):  # the first night and 6 more in October
        scheduler.tick(root, datetime(2026, 10, day, 0, 5), state, _ok(pulls))
    scheduler.tick(root, datetime(2026, 11, 1, 0, 5), state, _ok(pulls))   # the 7th re-pull
    scheduler.tick(root, datetime(2026, 11, 2, 0, 5), state, _ok(pulls))   # the week is over
    assert [p[2] for p in pulls] == [True] + [False] * 7
    assert quiet.count(TITLE) == 1                                         # only the first night tells
    scheduler.tick(root, datetime(2026, 10, 27, 0, 5), {}, _ok(pulls, new=2))
    assert quiet.count(TITLE) == 2                                         # a re-pull that brought new ones tells


def test_a_failed_pull_tries_again_half_an_hour_later_three_times(root, quiet):
    _due(root, "2026-10-24T23:59:00")
    state, tries = {}, []
    scheduler.tick(root, datetime(2026, 10, 25, 0, 5), state, _fails(tries))
    scheduler.tick(root, datetime(2026, 10, 25, 0, 20), state, _fails(tries))    # not yet
    assert len(tries) == 1
    scheduler.tick(root, datetime(2026, 10, 25, 0, 35), state, _fails(tries))
    scheduler.tick(root, datetime(2026, 10, 25, 1, 5), state, _fails(tries))
    scheduler.tick(root, datetime(2026, 10, 25, 1, 40), state, _fails(tries))    # three times are enough
    assert len(tries) == 3
    job = state[f"{COURSE}/{HW}@2026-10-25"]
    assert job["done"] and job["result"] == "נכשלה: Moodle 404"

    state, pulls = {}, []
    scheduler.tick(root, datetime(2026, 10, 25, 0, 5), state, _fails([]))
    scheduler.tick(root, datetime(2026, 10, 25, 0, 35), state, _ok(pulls))      # the second try works
    assert len(pulls) == 1 and state[f"{COURSE}/{HW}@2026-10-25"]["result"] == "ok"


def test_only_the_computer_of_whoever_took_the_pull(root):
    pulls = []
    _due(root, "2026-10-24T23:59:00", owner="יוסי")
    scheduler.tick(root, datetime(2026, 10, 25, 0, 5), {}, _ok(pulls))
    assert not pulls                                                    # someone else's: their computer pulls
    claims.set_task(root / COURSE, claims.task_key(HW, "pull"), False, who="יוסי")
    scheduler.tick(root, datetime(2026, 10, 25, 0, 5), {}, _ok(pulls))
    assert not pulls                                                    # nobody's: nobody pulls by themselves
    claims.set_task(root / COURSE, claims.task_key(HW, "pull"), True, who="מתן")
    scheduler.tick(root, datetime(2026, 10, 25, 0, 5), {}, _ok(pulls))
    assert len(pulls) == 1                                              # mine (GRADER_NAME=מתן)


def test_a_local_copy_never_pulls_at_night(root, tmp_path):
    local = tmp_path / "local" / "Exercise Checking System"
    shutil.copytree(root, local)
    pulls = []
    _due(local, "2026-10-24T23:59:00")
    scheduler.tick(local, datetime(2026, 10, 25, 0, 5), {}, _ok(pulls))
    assert not pulls
