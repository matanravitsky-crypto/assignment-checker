---
name: rubric-builder
description: Build the printed grading rubric (מחוון בדיקה) of one exercise sheet / assignment as a Hebrew PDF in the course's fixed format (points per step, error table with רגיל/מחמיר deductions, alternative solution methods), from the full solution and Y real submissions, by a committee of role agents, then loop on the user's remarks until approved. Use whenever anyone says "מחוון" in any form: "מחוון לדף תרגילים X", "תבנה מחוון", "תמשוך Y עבודות ותבנה מחוון", "מחוון PDF", "מחוון מודפס", "טעויות נפוצות", "פתרונות אפשריים", "דרכי פתרון", "ניכויים רגיל/מחמיר", "rubric", or sends remarks on a Rubric.pdf ("לא טוב, תתקנו X"). It is the only rubric skill: it also writes Solutions.md, Solution methods.md, the findings and the manual review rules into פדגוגי.
compatibility: Claude Code on Windows (MiKTeX, installed by setup/) or macOS (Homebrew).
---

# Rubric Builder: the printed מחוון, built by a committee from Y real submissions

**The flow, and nothing else (Ori, 2026-10-29):**
1. A TA says: "מחוון לדף תרגילים X, תמשוך Y עבודות" (Y is the TA's number; never guessed, see Step 1).
2. The skill fetches the full solution and Y submissions, as cheaply as possible (Step 1).
3. The committee (Step 2) sees ALL Y submissions, builds the rubric, and delivers `Rubric.pdf` (Steps 3–5).
4. The TA sends remarks ("לא טוב", "ב-11ג ההורדה גבוהה מדי", "חסרה טעות X").
5. The committee convenes on the remarks only (Step 6), rebuilds, delivers again. Repeat 4–5 until the TA approves.

**The format is fixed.** Never design layout: fill `rubric.json` (schema and example in `references/format.md`);
`scripts/make_pdf.py` validates it, renders `Rubric.md` (the bot) and `assets/template.tex`, and compiles the PDF with XeLaTeX.

**Run autonomously.** Ask nothing except for a missing input or install consent. Don't read page images yourself,
don't read the agents' files more than once, don't preview more than pages 1–2 of a build.

**One source, two files (Ori, 2026-10-29).** `rubric.json` is the rubric. From it `make_pdf.py` renders both
`Rubric.md`, the grading bot's rubric (grading sends every top-level `.md`/`.txt` of `פדגוגי` to Claude and takes the
points per question from its first table; `scripts/render_md.py`), and `Rubric.pdf` for people. Nobody edits either by
hand. A `Rubric.md` from the retired `rubric` skill (not rendered from `rubric.json`) is an INPUT: its points per section
and deductions are taken as רגיל, and on delivery it is archived to `Working notes/Rubric v<N> (council).md` and
replaced by the rendered one. Otherwise points per question come from `Assignment details.json` (`rubric.questions[].points`,
`max_grade`) or the sheet.

## Where things are

| What | Where |
|---|---|
| The assignment | `paths.assignment_dir(<moodle id>)` in the data folder. "דף תרגילים X" → the assignment whose `questions` in `Assignment details.json` name that sheet; if two do, ask |
| The full solution | `פדגוגי/Official solution*.pdf` (cut to the assigned questions) and the sheet `Exercise sheet*.pdf`; `Solutions.md` if an earlier run wrote it |
| Submissions | `1 - Submissions to grade/`, only through `python -m grading.sample` (page images by number, blank pages dropped); never the originals |
| Work | `%USERPROFILE%\.rubric-work\<id>\` (macOS `~/.rubric-work/<id>/`): outside OneDrive and the repo, it holds student pages. `inputs/`, `agents/`, `rubric.json`, `rubric.tex`, `rubric.pdf`, `CHANGELOG.md` |
| Output | everything the bot and the people need, all in `פדגוגי/`: `Rubric.md` (the bot) and `Rubric.pdf` (people), both from `rubric.json`; `Solutions.md`; `Solution methods.md`; `Manual review rules.md`; in `Working notes/`: `rubric.json`, `findings.md` (the errors seen in the Y submissions, with counts), the agents' reports, `Rubric PDF changelog.md` |

## When nothing is there for sheet X (Ori, 2026-10-29)

Never create an assignment folder, never pick another sheet, never pull or sample on your own. In order:

1. **No assignment names sheet X** (no `Assignment details.json` whose `questions` name it, in either course): look in
   Moodle, read-only, in the user's logged-in Chrome. The course page (`__ecs.course(<course_id>)` from the
   `start-assignment` skill's `scripts/moodle_course.js`; Linear Algebra 67024, Discrete Mathematics 67035) lists the
   assignments; an assignment's page (`__ecs.assign(<id>)`) says which sheet and questions. Without that skill in this
   checkout, open the course page with Claude in Chrome and read the list the same way. Never type or click in Moodle.
   - **On Moodle but not in the folder:** say so (title, due, questions), run the `start-assignment` skill for that
     הגשה (details, sheet, official solution, manual review rules), then say that the submissions still have to be
     pulled (the site's pull button, by the assignment's pull owner) and stop. The rubric run starts again once
     `1 - Submissions to grade` has them.
   - **Not on Moodle either:** say "כנראה שהמטלה על דף X עוד לא נפתחה במודל", with what was checked (the course,
     the assignments listed there), and stop. Nothing is written anywhere.
   - **Chrome or Moodle not reachable:** say which, and stop.
2. **The folder exists but `פדגוגי` has no sheet or no official solution:** ask for them (or for `Solutions.md`); role 0
   writes solutions only from the sheet and the official solution, never from memory. `start-assignment`'s `materials`
   step brings both.
3. **The sample is empty** (`grading.sample` found no submissions): the pull hasn't happened. Say so and stop; never pull.
   **Fewer than Y:** say how many there are and ask whether to go on with them; Y is the user's call.

## Step 0: environment (first run on a machine only)

Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "<skill>\setup\check.ps1"`; macOS: `bash "<skill>/setup/check.sh"`.
If it fails, say in two sentences what will be installed (MiKTeX ≈ 1 GB for this user only, no admin; Python packages;
5–15 minutes) and after a yes run `setup\install-windows.ps1 -NoPerl -NoUpdate` (macOS `bash setup/install-mac.sh`),
then the check again until ALL CHECKS PASSED. Perl (latexmk) and OCR are not needed.

## Step 1: fetch the solution and Y submissions (minimum tokens)

1. `<work>` = `%USERPROFILE%\.rubric-work\<id>`; create `inputs\` and `agents\`.
2. Copy into `<work>\inputs\` whatever exists in `פדגוגי`: `Solutions.md`, `Solution methods.md`, `Rubric.md` (council), `Working notes\findings.md`.
   Without `Solutions.md`, the official solution PDF goes in as page images (next step) and role 0 writes `Solutions.md` first.
3. The sheet: `python "<skill>\scripts\prep_inputs.py" "<פדגוגי>\Exercise sheet*.pdf" --images --out "<work>\inputs"`, rename the
   folder to `sheet\`. Always `--images` for Hebrew PDFs (their text extracts garbled). The official solution PDF the
   same way (folder `solution\`), when there is no `Solutions.md`.
4. `python -m grading.sample <id> --out "<work>\inputs\submissions" --n <Y> --fresh 6 --max-side 1000 --crop` (repo
   root). **Y is the number the TA said. Never guess one; without it, ask.** `--crop` cuts the white margins of each
   scan (only the rectangle with ink, `sample.ink_bbox`) and `--max-side 1000` keeps the page at 1000 px: measured on
   63 real pages, 1,471 → 585 tokens a page (−60%), handwriting still legible. `pages\<number>_pNN.jpg` and
   `manifest.json`. Skip numbers flagged "no readable page". Split `sample` into groups of ~10 submissions balanced by
   page count (one grader agent each); `fresh` is for the check in Step 4.
5. Header fields: course, code, term from the sheet's first page; `date` = `due` (dd/mm/yyyy); lecturer, TA from the
   sheet or `""`. Points per section from `Rubric.md` §0, else from the details or the sheet.

## Step 2: the committee, one turn, in parallel

**Role 0 first, alone, when `Solutions.md` is missing:** `solutions` (`references/roles.md` §0) reads the sheet and the
official solution pages and writes `<work>\inputs\Solutions.md`: the full solution of every assigned question and part in
Hebrew Markdown, each final answer boxed, numbers recomputed. Everyone else reads that file, never the solution images.

Prompts: `references/roles.md`. Every prompt gets: course and assigned questions, the fixed points per section, the
input paths, the privacy line, "use only Read/Glob on the inputs folder; write your file with Write". One file each in
`<work>\agents\`:
- `solver.md` (sheet, Solutions.md, Solution methods.md), `student.md` (sheet first, Solutions.md after),
  `lecturer.md` (sheet, Solutions.md, Rubric.md §0–§3), `ta.md` (Solutions.md, Solution methods.md, Rubric.md §0, §3, §4, findings.md).
- `grader-1.md` … `grader-K.md`, K = ceil(Y/10), model `sonnet`, `effort: "medium"`: each reads EVERY page of its
  ~10 submissions once (one Read per page, never twice) and reports a severity-sorted table of real errors with
  submission numbers, borderline cases, tips; tables only, no prose, no per-page narration. Together they cover all Y.
They do not see each other.

## Step 3: merge → rubric.json → PDF

`references/merge-rules.md` (`Rubric.md` wins on points and deductions). Question `n` is a string such as
`"קבוצות 11"`; identical sections share one block with `count`; `general_rules` ≤ 10 short rows, the first of them
stating what רגיל and מחמיר are. **מחמיר = רגיל + 1 on every row, capped at the section** (Ori, 2026-10-29: a rubric
whose two columns are identical is not deliverable; `validate_rubric.py` refuses it). Then
The merge agent also writes `<work>\agents\errors-summary.md` (the findings: per question the most common errors with
counts out of Y, missing or unreadable submissions by number, rows added, open questions for the lecturer) and
`<work>\Solution methods.md` (from `solver.md`: the accepted methods per section, what is outside the course scope, in
Hebrew, for people and for the bot). Then
`python "<skill>\scripts\make_pdf.py" "<work>\rubric.json"` (validate → `Rubric.md` → TeX → PDF). A validation error is a wrong number: fix and rerun.
A TeX error is a bad LaTeX string: fix that string. One preview of pages 1–2 at 60 dpi, no more.

## Step 4: a new grader tries it (first delivery only)

Role 6 (`new-grader.md`, model `sonnet`): `rubric.json` as text + 4 of the `fresh` submissions (the 4 with the most
pages), no solution. It grades by the rubric alone and lists every guess. Apply the fixes that are clearly right,
rebuild. Once; never in later rounds.

## Step 5: deliver

1. If `פדגוגי\Rubric.md` exists and was not rendered by this skill (no `rubric.json` line at its top), move it to
   `פדגוגי\Working notes\Rubric v<N> (council).md`. Then into `פדגוגי\`: `Rubric.md`, `Rubric.pdf`, `Solutions.md`
   (when role 0 wrote it), `Solution methods.md`, and `Manual review rules.md` from `assets\manual-review-rules.md` when
   missing. Into `פדגוגי\Working notes\`: `rubric.json`, `findings.md` (= `errors-summary.md`), `CHANGELOG.md` as
   `Rubric PDF changelog.md`, and the agents' reports in `Agents\` (numbers only). Nothing else on top of `פדגוגי`: every
   top-level `.md` goes to Claude with every submission. Check once with
   `python -c "from grading import grade; ...load_context(<assignment>)"` that every question's points are found.
   Send the PDF to the user (SendUserFile).
2. Keep `<work>` (the agents' files are what the loop runs on). Delete `<work>\inputs\submissions` only when the
   rubric is approved.
3. Not synced on this computer (`dashboard/shared_folder.py` doesn't find the shared folder)? Ask once; on yes, upload
   the files to `<course>/<assignment>/פדגוגי` in the lecturer's OneDrive with Claude in Chrome: open the folder (Create or
   upload → Folder for `פדגוגי` / `Working notes` if missing), patch the page so the file input doesn't open the Windows
   dialog (`HTMLInputElement.prototype.click` returns early for `type === 'file'`, appending a detached input to the body),
   Create or upload → Files upload, `find` the `input[type=file]`, `file_upload` the files (≤ 10 MB a call, copies in the
   scratchpad if the data folder isn't readable), "Replace all" on a name clash, restore `click`, close the tab. Never
   upload pages, ZIPs or the key table.
4. Report, ≤ 10 lines in Hebrew: total, points per question, the 3 heaviest deductions, the most common errors in the
   Y submissions with counts, the בודק חדש's line, every ⚠ disagreement with `Rubric.md`, where the files are.

## Step 6: the loop. It never ends on its own.

Only the TA ends it, with "מאושר" / "מספיק" / "סגור". Every other message after a delivery is a round of remarks,
and the committee convenes on each one, however small ("לא טוב" alone → ask in one line what is not good, then convene).
Each round of remarks, the committee convenes. How, by cost:
- **Technical remark** (a number, the wording of a row, a missing example): the chair applies it to `rubric.json`
  directly, no agent (≈ 3–5K), and logs it.
- **Substantive remark** (a deduction is too high, a method is missing, a rule contradicts another): ONE committee
  agent on `sonnet` gets the remarks + ONLY the relevant sections of `rubric.json` + the relevant paragraphs of the
  agent files (`solver`, `student`, `lecturer`, `ta`, `grader-*`, Grep them by section), never the inputs, and answers
  in the five voices: per remark, what changes, where, any objection, which grader file supports it. ≤ 30 lines →
  `<work>\agents\round-N.md` (≈ 8–12K).
- Several remarks in one message = one convening. Submissions are never re-read; grader files are quoted instead.
- One build per round, no preview (the validator is the check); the PDF goes straight to the user.
- Apply to `rubric.json`, rebalance inside the same section unless told otherwise, `make_pdf.py`, deliver as in
  Step 5, reply with only what changed (2–5 lines), one line in `CHANGELOG.md`.
- A remark about a specific submission: the committee agent may Read that number's pages from
  `<work>\inputs\submissions` (kept until approval). Nothing else is re-read.
- On another computer or after `<work>` is gone: start from `פדגוגי\Working notes\rubric.json`; the loop then runs
  without the agent files (say so).
- **A remark days or weeks later, even after "מאושר", reopens the loop at the current `rubric.json`** (round N+1 in the
  changelog), never from scratch: nothing is re-sampled, no agent re-reads submissions, and `Rubric.md` and `Rubric.pdf`
  are rebuilt from the edited JSON.
- "מאושר" ends the loop: write the line in `CHANGELOG.md`, delete `<work>\inputs\submissions`.
A remark that contradicts `Rubric.md` goes into the PDF only after the user says so, and then say that the bot's
`Rubric.md` still has the old rule.

## Who is who, in one line each

- **solutions** (role 0): writes `Solutions.md` from the sheet and the official solution pages when the folder has none.

- **solver / student / lecturer / ta**: four views of the sheet and the solution (methods, traps, what matters,
  steps and deductions). They never see submissions.
- **grader-1 … grader-K**: the only agents that read the Y submissions, every page, ~10 each, on `sonnet`.
- **chair (the main agent, or one merge agent for Y ≥ 30)**: merges all files into `rubric.json`; `Rubric.md` wins.
- **בודק חדש**: before the FIRST delivery only, grades 6 unseen submissions with the rubric alone and no
  solution; each guess it makes is a hole, fixed before the TA sees the PDF. Never runs again.
- **committee round**: one agent per round of remarks, with the remarks + `rubric.json` + the agents' files, no inputs.

## Token budget (measured on 3438636, 2026-10-29)

| Agent | Reads | Tokens |
|---|---|---|
| solver, student, lecturer | sheet (5 page images), Solutions.md, Solution methods.md / Rubric.md §0–§3 | 95K, 102K, 134K |
| ta | Solutions.md, Solution methods.md, Rubric.md (all 150 KB → now §0, §3, §4 only), findings.md | 210K (→ ~120K) |
| grader × 5, Y = 49, 508 pages | Solutions.md + ~90 page images each (1.5K a page at 1200 px; 0.6K with `--max-side 1000 --crop`; plus ≈1.2K a page of reasoning and output, less at `effort: medium`) | 239K–253K each at 1200 px, 1.24M together; ≈ 0.7M expected with crop + medium effort |
| merge agent (Y ≥ 30) | rubric.json, 5 grader files, ta.md | ~60–90K |
| בודק חדש (sonnet) | rubric.json + 4 unseen submissions (~40 pages) | ~70K |
| committee round | remarks + rubric.json + agent files | ~15–30K |
| main agent | no images, one 2-page preview per build | small if it stays out of the files |

Y = 50 first delivery ≈ 2.0M at 1200 px; with `--max-side 1000 --crop` the image part drops by 60% (≈ 1.3M); with
graders at `effort: medium` and the בודק חדש on 4 submissions ≈ 1.4M (sheet agents ~450K, graders ~700K, merge ~150K, בודק חדש ~70K). Each round ≈ 3–12K. Student and lecturer stay two
agents (Ori, 2026-10-29). The page images are the cost; the levers are Y, the image size and the margins. The grader
agents also spend ~1.3K a page on reasoning and output: keep their prompts to tables, no prose. Rules: graders on `sonnet`; nobody but
the TA and the lecturer gets `Rubric.md`, and only their sections; the sheet only to solver, student and lecturer; the
main agent reads no images and previews pages 1–2 once per build; no layout experiments in a run (`scripts/` and
`assets/` are tested; a cosmetic gap is reported, not chased).

## Privacy

Student pages exist only in `<work>\inputs\submissions` and are deleted when the rubric is approved. Nothing in the
delivered files names a student: submissions only by 4-digit number. Never open `Key - number to student.csv`.
