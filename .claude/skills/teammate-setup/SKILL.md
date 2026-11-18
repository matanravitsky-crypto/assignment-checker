---
name: teammate-setup
description: Set up a teammate's Windows computer for Bodek Hacham (assignment-checker) end to end and connect it to the lecturer's shared OneDrive folder YallaLinearit, including the BGU OneDrive sync problem ("Add shortcut to My files" fails, "Sorry, OneDrive can't add your folder right now", AADSTS50076, an unfinished OneDrive setup). Use when someone says "תכין את המחשב שלי", "תחבר אותי למערכת", "הסנכרון לוואן דרייב לא עובד", "Add shortcut לא עובד", "אין לי את התיקייה YallaLinearit", "root ריק", or asks to set up a new teammate. Also before grading, every time: "אני מתחיל לבדוק", "המחשב מוכן לבדיקה?", "המערכת מעודכנת?", "הבדיקה נכשלה", "cannot import name", or a teammate about to grade a batch (step 7).
compatibility: Claude Code on the teammate's own Windows computer (the desktop app's Code tab or `claude` in a terminal). Not a cloud or GitHub-only session. Lives in the repo (`.claude/skills/teammate-setup/`): Claude opened in the repo has it, updated with the repo. On a computer without the repo yet, install by unzipping into %USERPROFILE%\.claude\skills\ so this file is %USERPROFILE%\.claude\skills\teammate-setup\SKILL.md.
---

# Teammate setup: the system on this computer, synced with YallaLinearit

Worked end to end on Noa's computer on 2026-11-04/05 (with Matan's Claude over `claude-channel` issue #1).
The OneDrive part is the hard one; everything else is in CLAUDE.md, "Any teammate's computer".

**Talk to the user in Hebrew.** Before every install, say in one sentence what and why. Passwords, MFA codes
and Moodle/OneDrive sign-ins: the user types them; you say what to open and wait. Never print student names,
ID numbers, emails or file contents. Nothing goes up to Moodle from this skill (every upload needs a person's yes, CLAUDE.md).

## 0. Where am I?

If this is not the user's own Windows computer (claude.ai with GitHub, Claude Code on the web, any cloud
session): stop and tell them to open the Claude desktop app → Code, and ask again there.

**Paths:** `<skill>` below is this skill's own folder (the one this SKILL.md is in, wherever it was installed),
so `<skill>\scripts\check.ps1` is next to this file. Use its absolute path.

## 1. Read the state first (read only)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<skill>\scripts\check.ps1"
```
It works before the repo exists too. It prints JSON: software, every clone and which one
the Startup shortcut runs, the dashboard processes, `/api/health`, OneDrive (mounts, first-run, version), OneDrive's
sign-in failures in the AAD log, and whether `GRADER_NAME` is set. Fix what's missing in the order below.
`-Since "<yyyy-MM-dd HH:mm:ss>"` limits the AAD part to events after a moment (use it around a Sync attempt).

## 2. Software

Git, Python 3.12 (`py -3`; the Microsoft Store python doesn't count), 7-Zip (`C:\Program Files\7-Zip\7z.exe`),
Claude Code as a command (`claude --version`; the desktop app alone is not enough, the system runs `claude` itself).
`winget install -e --id Git.Git` / `Python.Python.3.12` / `7zip.7zip`; Claude Code: `irm https://claude.ai/install.ps1 | iex`.
Refresh PATH in the shell after each install.

## 3. The repo, and only one copy of the server

- Use an existing clone (`clones` in the check). With two clones, use the one `autostartRuns` points to and say the
  other exists. `git switch main` then `git pull --ff-only`; local changes: don't touch them, tell the user.
- No clone: `git clone https://github.com/matanravitsky-crypto/assignment-checker "%USERPROFILE%\Bodek Hacham\assignment-checker"`,
  then `cmd /c install-autostart.bat quiet` and wait up to 8 minutes for `/api/health` (log: `%TEMP%\bodek-hacham.log`).
- `.venv\Scripts\python -c "import pymupdf"` must work (Smart App Control blocks it on some computers).
- `health.version` older than `main`, or `claude: false` right after signing in: stop the `dashboard serve` python
  processes; the watchdog starts the right one within a minute. If `dashboardProcesses` shows servers from another
  clone, stop those too, or they may take port 8765 first.

## 4. Claude Code, Chrome, Moodle, name

- `claude auth status`; if not signed in, `claude auth login` in a terminal tab and the user signs in in the browser
  (a wrong account: sign out of it on claude.ai first). Check the email matches the user's without printing it.
- `POST http://127.0.0.1:8765/api/moodle/check` with header `X-Assignment-Checker: 1` and body
  `{"course": "<course folder>", "assignment": "<assignment folder>"}` (UTF-8). `moodle: false` although the user
  says they signed in: they signed in in another Chrome profile. Open `https://moodle.bgu.ac.il/moodle/my/` with
  Claude in Chrome and read `M.cfg.userId` (1 = guest); ask them to sign in in that tab.
- Ask them to turn off Chrome's "Ask where to save each file".
- No `GRADER_NAME` in `.env`: ask their team name in Hebrew, `POST /api/me` `{"name": "..."}` (UTF-8).

## 5. OneDrive: syncing YallaLinearit

The goal: a folder `C:\Users\<user>\BGU\נדב מאיר - YallaLinearit` (B2B sync of Nadav's library into the BGU tenant).
The system finds it by itself (`shared_folder.find_root`); `/api/health` → `root` then ends in
`...\נדב מאיר - YallaLinearit\Exercise Checking System`. No `.env` change and no restart needed, unless `.env` has
`ASSIGNMENT_CHECKER_ROOT`/`ASSIGNMENT_DATA` (`rootOverride` in the check), which wins over it.

**Facts that cost hours to find:**
- **Use "Sync", not "Add shortcut to My files".** Matan's working setup is a Sync mount, not a shortcut.
- **"No personal OneDrive" is usually a wrong check.** `bgu365-my.sharepoint.com/my` is the BGU tenant, where the
  teammate is a guest: 404 there means nothing. Their own OneDrive is `https://postbguacil-my.sharepoint.com/my`.
- **OneDrive never shows BGU's MFA prompt.** Its silent request fails with `AADSTS50076` (client
  `ab9b8c07-8f02-4f72-87fa-80105867a763`, authority `.../49470515-677a-4fbe-8686-afae308fe867`, resource
  `00000003-0000-0ff1-ce00-000000000000`); the `0xCAA2000C` / `0xCAA90056` lines at the same second belong to it.
  `0x8AA5015A` alone is normal B2B noise.
- **The registry lies afterwards:** on Noa's working computer `Business1` still has no `FirstRun`, `SPOResourceId`
  or `Tenants`. Trust the mount (`yallaMounts`) and `/api/health`, not those fields.

**Steps** (ask the user before 5.2 and before clicking anything in their browser):
1. Open with Claude in Chrome the folder itself, not a subfolder:
   `https://bgu365-my.sharepoint.com/personal/mein_bgu_ac_il/_layouts/15/onedrive.aspx?id=%2Fpersonal%2Fmein%5Fbgu%5Fac%5Fil%2FDocuments%2FYallaLinearit`
   No access at all: the user asks Nadav Meir to share it. Make sure OneDrive.exe runs
   (`Start-Process "$env:ProgramFiles\Microsoft OneDrive\OneDrive.exe"`).
2. **If the check shows `mfaRequiredBgu` > 0** (or Sync ends in "can't add your folder"), get the token through
   Windows' broker, once. Say: "מתקין את MSAL, הספרייה הרשמית של מיקרוסופט, בסביבה נפרדת, כדי לפתוח את חלון
   ההתחברות של Windows":
   ```powershell
   py -3.12 -m venv "$env:LOCALAPPDATA\BodekHacham\wam-venv"
   & "$env:LOCALAPPDATA\BodekHacham\wam-venv\Scripts\python" -m pip install "msal[broker]==1.39.0"
   ```
   Then, with the user at the computer (the window expires), in a terminal tab:
   `& "$env:LOCALAPPDATA\BodekHacham\wam-venv\Scripts\python.exe" "<skill>\scripts\wam_signin.py" go <their @post.bgu.ac.il email>`
   They type the password and approve MFA. Result (no token): `%LOCALAPPDATA%\BodekHacham\onedrive-signin\last.json`
   should have `"ok": true`. If the AAD failures name the home tenant `474cbbe4-ab8e-40ae-a518-715ca4c0ba5a` instead,
   add `474cbbe4-ab8e-40ae-a518-715ca4c0ba5a https://postbguacil-my.sharepoint.com/.default` to that command.
3. **Sync, once, and record what happens.** Note the time, then the user (or you, after their yes, with `find`
   "Sync" → click) clicks **Sync** in the command bar (under `...` in a narrow window). Chrome asks
   "Open Microsoft OneDrive?": only the user can click "Open". Ask exactly what showed:
   - **"Set up OneDrive" wizard:** the first-run that was missing. The user completes it. On **"Back up folders on
     this PC"** all switches stay **off** and they click **Next** (not "Try again"), even with "Unable to sync" and
     `0x8004016c`: that only means Documents/Desktop are already backed up by another OneDrive account. Backing up
     would move Documents, and the repo with it if it lives there. Skip "mobile app" and "Upgrade". Never Unlink.
   - **"Sorry, OneDrive can't add your folder right now":** run the check with `-Since`; back to 5.2 if it shows MFA.
   - **Nothing:** the Chrome prompt wasn't confirmed, or OneDrive isn't running.
4. Still no mount a minute after the wizard: click Sync once more. Still nothing: restart OneDrive once
   (`Get-Process OneDrive, OneDrive.Sync.Service | Stop-Process -Force; Start-Sleep 3; Start-Process "$env:ProgramFiles\Microsoft OneDrive\OneDrive.exe" -ArgumentList '/background'`)
   and Sync again. Change one thing at a time; don't update OneDrive itself.
5. Verify: the mount exists, `/api/health` → `root` is inside it, and `.venv\Scripts\python -m moodle status <id>`
   from the repo shows the numbers the team sees (numbers only).

**Before switching a computer that worked locally:** if `~/Exercise Checking System` holds grading that isn't in
OneDrive yet, upload it first (`onedrive/sync.js`, dry run first; CLAUDE.md). The old local folder can stay; once the
synced folder exists the system ignores it.

## 6. Finish

Open `http://localhost:8765` and ask whether they see the courses and assignments. Then give a table
(check | ✓/✗ | what was done or what's left), one line on what they can already do (pull, grade, return) and
what's missing, and the full path of the repo to open Claude from.

## 7. Ready to grade (before every grading round, also on a computer set up long ago)

A grading run on a computer that isn't ready still spends the teammate's Claude usage: on 2026-11-18 a server that
had loaded the code of 15.11 failed every grading with "cannot import name ..." only after Claude had graded
(~$0.9 each, no grade). So check first, fix what can be fixed without asking, and stop on the rest.

Run the check (step 1) and read `update` and `claudeAccount`:

| What the check says | What to do |
|---|---|
| `health` is null | The server is down: `start.bat` in the clone `autostartRuns` points to (or `install-autostart.bat quiet` if `update.watchdog` is false); wait for `/api/health` |
| `update.upToDate` false, `update.cloneOnMain` true, `update.cloneDirty` false | Fix it now. If `update.gradingNow` is true, wait until that run ends (never stop a running grading). Otherwise say "המערכת אצלך על גרסה ישנה, מפעיל אותה מחדש על הגרסה של GitHub", stop the `dashboard serve` python processes (`dashboardProcesses`); the watchdog runs `start.bat` (git pull, then the server) within a minute. Run the check again until `upToDate` is true (up to 3 minutes; `%TEMP%\bodek-hacham.log` if not) |
| `update.cloneOnMain` false or `update.cloneDirty` true | Stop. The automatic update skips such a clone, so it stays on old code. Tell the user the branch and that there are local changes; never switch, stash or discard them yourself. Grading waits until the server's clone is on `main` with no changes |
| `update.autoUpdateOff` true | Say that `AUTO_UPDATE=off` in `.env` keeps this computer on old code; ask before removing it |
| `update.watchdog` false | `cmd /c install-autostart.bat quiet` in the server's clone: without it a stopped server doesn't come back and nothing updates by itself |
| `claudeAccount.loggedIn` false | `claude auth login` (step 4) |
| `claudeAccount` signed in | Ask the user for their own university email and compare it with `claude auth status` without printing it (step 4). `emailDomain` should be `post.bgu.ac.il` and `orgName` `Nadav Meir`: the team's Claude organization, one seat per person, each with its own limits. Someone else's email means a shared sign-in, where everyone on it draws from one person's limits: sign out and in with their own account |
| `claudeAccount.modelOverride` set | `GRADING_MODEL` in `.env` replaces the system's model (Opus 5.5, `DEFAULT_MODEL` in `grading/grade.py`), so this computer grades differently from the team. Ask before removing it |

Then tell the user in one short table (check | ✓/✗ | done or what's left) and, when everything is ✓, that they can grade.

**Before a big batch, the limits:** have them look at their 5-hour limit (Claude settings → Usage). A submission takes
about 0.55% of it (measured 2026-11-18: 9 submissions = 5%). Under 30% used: their whole share (about 107 of 1,068
for ten graders) in one run. More: two runs of about half, the second after the limit resets. Grade in one sitting,
not one by one over the day: the rubric stays cached for about an hour, and the first submission after a long pause
costs almost double. If the limit runs out mid-run, grading stops until it resets and nothing is lost.
