"""The site's server on a Mac (2026-11-19): installing Claude Code, the self-update's watchdog (a LaunchAgent instead
of autostart.vbs), and Finder's own files, which never go up to the lecturer's OneDrive."""
from __future__ import annotations

import plistlib
import subprocess
from types import SimpleNamespace

import pytest

from dashboard import actions, sync, updater


def test_claude_code_installs_with_anthropics_mac_installer():
    cmd = actions.install_command("darwin")
    assert cmd[0] == "/bin/bash" and "https://claude.ai/install.sh" in cmd[-1]


def test_claude_code_installs_with_anthropics_windows_installer():
    cmd = actions.install_command("win32")
    assert cmd[0] == "powershell" and "https://claude.ai/install.ps1" in cmd[-1]


@pytest.mark.parametrize("name", [".DS_Store", "Linear Algebra/.DS_Store", "Linear Algebra/._0001.pdf"])
def test_finder_files_never_sync(name):
    assert sync.SKIP.search(name)


def test_a_normal_file_still_syncs():
    assert not sync.SKIP.search("Linear Algebra/Assignment 0/1 - Submissions to grade/0001.pdf")


def _agent(home, repo):
    agent = home / "Library" / "LaunchAgents" / f"{updater.LAUNCH_AGENT}.plist"
    agent.parent.mkdir(parents=True)
    agent.write_bytes(plistlib.dumps({"Label": updater.LAUNCH_AGENT, "WorkingDirectory": str(repo)}))
    return agent


def _launchctl(loaded: bool):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0 if loaded else 113, stdout=b"", stderr=b"")
    return run, calls


@pytest.fixture
def mac(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater.Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


def test_watchdog_on_a_mac_is_the_launch_agent_of_this_folder(mac):
    _agent(mac, updater.REPO)
    run, calls = _launchctl(loaded=True)
    assert updater.watchdog_running(run=run)
    assert calls == [["launchctl", "list", updater.LAUNCH_AGENT]]


def test_no_watchdog_when_the_launch_agent_is_not_loaded(mac):
    _agent(mac, updater.REPO)
    run, _ = _launchctl(loaded=False)
    assert not updater.watchdog_running(run=run)


def test_no_watchdog_when_the_launch_agent_runs_another_folder(mac):
    _agent(mac, mac / "another copy")
    run, calls = _launchctl(loaded=True)
    assert not updater.watchdog_running(run=run)
    assert calls == []


def test_no_watchdog_without_a_launch_agent(mac):
    run, _ = _launchctl(loaded=True)
    assert not updater.watchdog_running(run=run)


def test_a_launchctl_that_fails_means_no_watchdog(mac):
    _agent(mac, updater.REPO)

    def run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)
    assert not updater.watchdog_running(run=run)
