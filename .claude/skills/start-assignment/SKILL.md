---
name: start-assignment
description: Get the files that the work on one assignment (הגשה Y of a course), or on every assignment, needs into its folder, the way Assignment 0 has them - the assignment's details from its Moodle page, the exercise sheet, the official solution cut to the assigned questions, the manual review rules - exploring the Moodle course page, the staff drive and the lecturer's OneDrive for what's new. Files only; it never pulls submissions and never makes a sample (those are separate: the pull button, and rubric-builder with the size the user names). Use when someone says "תוריד את כל מה שצריך כדי להתחיל עבודה על מטלה Y", "תוריד את כל הקבצים הרלוונטיים לעבודה Y", "תכין את הגשה Y", "מה יש במודל על הגשה Y", "start assignment Y".
---

# Start an assignment: the files the work on הגשה Y needs, into its folder

What Assignment 0 of Linear Algebra ended up with is the model. After this skill, הגשה Y has:

| In the assignment folder | What | From |
|---|---|---|
| `Assignment details.json` | Moodle id, title, due, the questions (sheet and numbers), the rules | the assignment's page in Moodle |
| `Official solution.pdf` | the solutions of the assigned questions only (grading sends it to Claude with every submission) | the sheet's solutions PDF, cut by code |
| `פדגוגי/Exercise sheet N - <topic>.pdf` | the printed sheet | `Course material/Sheets/` |
| `פדגוגי/Manual review rules.md` | how the bot stays under 5-6% manual review (general) | `rubric-builder/assets/manual-review-rules.md` |
| `פדגוגי/Working notes/` | for rubric-builder; superseded copies go here, never deleted | |
| `Course material/Moodle - assignments, quizzes and pages.md` | the assignment's page text, appended | Moodle |

**Not here, ever (Ori, 2026-10-29):** submissions and samples. The pull is its own thing (the site's button, the night
pull), and a sample of submissions is made by `rubric-builder`, with the size the user names and nobody else
decides. This skill never runs a pull, never calls `grading.sample`, and doesn't decide anything about the rubric.
Also not here: `Solutions.md`, `Solution methods.md`, `Rubric.md`, `Rubric.pdf` (all `rubric-builder`'s).

**"For all the assignments"** (both courses, every slot): run step 0 for each of the 20 slots in one loop, then do
step 1 once per course (one course listing shows every assignment), step 1b once, and step 2 for each assignment
that Moodle has published. A slot Moodle hasn't published yet gets nothing new (its draft and "Expected - sheet"
files stay as they are).

**Never overwrite.** Before replacing a file (`--replace`), move the old one into `פדגוגי/Working notes/` under a
name that says what it was; a copy that the new file makes redundant (an older name of the same sheet, a hand-cut
solution) moves there too, after checking it really is the same (`cmp`, or the questions on each page).

**Run it this way.** Tokens go only to Moodle (Claude in Chrome) and to reading two short JSON outputs. Never read
submission pages, never screenshot Moodle, never read a PDF's pages to find the questions (the script finds them in the
text layer). Every file name and folder comes from `scripts/prepare.py`; don't spell them by hand.

## 0. Which assignment, and what's already there

The request names a course and a number: "מטלה 3" of the course the user is working on (Linear Algebra unless they say
דיסקרטית / Discrete Mathematics). Course folder names: `Linear Algebra`, `Discrete Mathematics`. Then, from the repo root:

```bash
python .claude/skills/start-assignment/scripts/prepare.py status --course "Linear Algebra" --slot 3
```

It says what the assignment folder already has (details, פדגוגי files), which exercise sheets the course has locally
(`Course material/Sheets/Sheet N - <topic>.pdf` with `- solutions.pdf`), and whether the data folder is the synced
shared folder. **What is there is not fetched again.** Before opening Moodle, also check what other
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
4. Course files that `Course material/` lacks (a tutorial, a summary in a staff folder): list a folder activity's
   files from `/moodle/mod/folder/view.php?id=<id>` (`a[href*=pluginfile]`), compare by name and size, and save new
   ones to Downloads under an English name ("Tutorial 2 - Lines and planes in space.pdf"), then move them into
   `<course>/Course material/`. **Chrome lets a page start only one download** before it asks: for several files,
   fetch them in the page and download one JSON bundle (`[[name, text]]` for text, or one at a time with the user's
   OK for PDFs), unpack it with Python, check each size against the source.
5. Close the tab. Never type into Moodle, never click anything there, never open a student's submission or the
   grading table, never download submissions.

## 1b. The other places: the staff drive and the lecturer's OneDrive

- Linear Algebra's "דרייב סגל" (a `url` activity on the course page) is a Google Drive folder: open it and
  `get_page_text` lists its files; compare with `Course material/` and `Course material/Staff/`.
- The lecturer's OneDrive, `YallaLinearit/Course Material (tex)/` (`exercises and solutions/` = one .tex per sheet,
  `Nadav Lecture notes/`), is kept in `Linear Algebra/Course material/Lecturer tex/` with the same file names. List it
  through SharePoint REST from a tab on the OneDrive (`/_api/web/GetFolderByServerRelativePath(decodedurl=@p)?@p='...'&$expand=Folders,Files`,
  write the result into the page and `get_page_text`: returning it from `javascript_tool` is blocked), and fetch what
  is missing or a different size through `/_layouts/15/download.aspx?SourceUrl=...` as one bundle (step 1.4). A tex
  file for a sheet Moodle hasn't published yet is the earliest sign of the next assignment's questions.

If Chrome or Moodle isn't reachable, say so and do steps 2-3 from what the user gives (the page text pasted, the PDFs).

## 2. The sheet and the official solution

```bash
python .claude/skills/start-assignment/scripts/prepare.py materials --course "Linear Algebra" --slot 3 --sheet 3
```

`--sheet` is the sheet's number in the booklet (the course page lists them in order; Discrete's names carry it, "דף
תרגילים 0", and then it's guessed). It copies the sheet into `פדגוגי/`, finds the assigned questions' pages in the
solutions PDF's text layer (`pages.found`, 1-based) and writes `Official solution.pdf`; `pages.missing` lists questions
whose heading wasn't found. A heading is ".N" alone on its line that continues the numbering; sub-items numbered
the same way (".1 .2 .3", Discrete's sheets) are skipped. Check `headings_seen`: it should be 1, 2, 3, ... with few
gaps. If it isn't, or a question is missing, read the solutions PDF's **text** (never images) around those pages,
decide the pages, and run again with `--pages 10-14 --replace`. An assignment from two sheets: run once per sheet
with `--numbers` and `--append` for the second. It also copies `Manual review rules.md` and creates `Working notes/`.

## 3. Finish

```bash
python .claude/skills/start-assignment/scripts/prepare.py readme
```

Report in Hebrew, at most 10 lines: the assignment (title, due, questions), what was written (each file once), and what
is missing and why (no solutions for the sheet, questions not found, the assignment not on Moodle yet). If an
existing `Rubric.md` / `Solutions.md` doesn't match the questions on Moodle (a question added), say so in one line
and stop there: what to do about it is the user's call. If the shared folder is not synced on this computer, say
that the new files reach the lecturer's OneDrive with `onedrive/sync.js` (CLAUDE.md). Don't offer the pull or a sample.

## Privacy and cost

Numbers only: never a student's name, ת"ז or email in the chat, the files or the report; never open `Key - number to
student.csv`, the grading table or a submission. One Moodle tab, no screenshots, no page images in this context. A
whole run costs a few thousand tokens plus the two Moodle calls; if it is heading past that, something is being read
that the script should have handled.
