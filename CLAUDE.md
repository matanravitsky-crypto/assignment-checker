# Assignment Checker: notes for Claude

University project (BGU) that grades student assignments with Claude:
pull submissions from Moodle → grade by rubric → TA approves → return grades and marked files to Moodle.
Courses are large (up to ~1,000 students per assignment). The team works in Hebrew.

## Repo layout

| Path | What |
|---|---|
| `moodle/` | Moving files between Moodle and the grader. `python -m moodle pending`, `ingest <id>`, `upload <id>` |
| `moodle/paths.py` | Where student data lives on the machine (see below) |
| `moodle/anonymize.py` | Numbers submissions 0001..N and writes `mapping.csv` |
| `moodle/ingest.py` | Downloads ZIP → extracted → numbered |
| `moodle/upload.py` | `results.csv` + `marked/` → `upload/grades.csv` + `upload/feedback-N.zip` |
| `moodle/schedule.py` | Which assignments in `assignments.json` are due for download |
| `moodle/download_task.md` | The scheduled download task's prompt |
| `assignments.json` | The team's assignments and due dates (no student data) |
| `docs/` | Static Hebrew (RTL) dashboard prototype on GitHub Pages; demo data only |
| `main.py` | Python skeleton |
| `test_*.py` | Tests; run each with `python test_<name>.py` |

## Student data: never in the repo

This repo is **public**. Submissions, names, ID numbers (ת"ז), emails and grades never go into git.
`.gitignore` blocks `data/` and `*.zip` as a safety net, but the data folder is outside the repo anyway:

```
~/assignment-data/                       (ASSIGNMENT_DATA overrides it)
  raw/<assignment id>-<timestamp>.zip      ZIP exactly as Moodle gave it
  submissions/<assignment id>/
    original/   one folder per student: "<full name>_<participant id>_assignsubmission_file"
    anon/       0001.pdf, 0002.pdf, ... (0001-2.pdf for a second file)  ← the grader reads only these
    mapping.csv number → participant id → original folder               ← private, the "key"
    results.csv number,grade,feedback                                   ← grading output
    marked/     0001.pdf, ... marked files by number
    upload/     grades.csv, feedback.zip                                ← what goes back to Moodle
```

The **key** that links a number back to a student is the Moodle *participant id* in the folder name
(not the ת"ז). It lives only in `mapping.csv` on the machine that downloaded the submissions.
Numbers are assigned in participant-id order, so re-downloading gives everyone the same number.

When working with this data:
- Grade from `anon/` only. Don't open `original/` or print names, ת"ז or emails into chat, commits or logs.
- Some students write their name or ת"ז inside the PDF or its filename; the team accepted that. Don't copy it anywhere.
- Match results to students **by number, never by row order**: one shifted row would give 1,000 students the wrong grade.

## Moodle (moodle.bgu.ac.il)

There is **no Moodle API**. Claude in Chrome works in the user's own logged-in Chrome.
- The user logs in themselves. Claude never types Moodle passwords.
- Downloads run when the user asks, or from the scheduled task they set up on their computer (below).
  Every **upload** to Moodle (grades or feedback) is a separate step that a person approves. Never upload on your own.
- Submissions page: `https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id=<assignment id>&action=grading`.
  The assignment id is the `id=` in that URL (the number at the end of the ZIP name too).
- Download: Actions (פעולות) → "הורדת כל ההגשות (השתמש ב 7ZIP לפתיחה)". Keep "organize submissions in folders per student" checked.
  The ZIP lands in Downloads as `<course>-<assignment>-<id>.zip`. Open with 7-Zip, not Python's zipfile (it garbles some Hebrew names).
- Feedback upload: Actions → "העלאת מספר קובצי משוב כקובץ 7Zip אחד" → `upload/feedback-N.zip`.
  A TA uploads these in Moodle and checks Moodle's confirmation list (file → student) before importing.
  The scripts split ZIPs at 9 MB, the limit for uploading through Claude in Chrome; if a TA uploads by hand,
  the limit is Moodle's own ("maximum size for new files" on that page), not yet checked.
- Grades upload needs **"Offline grading worksheet"** turned on in the assignment settings (not on yet in assignment 3438636).
  Then: Actions → download the grading worksheet, run `python -m moodle upload <id>`, upload `upload/grades.csv`.

## Problems already solved (don't re-solve)

| Problem | Fix |
|---|---|
| OneDrive refused to sync files whose names had invisible RTL marks (U+200E/2068/2069), a broken char (U+FFFD) or emoji, which phones add | Data lives in `~/assignment-data`, outside OneDrive. The grader uses clean names `0001.pdf` |
| Students name files anything ("Untitled (7).pdf", their own name, ...) | Ignore filenames. Only the folder's participant id matters |
| Chrome left the ZIP as "Unconfirmed *.crdownload" | Chrome was asking where to save. Turn off "Ask where to save each file" in Chrome settings for unattended runs |
| Re-running ingest failed deleting folders 7-Zip extracted as read-only | `ingest.remove_tree` clears read-only and retries |
| Moodle skips a feedback file identical in name/content to the submission | Feedback files are named `feedback.pdf` inside each student's folder |

## What grading must return

The feedback a student gets is **their own submission, marked**: the full PDF with the grader's comments
written on the page where each mistake is (say, at the determinant step that went wrong), not only a grade
and a line in a spreadsheet. So per submission the grader writes:
- `marked/0001.pdf`: the student's whole submission with comments added in place.
  Many submissions are phone scans of handwriting, so comments go on top of the page images.
- a row in `results.csv`: `number,grade,feedback`, where `feedback` is a short summary.

`python -m moodle upload` takes it from there.

## Assignments and automatic download

`assignments.json` lists the team's assignments: Moodle id, course, name, due date (ISO with offset).
It has no student data, so it lives in git: add an assignment there and every computer picks it up.
`python -m moodle pending` lists the ones past due that this computer hasn't downloaded since the due date.

`moodle/download_task.md` is the scheduled task that does the rest: for each pending assignment it confirms in
Moodle that the assignment is closed, downloads it with Claude in Chrome, runs `ingest`, and notifies.

## Setting up a computer

When a team member asks to set up their computer ("תגדיר לי את המחשב"), do this:
1. Install what's missing: `winget install Git.Git GitHub.cli Python.Python.3.12 7zip.7zip`, then `gh auth login` (they log in themselves).
2. Clone this repo and run all `test_*.py`.
3. They install the Claude in Chrome extension, connect it to the same Claude organization as this app, and log in to Moodle in that Chrome.
4. They turn off "Ask where to save each file" in Chrome settings (otherwise downloads stall on a Save As window).
5. Create a Claude desktop scheduled task from `moodle/download_task.md` with `<REPO>` replaced by the clone's absolute path,
   schedule `0 8,20 * * *`. Tell them it only runs while the Claude app is open, and catches up when it next opens.

Every computer that downloads also holds `mapping.csv`, the key from numbers to students. Keep that in mind when choosing who downloads.

## Working in git

Work on a branch and open a Pull Request; `main` changes only through reviewed PRs.
Run all `test_*.py` before pushing.
