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

## Preparing submissions from Moodle

1. In the assignment's Submissions page, use **Download all submissions** (open the ZIP with 7-Zip).
2. Extract it to `~/assignment-data/submissions/<assignment id>/original/` (one folder per student).
3. Run `python prepare_submissions.py <assignment id>`.

This writes `anon/0001.pdf ... anon/NNNN.pdf` for grading and a private `mapping.csv` (number → Moodle participant id and original folder) used to rebuild Moodle's names for the upload. The data folder lives outside the repo and OneDrive; set `ASSIGNMENT_DATA` to move it. Student files never go into this repo: it is public.

## Python

**Current stage:** a basic Hello World skeleton.

- Python 3.10+

```bash
python main.py
python test_main.py
```
