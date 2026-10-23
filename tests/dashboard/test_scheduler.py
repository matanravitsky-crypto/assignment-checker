"""Scheduled pull: the day is the due date, a warning half an hour before, the pull at 22:00."""
import json
from datetime import datetime

import pytest

from dashboard import scheduler
from moodle import paths

from tests.dashboard.helpers import COURSE, HW


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(scheduler, "notify", lambda t, m: sent.append(t))
    monkeypatch.setattr(scheduler, "_save", lambda state: None)
    monkeypatch.setenv("SCHEDULE_PULL_TIME", "00:05")
    monkeypatch.setenv("SCHEDULE_WARN_MIN", "30")
    return sent


def _due(root, iso):
    f = root / COURSE / HW / paths.INFO
    d = json.loads(f.read_text(encoding="utf-8"))
    d["due"] = iso
    f.write_text(json.dumps(d), encoding="utf-8")


def test_warns_then_pulls_once(root, quiet):
    _due(root, "2026-10-24T23:59:00")
    pulls, state = [], {}
    run = lambda c, a: pulls.append((c, a)) or "ok"

    assert scheduler.tick(root, datetime(2026, 10, 24, 22, 0), state, run) is False   # too early
    assert scheduler.tick(root, datetime(2026, 10, 24, 23, 35), state, run) is True   # warning, stays awake
    assert quiet == ["בודק חכם: משיכה ב-00:05"] and not pulls
    scheduler.tick(root, datetime(2026, 10, 24, 23, 50), state, run)
    assert len(quiet) == 1                                                            # warned once
    scheduler.tick(root, datetime(2026, 10, 25, 0, 5), state, run)
    assert pulls == [(COURSE, HW)]
    scheduler.tick(root, datetime(2026, 10, 25, 0, 6), state, run)
    assert len(pulls) == 1                                                            # once


def test_outside_the_window_does_nothing(root):
    _due(root, "2026-10-24T23:59:00")
    pulls = []
    run = lambda c, a: pulls.append(1) or "ok"
    scheduler.tick(root, datetime(2026, 10, 24, 12, 0), {}, run)    # before the window
    scheduler.tick(root, datetime(2026, 10, 25, 3, 30), {}, run)    # more than 3 hours late
    assert not pulls
    scheduler.tick(root, datetime(2026, 10, 25, 2, 0), {}, run)     # PC started late, inside catch-up: pulls
    assert len(pulls) == 1


def test_failed_pull_is_reported_not_retried(root, quiet):
    _due(root, "2026-10-24T23:59:00")
    state = {}

    def boom(c, a):
        raise RuntimeError("no chrome")

    scheduler.tick(root, datetime(2026, 10, 25, 0, 5), state, boom)
    scheduler.tick(root, datetime(2026, 10, 25, 0, 10), state, boom)
    assert quiet.count("בודק חכם: הגשה 0 - קבוצות ומרוכבים") == 1
    assert next(iter(state.values()))["result"] == "נכשלה: no chrome"
