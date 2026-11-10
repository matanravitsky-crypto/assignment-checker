# Assignment Checker: notes for Claude

University project (BGU) that grades student assignments with Claude:
pull submissions from Moodle → grade by rubric → TA approves → return grades and marked files to Moodle.
Courses are large (up to ~1,000 students per assignment). The team works in Hebrew.

## Any teammate's computer

The system runs on the computer of whoever uses it, not on a server, and every teammate's computer can pull, grade
and return once it is set up. Nothing is tied to one person's PC: "Matan's PC" or "Ori's laptop" below says where
something was first seen or checked, not the only place it works. Names in tests and `docs/Roadmap.md` (יוסי and
the like) are made up. Never tell a teammate "it only works on Matan's computer"; find which of these is missing on
theirs, in this order, and say how to fix it:
1. **The repo on this computer, and its server up**: `curl http://127.0.0.1:8765/api/health`. If not, `start.bat`
   (once, `install-autostart.bat`). Setup of a new computer: README.md, "הפעלה אצל כל אחד מהצוות".
2. **The shared folder**: `/api/health` names it, or `python -m moodle status <id>`. The site and the commands find
   the synced OneDrive folder the same way (`shared_folder.find_root`, `use_for_commands`; before 2026-11-03 the
   commands looked only in `~/Exercise Checking System` and failed on every computer that only syncs OneDrive).
3. **Claude Code signed in to this person's own Claude account** (`claude auth status`): grading, pull and upload.
4. **Chrome with the Claude in Chrome extension, signed in to Moodle**: pull and upload.
5. **`GRADER_NAME` in the repo's `.env`** (the site asks for it): whose claims and grades these are.

**A Claude that sees only GitHub** (claude.ai with the GitHub connector, Claude Code on the web, any cloud session)
runs on Anthropic's machines, not on the user's computer. It can read and change the code and open PRs, but it cannot
reach the OneDrive folder, Moodle, Chrome or the local server, so it cannot pull, grade, check copying or upload. Say
so plainly and send the user to Claude Code on their own computer: the Claude desktop app → Code → the
`assignment-checker` folder they cloned (or `claude` in a terminal there).

**GitHub**: every teammate has write access (orimes-source, ezraariel, noa-rodnizky, tikochin; Shazumi178 is
Nadav). Work on a branch and open a PR. The first push from a new computer opens a GitHub sign-in in the browser
(Git Credential Manager); `gh auth login` once for PRs from the command line.

**Moodle uploads are on hold** (Matan, 2026-10-22, and the team's setup issue #22): nothing goes up to Moodle, not
even a dry run of `send`, until Matan says the course staff approved returning feedback through the system.

## Repo layout

Each folder has a README.md that explains it.

| Path | What |
|---|---|
| `moodle/` | Steps 1 and 3: Moodle ZIP → numbered submissions (`ingest`), grades + marked files → ZIPs (`upload`), and the automatic upload to Moodle (`send`, `record`). `python -m moodle ingest|status|upload|send|record <id>`, `guide` |
| `moodle/paths.py` | Every folder and file name in the shared folder (constants). Everything else imports names from here |
| `grading/` | Step 2: grading with Claude. `python -m grading <id>` or the dashboard's "Grade" button. Through the API with `ANTHROPIC_API_KEY`, otherwise through the logged-in Claude Code (`grading/claude_cli.py`). Its README has the input/output contract, the rubric format and the `Grades.csv` columns |
| `activity_log/` | The activity log: `record(folder, action, by, **details)` and `read(folder, action, **match)`. `<folder>/Activity log/<who>.jsonl`, one file per writer, lines only added. Grade edits write `grade_edit` / `grade_edit_failed` |
| `stats/` | The statistics database: per assignment and per question, averages, distribution, common mistakes, review counts. Numbers only. Saved as a derived `Statistics/<course>/Assignment N.json` in the data folder (recomputed when the grades or notes change, after every grading run and approval), shown in the site's "סטטיסטיקה" tab (`#/stats`, `GET /api/stats`), read from the CLI with `python -m stats show <id>` / `show --all --brief` / `rebuild` / `export --sqlite`. The skill `stats-db` explains it. Claude reads statistics only through it, never from `Grades by` or `Grading notes` by hand. Plan and phases: `docs/Statistics database plan.md` |
| `datastore/` | The integrity gate of the file "database" (DB_UPGRADE_PLAN.md, proposal B): `atomic` (atomic writes, O_EXCL lock files, a local process lock around read-modify-write), `schema` (what a valid grade row, notes file, details file and key table are; `reject` for new writes, `warn` for old rows), `doctor` (`python -m datastore check <id>` / `fix`, `GET /api/integrity`, the site's integrity banner): duplicates, marked PDF without a grade row, conflict copies of every kind, stuck locks, invalid files. Grades are written only through `grades.update_own`. `ledger` (proposal A): every grade change is an event in `activity_log` (`grade_set`, `grade_failed`, `grade_edit_intent`, `grade_edit`, `grade_edit_failed`, `grade_replayed`; deterministic `id`, per-writer `seq`); `projection` says what the grade should be (approval wins, then time, then id), `compare`/`replay` (`python -m datastore replay <id> [--yes]`, also inside `fix`) put a lost row back into the original writer's file, `history <id> <number>` lists a work's grade events (also `/api/grade-log` → `history`, shown on the review page). The dashboard connects `LedgerStore` at startup (`web_server.connect_stores`) so an edit writes "started" before the other targets |
| `copying/` | Suspected copying between submissions, no Claude and no tokens: `python -m copying <id>` only: the site's "העתקות" page was removed and a pull no longer starts it (Matan, 2026-11-10: "not needed"). Layer 0: the same file, or the same PDF document id / author / creation time. Layer 1: the same page (dHash for scans, rare shared 3-word sequences for typed pages). Writes `Copying check.json` (numbers and hashes only). Its README has the thresholds and what it can't catch |
| `.claude/skills/rubric-builder/` | "מחוון לדף X, תמשוך Y עבודות": the one rubric skill (the older `rubric` skill and its workflow were retired on 2026-10-29). A committee of agents builds the rubric from the full solution and all Y submissions, with `rubric.json` as the one source, and writes everything into `פדגוגי/`: `Solutions.md`, `Solution methods.md`, `Manual review rules.md`, and `Working notes/` (`rubric.json`, `findings.md`, the agents' reports). `scripts/make_pdf.py` renders from it both `פדגוגי/Rubric.md` (the grading bot's rubric; the bot deducts by רגיל) and `פדגוגי/Rubric.pdf` (people: steps and points, error tables with רגיל/מחמיר = רגיל + 1, alternative methods) in the course's fixed format. A council `Rubric.md` from the `rubric` skill is an input (its numbers) and is archived on delivery. Then a committee loop on the TA's remarks until approved. Needs MiKTeX once per computer (`setup/check.ps1`, `setup/install-windows.ps1 -NoPerl -NoUpdate`). Its README.md explains it to people |
| `dashboard/` | Local server that connects the website to the shared folder: `python -m dashboard serve` (or `start.bat`) |
| `dashboard/actions.py` | Pull (Claude in Chrome downloads the ZIP when none waits in Downloads, then `moodle ingest`, with a lock and a key-conflict check), prepare return (`moodle upload`), upload to Moodle in the background (`moodle send`) with a readiness check, and the state the site shows (numbers only, no names) |
| `website/` | The dashboard site "בודק חכם" (static HTML/JS, Hebrew RTL). Published to Vercel (project `bodek-hacham`, root dir `website`, https://bodek-hacham.vercel.app) from `main` through Vercel's Git integration. No demo data: it shows only what `dashboard/` reads from the shared folder, and the Vercel page connects to the dashboard on the same PC at `http://127.0.0.1:8765` (CORS for that exact origin only, `SITE_ORIGINS` in `dashboard/web_server.py`) |
| `pages-redirect/` | The old address `matanravitsky-crypto.github.io/assignment-checker` (GitHub Pages) kept serving the demo site with fake data after the move to Vercel. It now only forwards to bodek-hacham.vercel.app (`.github/workflows/pages-redirect.yml`). Never publish the site there again |
| `tests/` | All tests (`tests/moodle/`, `tests/dashboard/`). Run `python -m pytest` from the repo root; CI runs them on every PR |
| `install-autostart.bat`, `autostart.vbs` | Once per computer: a shortcut in the Windows Startup folder runs `autostart.vbs` at every sign-in, a watchdog that checks `/api/health` every minute and runs `start.bat background` hidden when the system is down (no browser, no pause; output to `%TEMP%odek-hacham.log`). The Vercel page talks to the local system directly (`BASE` = `http://127.0.0.1:8765/`, CORS for that origin only), so the address bar stays bodek-hacham.vercel.app (Matan, 2026-11-03). Chrome asks once per computer to allow it (Local Network Access, `loopback-network`; "prompt" on Matan's Chrome 156 on 2026-11-03). From 10-23 to 11-03 the page forwarded to `http://localhost:8765` instead (localStorage `ac:openLocal`, no longer read): teammates whose system was down at that moment (just booted, or the self-update restart) got Chrome's error page with no way back to the instructions. The not-connected page now reads the permission state (`localAccess`) and says which step is missing. Installed on Matan's PC on 2026-10-22 |
| `start.bat` | Double-click: updates from GitHub (`git pull --ff-only`, skipped with a message if it can't), runs `claude update` (an old Claude Code refuses the new models; stopped after `CLAUDE_UPDATE_WAIT_S`, default 120 seconds), sets up `.venv` once, installs `requirements.txt`, starts the dashboard. Teammate setup (folder shortcut, Python, 7-Zip, Git, `git clone`) is in `README.md` and on the site's not-connected page |
| `dashboard/public_status.py` | The public numbers board (Matan, 2026-11-03: "numbers only, for everyone"). The public site shows nothing of the shared folder by itself, so one computer, the one with `PUBLIC_STATUS_GIST=<gist id>` in its `.env` (Matan's PC: gist f1d11991473c2ece643fc479ed963117) and `gh` signed in, publishes a summary of numbers only to that gist (`gh api --method PATCH gists/<id>`): per course and assignment, how many were pulled, graded, wait for manual review, approved and returned, when, and who pulls. No submission numbers, grades, averages, comments, copying, files or anything about one student (`tests/dashboard/test_public_status.py` checks it). Checked every 2 minutes against `actions.changes`; published only when the numbers changed, and hourly anyway as a heartbeat. The site (`PUBLIC_STATUS_URL` in `website/app.js`, the gist's raw URL) shows it as "מצב העבודה" to anyone without a connected system, refreshed every minute, and says the numbers may be old after 3 hours without an update |
| `website/connect.ps1` | Teammate setup in one command, shown with a copy button on the site's not-connected page: `irm https://bodek-hacham.vercel.app/connect.ps1 \| iex`. Installs what is missing (Git, Python 3.12, 7-Zip with winget; Claude Code with Anthropic's installer, the same `INSTALL_COMMAND` the site's button runs), clones to `%USERPROFILE%\Bodek Hacham\assignment-checker` (a computer whose Startup shortcut already exists keeps that folder; a running server skips all of it), runs `install-autostart.bat quiet` (no `pause`), waits up to 8 minutes for `/api/health`, and opens the site, where Chrome asks once to allow it to reach the system on this computer. ASCII-only English output: Hebrew prints backwards in a PowerShell window. `website/vercel.json` serves it as UTF-8 text. It cannot add the OneDrive shortcut; it says so when `/api/health` has no root |

## Student data: never in the repo

This repo is **public**. Submissions, names, ID numbers (ת"ז), emails and grades never go into git.
`.gitignore` blocks `data/` and `*.zip` as a safety net, but student data lives outside the repo.
Folders and files have plain English names that say what they are (the README.txt files inside explain
them in Hebrew). The names are constants
in `moodle/paths.py`, so code never spells them out by hand:

```
Exercise Checking System/                  the data folder (the synced one, found by itself; else ASSIGNMENT_DATA, default ~/Exercise Checking System)
  README.txt
  Linear Algebra/                           a folder per course
    README.txt
    Assignment 0 - Sets and Complex Numbers/   a folder per assignment (its Hebrew title is in the details)
      README.txt
      1 - Submissions to grade/   0001.pdf, 0002.pdf, ... (0001-2.pdf = second file)  ← grading reads only these
      2 - Graded with comments/   0001.pdf ... marked by the grader
      3 - Ready to upload to Moodle/  built by `upload`/`send`: ZIPs, grades sheet, Upload steps.txt,
                                  Upload log.csv (what went up, per number), Upload batch.json (the current batch),
                                  Upload batch <id>/ (that batch's ZIPs; `upload` never writes there)
      Assignment details.json     Moodle id, course, name, Hebrew title, due date, questions, rules, max_grade, rubric,
                                  official_key_points (the points per question from the lecturer's key)
      Official key/, Official key.txt   the lecturer's official grading key (המכוון), uploaded from the site's grading step
                                  (POST /api/official-key). When present every grading run sends it first and it wins over
                                  any other rubric (grading.official_key, KEY_RULE). Replaced ones go to Earlier official keys/
      Grades.csv                  number,grade,feedback: older grades and approvals typed by hand
      Grades by <name>.csv        each grader's own grades  ← grading output (readers merge all of them, moodle/grades.py)
      Who grades what/<name>.json the numbers each grader took (moodle/claims.py)
      Grading notes/              0001.json ...: per question comments, mistakes, "unsure", the marks, why a person should look (numbers only)
      Key - number to student.csv number → Moodle participant id → original folder  ← the one key
      Copying check.json          suspected copying: pairs of numbers and why, per-file hashes (`python -m copying`)
      Upload in progress.txt      exists only while an upload runs ("<user> (<PC>) pid=<pid>", since when; 30 minutes without an update = stuck)
      Pull in progress.txt        the same while a pull runs
      Pull log.csv                pulled_at,by,students,new,files,parts: one row per pull (numbers only), so every
                                  computer sees when it was pulled
      Pull check.json             the last pull's check: nothing lost, missed, doubled or changed (moodle/pull_check.py)
      (older pulls left "Moodle download <date>.zip" here; new ones keep it on the puller's computer only)

Moodle originals/                          on the downloader's computer only (ASSIGNMENT_WORK)
  <course>/<assignment>/   the extracted ZIP: one folder per student, "<full name>_<participant id>_assignsubmission_file"
  Backup - Moodle downloads/<course>/<assignment>/   every download exactly as Moodle gave it ("Moodle download <date>.zip",
                           or a "Moodle download <date>/" folder of parts). Never in OneDrive: names, and 2-3 GB a pull
```

The extracted ZIP never goes to OneDrive: students' file names break its sync (see below). It can be rebuilt
from the ZIP. Commands take the assignment's Moodle id; `paths.find_assignment` finds its folder through
`Assignment details.json`. A new assignment needs its folder names once, in English:
`python -m moodle ingest <id> --course "Linear Algebra" --name "Assignment 1 - Vectors"`
(its Hebrew title comes from the ZIP's file name).

**Ten assignments per course, two courses.** The site shows every course folder (Linear Algebra and Discrete
Mathematics, even before it has an assignment) with ten slots, "הגשה 0" to "הגשה 9" (`folder_view.SLOTS`). A folder
named `Assignment N` or `Assignment N - <words>` fills slot N; a slot with no folder is an empty one (`"empty": true`
in `/api/state`, no Moodle id). Its first pull takes the Moodle link or id from a field on the pull page
(`POST /api/pull` with `moodleId`): `actions.new_assignment` creates `<course>/Assignment N/` with its details
(id, course, name), refuses an id that another assignment already has, and the Hebrew title is filled from the ZIP's
name. The id is saved even if the download then fails, so the next pull doesn't ask again.

The **key** that links a number back to a student is the Moodle *participant id* in the folder name
(not the ת"ז). It lives only in the key table. A student keeps their number on every later download:
`anonymize.prepare` reads the existing key, and students who submitted since then get the next free numbers.
Never delete or rebuild the key table of an assignment that is being graded.

## One puller per assignment, one key

Ori is the one who pulls (his decision, 2026-10-29), for any assignment he likes, from his own laptop, where the data
folder is a local copy (`~/Exercise Checking System`, `ASSIGNMENT_CHECKER_ROOT` in `.env`) that he uploads to the
lecturer's OneDrive with the browser sync (`onedrive/sync.js`). His university account has no OneDrive of its own
("Add shortcut to My files" fails with "Couldn't update", `/my` says the user does not exist), so his laptop cannot
sync YallaLinearit; that is why the earlier rule (2026-10-23: pull only where the shared folder is synced,
`NOT_SHARED`) was dropped the same day he asked. `paths.in_shared_folder` still tells a synced folder from a local
copy, but nothing refuses a pull by it: not the site's button, not the night pull, not `moodle ingest`.
The thing that keeps numbers right is **one key table per assignment**, the one in the folder the puller pulls into:
`anonymize.prepare` reads it before numbering, so every student keeps their number on every later pull.
**Anyone on the team may pull any assignment** (Ori, 2026-11-02): the site's pull button works for everyone, also when
the pull is registered to someone else (`claims.task_owners` decides only who pulls at night). Three things keep that safe:
- **The pull check** (`moodle/pull_check.py`). Before the new key is written, `prepare` looks at the disk again on its
  own: every student keeps their number, no number has two students; every numbered file that was there is still there
  as it was, or (for a student in this download whose file it replaced) its old version is in `Earlier versions`; a file
  of a student not in the download is unchanged (size and time); every file of the download is in the folder with
  exactly its bytes; nothing appeared that the download did not bring; no student came in two folders. Any failure
  raises `PullCheckFailed` and every file goes back, with no key written. Then, against Moodle (`moodle_side`): the
  students whose ZIPs came (the `ids` of every part in the list of `download_parts.js`) are exactly the extracted
  folders; if fewer came than the students Moodle's table shows with a submission date (`with_date`), the difference
  is counted for a person to look at (by count: the table knows user ids, the ZIP participant ids). First real run,
  Discrete 3453769 on 2026-11-02: 64 in the table, 64 with a date, 64 came, 14 earlier students kept as they were. The result is `Pull check.json` in the assignment folder (numbers
  only) and lines in the pull's report.
- **The key between computers** (`onedrive/sync.js`). Two computers that pulled the same assignment each have their own
  key, and uploading one over the other would drop students or give one number to two students. Before uploading an
  assignment whose key in OneDrive differs from this computer's, the sync compares them (`keyProblems`): the local key
  must hold every student of the OneDrive key with the same number, and no number of someone else. Otherwise nothing of
  that assignment is uploaded (`withoutConflicts`) and the report says which numbers clash. A key that only adds new
  students uploads as usual.
- The lock and the rest below.
`dashboard/actions.py` also guards the dashboard's pull:
- **Lock:** while a pull runs, the assignment folder has `Pull in progress.txt` (who and since when). Another
  pull of that assignment waits until it's gone (a lock older than 30 minutes counts as stuck and is ignored).
  The lock text is `<user> (<PC>) pid=<pid>` (`moodle/lock.py`): a fresh lock of the same person on the same PC
  still blocks when another process that is alive holds it (say the CLI and the dashboard). Messages show who
  without the pid; old lock text without a pid still works.
- **Conflicts:** if OneDrive still made a conflict copy of the key (`Key - number to student-<PC>.csv`), the
  dashboard shows it and refuses to pull until someone merges the copy into the main key and deletes it.
- Let OneDrive finish syncing (the cloud icon) before pulling on another computer.
- **A pull deletes nothing and overwrites nothing** (`anonymize.prepare`): files are written in place, a file that is
  byte for byte the same stays untouched, and one a newer download replaces (a resubmission, a second file that is gone)
  moves to `Earlier versions/<date>/` first. The key is checked before any file is touched (`check_key`: every old
  student keeps their number, no number has two students; otherwise `KeyBroken` and nothing changes), written whole
  through a temp file, and the old key is copied to `Key history/` (not next to the key: that would look like an
  OneDrive conflict copy). A kept download never replaces another (`ingest._free`).
  If the key changes on disk during the pull (another computer pulled the same assignment and OneDrive brought its
  key), the pull puts back every file it copied or moved and writes nothing. OneDrive conflict copies of submissions
  (`0571-DESKTOP-ABC.pdf`, `anonymize.submission_conflicts`) stop the pull and the upload until a person checks them.
- **The right folder:** a ZIP is taken only by its exact `-<id>` ending, and `paths.find_assignment` refuses an id that
  two assignment folders carry (`TwoFolders`), so הגשה 0 of Linear Algebra can never land in הגשה 1 of Discrete Mathematics.
  When Moodle's grading table listed fewer students than the key has (a filter left on), the pull says so.

Then:
- Team: grade from `1 - Submissions to grade`, write `Grades by <name>.csv` and `2 - Graded with comments` next to it
  (the dashboard's "Grade" button or `python -m grading <id>`). See "Splitting the grading" below.
- Whoever returns: `python -m moodle upload <id>` (or "Prepare return" in the dashboard) → upload to Moodle (below).

## Splitting the grading between the team

Each teammate grades on their own computer with their own Claude subscription, so an assignment is split between them:
- **Claims** (`moodle/claims.py`): in step 2 of the site each grader takes submissions ("קח" on a row, or "take N free ones").
  Each grader writes only their own file, `Who grades what/<name>.json` (number → when taken), so OneDrive never merges
  two versions of a file. Two claims of one number made before sync: the earlier one wins (then by name), on every computer.
- **Pull and return owners** (per assignment, `claims.task_owners`): `<course>/Who does what/<name>.json` holds take and
  release events keyed `"<slot>:pull"` / `"<slot>:return"`; the latest event in anyone's file decides, so a teammate can
  take over ("העבר אליי"). Pulling or uploading with no owner makes you the owner. Someone else's task turns that
  stage's button into "אצל <name>". Each stage page opens with a table of that stage across all the course's assignments
  (from the folder: counts, who took what, what's left).
- **Live**: the site polls `GET /api/changes` every 5 seconds (a hash of names, mtimes and sizes of the files the state
  is built from; folders count by name only, since Windows updates a folder's mtime late) and reloads when it changes.
  Numbers this computer is grading right now come back from `/api/state` as `"grading"`. A focused form field holds
  the reload only for 15 seconds after it was last touched (before 2026-11-03 a focused `<select>`, such as the
  assignment picker, stopped the reloads until the user clicked elsewhere, so a pull didn't show).
- **"סנכרון"** (top bar, `POST /api/refresh`): reads the whole folder again and lists what changed per assignment
  (pulled, graded, returned). It also checks OneDrive itself on this computer (`dashboard/onedrive_check.py`): the
  folder is inside OneDrive (Cloud Files API), OneDrive.exe runs (started if not), no AADSTS50076 in the AAD log in the
  last 20 minutes (BGU wants MFA, see the shortcut "חיבור OneDrive BGU"), and how many files from here are not uploaded yet.
  That shortcut exists only on Matan's PC (`%LOCALAPPDATA%\BodekHacham\onedrive-signin`, not in the repo); elsewhere
  the person signs in to OneDrive themselves. "Not synced" has three causes, checked in this order: a stale tab
  (`/api/state` already has it), a server still running old code (see "Problems already solved"), or OneDrive stuck.
  The button shows for everyone on the public site, also without a system on that computer (until 2026-11-03 it was
  hidden there, so only Matan saw it): then it fetches the public numbers board fresh from the gist (`syncPublic`,
  a `?t=` URL no cache has seen) and says what changed and when the publishing computer last published. A system from
  before the button answers 404 on `/api/refresh`; the site then says it is old and updates when it restarts.
- **Grading** skips numbers someone else holds and claims what it grades. Once anyone took something, the site's "Grade"
  button grades only my claimed, ungraded work; with no claims at all it grades everything pending, as before.
- **Grades never share a file**: grading writes `Grades by <name>.csv` (with `graded_at`, `graded_by`). Every reader
  (`grading.read_grades`, `moodle upload`/`send`/`status`, the dashboard) merges `Grades.csv` and all those files per number:
  an approved row wins, then the latest `graded_at`, and a row without it (old `Grades.csv`) loses to one with it.
- **My name**: `GRADER_NAME` in the repo's `.env`, set from the site (`POST /api/me`); renaming moves my claims. Without it,
  the Windows user name.

## The shared folder (lecturer's OneDrive)

`YallaLinearit/Exercise Checking System/` in the lecturer's (Nadav Meir) OneDrive (5 TB) mirrors Ori's
`~/Exercise Checking System`, with a folder per course (Linear Algebra, Discrete Mathematics):
https://bgu365-my.sharepoint.com/personal/mein_bgu_ac_il/_layouts/15/onedrive.aspx?id=%2Fpersonal%2Fmein%5Fbgu%5Fac%5Fil%2FDocuments%2FYallaLinearit%2FExercise%20Checking%20System
Next to it, `YallaLinearit/Course Material (tex)/exercises and solutions/` has the linear algebra questions and solutions as .tex.

Each teammate **syncs** the folder on their own computer through "Add shortcut to My files" on the shared folder (the
older note that the button fails is out of date); OneDrive names it `<owner> - YallaLinearit`, e.g. on Matan's PC
`C:\Users\PC\BGU\נדב מאיר - YallaLinearit`. The dashboard and the `moodle`/`grading`/`copying` commands find the synced
folder by themselves (`dashboard/shared_folder.py`). To point at another path, set `ASSIGNMENT_CHECKER_ROOT` (both; also
in `.env`) to the synced path of `Exercise Checking System`, or `ASSIGNMENT_DATA` (the commands only; it wins), and check
with `python -m moodle status <id>`.
- A teammate without the shortcut can still open the link above (the lecturer shares it) and view or download what
  they need, e.g. `Linear Algebra/Assignment 0 - Sets and Complex Numbers/1 - Submissions to grade/0023.pdf`.
- Without sync, Ori works locally and uploads from the web: Create or upload → Folder upload → the course folder.
  Re-uploading replaces files with the same name. The folder picker is a native Windows dialog Claude can't see,
  so Ori picks the folder himself.

**Automatic upload to the lecturer's OneDrive (`onedrive/`).** Instead of dragging the course folder and pressing
"Replace", `onedrive/sync.js` runs in the lecturer's OneDrive tab (Claude in Chrome, `javascript_tool`) and uploads only
what is new or changed, through SharePoint REST with the signed-in user's own rights (no app, no admin consent):
`eval(await (await fetch("http://127.0.0.1:8765/api/sync/script.js")).text()); await window.__ecsSyncAll({dryRun: true})`,
then without `dryRun`. The files come from the dashboard (`/api/sync/`, `dashboard/sync.py`: course list, file list
with size and mtime, file bytes; only from inside a course folder of `ASSIGNMENT_DATA`, CORS only for
`https://bgu365-my.sharepoint.com`), so they go computer → browser → OneDrive and not through Claude (few tokens, no
10 MB limit). It never deletes, never overwrites a OneDrive file newer than the local one (a team's `Grades.csv`),
skips locks and temp files, and checks sizes after uploading. Don't sync while `Grading part N in progress.txt` exists.
Once per computer Chrome asks to allow the site to reach the local network: the user clicks "Allow" (each new port
asks again).
**Archived grading stays archived.** On 2026-11-03 Ori's test grading of 23/10-30/10 (Discrete Assignment 0, LA
Assignment 0: marked PDFs, `Grading notes`, `Who grades what`, `Grades*.csv`) was moved in OneDrive to
`<assignment>/Old test grading/` (its README says how to restore), so the site counts 0 graded there. A local copy that
still has those files in their old places would upload them again as "new", so `plan` holds back a grading file that
is missing in OneDrive when that assignment has `Old test grading/README.txt` in OneDrive and the file was saved before
that README (`archived` in the report, with advice to move them locally too). Grading saved after it uploads as usual.
`tests/onedrive/test_sync_plan.py` runs `plan` in Node.
Checked 2026-10-23: 12 MB from the computer in 10 s, byte-identical; a dry run found Discrete Mathematics identical.

When working with this data:
- Grade from `1 - Submissions to grade` only. Don't open the extracted originals or print names, ת"ז or emails into chat, commits or logs.
- The key table sits in the shared folder, so everyone with access to it can link numbers to students. Don't open it while grading.
- Some students write their name or ת"ז inside the PDF or its filename; the team accepted that. Don't copy it anywhere.
- Match grades to students **by number, never by row order**: one shifted row would give 1,000 students the wrong grade.

## Moodle (moodle.bgu.ac.il)

There is **no Moodle API**. Claude in Chrome works in the user's own logged-in Chrome.
- The user logs in themselves. Claude never types Moodle passwords.
- Download when someone on the team asks, and by itself at night after an assignment closes: `dashboard/scheduler.py` (a thread
  of the dashboard server) warns 30 minutes before `SCHEDULE_PULL_TIME` (default 00:05 on the day after `due`, so a 23:59
  deadline is in; `.env`), keeps the PC awake, and runs the same `actions.pull` as the button, of everyone. Then at the same
  time every night for `SCHEDULE_REPULL_DAYS` (default 7) it pulls only what changed (late submissions, extensions), and
  tells only when something new came in or it failed. A failed night pull tries again 30 minutes later, 3 times a night.
  **Only one computer pulls at night**: the one whose user took the assignment's pull on the site (`claims.task_owners`;
  the first pull with the button takes it), and only where the shared folder is synced. Nobody's pull, no night pull.
  `due` is read from Moodle on every pull (the assignment's page, by `download_parts.js`) and saved in
  `Assignment details.json`, so nobody types it. A closed Chrome is opened on Moodle's home page (`claude_driver.open_chrome`);
  it still needs the PC on and Chrome logged in to Moodle and to the Claude extension. `SCHEDULE_PULL=off` turns it off.
  No other scheduled downloads. Every **upload** to Moodle (grades or feedback) needs a person's yes.
- Submissions page: `https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id=<assignment id>&action=grading`.
  The assignment id is the `id=` in that URL (the number at the end of the ZIP name too).
- Download by hand: Actions (פעולות) → "הורדת כל ההגשות (השתמש ב 7ZIP לפתיחה)", or straight `view.php?id=<id>&action=downloadall`.
  Keep "הורדת הגשות המאורגנות לתיקיות לפי סטודנט" (download in folders, next to פעולות) checked: `anonymize` needs a folder per student.
  The ZIP lands in Downloads as `<course code>-<assignment>-<id>.zip`. Open with 7-Zip, not Python's zipfile (it garbles some Hebrew names).
  **BGU Moodle cuts a big "download all" ZIP** (2026-10-23: 356, 913, 889 and 475 MB of ~2.4 GB, after 1-2 minutes) and
  Chrome still saves it as a finished .zip. `ingest.check_whole` tests every ZIP with 7-Zip before anything is touched and
  renames a broken one to `... (incomplete).zip`, so it is never taken again.
- **An expired Moodle session shows nginx "404 Not Found"**, not a login page. Opening `https://moodle.bgu.ac.il/moodle/my/`
  signs Chrome in again by itself (SSO). Every Claude prompt does that once before giving up (`SESSION_RULE`).
- **The pull button runs through the Claude of whoever clicks it** (2026-11-03, Matan: "the system tells the Claude on that
  user's computer to pull and put the files in the right place in the Drive"). On the site, "משוך" and "משוך הכול מחדש"
  first go through the same readiness list as the upload (`startPullFlow` → `readyLoop`, `then: "pull"`): Claude Code
  installed (button, after a yes), signed in to this person's account (the sign-in page opens by itself), the Claude in
  Chrome extension and Moodle connected (the short check, cached 30 minutes, so a connected computer pulls at once). When
  all are ✓ the pull starts with no further click, through `claude -p --chrome` on that computer. An empty slot (first pull,
  with its link) goes straight to `POST /api/pull`, where `require_moodle` checks the same. A computer that is not connected
  sees `website/connect.ps1` on the not-connected page.
- **A Claude Code that fails to start is run once more.** On 2026-11-03 at 12:01 a pull from the button failed with
  "Claude Code נכשל (קוד יציאה 4294967295)", right after a `claude update` that hung, and looked like it did nothing.
  `ClaudeChromeDriver.execute(again_if_crashed=True)` (the check and the download only, never an upload: Moodle may have
  imported) runs the same command again after `CRASH_PAUSE_S` when it ended with an error code and no output within
  `CRASH_WINDOW_S` (20 s; reaching Moodle takes Claude several turns, so the parts script cannot have started). A failure's
  message now carries the last line Claude Code wrote to stderr.
- **The pull button downloads by itself, in parts.** `POST /api/pull` first takes an unconsumed ZIP (or list of parts) of
  the assignment in Downloads. If there is none, `ClaudeChromeDriver.download` runs one locked-down `claude -p --chrome`
  (`--tools ""`, an empty temp folder, `download_prompt`): it opens the grading page, ticks the folders checkbox if it is off
  (the only click it may make), and runs `moodle/download_parts.js` with the javascript tool, inside `String.raw` with its
  SHA-256 (the page refuses a script that was not copied exactly). The script lists every student of the grading table, asks
  Moodle for ~40 at a time (POST `action=gradingbatchoperation&operation=downloadselected`, ~10 s per part), counts the
  students in each ZIP's central directory, asks again in two halves for a part that is not whole (a single student together
  with one who already came: Moodle sends one file without a ZIP), and saves each part to Downloads at once
  (`<name>-<id> part 003 of 015.zip`: "of" is the parts planned so far, so the bar knows the total from the first part); last comes `<name>-<id>.json`, the list of parts with their sizes. A student that fails 3 times
  stops it all with an error and no list. **Claude waits in its run until the script says "saved"**: Claude in Chrome closes
  the tab of an ended run within ~2 minutes (the parts stopped at 14 of 15). Meanwhile the dashboard counts the parts in
  Downloads for the progress bar (`GET /api/pull`, phases claude/parts/check/extract/number, with `eta_s`: the seconds left in
  the phase at its pace so far, shown as "נשארו בערך N דקות").
  The site asks `/api/changes` every 5 seconds (when visible and idle) and reloads when the folder changed, so a pull on another PC shows up through OneDrive without a refresh. `ingest.gather_parts` takes the
  list only if every part is there with its exact size, checks each, extracts all into one originals folder and numbers once;
  the parts are kept in `Moodle download <date>/` under `Backup - Moodle downloads` on the puller's computer, and the pull is
  logged in the assignment's `Pull log.csv`. Run for real on 3438636 on 2026-10-23: 566 students in 15 parts, every
  earlier number kept. The download shares the "one Chrome job at a time" guard with the connection check and the upload.
- **A pull after a pull asks only for what changed.** `actions._since` takes the last row of `Pull log.csv` minus an hour and
  passes it to the script (`__SINCE__`, ms): it asks Moodle only for students whose "עדכון אחרון (הגשה)" in the grading table
  is at or after it (a date it can't read counts as changed; no date = no submission). Everyone else keeps their files
  (`anonymize.prepare` keeps students who are not in a download). The list then has `since` and `changed`; with nothing
  changed it has no parts, and `ingest` only logs the pull (`nothing_changed`). The first night pull, a pull with no earlier
  log row, and the site's "משוך הכול מחדש" (`POST /api/pull` with `full: true`) ask for everyone.
- Feedback upload: Actions → "העלאת מספר קובצי משוב כקובץ 7Zip אחד" → the ZIPs in `3 - Ready to upload to Moodle`
  (`Graded - part 01.zip` ...), one at a time. **BGU Moodle imports at once**: clicking "יבוא קבצי משוב" imports
  immediately, with no confirmation list (file → student) before it. Moodle then lands on the grading page with a
  message saying how many files were imported; that count against the files in the ZIP is the only check.
  `Upload steps.txt` there has the steps and a checklist. That page takes .zip only, up to **31 MB** ("הגודל המירבי לקבצים חדשים", checked on assignment 3438636), so ZIPs are split at 30 MB
  (`--max-mb` to change). The course's max upload size is a course setting, capped by the site.
- Grades upload needs **"Offline grading worksheet"** turned on in the assignment settings (not on yet in assignment 3438636).
  Then: Actions → download the grading worksheet, run `python -m moodle upload <id>`, upload `Grades for Moodle worksheet.csv`.

## Uploading to Moodle with Claude

The site (or the CLI) uploads the marked files through Claude in Chrome, ZIP after ZIP. A person can always do
the same by hand with the ZIPs from `3 - Ready to upload to Moodle` (see `Upload steps.txt`).

**The flow**
1. Step 3 of the site (local mode): the button "העלה N למודל" calls `POST /api/upload/prepare`, which builds the batch:
   only marked work that is new or changed since its last upload (`Upload log.csv`), packed into ZIPs of at most
   9 MB (`CLAUDE_MAX_ZIP_BYTES = 9_000_000`; Claude in Chrome's `file_upload` takes about 10 MB) in a folder of
   their own, `3 - Ready to upload to Moodle/Upload batch <id>/Graded - part NN.zip`, and writes `Upload batch.json`
   with each ZIP's sha256. "Prepare return" writes its ZIPs straight into the upload folder, so it can't overwrite
   a batch; a new batch removes the folders of earlier ones, but only the ZIPs this code wrote (OneDrive conflict
   copies are never deleted). A number resubmitted after grading, or with a file over 9 MB, stays out and is reported.
   Prepare is refused (numbers only, never names) while a pull or an upload of the assignment runs, while OneDrive
   left a conflict copy of the key, `Upload log.csv` or `Upload batch.json`, and when the key doesn't hold together:
   a number with two participant ids, a participant id with two numbers, or a row whose `original_folder` carries
   another participant id than its `participant_id`.
2. A readiness checklist: is Claude Code installed (with an install button), is it logged in (the site starts the
   login itself and the browser sign-in completes it), and are Chrome and Moodle connected (a short Claude check,
   cached for 30 minutes).
3. A confirm panel (assignment, number of ZIPs, number of students). **Every batch goes up only after a person's yes**:
   the button in that panel, or `y` / `--yes` on the CLI.
4. `moodle/send.py` `run_batch` loops over the ZIPs under a lock (`Upload in progress.txt`), one headless
   `claude -p --chrome` run per ZIP (`moodle/claude_driver.py`, prompt in `moodle/claude_upload.md`). The site shows
   progress, can stop after the current ZIP, and can resume. Right before each ZIP and again before logging it,
   Python hashes the ZIP against the batch list: missing or changed stops the run ("stale") and logs nothing. After
   each ZIP Python (not Claude) checks Moodle's "N files imported" against the ZIP's file count and appends the files
   to `Upload log.csv` (`number,file,sha256,zip,uploaded_at,by`: numbers only, never names). Imported with counts
   that don't add up stops as "mismatch": Moodle already imported, so a person checks Moodle before anything runs
   again (the site offers "resume" only for `needs_login`, `user` and `error`). "Prepare return" (dashboard) and
   `send` (CLI) are refused while an upload of the assignment runs.
5. Uploaded by hand instead? `python -m moodle record <id> "<zip name>"` writes that ZIP's files to the log. It looks
   for the ZIP in the current batch's folder and refuses one that is missing or changed since it was prepared.

CLI: `python -m moodle send <id> [--dry-run] [--yes]`.

**Facts from the first real runs (2026-10-22)**
- **BGU Moodle imports at once.** Clicking "יבוא קבצי משוב" on the uploadzip page imports immediately. There is NO
  confirmation list (file → student) before the import; Moodle then lands on the grading page with a message about
  how many files were imported. So a **dry run must never click it**: it stops after attaching the file, at cancel.
  The only check is Moodle's result count against the files in the ZIP.
- **The ZIP format is verified.** A ZIP built by `prepare_batch` (folder `<name>_<participant id>_assignsubmission_file/`
  with `feedback.pdf`) was imported by BGU Moodle into the right student's feedback on assignment 3438636.
- **Headless Claude.** `claude -p --chrome` reaches the user's Chrome and their logged-in Moodle. The structured
  answer is in `structured_output`. `--allowedTools` alone does not restrict tools; `--tools` does, so the driver
  passes `--tools "Read"` (all other built-ins off) plus `--allowedTools mcp__claude-in-chrome`, `--no-session-persistence`,
  `--json-schema`, `--max-budget-usd` and `--model claude-sonnet-5-5`. With the default (Opus) model a run cost about
  $0.5 in 4 turns; with Sonnet about $0.10-0.35 per run. That counts against the Claude subscription's usage and is
  not billed separately.
- **Claude Code login: once per computer that uploads.** What worked: sign out of the wrong claude.ai account in
  Chrome, run `claude auth login` (or use the site's readiness button), and sign in in the browser; the browser
  callback completes the login. Pasting the code into the terminal did not work, neither in the Claude desktop app's
  terminal nor in Windows Terminal.
- **The run's folder.** Each upload run starts in a fresh temp folder outside OneDrive (`tempfile.mkdtemp`) that holds
  only a copy of the ZIP, checked against the batch's sha256. That folder is the run's working folder and its only
  `--add-dir`, and it is deleted afterwards. The run never starts in the shared upload folder: anyone on the team
  can write there, and with `--setting-sources project` a `.claude/settings.json` (hooks) or `CLAUDE.md` there would
  be loaded.
- **Resolved (read permission):** the first fully automatic test had `file_upload` refused because `--tools ""` left
  the run no file-read permission. The upload run now has `--tools "Read"` only (no Bash, Edit or Write), scoped to its
  temp folder with the single ZIP. The user approved this on 2026-10-22. The connection check keeps `--tools ""`.

**Before the first real upload:** do it once on a test assignment (ask the lecturer for one). Never try it for the
first time on an assignment with real students.

**Real Moodle only (Noa's decision, 2026-10-26).** There is no demo or simulated mode: no fake data folder, no
simulated driver, no `MOODLE_DRIVER=simulate` / `MOODLE_READY=simulate`, no `send --simulate`. Every pull and every upload
first runs `actions.require_moodle`: the Claude extension in Chrome must be connected and Chrome logged in to Moodle (a
passing check from the last 30 minutes counts, otherwise a short Claude check runs now, opening a closed Chrome first).
If not, nothing is pulled or uploaded and the site says what to fix. A pull always downloads fresh from Moodle: a ZIP
already waiting in Downloads is not taken. Fakes live only in `tests/` (`tests/fakes.py`, the dashboard tests' conftest).

Never upload without the user's yes for that batch, never to a different assignment than the ZIPs were built for,
and never change assignment settings. Grades (`Grades for Moodle worksheet.csv`) still go by hand through Actions →
"העלאת גיליון ציונים", with Moodle's preview checked before confirming; that needs "Offline grading worksheet" on
in the assignment.

## Problems already solved (don't re-solve)

| Problem | Fix |
|---|---|
| OneDrive refused to sync files whose names had invisible RTL marks (U+200E/2068/2069), a broken char (U+FFFD) or emoji, which phones add | Extracted originals stay in the local work folder; the shared folder only has clean names. `status` checks it |
| Students name files anything ("Untitled (7).pdf", their own name, ...) | Ignore filenames. Only the folder's participant id matters |
| A name with words after the extension ("x.pdf דיסקרטית מתוקן") or none at all became "0044.pdf דיסקרטית מתוקן" / "0474", which grading can't open as a PDF (2026-11-03) | `anonymize.extension`: a real extension stays; otherwise the file's first bytes decide (PDF, JPEG, PNG). The next pull of such a student writes `0044.pdf` and moves the old name to `Earlier versions` |
| `claude update` in `start.bat` hung for over 5 minutes (2026-11-03): nothing after it ran, so the site and the night pull stayed down until someone killed it | `start.bat` runs the update through PowerShell and stops it (with its children) after `CLAUDE_UPDATE_WAIT_S` seconds (default 120), says so, and starts the version already on the computer |
| A test through the site ran old code (2026-11-02: the server was 69 commits behind `main`), and every merge reached a teammate only when their computer restarted | `dashboard/updater.py` (2026-11-03): the server asks GitHub every `UPDATE_CHECK_MINUTES` (default 60; first check 10 minutes after it starts). When `main` moved forward, the checkout is on `main` with no edits to tracked files, nothing runs (`actions.running_jobs`, no night pull in `scheduler.in_night_window`), it serves port 8765 and this checkout's `autostart.vbs` runs, it takes the buttons' lock and stops (`httpd.shutdown`). The watchdog runs `start.bat` within a minute (git pull, claude update, pip), and the site reloads itself when `/api/changes` reports a new `version`. A version it already tried (`Self update.json` in the work folder) is not tried again, so a failing `git pull` can't restart it every hour. `AUTO_UPDATE=off` in `.env` turns it off. A server from before this change still needs one restart. Before a real test now: wait for it, or stop the server's python process (the watchdog brings it back within a minute) |
| After a pull cut to N students ("כמה?"), the next pull (also the night pulls) asked Moodle for everyone (2026-11-03) | By design: `_since` counts only complete pulls. Release the pull task after a cut pull unless the rest is wanted |
| Stopping the headless `claude -p --chrome` of a pull did not stop the download | `download_parts.js` keeps running in its Moodle tab and parts keep landing in Downloads until the tab is closed. Close it, and move those parts aside before the next pull |
| Chrome left the ZIP as "Unconfirmed *.crdownload" | Chrome was asking where to save. Turn off "Ask where to save each file" in Chrome settings |
| Re-running ingest failed deleting folders 7-Zip extracted as read-only | `ingest.remove_tree` clears read-only and retries |
| A pull that failed halfway could leave an empty key (the next pull renumbered everyone) or lose the files of students not in the next download; two pulls in one minute overwrote the kept download | `anonymize.prepare` updates "1 - Submissions to grade" in place, only what changed, each file and the key via `.tmp` + `os.replace`; `check_key` refuses to pull (before Chrome opens) when the key is empty or broken but submissions exist; kept downloads are named to the second, with " (2)" when taken. `tests/moodle/test_repeated_pulls.py` pulls 8 times in a row with changing submissions |
| Moodle skips a feedback file identical in name/content to the submission | Feedback files are named `feedback.pdf` inside each student's folder |
| Folders the web upload never saw (empty ones) | `guide` puts a `README.txt` in "2 - Graded with comments" and "3 - Ready to upload to Moodle" so they exist from day one |

## Grading through Claude Code (no API key)

Without `ANTHROPIC_API_KEY`, `grading.claude_ask()` grades through the Claude Code that is logged in on the computer
(the team's subscription, like the upload), in `grading/claude_cli.py`: one `claude -p` per submission with
`--tools Read` only, `--no-chrome`, `--strict-mcp-config`, `--setting-sources project`, `--no-session-persistence`,
the same SYSTEM prompt (`--system-prompt-file`), `--json-schema SCHEMA`, `--effort high` and the chosen model, in a
fresh temp folder outside OneDrive that holds only that submission's page images (and the official solution). The
request goes in on stdin. The answer is the same JSON as through the API, so everything after it is shared.
The dashboard reports `claudeVia: "api" | "code" | null`. Checked on 2026-10-22 on a synthetic submission: graded,
flagged for review, marked PDF written, ~20 seconds with Opus. Claude Code 2.1.247 refused `claude-opus-5-5`
("version 2.1.280 or newer is required"); `start.bat` now runs `claude update`.

## What grading gets

For each assignment, in its folder:
- `1 - Submissions to grade/0001.pdf ...`: the submissions. Mostly phone scans of handwriting. For "הגשה 0" the rules say
  one PDF, each question on its own page, so a page usually maps to a question (students don't always follow it).
- `Assignment details.json`: which questions were asked (sheet and number), the rules, and `max_grade` / `rubric`
  (null until the lecturer gives them).
- The questions and solutions: `YallaLinearit/Course Material (tex)/exercises and solutions/` in the lecturer's OneDrive,
  and the exercise and solutions booklets on the course page in Moodle.

To start on the grading bot: open the shared folder, read the assignment's `README.txt` and `Assignment details.json`,
and try a handful of submissions before running on all of them.

## What grading must return

The feedback a student gets is **their own submission, marked**: the full PDF with the grader's comments
written on the page where each mistake is (say, at the determinant step that went wrong), not only a grade
and a line in a spreadsheet. So per submission the grader writes:
- `2 - Graded with comments/0001.pdf`: the student's whole submission with comments added in place.
  Many submissions are phone scans of handwriting, so comments go on top of the page images.
  **Keep each marked PDF around 1–2 MB** (pages as JPEG at ~150 dpi). BGU Moodle takes 31 MB per upload:
  at the scans' own size (avg 4.7 MB, up to 56 MB) one assignment of 285 needs 45 ZIPs and 6 files don't fit
  at all; at ~1.5 MB it's about 15 ZIPs. Compress in the grading code: on Ori's computer, Windows Smart App
  Control blocks PyMuPDF's DLLs, so check what runs on the grading machine.
- a row in `Grades.csv`: `number,grade,feedback`, where `feedback` is a short summary.
- `Grading notes/0001.json`: what Claude said per question (comment, mistakes, unsure), the marks, and why it needs a person.

**Manual review.** Claude sends every work it is not sure of (`needs_review`, with `review_reason` saying which question and page,
and `review_kind`) and every work whose grading failed to the site's "בדיקה ידנית" queue (`#/review`). There a TA picks ready-made
comments (the rubric's `deductions`, the assignment's common mistakes, Claude's own), the points follow, and "approve" calls
`grading.save_review`: it writes `approved = "<user> (<PC>) <time>"` in `Grades.csv` and redraws the marked PDF's summary page.

**Editing a grade** ("ערוך ציון", Matan 2026-11-07): the same page, with a required "סיבה לשינוי" for any work that
already has a grade (not for a first approval from the queue). Every save goes through one function,
`grading/grade_edit.edit_grade`, which updates each place in `TARGETS` in order (the event ledger, the marked PDF's summary
page, `Grading notes`, the editor's `Grades by <name>.csv` as an approved row, which wins the merge and is what goes to
Moodle, and last the statistics database in the Drive, `Statistics/`) and logs who, when, from, to and why to `activity_log/` (`<assignment>/Activity log/<who>.jsonl`, one file per
writer; any other action may write there too). A new place to update is one more target, not a change to the function.
The database is connected (2026-11-10): `DatabaseTarget` gets `datastore/ledger.LedgerStore` at dashboard start, and
`StatsTarget` rebuilds `Statistics/<course>/Assignment N.json`. A target with `optional = True` (the statistics: derived,
rebuilt by the next reader) does not stop an edit when it fails; it is logged as `not_updated`.

`python -m moodle upload` takes it from there.

## Working in git

Work on a branch and open a Pull Request; `main` changes only through reviewed PRs.
Run `python -m pytest` before pushing (CI runs it on every PR too).
