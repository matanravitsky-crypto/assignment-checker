"""Ask Windows' sign-in broker (WAM) for the token OneDrive is stuck on.

OneDrive's silent sign-in to the BGU tenant (Nadav's library) fails with
AADSTS50076 (MFA required) and it never shows the prompt itself, so "Sync" ends in
"Sorry, OneDrive can't add your folder right now". This makes the same request
(OneDrive's client id, BGU tenant, SharePoint) through WAM, so the standard
Microsoft sign-in window appears. The user types the password and approves MFA
themselves; once that is done WAM holds a fresh token and OneDrive's next silent
request succeeds. Fixed it on Matan's PC (2026-11-03) and Noa's (2026-11-05).

No token is printed or saved: only ok/error, the account name and the expiry go to
%LOCALAPPDATA%\\BodekHacham\\onedrive-signin\\last.json (outside the repo).

Setup (once, outside the repo):
    py -3.12 -m venv "%LOCALAPPDATA%\\BodekHacham\\wam-venv"
    "%LOCALAPPDATA%\\BodekHacham\\wam-venv\\Scripts\\python" -m pip install "msal[broker]==1.39.0"
Usage:
    "%LOCALAPPDATA%\\BodekHacham\\wam-venv\\Scripts\\python" wam_signin.py go <university email> [tenant id] [scope]
Modes: go = sign-in window with the email filled in, pick = choose the account, silent = check only.
"""
import ctypes
import json
import os
import sys
import time
from pathlib import Path

import msal

CLIENT = "ab9b8c07-8f02-4f72-87fa-80105867a763"  # OneDrive sync client (public id)
BGU_TENANT = "49470515-677a-4fbe-8686-afae308fe867"  # BGU, hosts bgu365 SharePoint
BGU_SCOPE = "https://bgu365-my.sharepoint.com/.default"
OUT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BodekHacham" / "onedrive-signin" / "last.json"


def summary(result):
    if not result:
        return {"ok": False, "error": "no result"}
    if "access_token" in result:
        return {"ok": True, "expires_in": result.get("expires_in"),
                "account": (result.get("id_token_claims") or {}).get("preferred_username")}
    return {"ok": False, "error": result.get("error"),
            "codes": result.get("error_codes"),
            "description": (result.get("error_description") or "")[:300]}


def main(mode, user, tenant=BGU_TENANT, scope=BGU_SCOPE):
    app = msal.PublicClientApplication(
        CLIENT, authority=f"https://login.microsoftonline.com/{tenant}",
        enable_broker_on_windows=True)
    accounts = app.get_accounts(username=user)
    print("accounts:", len(accounts), flush=True)
    if mode == "silent":
        result = app.acquire_token_silent([scope], account=accounts[0]) if accounts else None
    else:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        kwargs = {"prompt": "select_account"} if mode == "pick" else {"login_hint": user}
        result = app.acquire_token_interactive([scope], parent_window_handle=hwnd, **kwargs)
    outcome = summary(result)
    outcome.update(mode=mode, tenant=tenant, scope=scope, at=time.strftime("%Y-%m-%d %H:%M:%S"))
    print(json.dumps({k: v for k, v in outcome.items() if k != "account"}, ensure_ascii=False), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(outcome, ensure_ascii=False), encoding="utf-8")
    if mode == "go":
        if outcome["ok"]:
            text = "ההתחברות הצליחה. עכשיו אפשר ללחוץ שוב על Sync בתיקייה של נדב."
        else:
            text = "ההתחברות לא הושלמה: " + str(outcome.get("error")) + "\nאפשר לנסות שוב."
        ctypes.windll.user32.MessageBoxW(0, text, "חיבור OneDrive ל-BGU", 0x40 | 0x40000)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: python wam_signin.py <go|pick|silent> <university email> [tenant id] [scope]")
    main(*sys.argv[1:5])
