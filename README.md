# Assignment Checker

A university project for checking student assignments automatically.

The pipeline:

1. **Pull** submissions and student details from the university course site.
2. **Grade** each submission with Claude, using the assignment's rubric and grading notes.
3. **Mark & approve**: comments are marked on the submission, a TA reviews and approves.
4. **Return** the grade, comments and marked file back to the university site.

## Dashboard (skeleton)

Live: https://matanravitsky-crypto.github.io/assignment-checker/

`docs/` holds a static, Hebrew (RTL) dashboard prototype: the pipeline overview, the submissions table, a submission view with red-pen comments and a score breakdown, the rubric editor, a run log and the connection settings. All data is demo data from `docs/data.js`; the buttons simulate the pipeline.

Run it locally by opening `docs/index.html` through any static server, for example:

```bash
npx http-server docs
```

## Moodle in and out (`moodle/`)

There is no Moodle API, so Claude in Chrome does the clicking and these scripts do the rest. Student files never enter this repo (it is public). They live in `Exercise Checking System`, a folder per course and per assignment with plain English names, shared through the lecturer's OneDrive; see `moodle/paths.py` and `CLAUDE.md`.

Needs Python 3.10+ and 7-Zip (`winget install 7zip.7zip`).

**In** — after the due date, in the assignment's Submissions page: Actions → *Download all submissions*, then:

```bash
python -m moodle ingest <assignment id> --course "Linear Algebra" --name "Assignment 0 - Sets and Complex Numbers"
```

(`--course` and `--name` only the first time.) It takes the newest `…-<assignment id>.zip` from Downloads into `<course>/<assignment name>/`, keeps the ZIP there, and writes `1 - Submissions to grade/0001.pdf …` for grading plus the key table `Key - number to student.csv` (number → Moodle participant id). On a later download every student keeps their number, and students who submitted since then get the next numbers.

**Out** — grading writes `Grades.csv` (`number,grade,feedback`) and `2 - Graded with comments/0001.pdf …`; download the grading worksheet from Moodle, then:

```bash
python -m moodle upload <assignment id>
```

It fills `3 - Ready to upload to Moodle/` with `Grades for Moodle worksheet.csv` (Actions → *Upload grading worksheet*), `Graded - part 01.zip …` (Actions → *Upload multiple feedback files in a zip*; each under Moodle's 31 MB limit) and `Upload steps.txt`, the steps for whoever uploads. Grades are matched by number, never by row order.

**Check** — `python -m moodle status <assignment id>` shows what's done and flags file names OneDrive would refuse. `python -m moodle guide` rewrites the `README.txt` files (in Hebrew).

One person downloads and uploads, so there is one key table per assignment; the team works from the shared folder.

`CLAUDE.md` has the full picture for working on this with Claude.

## Python

**Current stage:** a basic Hello World skeleton.

- Python 3.10+

```bash
python main.py
python test_main.py
python test_anonymize.py
python test_ingest.py
python test_upload.py
python test_status.py
python test_guide.py
```
