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

## The shared folder (lecturer's OneDrive)

`YallaLinearit/מערכת בדיקת תרגילים/` in the lecturer's (Nadav Meir) OneDrive holds the project's data:
https://bgu365-my.sharepoint.com/personal/mein_bgu_ac_il/_layouts/15/onedrive.aspx?id=%2Fpersonal%2Fmein%5Fbgu%5Fac%5Fil%2FDocuments%2FYallaLinearit%2F%D7%9E%D7%A2%D7%A8%D7%9B%D7%AA%20%D7%91%D7%93%D7%99%D7%A7%D7%AA%20%D7%AA%D7%A8%D7%92%D7%99%D7%9C%D7%99%D7%9D
Inside it, `assignment-data/` mirrors Ori's `~/assignment-data` (raw/, submissions/<id>/...).
Next to it, `YallaLinearit/Course Material (tex)/exercises and solutions/` has the questions and solutions as .tex.

For now it is **not synced** to anyone's computer: the team's student accounts have no OneDrive of their own
(the "Add shortcut to My files" button fails, and `bgu365-my.sharepoint.com/my` returns 404). So:
- Ori works locally in `~/assignment-data` and uploads to the shared folder from the web
  (Create or upload → Folder upload → `assignment-data`). Re-uploading replaces files with the same name.
- Teammates open the link above (the lecturer shares it with them) and view or download what they need,
  e.g. `assignment-data/submissions/3438636/anon/0023.pdf`. No install needed.

When university OneDrive is enabled for the team, sync instead: the folder → "Add shortcut to My files",
then `setx ASSIGNMENT_DATA "<synced path to assignment-data>"`, and `python -m moodle status <id>` to check.

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
- Feedback upload: Actions → "העלאת מספר קובצי משוב כקובץ 7Zip אחד" → `upload/feedback-N.zip`, one at a time.
  A person (TA or lecturer) uploads them and checks Moodle's confirmation list (file → student) before importing;
  `upload/הוראות העלאה.txt` has the steps and a checklist of ZIPs. That page takes .zip only, up to **31 MB**
  ("הגודל המירבי לקבצים חדשים", checked on assignment 3438636), so ZIPs are split at 30 MB (`--max-mb` to change).
  A higher limit would mean fewer ZIPs: the course's max upload size is a course setting, capped by the site.
- Grades upload needs **"Offline grading worksheet"** turned on in the assignment settings (not on yet in assignment 3438636).
  Then: Actions → download the grading worksheet, run `python -m moodle upload <id>`, upload `upload/grades.csv`.

## Uploading to Moodle with Claude

Claude uploads the marked files itself through Claude in Chrome, as much as it can. A person can always do
the same by hand with the 30 MB ZIPs (see `upload/הוראות העלאה.txt`).

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
   d. Confirm, read the result ("N files imported"), and append `<zip name> <N>` to `upload/uploaded.txt`.
5. If anything fails mid-way, `upload/uploaded.txt` says where to resume. Re-uploading a ZIP replaces the same
   students' feedback file, so a retry is safe.
6. Grades (`upload/grades.csv`) go the same way through Actions → "העלאת גיליון ציונים", with Moodle's preview
   checked before confirming. That needs "Offline grading worksheet" on in the assignment.

Never upload without the user's yes for that batch, never to a different assignment than the ZIPs were built for,
and never change assignment settings.

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
  **Keep each marked PDF around 1–2 MB** (pages as JPEG at ~150 dpi). BGU Moodle takes 31 MB per upload:
  at the scans' own size (avg 4.7 MB, up to 56 MB) one assignment of 285 needs 45 ZIPs and 6 files don't fit
  at all; at ~1.5 MB it's about 15 ZIPs. Compress in the grading code: on Ori's computer, Windows Smart App
  Control blocks PyMuPDF's DLLs, so check what runs on the grading machine.
- a row in `results.csv`: `number,grade,feedback`, where `feedback` is a short summary.

`python -m moodle upload` takes it from there.

## Working in git

Work on a branch and open a Pull Request; `main` changes only through reviewed PRs.
Run all `test_*.py` before pushing.
