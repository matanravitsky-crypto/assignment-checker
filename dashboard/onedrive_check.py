"""האם OneDrive באמת מסנכרן את התיקייה במחשב הזה? בשביל הכפתור "סנכרון" באתר (POST /api/refresh).

המערכת לא מדברת עם OneDrive דרך האינטרנט: היא קוראת את התיקייה המסונכרנת. אז מה שהאתר מציג נכון רק כש-OneDrive
עצמו עובד. כאן בודקים את הדברים שכבר תקעו אותו:
- התיקייה לא בתוך OneDrive (עותק מקומי, כמו אצל אורי): שום דבר לא מגיע אליה מהענן לבד.
- האפליקציה לא רצה (OneDrive.exe): מפעילים אותה ברקע.
- האוניברסיטה דורשת אימות דו-שלבי (AADSTS50076 ביומן AAD של Windows, 2026-11-02): OneDrive לא מצליח להתחבר,
  לא מראה חלון ולא מסנכרן כלום. כל עוד זה כך השגיאה חוזרת כל 2-11 דקות. רק אדם יכול להתחבר (הקיצור
  "חיבור OneDrive BGU" בשולחן העבודה).
- קבצים שנכתבו כאן ועוד לא עלו לענן (Cloud Files API: קובץ ש-OneDrive עוד לא לקח, או שהשתנה ועוד לא עלה).
  שאר הצוות יראה אותם רק אחרי שיעלו. קובץ חדש עולה בדרך כלל תוך כמה שניות.
הכל ב-Windows בלבד. במקום אחר (CI) התשובה היא "לא ידוע" (None), ושום דבר לא נכשל בגלל זה.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

SIGNIN_MINUTES = 20   # שגיאת 50076 בזמן הזה = OneDrive תקוע עכשיו (כשהוא תקוע היא חוזרת כל 2-11 דקות)
MFA_ERROR = "50076"
AAD_LOG = "Microsoft-Windows-AAD/Operational"
EXAMPLES = 5          # כמה קבצים שעוד לא עלו מציגים בשמם (רק מספרים ושמות תיקיות, אין שם שמות של סטודנטים)

# Cloud Files API (cldapi.dll)
_S_OK = 0
_MORE_DATA = 0x800700EA          # FileIdentity לא נכנס בחוצץ. השדות שלפניו (InSyncState) כבר מולאו
_NOT_A_CLOUD_FILE = 0x80070178   # OneDrive עוד לא לקח את הקובץ
_NOT_A_SYNC_ROOT = 0x80070186
_IN_SYNC = 1                     # CF_IN_SYNC_STATE_IN_SYNC
_FILE_READ_ATTRIBUTES = 0x80     # רק התכונות: לא מוריד מהענן קובץ שנמצא רק שם
_OPEN_EXISTING = 3
_FLAGS = 0x02000000 | 0x00200000  # FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT
_NO_WINDOW = 0x08000000           # CREATE_NO_WINDOW
_DETACHED = 0x00000008            # DETACHED_PROCESS


def _run(args: list[str], timeout: float = 15) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=_NO_WINDOW)


def running() -> bool | None:
    """האם OneDrive.exe רץ במחשב."""
    if sys.platform != "win32":
        return None
    try:
        out = _run(["tasklist", "/FI", "IMAGENAME eq OneDrive.exe", "/NH", "/FO", "CSV"]).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return "onedrive.exe" in out.lower()


def exe() -> Path | None:
    """איפה מותקן OneDrive (התקנה למשתמש, או לכל המחשב)."""
    bases = [(os.environ.get("LOCALAPPDATA"), "Microsoft/OneDrive"),
             (os.environ.get("ProgramFiles"), "Microsoft OneDrive"),
             (os.environ.get("ProgramFiles(x86)"), "Microsoft OneDrive")]
    for base, sub in bases:
        if base and (p := Path(base) / sub / "OneDrive.exe").is_file():
            return p
    return None


def start() -> bool:
    """מפעיל את OneDrive ברקע, בלי חלון. True אם הופעל."""
    path = exe()
    if sys.platform != "win32" or not path:
        return False
    try:
        subprocess.Popen([str(path), "/background"], creationflags=_DETACHED | _NO_WINDOW, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True


def needs_signin() -> bool | None:
    """האם האוניברסיטה דחתה את OneDrive כי צריך אימות דו-שלבי (AADSTS50076) בדקות האחרונות."""
    if sys.platform != "win32":
        return None
    query = f"*[System[(EventID=1098) and TimeCreated[timediff(@SystemTime) <= {SIGNIN_MINUTES * 60_000}]]]"
    try:
        r = _run(["wevtutil", "qe", AAD_LOG, f"/q:{query}", "/f:text", "/c:100", "/rd:true"])
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return MFA_ERROR in r.stdout


class _CloudFiles:
    """עטיפה קטנה ל-cldapi.dll: האם תיקייה בתוך OneDrive, והאם קובץ כבר עלה."""

    def __init__(self):
        from ctypes import wintypes
        self.w = wintypes
        self.cf = ctypes.WinDLL("cldapi.dll")
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k32.CreateFileW.restype = wintypes.HANDLE
        self.k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self.k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.cf.CfGetPlaceholderInfo.restype = ctypes.c_long
        self.cf.CfGetPlaceholderInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                                 ctypes.POINTER(wintypes.DWORD)]
        self.cf.CfGetSyncRootInfoByPath.restype = ctypes.c_long
        self.cf.CfGetSyncRootInfoByPath.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                                    ctypes.POINTER(wintypes.DWORD)]
        self.buf = ctypes.create_string_buffer(4096)
        self.n = wintypes.DWORD()

    def synced(self, folder: Path) -> bool | None:
        hr = self.cf.CfGetSyncRootInfoByPath(str(folder), 0, self.buf, len(self.buf), ctypes.byref(self.n)) & 0xFFFFFFFF
        return True if hr in (_S_OK, _MORE_DATA) else False if hr == _NOT_A_SYNC_ROOT else None

    def in_sync(self, file: Path) -> bool | None:
        h = self.k32.CreateFileW(str(file), _FILE_READ_ATTRIBUTES, 7, None, _OPEN_EXISTING, _FLAGS, None)
        if h in (None, self.w.HANDLE(-1).value):
            return None  # נמחק בינתיים, או נעול
        try:
            hr = self.cf.CfGetPlaceholderInfo(h, 0, self.buf, len(self.buf), ctypes.byref(self.n)) & 0xFFFFFFFF
        finally:
            self.k32.CloseHandle(h)
        if hr == _NOT_A_CLOUD_FILE:
            return False
        if hr in (_S_OK, _MORE_DATA):  # CF_PLACEHOLDER_BASIC_INFO: PinState, ואחריו InSyncState
            return int.from_bytes(self.buf.raw[4:8], "little") == _IN_SYNC
        return None


def _cloud_files() -> _CloudFiles | None:
    if sys.platform != "win32":
        return None
    try:
        return _CloudFiles()
    except (OSError, AttributeError):
        return None


def _files(folders: Iterable[Path]) -> Iterable[Path]:
    for folder in folders:
        try:
            with os.scandir(folder) as it:
                entries = [Path(e.path) for e in it if e.is_file(follow_symlinks=False)]
        except OSError:
            continue
        yield from entries


def status(root: Path, folders: Iterable[Path], start_if_stopped: bool = True) -> dict:
    """מצב OneDrive בשביל התיקייה root. folders: התיקיות שהאתר נבנה מהן (בודקים בהן מה עוד לא עלה).

    synced: התיקייה בתוך OneDrive (False = עותק מקומי). running: OneDrive.exe רץ (started: הופעל עכשיו).
    signin: צריך להתחבר מחדש (אימות דו-שלבי). pending: כמה קבצים מכאן עוד לא עלו לענן, pendingFiles: כמה מהם.
    None בכל אחד מהם = לא ידוע (לא Windows, או שהבדיקה עצמה לא הצליחה)."""
    cloud = _cloud_files()
    synced = cloud.synced(root) if cloud else None
    out: dict = {"synced": synced, "running": None, "started": False, "signin": None, "pending": None, "pendingFiles": []}
    if synced is False:
        return out  # עותק מקומי: OneDrive לא קשור לתיקייה הזו
    out["running"] = running()
    if out["running"] is False and start_if_stopped:
        out["started"] = start()
    out["signin"] = needs_signin()
    if cloud and synced:
        pending = [f for f in _files(folders) if cloud.in_sync(f) is False]
        out["pending"] = len(pending)
        out["pendingFiles"] = [f.relative_to(root).as_posix() for f in pending[:EXAMPLES]]
    return out
