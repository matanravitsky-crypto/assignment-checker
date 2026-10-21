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

There is no Moodle API, so Claude in Chrome does the clicking and these scripts do the rest. Student files never enter this repo (it is public). They live in a shared data folder (the lecturer's OneDrive; `ASSIGNMENT_DATA`) plus a local work folder for the extracted originals (`ASSIGNMENT_WORK`); see `moodle/paths.py`.

Needs Python 3.10+ and 7-Zip (`winget install 7zip.7zip`).

**In** — after the due date, in the assignment's Submissions page: Actions → *Download all submissions*, then:

```bash
python -m moodle ingest <assignment id>
```

It takes the newest `…-<assignment id>.zip` from Downloads, keeps it in `raw/`, extracts it, and writes `anon/0001.pdf …` for grading plus a private `mapping.csv` (number → Moodle participant id). The numbers follow the participant id, so a second download gives every student the same number.

**Out** — put grades in `results.csv` (`number,grade,feedback`) and marked files in `marked/0001.pdf …`, download the grading worksheet from Moodle, then:

```bash
python -m moodle upload <assignment id>
```

It writes `upload/grades.csv` (Actions → *Upload grading worksheet*) and `upload/feedback-1.zip …` (Actions → *Upload multiple feedback files in a zip*). Grades are matched by number, never by row order. Uploading to Moodle is a separate step a TA approves.

**Check** — `python -m moodle status <assignment id>` shows what's done and flags file names OneDrive would refuse.

One person downloads and uploads, so there is one `mapping.csv` per assignment; the team works from the shared folder (see `CLAUDE.md`).

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
```
