---
name: rubric
description: Build the rubric for an assignment - common mistakes, every correct solution method, and a 0-100 rubric that a council of agents debated and field-tested on real submissions. Use when someone says "מחוון", "תבנה מחוון", "טעויות נפוצות", "פתרונות אפשריים", "rubric" for an assignment in the shared folder.
---

# מחוון: rubric, common mistakes and solution methods for one assignment

The result is three files at the top of the assignment's `פדגוגי` folder, `Solutions.md`, `Solution methods.md`
and `Rubric.md`, plus `findings.md` in its `Working notes` subfolder. **Grading sends every top-level .md/.txt
of `פדגוגי` to Claude with each submission** and takes the points per question from the rubric's points table
(`| <question> | <points> | ...`), so only material for the grader goes on top; drafts, old versions and
sample statistics go in `Working notes` (never sent). They are built from a random sample of
real submissions, then a 5-member council (lecturer, TA, weak student, strong student, appeals) debates,
two TAs field-test the draft on fresh submissions, critics review, and a final check runs.
`Rubric.md` always follows `rubric-template.md` (same sections, same codes; no length limit: TAs ask their Claude about it rather than read it).

**Run it this way and no other.** Every step below was worked out on Assignment 0 (Linear Algebra, 3438636);
exploring again costs tokens and gains nothing. Don't read page images yourself (except the one check in step 3),
don't read the agents' reports, don't print the rubric into the chat.

## 1. Which assignment

Take the Moodle id from the request. If it's missing, list the assignments and ask:
```bash
python -c "from moodle import paths; [print(paths.read_info(d)['id'], d.relative_to(paths.data_dir())) for d in paths.assignment_dirs()]"
```
Read its `Assignment details.json`: `questions` says which sheets and question numbers were assigned.
Work folder: `%TEMP%\rubric-<id>` (outside the repo and outside OneDrive: it will hold student pages).

## 2. questions.md: the printed questions and the lecturer's solutions

The questions and solutions are `.tex` files in the lecturer's OneDrive,
`YallaLinearit/Course Material (tex)/exercises and solutions/` (one file per topic, numbered in course order:
`01-sets.tex`, `02-complex.tex`, ...). Get them through Claude in Chrome, in the user's logged-in Chrome:
1. Open the folder, `get_page_text` to list the files, match each sheet in `questions` to its file.
2. Fetch the files in the page and keep them in `window`, e.g.
   `fetch("/personal/mein_bgu_ac_il/_layouts/15/download.aspx?SourceUrl=" + encodeURIComponent("/personal/mein_bgu_ac_il/Documents/YallaLinearit/Course Material (tex)/exercises and solutions/02-complex.tex"))`.
   **Returning the text from `javascript_tool` is blocked** ("Cookie/query string data"): instead replace
   `document.body` with a `<pre>` holding the text, then `get_page_text`. Close the tab afterwards.
3. Write `<work>\questions.md`, in English headings with the Hebrew/LaTeX copied **verbatim**:
   - for each assigned question: the whole `\item` — the printed text (`qbox`) including every blank,
     template and set the student fills in (the rubric depends on the exact printed form), and the
     lecturer's solution (`solbox`).
   - **Course scope:** the topics of all tex files up to and including the assigned sheets have been taught;
     list the later files' topics (e.g. matrices, determinants) as not taught yet.
   Count the top-level `\item`s carefully: question N is the N-th one.

If Chrome isn't connected, ask the user for the tex files or the exercise PDF; don't guess the questions.

## 3. The sample

From the repo root:
```bash
python -m grading.sample <id> --out "%TEMP%\rubric-<id>"
```
50 random submissions for reading, 6 others for the field test, pages as small JPEGs, blank pages skipped,
`manifest.json` with the numbers. Then Read **one** page of one sampled submission to confirm the question
numbers students wrote match `questions.md` (a sheet can be renumbered after it was handed out). If they
don't match, fix `questions.md` before going on.

## 4. The council

Run the saved workflow (the user invoking this skill is the opt-in):
`Workflow({name: "rubric", args: {work: "<work>", template: "<repo>\\.claude\\skills\\rubric\\rubric-template.md", sample: [...manifest.sample], fresh: [...manifest.fresh]}})`.
It runs in the background (about an hour). Tell the user in two lines what is running, then wait for the
notification. While waiting, answer the user but don't poll.

## 5. When it's done

**The check that matters most (Ori, 2026-10-23): manual review must stay at 5-6%.** Before delivering, count the
field-test submissions the rubric would send to a person (§5 of the rubric plus any "to the checker" in §3/§4).
Above 6% the rubric is not done: group the reasons and turn each group into a decision in a row, as
`manual-review-rules.md` says. No row or rule may say "to the checker".

1. Read the workflow's result (the `check` report), not the files. If it reports something still wrong
   that you can fix from `questions.md` (an answer, a printed template), fix it in `Rubric.md`.
2. If a `Rubric.md` is already in `<assignment>\פדגוגי\`, move it first to
   `<assignment>\פדגוגי\Working notes\Rubric v<N>.md`. Then copy `Solutions.md`, `Solution methods.md`,
   `Rubric.md` from `<work>` to `<assignment>\פדגוגי\`, `manual-review-rules.md` from this skill's folder too
   (grading sends it to Claude with every submission, so it stays short), and `findings.md` to
   `<assignment>\פדגוגי\Working notes\`.
   Nothing else goes on top of `פדגוגי`: grading would send it to Claude with every submission.
3. Delete `<work>` (it holds student pages).
4. Don't write anything into `Assignment details.json`. Tell the user that from now on grading uses this rubric
   (it reads `פדגוגי`), and that the ⚠ decisions in §7 still wait for the lecturer.

## 6. Upload to the shared folder (ask once)

If the shared folder is synced on this computer (`dashboard/shared_folder.py` finds it), step 5 already put the
files there; skip this step. Otherwise ask the user once: upload the files to `<course>/<assignment>/פדגוגי` in
the shared folder (the three on top, `findings.md` into `Working notes`)? On yes, in Chrome: open that folder
(create `פדגוגי` / `Working notes` with Create or upload → Folder if missing), then patch the page so the file
input doesn't open the Windows dialog:
```js
window.__origClick = window.__origClick || HTMLInputElement.prototype.click;
HTMLInputElement.prototype.click = function () { if (this.type === 'file') { if (!this.isConnected) document.body.appendChild(this); return; } return window.__origClick.call(this); };
```
Create or upload → Files upload, `find` the `input[type=file]`, `file_upload` the four files (copy them to
your scratchpad first if the data folder isn't readable by this session; ≤ 10 MB per call). If OneDrive says
the names exist, "Replace all" keeps the old ones in version history. Restore `click`, close the tab,
check the folder shows the files. Never upload anything else (no pages, no ZIPs, no key table).

## 7. Report (≤ 15 lines, Hebrew)

Points per question, the 3–5 most common mistakes, the field-test agreement, the ⚠ decisions waiting for
the lecturer (one line each), and where the files are (local and shared).

## Privacy

Student pages exist only in `<work>` and are deleted at the end. Nothing in the four files names a student:
submissions only by 4-digit number. Never open `Key - number to student.csv`.
