---
name: start-assignment
description: Get everything needed to start working on one assignment (הגשה Y of a course) into its folder, the way Assignment 0 has it - the assignment's details from its Moodle page, the exercise sheet, the official solution cut to the assigned questions, the manual review rules, and a sample of submissions - exploring the Moodle course page for what's new. Use when someone says "תוריד את כל מה שצריך כדי להתחיל עבודה על מטלה Y", "תכין את הגשה Y", "תתחיל לעבוד על מטלה Y", "מה יש במודל על הגשה Y", "start assignment Y". Then `rubric` (Solutions.md, Rubric.md) and `rubric-builder` (Rubric.pdf) take it from there.
---

# Start an assignment: everything the work on הגשה Y needs, into its folder

What Assignment 0 of Linear Algebra ended up with is the model. After this skill, הגשה Y has:

| In the assignment folder | What | From |
|---|---|---|
| `Assignment details.json` | Moodle id, title, due, the questions (sheet and numbers), the rules | the assignment's page in Moodle |
| `Official solution.pdf` | the solutions of the assigned questions only (grading sends it to Claude with every submission) | the sheet's solutions PDF, cut by code |
| `פדגוגי/Exercise sheet N - <topic>.pdf` | the printed sheet | `Course material/Sheets/` |
| `פדגוגי/Manual review rules.md` | how the bot stays under 5-6% manual review (general) | copied from the newest assignment |
| `פדגוגי/Working notes/` | empty, for the rubric skills | |
| `Course material/Moodle - assignments, quizzes and pages.md` | the assignment's page text, appended | Moodle |
| `1 - Submissions to grade/` + a sample in `%USERPROFILE%\.rubric-work\<id>\inputs\submissions` | submissions, and 10 of them as small page images for the rubric skills | the pull, then `grading.sample` |

Not here: `Solutions.md`, `Solution methods.md`, `Rubric.md` are the `rubric` skill's (from the lecturer's tex files);
`Rubric.pdf` is `rubric-builder`'s. End by offering them.

**Run it this way.** Tokens go only to Moodle (Claude in Chrome) and to reading two short JSON outputs. Never read
submission pages, never screenshot Moodle, never read a PDF's pages to find the questions (the script finds them in the
text layer). Every file name and folder comes from `scripts/prepare.py`; don't spell them by hand.

## 0. Which assignment, and what's already there

The request names a course and a number: "מטלה 3" of the course the user is working on (Linear Algebra unless they say
דיסקרטית / Discrete Mathematics). Course folder names: `Linear Algebra`, `Discrete Mathematics`. Then, from the repo root:

```bash
python .claude/skills/start-assignment/scripts/prepare.py status --course "Linear Algebra" --slot 3
```

It says what the assignment folder already has (details, פדגוגי files, submissions, last pull), which exercise sheets the
course has locally (`Course material/Sheets/Sheet N - <topic>.pdf` with `- solutions.pdf`), and whether the data
folder is the synced shared folder. **What is there is not fetched again.** Before opening Moodle, also check what other
chats already found: `mcp__ccd_session_mgmt__search_session_transcripts` with the assignment's title ("הגשה 3") or its
Moodle id; a hit that already lists the questions or the sheet saves the Moodle round trip (still verify the due date on
Moodle: extensions happen).

## 1. Moodle: the assignment's page, and what's new on the course page

Claude in Chrome, in the user's own logged-in Chrome (load `tabs_context_mcp`, `tabs_create_mcp`, `navigate`,
`javascript_tool`, `tabs_close_mcp` in one ToolSearch). Open a new tab on `https://moodle.bgu.ac.il/moodle/my/`
(an expired session shows nginx "404 Not Found"; this page signs in again by itself). Paste the whole of
`scripts/moodle_course.js` into `javascript_tool` once (it answers "ready"), then:

1. `await __ecs.course(<course_id>)` (`course_id` is in the course's `Course rules.md` and in any assignment's details:
   Linear Algebra 67024, Discrete Mathematics 67035). The listing is sections and activities with `<type id>`. Find
   "הגשה Y" (`<assign id>`), and note files that `Course material/Sheets` doesn't have yet (a new sheet, "חוברת חלק ב'").
2. `await __ecs.assign(<id>)` → title, dates, intro. Write `<scratchpad>\details.json`:
   ```json
   {"id": "3438638", "course_id": "67024", "course_title": "אלגברה לינארית להנדסה",
    "title": "הגשה 1 - וקטורים במישור ℝ² ובמרחב ℝ³",
    "due": "יום שני, 2 נובמבר 2026, 11:59 PM",
    "questions": [{"sheet": "דף וקטורים וגאומטריה ב-ℝ² וב-ℝ³", "numbers": [11, 13, 14, 15, 16]}],
    "submission_rules": ["כתב יד, קובץ PDF אחד", "כל שאלה בעמוד נפרד", "רק הקובץ האחרון שהוגש נבדק"],
    "page_text": "<the intro, verbatim>"}
   ```
   `due` is the "מסתיים" line as Moodle shows it (the script converts it) or ISO. `questions` is exactly what the page
   says, sheet names verbatim. Then:
   ```bash
   python .claude/skills/start-assignment/scripts/prepare.py details --course "Linear Algebra" --slot 3 --from "<scratchpad>\details.json"
   ```
   It creates `Assignment 3/` if the slot is empty (the same folder the site's first pull would make), refuses an id
   another folder has, keeps `max_grade` / `rubric` / `notes` that people typed, and appends the page text to the
   course's Moodle pages file.
3. A sheet the course folder lacks (the `status` output has no entry for its number): `await __ecs.download(<file id>,
   "sheet-N.pdf")` and `await __ecs.download(<file id>, "sheet-N-solutions.pdf")` save to `~/Downloads` (Chrome's
   "ask where to save" must be off, as for pulls). Then:
   ```bash
   python .claude/skills/start-assignment/scripts/prepare.py add-sheet --course "Linear Algebra" --sheet 9 --topic "Vector spaces" --file "%USERPROFILE%\Downloads\sheet-9.pdf" --solutions "%USERPROFILE%\Downloads\sheet-9-solutions.pdf"
   ```
   A booklet of several sheets (Linear Algebra's "חוברת תרגילים חלק ב'") is one PDF: download it to
   `Course material/` under its booklet name, and for each sheet in it pass `--pages` in step 2 instead of `add-sheet`.
   Read the booklet's contents page by text (`pymupdf`, `page.get_text(sort=True)`), not as images.
4. Close the tab. Never type into Moodle, never click anything there, never open a student's submission or the
   grading table (the download is a pull, step 3).

If Chrome or Moodle isn't reachable, say so and do steps 2-3 from what the user gives (the page text pasted, the PDFs).

## 2. The sheet and the official solution

```bash
python .claude/skills/start-assignment/scripts/prepare.py materials --course "Linear Algebra" --slot 3 --sheet 3
```

`--sheet` is the sheet's number in the booklet (the course page lists them in order; Discrete's names carry it, "דף
תרגילים 0", and then it's guessed). It copies the sheet into `פדגוגי/`, finds the assigned questions' pages in the
solutions PDF's text layer (`pages.found`, 1-based) and writes `Official solution.pdf`; `pages.missing` lists questions
whose heading wasn't found: then read the solutions PDF's **text** (never images) around `headings_seen`, decide the
pages, and run again with `--pages 10-14 --replace`. An assignment from two sheets: run once per sheet with
`--numbers` and `--append` for the second. It also copies `Manual review rules.md` from the newest assignment that has
one and creates `Working notes/`.

## 3. Submissions: the pull, and a sample

Submissions arrive only through the pull (one key table per assignment, written only where the shared folder is
synced: `status` says `shared_folder`). Decide:
- The assignment is closed (`due` passed) and `last_pull` is older than that, or there are no submissions yet: pull.
  With the dashboard running (`GET http://127.0.0.1:8765/api/health`), `POST http://127.0.0.1:8765/api/pull` with
  `{"course": "Linear Algebra", "assignment": "<folder name>"}` (plus `"moodleId"` for a slot with no folder yet) and
  follow `GET /api/pull` until it ends; otherwise tell the user to press "משוך הגשות" on the site. `NOT_SHARED` means
  this computer doesn't sync the shared folder: say who pulls (the pull owner, `Who does what`) and go on without.
- Still open: an early pull is fine for a first look (Assignment 0 was pulled early, noted in `notes`), but say that
  the final set comes after the deadline (the night pull does it by itself).
- A sample for the rubric skills, only when there are submissions, `Y` = the number the user said, else 10:
  ```bash
  python -m grading.sample <id> --out "%USERPROFILE%\.rubric-work\<id>\inputs\submissions" --n 10 --fresh 0 --max-side 1000 --crop
  ```
  That is where `rubric-builder` looks for its inputs. Don't open the images. The folder holds student pages:
  outside the repo and outside OneDrive, by number only.

## 4. Finish

```bash
python .claude/skills/start-assignment/scripts/prepare.py readme
```

Report in Hebrew, at most 12 lines: the assignment (title, due, questions), what was written (each file once), what is
missing and why (no solutions for the sheet, pull not possible here, questions not found), and the next steps:
`/rubric` for `Solutions.md` + `Rubric.md`, `/rubric-builder` for the printed rubric. If the shared folder is not synced on
this computer, say which files need to reach it (the `rubric` skill's step 6 has the upload).

## Privacy and cost

Numbers only: never a student's name, ת"ז or email in the chat, the files or the report; never open `Key - number to
student.csv` or the grading table. One Moodle tab, no screenshots, no page images in this context. A whole run costs a
few thousand tokens plus the two Moodle calls; if it is heading past that, something is being read that the script
should have handled.
