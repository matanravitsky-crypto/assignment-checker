# Assignment Checker: notes for Claude

University project (BGU) that grades student assignments with Claude:
pull submissions from Moodle → grade by rubric → TA approves → return grades and marked files to Moodle.
Courses are large (up to ~1,000 students per assignment). The team works in Hebrew.

## Repo layout

Each folder has a README.md that explains it.

| Path | What |
|---|---|
| `moodle/` | Steps 1 and 3: Moodle ZIP → numbered submissions (`ingest`), and grades + marked files → upload to Moodle (`upload`). `python -m moodle ingest|status|upload <id>`, `guide` |
| `moodle/paths.py` | Every folder and file name in the shared folder (constants). Everything else imports names from here |
| `grading/` | Step 2: grading with Claude. `python -m grading <id>` or the dashboard's "Grade" button. Its README has the input/output contract, the rubric format and the `Grades.csv` columns |
| `dashboard/` | Local server that connects the website to the shared folder: `python -m dashboard serve` (or `start.bat`) |
| `dashboard/actions.py` | Pull (`moodle ingest`, with a lock and a key-conflict check), prepare return (`moodle upload`), and the state the site shows (numbers only, no names) |
| `website/` | The dashboard site (static HTML/JS, Hebrew RTL). Published to GitHub Pages from `main` by `.github/workflows/website.yml`; demo data unless it runs through `dashboard/` |
| `tests/` | All tests (`tests/moodle/`, `tests/dashboard/`). Run `python -m pytest` from the repo root; CI runs them on every PR |
| `start.bat` | Double-click: sets up `.venv` once and starts the dashboard |

## Student data: never in the repo

This repo is **public**. Submissions, names, ID numbers (ת"ז), emails and grades never go into git.
`.gitignore` blocks `data/` and `*.zip` as a safety net, but student data lives outside the repo.
Folders and files have plain English names that say what they are (the README.txt files inside explain
them in Hebrew). The names are constants
in `moodle/paths.py`, so code never spells them out by hand:

```
Exercise Checking System/                  the data folder (ASSIGNMENT_DATA, default ~/Exercise Checking System)
  README.txt
  Linear Algebra/                           a folder per course
    README.txt
    Assignment 0 - Sets and Complex Numbers/   a folder per assignment (its Hebrew title is in the details)
      README.txt
      1 - Submissions to grade/   0001.pdf, 0002.pdf, ... (0001-2.pdf = second file)  ← grading reads only these
      2 - Graded with comments/   0001.pdf ... marked by the grader
      3 - Ready to upload to Moodle/  built by `upload`: ZIPs, grades sheet, upload steps
      Assignment details.json     Moodle id, course, name, Hebrew title, due date, questions, rules, max_grade, rubric
      Grades.csv                  number,grade,feedback  ← grading output
      Key - number to student.csv number → Moodle participant id → original folder  ← the one key
      Backup - Moodle downloads/  every ZIP exactly as Moodle gave it (backup only; parts as "part N")

Moodle originals/                          on the downloader's computer only (ASSIGNMENT_WORK)
  <course>/<assignment>/   the extracted ZIP: one folder per student, "<full name>_<participant id>_assignsubmission_file"
```

The extracted ZIP never goes to OneDrive: students' file names break its sync (see below). It can be rebuilt
from the ZIP. Commands take the assignment's Moodle id; `paths.find_assignment` finds its folder through
`Assignment details.json`. A new assignment needs its folder names once, in English:
`python -m moodle ingest <id> --course "Linear Algebra" --name "Assignment 1 - Vectors"`
(its Hebrew title comes from the ZIP's file name).

The **key** that links a number back to a student is the Moodle *participant id* in the folder name
(not the ת"ז). It lives only in the key table. A student keeps their number on every later download:
`anonymize.prepare` reads the existing key, and students who submitted since then get the next free numbers.
Never delete or rebuild the key table of an assignment that is being graded.

## Anyone can pull, one key

Anyone on the team can download from Moodle and pull: the dashboard's "Pull submissions" button or
`python -m moodle ingest <id>` on their own computer. There is still **one** key table per assignment, in the
shared folder, and `anonymize.prepare` reads it before numbering, so every student keeps their number no matter
who pulls. What can break it is two pulls of the same assignment at once, before OneDrive synced the key between them.
So `dashboard/actions.py` guards the dashboard's pull:
- **Lock:** while a pull runs, the assignment folder has `Pull in progress.txt` (who and since when). Another
  pull of that assignment waits until it's gone (a lock older than 30 minutes counts as stuck and is ignored).
- **Conflicts:** if OneDrive still made a conflict copy of the key (`Key - number to student-<PC>.csv`), the
  dashboard shows it and refuses to pull until someone merges the copy into the main key and deletes it.
- Let OneDrive finish syncing (the cloud icon) before pulling on another computer.

Then:
- Team: grade from `1 - Submissions to grade`, write `Grades.csv` and `2 - Graded with comments` next to it.
- Whoever returns: `python -m moodle upload <id>` (or "Prepare return" in the dashboard) → upload to Moodle (below).

## The shared folder (lecturer's OneDrive)

`YallaLinearit/Exercise Checking System/` in the lecturer's (Nadav Meir) OneDrive (5 TB) mirrors Ori's
`~/Exercise Checking System`, with a folder per course (Linear Algebra, Discrete Mathematics):
https://bgu365-my.sharepoint.com/personal/mein_bgu_ac_il/_layouts/15/onedrive.aspx?id=%2Fpersonal%2Fmein%5Fbgu%5Fac%5Fil%2FDocuments%2FYallaLinearit%2FExercise%20Checking%20System
Next to it, `YallaLinearit/Course Material (tex)/exercises and solutions/` has the linear algebra questions and solutions as .tex.

For now it is **not synced** to anyone's computer: the team's student accounts have no OneDrive of their own
(the "Add shortcut to My files" button fails, and `bgu365-my.sharepoint.com/my` returns 404). So:
- Ori works locally and uploads from the web: in the shared folder, Create or upload → Folder upload → the course
  folder (e.g. `~/Exercise Checking System/Linear Algebra`). Re-uploading replaces files with the same name.
  The folder picker is a native Windows dialog Claude can't see, so Ori picks the folder himself.
- Teammates open the link above (the lecturer shares it with them) and view or download what they need,
  e.g. `Linear Algebra/Assignment 0 - Sets and Complex Numbers/1 - Submissions to grade/0023.pdf`. No install needed.

When university OneDrive is enabled for the team, sync instead: the folder → "Add shortcut to My files",
then `setx ASSIGNMENT_DATA "<synced path to Exercise Checking System>"`, and `python -m moodle status <id>` to check.

When working with this data:
- Grade from `1 - Submissions to grade` only. Don't open the extracted originals or print names, ת"ז or emails into chat, commits or logs.
- The key table sits in the shared folder, so everyone with access to it can link numbers to students. Don't open it while grading.
- Some students write their name or ת"ז inside the PDF or its filename; the team accepted that. Don't copy it anywhere.
- Match grades to students **by number, never by row order**: one shifted row would give 1,000 students the wrong grade.

## Moodle (moodle.bgu.ac.il)

There is **no Moodle API**. Claude in Chrome works in the user's own logged-in Chrome.
- The user logs in themselves. Claude never types Moodle passwords.
- Download only when someone on the team asks. No scheduled downloads: Moodle sessions expire, and
  downloading per schedule wastes runs. Every **upload** to Moodle (grades or feedback) needs a person's yes.
- Submissions page: `https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id=<assignment id>&action=grading`.
  The assignment id is the `id=` in that URL (the number at the end of the ZIP name too).
- Download: Actions (פעולות) → "הורדת כל ההגשות (השתמש ב 7ZIP לפתיחה)". Keep "organize submissions in folders per student" checked.
  The ZIP lands in Downloads as `<course code>-<assignment>-<id>.zip`. Open with 7-Zip, not Python's zipfile (it garbles some Hebrew names).
- Feedback upload: Actions → "העלאת מספר קובצי משוב כקובץ 7Zip אחד" → the ZIPs in `3 - Ready to upload to Moodle`
  (`Graded - part 01.zip` ...), one at a time. Whoever uploads checks Moodle's confirmation list
  (file → student) before importing; `Upload steps.txt` there has the steps and a checklist. That page takes .zip
  only, up to **31 MB** ("הגודל המירבי לקבצים חדשים", checked on assignment 3438636), so ZIPs are split at 30 MB
  (`--max-mb` to change). The course's max upload size is a course setting, capped by the site.
- Grades upload needs **"Offline grading worksheet"** turned on in the assignment settings (not on yet in assignment 3438636).
  Then: Actions → download the grading worksheet, run `python -m moodle upload <id>`, upload `Grades for Moodle worksheet.csv`.

## Uploading to Moodle with Claude

Claude uploads the marked files itself through Claude in Chrome, as much as it can. A person can always do
the same by hand with the 30 MB ZIPs (see `Upload steps.txt`).

**Before the first real upload:** do it once on a test assignment (ask the lecturer for one). Never try the
steps for the first time on an assignment with real students.

1. Build ZIPs Claude can carry: `python -m moodle upload <id> --for-claude`. Each ZIP is under 9 MB
   (Claude in Chrome's `file_upload` takes up to 10 MB per call). Files over 9 MB on their own are listed as
   too big; they need to be saved smaller first (see "What grading must return").
2. The upload folder must be readable by this session: if it's not under the working directory, ask for access to it.
3. **Ask the user once for the whole batch**, saying the assignment, how many ZIPs, and how many students.
   Their yes covers uploading those ZIPs and confirming Moodle's import screens for this assignment only.
4. For each ZIP, in order:
   a. Open `https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id=<id>&plugin=file&pluginsubtype=assignfeedback&action=viewpluginpage&pluginaction=uploadzip`.
   b. Open the file picker → "העלאת קובץ" → find the `input[type=file]` with `find`/`read_page` and use
      `file_upload` with the ZIP's path. Don't click the file input (it opens a native dialog Claude can't see).
      Then click "העלאת קובץ זה" and submit the form.
   c. Moodle shows a confirmation list (file → student). Check its row count equals the number of files in the ZIP
      (`python -c "import zipfile,sys; print(len(zipfile.ZipFile(sys.argv[1]).namelist()))" <zip>`).
      If it differs, stop and tell the user. Don't print the student names from that screen.
   d. Confirm, read the result ("N files imported"), and append `<zip name> <N>` to `Uploaded.txt` in the upload folder.
5. If anything fails mid-way, `Uploaded.txt` says where to resume. Re-uploading a ZIP replaces the same
   students' feedback file, so a retry is safe.
6. Grades (`Grades for Moodle worksheet.csv`) go the same way through Actions → "העלאת גיליון ציונים", with Moodle's
   preview checked before confirming. That needs "Offline grading worksheet" on in the assignment.

Never upload without the user's yes for that batch, never to a different assignment than the ZIPs were built for,
and never change assignment settings.

## Problems already solved (don't re-solve)

| Problem | Fix |
|---|---|
| OneDrive refused to sync files whose names had invisible RTL marks (U+200E/2068/2069), a broken char (U+FFFD) or emoji, which phones add | Extracted originals stay in the local work folder; the shared folder only has clean names. `status` checks it |
| Students name files anything ("Untitled (7).pdf", their own name, ...) | Ignore filenames. Only the folder's participant id matters |
| Chrome left the ZIP as "Unconfirmed *.crdownload" | Chrome was asking where to save. Turn off "Ask where to save each file" in Chrome settings |
| Re-running ingest failed deleting folders 7-Zip extracted as read-only | `ingest.remove_tree` clears read-only and retries |
| Moodle skips a feedback file identical in name/content to the submission | Feedback files are named `feedback.pdf` inside each student's folder |
| Folders the web upload never saw (empty ones) | `guide` puts a `README.txt` in "2 - Graded with comments" and "3 - Ready to upload to Moodle" so they exist from day one |

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

`python -m moodle upload` takes it from there.

## Working in git

Work on a branch and open a Pull Request; `main` changes only through reviewed PRs.
Run `python -m pytest` before pushing (CI runs it on every PR too).
