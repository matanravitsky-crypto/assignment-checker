"""A lock file in the shared folder, so two people don't run the same step on one assignment at once.

The lock is a small text file that says who took it: "<user> (<host>) pid=<pid>". Its modification time says since
when: a lock that was not refreshed for LOCK_MINUTES counts as stuck (a crashed run) and is ignored. Pull and
upload use it, each with its own file name.

The pid keeps two programs of the same person on the same computer apart (say the CLI and the dashboard): a fresh
lock of mine held by another process that is still alive counts as locked too. A lock written before the pid was
added ("<user> (<host>)") still works: someone else's blocks, my own does not. Messages show who without the pid.
"""

import getpass
import os
import re
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path

LOCK_MINUTES = 30
SOMEONE_ELSE = "מישהו אחר"  # shown when the lock file is empty
PID_SUFFIX = re.compile(r"\s+pid=(\d+)\s*$")


class Locked(Exception):
    """Someone else holds a fresh lock. `who` is what their lock file says (without the pid), `since` its last update."""

    def __init__(self, who: str, since: datetime):
        super().__init__(f"locked by {who} since {since:%H:%M}")
        self.who = who
        self.since = since


def me() -> str:
    """Who I am, for messages and for the "by" column of the upload log: "<user> (<host>)"."""
    return f"{getpass.getuser()} ({socket.gethostname()})"


def my_text() -> str:
    """What my lock file says: me() and this process."""
    return f"{me()} pid={os.getpid()}"


def parse(text: str) -> tuple[str, int | None]:
    """Lock text -> (who to show, pid or None). Old text without a pid gives None; empty text gives SOMEONE_ELSE."""
    text = text.strip()
    match = PID_SUFFIX.search(text)
    pid = int(match.group(1)) if match else None
    who = (text[:match.start()] if match else text).strip()
    return who or SOMEONE_ELSE, pid


def pid_alive(pid: int) -> bool:
    """Is process `pid` running on this computer? When unsure, say yes (a lock then waits instead of being shared)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        process_query_limited_information, still_active, access_denied = 0x1000, 259, 5
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return ctypes.get_last_error() == access_denied  # it exists, we just may not look at it
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def blocks_me(who: str, pid: int | None) -> bool:
    """Does a fresh lock with this text keep me out? Someone else's always does; mine only from another live process."""
    if who != me():
        return True
    return pid is not None and pid != os.getpid() and pid_alive(pid)


def holder(lock: Path, minutes: int = LOCK_MINUTES) -> tuple[str, datetime] | None:
    """(who, since) of a fresh lock in `lock` that keeps me out, or None (no lock, a stuck one, or my own of a dead process)."""
    try:
        since = datetime.fromtimestamp(lock.stat().st_mtime)
        text = lock.read_text(encoding="utf-8")
    except OSError:
        return None
    if datetime.now() - since >= timedelta(minutes=minutes):
        return None
    who, pid = parse(text)
    return (who, since) if blocks_me(who, pid) else None


def take(folder: Path, name: str, minutes: int = LOCK_MINUTES) -> Path:
    """Write my lock into folder/name. Raises Locked if a fresh lock there keeps me out (see blocks_me)."""
    lock = folder / name
    held = holder(lock, minutes)
    if held:
        raise Locked(*held)
    lock.write_text(my_text(), encoding="utf-8")
    return lock


def refresh(lock: Path) -> None:
    """Write my lock text again so the lock's modification time moves (a long run keeps its lock alive)."""
    lock.write_text(my_text(), encoding="utf-8")
