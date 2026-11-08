"""The system updates itself from GitHub while it runs (dashboard/updater.py), but never in the middle of work, never on
a checkout someone develops in, and only when autostart.vbs is there to bring it back."""
from __future__ import annotations

import threading
import time

import pytest

from dashboard import actions, scheduler, updater
from tests.dashboard.helpers import call

HEAD, NEW = "a" * 40, "b" * 40


class Git:
    """git in the tests: answers by the first argument, records every call. A value of None is a failed command."""

    def __init__(self, **answers):
        self.answers = {"rev-parse --abbrev-ref HEAD": "main", "status": "", "fetch": "", "rev-parse origin/main": NEW,
                        "rev-parse HEAD": HEAD, "merge-base": "", **answers}
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        line = " ".join(args)
        for key in sorted(self.answers, key=len, reverse=True):
            if line.startswith(key):
                return self.answers[key]
        raise AssertionError(f"unexpected git {line}")


def test_an_update_waits_when_main_moved_forward():
    assert updater.waiting_update(git=Git()) == NEW


@pytest.mark.parametrize("answers, why", [
    ({"rev-parse --abbrev-ref HEAD": "pull-for-everyone"}, "another branch: someone develops here"),
    ({"status": " M dashboard/actions.py"}, "edited files: git pull would fail or lose them"),
    ({"status": None}, "git itself failed"),
    ({"fetch": None}, "no network"),
    ({"rev-parse origin/main": HEAD}, "nothing new"),
    ({"merge-base": None}, "the history went apart: git pull --ff-only would fail"),
])
def test_no_update_when_this_checkout_should_not_move(answers, why):
    assert updater.waiting_update(git=Git(**answers)) is None, why


def test_tick_stops_only_when_idle_and_the_watchdog_brings_it_back():
    waiting, never = (lambda: NEW), (lambda target: False)
    assert updater.tick(lambda: [], waiting=waiting, watchdog=lambda: True, tried=never) == (NEW, 0)
    # a pull (or grading, an upload, a night pull...) runs: look again in a few minutes
    assert updater.tick(lambda: ["pull"], waiting=waiting, watchdog=lambda: True, tried=never) == (None, updater.BUSY_RETRY_S)
    # started by hand (start.bat in a window, a test server): nobody would start it again
    assert updater.tick(lambda: [], waiting=waiting, watchdog=lambda: False, tried=never) == (None, updater.check_s())
    # nothing new on GitHub
    assert updater.tick(lambda: [], waiting=lambda: None, watchdog=lambda: True, tried=never) == (None, updater.check_s())


def test_an_update_that_did_not_take_is_not_tried_again():
    """start.bat's git pull failed and the same old version came up: stopping again every hour would only cut the site."""
    assert updater.tick(lambda: [], waiting=lambda: NEW, watchdog=lambda: True,
                        tried=lambda target: target == NEW) == (None, updater.check_s())


def test_the_try_is_remembered_on_this_computer(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_state_path", lambda: tmp_path / "work" / updater.STATE_FILE)
    monkeypatch.setattr(updater, "_version", "aaaaaaa")
    assert not updater.tried(NEW)
    updater.remember_try(NEW)
    assert updater.tried(NEW) and not updater.tried(HEAD)


def test_check_interval_comes_from_env(monkeypatch):
    monkeypatch.setenv("UPDATE_CHECK_MINUTES", "90")
    assert updater.check_s() == 90 * 60
    monkeypatch.setenv("UPDATE_CHECK_MINUTES", "1")
    assert updater.check_s() == 5 * 60  # not more often than every 5 minutes
    monkeypatch.setenv("UPDATE_CHECK_MINUTES", "soon")
    assert updater.check_s() == 60 * 60


def test_start_only_on_the_watched_port_and_when_on(monkeypatch):
    assert updater.start(8768, lambda: None, threading.Lock(), list) is None  # a test server never stops itself
    monkeypatch.setenv("AUTO_UPDATE", "off")
    assert updater.start(updater.WATCHED_PORT, lambda: None, threading.Lock(), list) is None


def _run_loop(monkeypatch, tick, lock):
    monkeypatch.setattr(updater, "FIRST_CHECK_S", 0.01)
    monkeypatch.setattr(updater, "check_s", lambda: 0.01)
    monkeypatch.setattr(updater, "BUSY_RETRY_S", 0.01)
    monkeypatch.setattr(updater, "tick", tick)
    monkeypatch.setattr(updater, "remember_try", lambda target: None)
    monkeypatch.setattr(updater, "_version", "test")
    stopped = threading.Event()
    t = updater.start(updater.WATCHED_PORT, stopped.set, lock, list)
    return t, stopped


def test_the_server_stops_holding_the_buttons_lock(monkeypatch):
    """From the last check to the end of the process no pull can start: the lock stays taken."""
    lock = threading.Lock()
    t, stopped = _run_loop(monkeypatch, lambda busy: (NEW, 0), lock)
    assert stopped.wait(5)
    t.join(5)
    assert not t.is_alive() and lock.locked()


def test_a_button_in_progress_puts_the_update_off(monkeypatch):
    lock, ticks = threading.Lock(), []
    lock.acquire()  # a pull runs (web_server holds the lock for the whole POST /api/pull)
    t, stopped = _run_loop(monkeypatch, lambda busy: ticks.append(1) or (NEW, 0), lock)
    time.sleep(0.2)
    assert not ticks and not stopped.is_set()  # never even looked while the button ran
    lock.release()
    assert stopped.wait(5)


def test_a_failed_check_never_keeps_the_lock(monkeypatch):
    lock, calls = threading.Lock(), []

    def tick(busy):
        calls.append(1)
        raise RuntimeError("git exploded")

    _run_loop(monkeypatch, tick, lock)
    deadline = time.time() + 5
    while len(calls) < 3 and time.time() < deadline:
        time.sleep(0.01)
    assert len(calls) >= 3  # it keeps checking
    assert lock.acquire(timeout=1)  # and the buttons still work
    lock.release()


def test_running_jobs_lists_what_runs(monkeypatch):
    assert actions.running_jobs() == []
    monkeypatch.setattr(actions._pull, "running", True)
    monkeypatch.setattr(actions, "_checking", True)
    assert actions.running_jobs() == ["pull", "chrome check"]


def test_night_window_follows_the_scheduler(monkeypatch):
    monkeypatch.setattr(scheduler, "_awake", True)
    assert scheduler.in_night_window()


def test_the_site_gets_the_version_with_every_change_check(server, monkeypatch):
    """The site reloads itself when the version changes: the server came back updated."""
    monkeypatch.setattr(updater, "_version", "abc1234")
    st, body = call(server, "GET", "/api/changes")
    assert st == 200 and body["version"] == "abc1234" and body["sig"]
    assert call(server, "GET", "/api/health")[1]["version"] == "abc1234"
