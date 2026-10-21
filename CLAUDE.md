# Assignment Checker: notes for Claude

University project (BGU) that grades student assignments with Claude:
pull submissions from Moodle → grade by rubric → TA approves → return grades and marked files to Moodle.
Courses are large (up to ~1,000 students per assignment). The team works in Hebrew.

## Repo layout

| Path | What |
|---|---|
| `moodle/` | Moving files between Moodle and the grader. `python -m moodle status|ingest|upload <id>` |
| `moodle/status.py` | What's done for an assignment; file names OneDrive would refuse |
| `moodle/paths.py` | Where student data lives on the machine (see below) |
| `moodle/anonymize.py` | Numbers submissions 0001..N and writes `mapping.csv` |
| `moodle/ingest.py` | Downloads ZIP → extracted → numbered |
| `moodle/upload.py` | `results.csv` + `marked/` → `upload/grades.csv` + `upload/feedback-N.zip` |
| `docs/` | Static Hebrew (RTL) dashboard prototype on GitHub Pages; demo data only |
| `main.py` | Python skeleton |
| `test_*.py` | Tests; run each with `python test_<name>.py` |

## Student data: never in the repo

This repo is **public**. Submissions, names, ID numbers (ת"ז), emails and grades never go into git.
`.gitignore` blocks `data/` and `*.zip` as a safety net, but student data lives in two folders outside the repo
(see `moodle/paths.py`):

```
data folder: shared (the lecturer's OneDrive)      ASSIGNMENT_DATA, default ~/assignment-data
  raw/<assignment id>-<timestamp>.zip      ZIP exactly as Moodle gave it
  submissions/<assignment id>/
    assignment.json  course, name, due date, which questions, submission rules, max grade, rubric
    materials/  the questions and official solutions (from the course page in Moodle)
    anon/       0001.pdf, 0002.pdf, ... (0001-2.pdf for a second file)  ← the grader reads only these
    mapping.csv number → participant id → original folder               ← the one "key"
    results.csv number,grade,feedback                                   ← grading output
    marked/     0001.pdf, ... marked files by number
    upload/     grades.csv, feedback-N.zip                              ← what goes back to Moodle

work folder: the downloader's computer only          ASSIGNMENT_WORK, default ~/assignment-work
  <assignment id>/original/   one folder per student: "<full name>_<participant id>_assignsubmission_file"
```

`original/` never goes to OneDrive: students' file names break its sync (see below). It can be rebuilt from the ZIP in `raw/`.
`python -m moodle status <id>` shows what's done and flags any file name OneDrive would refuse.

The **key** that links a number back to a student is the Moodle *participant id* in the folder name
(not the ת"ז). It lives only in `mapping.csv`.
Numbers are assigned in participant-id order, so re-downloading gives everyone the same number.

## One downloader, one key

There is **one** `mapping.csv` per assignment, and it belongs to the one person who downloads from Moodle
and uploads back to it. Today that is Ori (orimes-source). Everyone else gets only the numbered files and
never downloads from Moodle themselves: a second download would make a second key, and the two could disagree.
- Ori: download (when he asks) → `python -m moodle ingest <id>` → it lands in the shared data folder.
- Team: grade from `anon/` there, write `results.csv` and `marked/` next to it.
- Ori: `python -m moodle upload <id>` → a TA uploads to Moodle.

The shared data folder is the lecturer's OneDrive (5 TB), not this repo (public, and one assignment is ~2.5 GB).

## Connecting the lecturer's OneDrive

Once the lecturer shares the folder with Ori's university account:
1. In OneDrive on the web, open the shared folder → "Add shortcut to My files", so it syncs to this computer
   (OneDrive signed in with the university account; it shows up under `C:\Users\<user>\OneDrive - <university>\`).
2. Move everything in `~/assignment-data` into that folder, then point the scripts at it:
   `setx ASSIGNMENT_DATA "<that folder>"` (new terminals pick it up).
3. Run `python -m moodle status <id>` for each assignment: counts must match and all names must be safe.
4. Teammates add the same shortcut on their computers and set `ASSIGNMENT_DATA` the same way; they don't need `ASSIGNMENT_WORK`.

When working with this data:
- Grade from `anon/` only. Don't open `original/` or print names, ת"ז or emails into chat, commits or logs.
- `mapping.csv` sits in the shared folder, so everyone with access to it can link numbers to students. Don't open it while grading.
- Some students write their name or ת"ז inside the PDF or its filename; the team accepted that. Don't copy it anywhere.
- Match results to students **by number, never by row order**: one shifted row would give 1,000 students the wrong grade.

## Moodle (moodle.bgu.ac.il)

There is **no Moodle API**. Claude in Chrome works in the user's own logged-in Chrome.
- The user logs in themselves. Claude never types Moodle passwords.
- Download only when the downloader (see above) asks. No scheduled downloads: Moodle sessions expire, and
  downloading per schedule wastes runs. Every **upload** to Moodle (grades or feedback) is a separate step that a person approves. Never upload on your own.
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
| OneDrive refused to sync files whose names had invisible RTL marks (U+200E/2068/2069), a broken char (U+FFFD) or emoji, which phones add | Extracted originals stay in the local work folder; the shared folder only has clean names (`0001.pdf`). `status` checks it |
| Students name files anything ("Untitled (7).pdf", their own name, ...) | Ignore filenames. Only the folder's participant id matters |
| Chrome left the ZIP as "Unconfirmed *.crdownload" | Chrome was asking where to save. Turn off "Ask where to save each file" in Chrome settings for unattended runs |
| Re-running ingest failed deleting folders 7-Zip extracted as read-only | `ingest.remove_tree` clears read-only and retries |
| Moodle skips a feedback file identical in name/content to the submission | Feedback files are named `feedback.pdf` inside each student's folder |

## What grading gets

For each assignment, in its folder in the shared data folder:
- `anon/0001.pdf ...`: the submissions. Mostly phone scans of handwriting. For "הגשה 0" (3438636) the rules say
  one PDF, each question on its own page, so a page usually maps to a question (students don't always follow it).
- `assignment.json`: which questions were asked (sheet and number), the rules, and `max_grade` / `rubric`
  (null until the lecturer gives them).
- `materials/`: the exercise booklet and the solutions booklet the questions come from.

To start on the grading bot: open the shared folder (see "Connecting the lecturer's OneDrive"), read
`assignment.json`, and try a handful of `anon/` files before running on all of them.

## What grading must return

The feedback a student gets is **their own submission, marked**: the full PDF with the grader's comments
written on the page where each mistake is (say, at the determinant step that went wrong), not only a grade
and a line in a spreadsheet. So per submission the grader writes:
- `marked/0001.pdf`: the student's whole submission with comments added in place.
  Many submissions are phone scans of handwriting, so comments go on top of the page images.
- a row in `results.csv`: `number,grade,feedback`, where `feedback` is a short summary.

`python -m moodle upload` takes it from there.

## Working in git

Work on a branch and open a Pull Request; `main` changes only through reviewed PRs.
Run all `test_*.py` before pushing.
