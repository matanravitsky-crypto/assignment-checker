---
name: copying-check
description: Check one assignment's submissions for suspected copying (העתקות) exactly like Bodek Hacham's copying check - the same file, the same PDF origin, the same handwritten page inside another file, typed pages that share rare text - with no Claude tokens spent on the comparison, and report pairs of submission numbers only. Use when a teammate asks "בדוק העתקות", "יש העתקות במטלה X?", "חשד להעתקה", "copying check", for an assignment by its Moodle id or its folder.
compatibility: Python 3 with pymupdf. Built by assignment-checker's tools/extract_skill.py from the system's own copying/ code and the core it needs (scripts/MANIFEST.json says from which commit); it runs without the repo.
---

# Copying check: suspected copying between submissions, numbers only

The same code as the system's `python -m copying` (assignment-checker, `copying/`), taken out to a skill by
`tools/extract_skill.py`: `scripts/` holds `copying/` and the few files of the system's core it needs (`moodle/paths.py`
and its neighbours). `<skill>` below is this skill's folder; use the absolute path of `<skill>\scripts\run.py`.

**Talk to the user in Hebrew.** Never open `Key - number to student.csv`, and never print, write or say a student's name,
ID number (ת"ז) or email, even if one appears in a file or its name. Talk about submissions by their number only.

## 1. Python (once per computer)

Check: `py -3 -c "import pymupdf"` (macOS/Linux: `python3 -c ...`). If it fails, say in one sentence
"מתקין את PyMuPDF בסביבה נפרדת, כדי לקרוא את הקבצים", then:
```powershell
py -3 -m venv "$env:LOCALAPPDATA\BodekHacham\copying-venv"
& "$env:LOCALAPPDATA\BodekHacham\copying-venv\Scripts\python" -m pip install pymupdf
```
and use that python below (`PY`). If a working `exercise-grader` venv exists (`%LOCALAPPDATA%\BodekHacham\grader-venv`),
it has pymupdf too.

## 2. Run it

```powershell
PY "<skill>\scripts\run.py" <the assignment's Moodle id, or its folder>
```
- **A Moodle id** (the `id=` in the assignment's Moodle address): the assignment is found in the team's synced OneDrive
  folder (`YallaLinearit\Exercise Checking System`), the same way the site finds it. `ASSIGNMENT_CHECKER_ROOT` or
  `ASSIGNMENT_DATA` point elsewhere when it is not found.
- **A folder**: the assignment folder (the one with `1 - Submissions to grade` in it), or that folder itself. Files are
  read by number only: `0001.pdf`, `0001-2.jpg` (a second file of 0001). Other names are skipped.

The first run reads every page (about 0.1 s a page: a few minutes for 1,000 submissions); later runs read only files
that are new or changed. It writes `Copying check.json` next to `1 - Submissions to grade` (numbers and hashes only) and
prints a summary and every pair. Don't run while `Pull in progress.txt` is in the assignment folder: a pull is writing
the submissions.

## 3. Report

In Hebrew, short: how many submissions were checked, then a table of the pairs, strong ones first:
| זוג | חוזק | למה |
with "חשד חזק" for `!` lines and "כדאי להסתכל" for `?` lines, and the reason as printed (the same file, the same document
id, the same author or creation time, the same pages with their page numbers, typed text). Then any page that repeats
in many submissions ("עמוד שחוזר"): usually the question sheet, sometimes a solution that went around.

Say plainly that this is a suspicion for a person to check, not a verdict. What it cannot see (the same work rewritten
by hand, a photo of another student's work) is in `copying/README.md` of the system.
