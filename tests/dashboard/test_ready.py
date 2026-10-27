"""Tests for "is this computer ready to upload": readiness, the Chrome check, login and install.

Everything here is a fake: no test starts `claude`, an installer or a login.
"""
from __future__ import annotations

import time

import pytest

from dashboard import actions
from moodle import claude_driver
from tests.fakes import FakeDriver
from tests.dashboard.helpers import BODY, COURSE, HDR, HW, call, mark

OK = {"chrome": True, "moodle": True, "message": "Chrome ו-Moodle מוכנים.", "answered": True}


class FakeChrome:
    """Stands in for ClaudeChromeDriver: counts the checks."""
    calls = 0
    answer = OK

    def check(self, info):
        type(self).calls += 1
        return type(self).answer


@pytest.fixture
def chrome(monkeypatch):
    FakeChrome.calls, FakeChrome.answer = 0, OK
    monkeypatch.setattr(claude_driver, "ClaudeChromeDriver", FakeChrome)
    return FakeChrome


@pytest.fixture
def logged_in(monkeypatch):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "C:/x/claude.exe")
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": True, "message": "Claude Code מחובר."})


class FakeProc:
    """A background process that never really started."""
    made: list = []

    def __init__(self, cmd, **kwargs):
        self.cmd, self.kwargs, self.alive, self.killed = cmd, kwargs, True, False
        FakeProc.made.append(self)

    def poll(self):
        return None if self.alive else 0

    def kill(self):
        self.alive, self.killed = False, True


@pytest.fixture
def popen(monkeypatch):
    FakeProc.made = []
    monkeypatch.setattr(actions.subprocess, "Popen", FakeProc)
    return FakeProc


# ---------- readiness ----------
def test_readiness_without_claude_is_fast_and_never_checks(root, monkeypatch, chrome):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: None)
    out = actions.readiness(root, COURSE, HW)
    assert out["installed"] is False and out["logged_in"] is False
    assert out["chrome"] is None and out["moodle"] is None and out["checked_at"] is None
    assert out["message"] == claude_driver.NOT_INSTALLED
    assert chrome.calls == 0


def test_readiness_not_logged_in(root, monkeypatch, chrome):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "C:/x/claude.exe")
    out = actions.readiness(root, COURSE, HW)  # conftest: auth_status says logged out
    assert (out["installed"], out["logged_in"], out["chrome"]) == (True, False, None)
    assert chrome.calls == 0


def test_readiness_does_not_start_a_chrome_check_and_uses_the_cache(root, logged_in, chrome):
    first = actions.readiness(root, COURSE, HW)
    assert (first["logged_in"], first["chrome"], first["moodle"]) == (True, None, None) and chrome.calls == 0
    checked = actions.check_ready(root, COURSE, HW)
    assert chrome.calls == 1
    assert (checked["chrome"], checked["moodle"]) == (True, True) and checked["checked_at"]
    again = actions.readiness(root, COURSE, HW)
    assert (again["chrome"], again["moodle"], again["checked_at"]) == (True, True, checked["checked_at"])
    assert chrome.calls == 1  # the second call did not start a check


def test_readiness_cache_expires_after_30_minutes_and_is_per_assignment(root, logged_in, chrome, monkeypatch):
    now = [5000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    actions.check_ready(root, COURSE, HW)
    now[0] += 29 * 60
    assert actions.readiness(root, COURSE, HW)["chrome"] is True
    now[0] += 2 * 60
    out = actions.readiness(root, COURSE, HW)
    assert out["chrome"] is None and out["moodle"] is None and out["checked_at"] is None
    assert chrome.calls == 1


def test_an_answered_no_is_remembered_with_its_message(root, logged_in, chrome):
    chrome.answer = {"chrome": False, "moodle": False, "message": "הכלים של Chrome לא עבדו.", "answered": True}
    out = actions.check_ready(root, COURSE, HW)
    assert (out["chrome"], out["moodle"], out["message"]) == (False, False, "הכלים של Chrome לא עבדו.")
    assert "check_error" not in out
    assert actions.readiness(root, COURSE, HW)["chrome"] is False  # a real answer stays for 30 minutes


def test_a_failed_check_is_not_remembered_and_its_message_comes_back(root, logged_in, chrome):
    chrome.answer = {"chrome": False, "moodle": False, "message": "Claude Code לא הצליח לרוץ (TimeoutExpired)."}
    out = actions.check_ready(root, COURSE, HW)
    assert (out["chrome"], out["moodle"], out["checked_at"]) == (None, None, None)
    assert out["check_error"] == "Claude Code לא הצליח לרוץ (TimeoutExpired)."
    assert actions.readiness(root, COURSE, HW)["chrome"] is None  # nothing cached: the next click checks again
    chrome.answer = OK
    assert actions.check_ready(root, COURSE, HW)["chrome"] is True and chrome.calls == 2


def test_a_check_that_finds_claude_logged_out_drops_the_status_cache(root, logged_in, chrome, monkeypatch):
    assert actions.moodle_status()["logged_in"] is True
    chrome.answer = {"chrome": False, "moodle": False, "message": claude_driver.NOT_LOGGED_IN}
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": False, "message": claude_driver.NOT_LOGGED_IN})
    assert actions.check_ready(root, COURSE, HW)["logged_in"] is False


def test_readiness_of_a_missing_assignment(root):
    with pytest.raises(FileNotFoundError):
        actions.readiness(root, COURSE, "../../Recordings")


def test_not_logged_in_hides_an_old_chrome_result(root, logged_in, chrome, monkeypatch):
    actions.check_ready(root, COURSE, HW)
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": False, "message": claude_driver.NOT_LOGGED_IN})
    actions._moodle_cache = None
    out = actions.readiness(root, COURSE, HW)
    assert (out["logged_in"], out["chrome"], out["moodle"]) == (False, None, None)


# ---------- the check and an upload never run together ----------
def test_check_ready_is_refused_while_an_upload_runs(root, logged_in, chrome):
    actions._send.running = True
    with pytest.raises(RuntimeError, match="העלאה אחרת כבר רצה."):
        actions.check_ready(root, COURSE, HW)
    with pytest.raises(RuntimeError):
        actions.check_moodle(root, COURSE, HW)
    assert chrome.calls == 0


def test_an_upload_cannot_start_during_a_check(root):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    actions._checking = True
    with pytest.raises(RuntimeError, match="החיבור"):
        actions.start_send(root, COURSE, HW, rep["id"], driver=FakeDriver(), wait=True)
    assert not actions.send_status()["running"]


def test_the_check_flag_is_released_even_if_the_check_explodes(root, monkeypatch):
    class Boom:
        def check(self, info):
            raise OSError("x")
    monkeypatch.setattr(claude_driver, "ClaudeChromeDriver", Boom)
    with pytest.raises(OSError):
        actions.check_moodle(root, COURSE, HW)
    assert actions._checking is False


def test_server_check_endpoints_return_409_while_an_upload_runs(root, server, logged_in, chrome):
    actions._send.running = True
    for path in ("/api/moodle/check", "/api/ready/check"):
        st, err = call(server, "POST", path, BODY, HDR)
        assert st == 409 and err["error"] == "העלאה אחרת כבר רצה."
    actions._send.running = False
    st, rep = call(server, "POST", "/api/ready/check", BODY, HDR)
    assert st == 200 and (rep["chrome"], rep["moodle"], rep["logged_in"]) == (True, True, True)
    assert call(server, "POST", "/api/moodle/check", BODY, HDR)[1]["chrome"] is True


# ---------- login and install: one background process at a time ----------
def test_login_spawns_one_process_and_refuses_a_second(monkeypatch, popen):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "C:/x/claude.exe")
    out = actions.start_claude_login()
    assert out["started"] is True and out["message"]
    assert len(popen.made) == 1
    proc = popen.made[0]
    assert proc.cmd == ["C:/x/claude.exe", "auth", "login"]  # no --email: everyone signs in with their own account
    assert proc.kwargs["stdin"] is actions.subprocess.DEVNULL
    again = actions.start_claude_login()
    assert again["started"] is False and again["running"] is True and len(popen.made) == 1
    proc.alive = False  # the person finished signing in: the process exited by itself
    assert actions.start_claude_login()["started"] is True and len(popen.made) == 2


def test_login_retry_replaces_the_running_process(monkeypatch, popen):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    actions.start_claude_login()
    first = popen.made[0]
    assert actions.start_claude_login(restart=True)["started"] is True
    assert first.killed and len(popen.made) == 2 and popen.made[1].alive


def test_login_without_claude_installed_starts_nothing(monkeypatch, popen):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: None)
    out = actions.start_claude_login()
    assert out["started"] is False and out["message"] == claude_driver.NOT_INSTALLED and popen.made == []


def test_login_that_cannot_start_says_so(monkeypatch):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")

    def broken(*a, **k):
        raise OSError("no such file")
    monkeypatch.setattr(actions.subprocess, "Popen", broken)
    out = actions.start_claude_login()
    assert out["started"] is False and "no such file" in out["message"]


def test_a_login_that_runs_too_long_is_killed(monkeypatch, popen):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    monkeypatch.setattr(actions._login, "minutes", 0.0005)  # about 30 ms
    actions.start_claude_login()
    proc = popen.made[0]
    end = time.time() + 3
    while not proc.killed and time.time() < end:
        time.sleep(0.01)
    assert proc.killed
    assert actions.start_claude_login()["started"] is True  # and a new one can start


def test_login_in_progress_bypasses_the_status_cache(root, monkeypatch, popen):
    state = {"logged_in": False, "calls": 0}

    def status(*a, **k):
        state["calls"] += 1
        return {"logged_in": state["logged_in"], "message": "x"}
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    monkeypatch.setattr(claude_driver, "auth_status", status)
    assert actions.moodle_status()["logged_in"] is False
    assert actions.moodle_status()["logged_in"] is False and state["calls"] == 1  # cached for a minute
    actions.start_claude_login()  # clears the cache and, while it runs, every call asks again
    state["logged_in"] = True  # the person signed in
    out = actions.readiness(root, COURSE, HW)
    assert out["logged_in"] is True and out["login_running"] is True
    calls = state["calls"]
    actions.readiness(root, COURSE, HW)
    assert state["calls"] == calls + 1


def test_install_spawns_the_official_installer_once(monkeypatch, popen):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: None)
    out = actions.start_claude_install()
    assert out["started"] is True and len(popen.made) == 1
    assert popen.made[0].cmd == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                                 "irm https://claude.ai/install.ps1 | iex"]
    again = actions.start_claude_install()
    assert again["started"] is False and again["running"] is True and len(popen.made) == 1


def test_install_is_not_run_when_claude_is_already_there(monkeypatch, popen):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    out = actions.start_claude_install()
    assert out["started"] is False and popen.made == []


def test_readiness_sees_a_fresh_install_without_waiting_for_the_status_cache(root, monkeypatch):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: None)
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: (
        {"logged_in": False, "message": claude_driver.NOT_INSTALLED} if claude_driver.find_claude() is None
        else {"logged_in": False, "message": claude_driver.NOT_LOGGED_IN}))
    actions.moodle_status()  # cached: "not installed"
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "C:/x/claude.exe")  # the installer finished
    out = actions.readiness(root, COURSE, HW)
    assert out["installed"] is True and out["message"] == claude_driver.NOT_LOGGED_IN


def test_installing_and_login_running_show_in_readiness(root, monkeypatch, popen):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: None)
    actions.start_claude_install()
    assert actions.readiness(root, COURSE, HW)["installing"] is True
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    actions.start_claude_login()
    assert actions.readiness(root, COURSE, HW)["login_running"] is True


# ---------- the server ----------
def test_server_ready_endpoint(root, server, logged_in):
    st, rep = call(server, "GET", f"/api/ready?course={COURSE.replace(' ', '%20')}&assignment={HW.replace(' ', '%20')}")
    assert st == 200 and rep["installed"] is True and rep["logged_in"] is True and rep["chrome"] is None
    assert call(server, "GET", "/api/ready")[0] == 400
    assert call(server, "GET", f"/api/ready?course={COURSE.replace(' ', '%20')}&assignment=nope")[0] == 404


def test_server_login_and_install_endpoints(root, server, monkeypatch, popen):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    st, rep = call(server, "POST", "/api/claude/login", {}, HDR)
    assert st == 200 and rep["started"] is True and len(popen.made) == 1
    st, rep = call(server, "POST", "/api/claude/login", {}, HDR)
    assert rep["started"] is False and len(popen.made) == 1
    st, rep = call(server, "POST", "/api/claude/login", {"restart": True}, HDR)
    assert rep["started"] is True and len(popen.made) == 2
    st, rep = call(server, "POST", "/api/claude/install", {}, HDR)
    assert st == 200 and rep["started"] is False  # already installed: nothing to run


def test_server_ready_posts_need_the_header_and_a_local_origin(root, server, popen):
    for path in ("/api/ready/check", "/api/claude/login", "/api/claude/install"):
        assert call(server, "POST", path, BODY)[0] == 403
        assert call(server, "POST", path, BODY, {**HDR, "Origin": "https://evil.example"})[0] == 403
    assert popen.made == []


def test_server_ready_check_errors(root, server, logged_in, chrome):
    assert call(server, "POST", "/api/ready/check", {"course": COURSE}, HDR)[0] == 400
    assert call(server, "POST", "/api/ready/check", {**BODY, "assignment": "nope"}, HDR)[0] == 404


# ---------- a login or install that just ended ----------
def test_a_login_that_just_ended_asks_auth_again_at_once(root, monkeypatch, popen):
    state = {"logged_in": False}
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": state["logged_in"], "message": "x"})
    actions.start_claude_login()
    proc = popen.made[0]
    out = actions.readiness(root, COURSE, HW)  # while it runs: "not logged in" gets stored
    assert (out["logged_in"], out["login_running"]) == (False, True)
    state["logged_in"] = True  # the person authorized, and `claude auth login` exited
    proc.alive = False
    out = actions.readiness(root, COURSE, HW)  # well under 60 s later
    assert (out["logged_in"], out["login_running"]) == (True, False)


def test_the_status_cache_is_dropped_only_once_per_ended_process(root, monkeypatch, popen):
    calls = []
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: calls.append(1) or {"logged_in": True, "message": "x"})
    actions.start_claude_login()  # (auth_status is asked once here, and says logged in: nothing starts)
    calls.clear()
    popen.made.clear()
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: calls.append(1) or {"logged_in": False, "message": "x"})
    actions.start_claude_login()
    popen.made[0].alive = False
    actions.moodle_status()
    n = len(calls)
    actions.moodle_status()
    actions.moodle_status()
    assert len(calls) == n  # the ended process is reported once, then the cache works again


def test_an_install_that_just_ended_is_seen_at_once(root, monkeypatch, popen):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: None)
    actions.start_claude_install()
    assert actions.readiness(root, COURSE, HW)["installing"] is True
    popen.made[0].alive = False
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "C:/x/claude.exe")
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": True, "message": "x"})
    out = actions.readiness(root, COURSE, HW)
    assert (out["installed"], out["installing"], out["logged_in"]) == (True, False, True)


def test_login_is_refused_when_already_logged_in(monkeypatch, popen):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": True, "message": "x"})
    out = actions.start_claude_login()
    assert out["started"] is False and out["message"] == "כבר מחובר ל-Claude." and popen.made == []
    assert actions.start_claude_login(restart=True)["started"] is False and popen.made == []


def test_time_limits_login_ten_minutes_install_twenty():
    assert (actions._login.minutes, actions._install.minutes) == (10, 20)


def test_login_and_install_endpoints_do_not_need_the_shared_folder(root, server, monkeypatch, popen, tmp_path):
    monkeypatch.setenv("ASSIGNMENT_CHECKER_ROOT", str(tmp_path / "does-not-exist"))
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    assert call(server, "POST", "/api/upload/stop", {}, HDR)[0] == 503  # a call that does need it
    st, rep = call(server, "POST", "/api/claude/login", {}, HDR)
    assert st == 200 and rep["started"] is True
    assert call(server, "POST", "/api/claude/install", {}, HDR)[0] == 200
