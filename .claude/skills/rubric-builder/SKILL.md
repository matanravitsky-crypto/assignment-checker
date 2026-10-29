---
name: rubric-builder
description: Build the printed grading rubric (מחוון בדיקה) of one assignment as a Hebrew PDF in the course's fixed format (points per step, error table with רגיל/מחמיר deductions, alternative solution methods), for the TAs who grade or review by hand and for the grading committee. A council of role agents (solver, student, lecturer, graders, TA, auditor) fills rubric.json, scripts validate it and compile the PDF, then a committee loop applies remarks until approved. Use when someone asks for "מחוון PDF", "מחוון מודפס", "מחוון בדיקה בפורמט הקורס", "חלוקת ניקוד לשלבים", "ניכויים רגיל/מחמיר", or wants the rubric as a PDF. For the Markdown rubric that the grading bot reads (Rubric.md in פדגוגי) use the `rubric` skill instead.
compatibility: Claude Code on Windows (MiKTeX, installed by setup/) or macOS (Homebrew).
---

# Rubric Builder: the printed מחוון of one assignment

An assignment's `פדגוגי/` folder can hold two rubrics:
- `Rubric.md`: the grading bot's rubric, built by the `rubric` skill. Grading sends every top-level `.md`/`.txt` of
  `פדגוגי` to Claude with each submission, and takes the points per question from its table.
- `Rubric.pdf`: this skill. The same rules in the course's printed format, for a person: the TAs who grade or review
  by hand, and the committee that approves the rubric. Grading never sends it (only `.md`/`.txt` go to Claude).

**The format is fixed.** Never design layout: fill `rubric.json` (schema and example in `references/format.md`) and
`scripts/make_pdf.py` validates it, renders `assets/template.tex` and compiles with XeLaTeX.

**Run autonomously.** Ask nothing except for a missing input or install consent. The humans are a grading committee:
they see a finished PDF and send remarks.

**When `Rubric.md` exists, it wins.** Points per section and the deductions come from it; the council fills what the
printed format needs (steps a grader judges in 10 seconds, final answers, error tables, alternative methods). Anything
an agent disagrees with goes into the report as a ⚠ line for the lecturer, never silently into the PDF. Without a
`Rubric.md`, points per question come from `Assignment details.json` (`rubric.questions[].points`, `max_grade`) or
the sheet, and the council decides the rest (`references/merge-rules.md`).

## Where things are

| What | Where |
|---|---|
| The assignment | `paths.assignment_dir(<moodle id>)` in the data folder (`Exercise Checking System/<course>/<assignment>/`) |
| Inputs | its `פדגוגי/`: `Exercise sheet*.pdf`, `Official solution*.pdf`, `Solutions.md`, `Solution methods.md`, `Rubric.md`, `Working notes/findings.md` (whatever exists) |
| Submissions | `1 - Submissions to grade/`, only through `python -m grading.sample` (page images by number; never the originals) |
| Work | `%USERPROFILE%\.rubric-work\<id>\` (macOS `~/.rubric-work/<id>/`): outside OneDrive and outside the repo, it holds student pages. `inputs/`, `agents/`, `rubric.json`, `rubric.tex`, `rubric.pdf`, `CHANGELOG.md` |
| Output | `פדגוגי/Rubric.pdf`, plus `פדגוגי/Working notes/rubric.json` and `Rubric PDF changelog.md` so the committee loop can go on from any computer |

## Step 0: environment (first run on a machine only)

Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "<skill>\setup\check.ps1"`; macOS: `bash "<skill>/setup/check.sh"`.
If it fails, say in two sentences what will be installed (MiKTeX ≈ 1 GB for this user only, no admin; Python packages;
5–15 minutes) and after a yes run `setup\install-windows.ps1 -NoPerl -NoUpdate` (macOS `bash setup/install-mac.sh`),
then the check again until ALL CHECKS PASSED; tell the user to open a new terminal. Never sudo, never type passwords,
always quote paths. Perl (latexmk) is optional: `build_pdf.py` runs xelatex twice without it. OCR is not needed in this
project: submissions are handwriting, and `grading.sample` makes their page images.

## Step 1: inputs

1. The Moodle id from the request. Without one, list the assignments and ask:
   `python -c "from moodle import paths; [print(paths.read_info(d)['id'], d.relative_to(paths.data_dir())) for d in paths.assignment_dirs()]"`
2. `<work>` = `%USERPROFILE%\.rubric-work\<id>`; create `inputs\` and `agents\`.
3. Copy into `<work>\inputs\`: `פדגוגי\Solutions.md`, `Solution methods.md`, `Rubric.md`, `Working notes\findings.md` (those that exist).
4. The sheet: `python "<skill>\scripts\prep_inputs.py" "<פדגוגי>\Exercise sheet*.pdf" --images --out "<work>\inputs"`, then rename the
   folder to `sheet\` (`page-NN.jpg`). Always `--images` for Hebrew PDFs: their extracted text comes out reversed and
   interleaved. The official solution PDF only when there is no `Solutions.md` (same command).
5. Submissions: `python -m grading.sample <id> --out "<work>\inputs\submissions" --n 15 --fresh 3` (from the repo root).
   `pages\<number>_pNN.jpg` and `manifest.json`: `sample` goes to the graders, `fresh` to the auditor. Skip a number
   flagged "no readable page". More than ~12 submissions: split the graders in two by page count.
6. Header fields: course, code and term from the sheet's first page; `date` = `due` of `Assignment details.json`
   (dd/mm/yyyy); lecturer and TA from the sheet, `""` if absent. Points per section from `Rubric.md` §0 ("חלוקת הנקודות").

## Step 2: the council, one turn, in parallel

Prompts: `references/roles.md`. Add to every prompt: the course and the assigned questions, the fixed points per section
(from `Rubric.md`), the input paths, the privacy line (numbers only, never a name, ID or email even if one is on a page),
and "use only Read/Glob on the inputs folder; write your file with Write". Each agent writes one file in `<work>\agents\`:
`solver.md` (sheet, Solutions.md, Solution methods.md), `student.md` (sheet first, Solutions.md after), `lecturer.md`
(sheet, Solutions.md, Rubric.md §0–§3), `grader-1.md` and `grader-2.md` (sheet, Solutions.md, findings.md, their
submissions; model `sonnet`, they mostly read images), `ta.md` (Solutions.md, Solution methods.md, Rubric.md whole,
findings.md). They do not see each other. Don't read the submissions' pages yourself and don't read the agents' files
beyond what the merge needs.

## Step 3: merge

`references/merge-rules.md`, with `Rubric.md` winning on points and deductions. Write `<work>\rubric.json` (question
`n` is a string such as `"קבוצות 11"`; `general_rules` from `Rubric.md` §3 in ≤ 9 short rows, or the defaults).
Then `python "<skill>\scripts\make_pdf.py" "<work>\rubric.json"` (validate → TeX → PDF). A validation error is a wrong
number in the JSON: fix and rerun. A TeX error is a bad LaTeX string: fix that string.

## Step 4: self-audit before anyone sees it

Spawn role 6 (`auditor.md`) with `rubric.json` and the 3 `fresh` submissions' pages. Apply its "תיקונים מוצעים" that are
clearly right, rebuild. Once.

## Step 5: deliver

1. Copy `<work>\rubric.pdf` → `<assignment>\פדגוגי\Rubric.pdf` (overwrite), `<work>\rubric.json` →
   `פדגוגי\Working notes\rubric.json`, `<work>\CHANGELOG.md` → `Working notes\Rubric PDF changelog.md`. Nothing else goes
   into `פדגוגי` (a top-level `.md` would be sent to Claude with every submission).
2. Delete `<work>\inputs\submissions` (student pages). The rest of `<work>` may stay for the committee loop.
3. If the shared folder isn't synced on this computer (`dashboard/shared_folder.py` doesn't find it), ask once and upload
   the three files as the `rubric` skill's step 6 does.
4. Report, ≤ 10 lines in Hebrew: total, points per question, the 3 heaviest deductions, the auditor's line (could it
   grade without guessing?), every ⚠ disagreement with `Rubric.md` (one line each, for the lecturer), where the files are.

## Step 6: committee loop, until מאושר

Each round of remarks:
- **Committee pass (cheap):** one subagent gets ONLY the remarks + current `rubric.json` + the agent files, never the
  inputs again, and answers in the five voices: per remark, what changes, where, any objection. ≤ 30 lines →
  `<work>\agents\round-N.md`.
- Apply to `rubric.json`, rebalance inside the same section unless told otherwise, `make_pdf.py`, deliver as in step 5,
  reply with only what changed (2–5 lines), one line in `CHANGELOG.md`.
- Reread a submission only when a remark is about that submission, from `grading.sample` of that number.
- On another computer, or after `<work>` was deleted: start from `פדגוגי\Working notes\rubric.json`.
If asked "why X points?", quote the agent file that justified it. A remark that contradicts `Rubric.md` is applied to
the PDF only after the user says so, and then say that `Rubric.md` (the bot) still has the old rule.

## Token budget (Ori, 2026-10-29: "you are grinding tokens")

The first run on 3438636 cost about 1.1M tokens in agents (two graders 200K each, TA 210K because it read all of
`Rubric.md`, lecturer 135K, solver and student 100K each, auditor 135K) plus the main agent. Keep it under ~700K:
- Sample `--n 10 --fresh 3`, not more; graders on `sonnet`; one grader when the sample is ≤ 8 submissions.
- The TA gets `Rubric.md` §0, §3 and §4 only (Read with offset/limit by its headers), never §1, §2, §5–§9. The
  lecturer gets §0–§3. Nobody else gets `Rubric.md`.
- The sheet goes only to solver, student and lecturer; graders get `Solutions.md` (it has the question text).
- The main agent never reads page images, never reads the agents' files twice, and checks the PDF with ONE preview
  (pages 1–2 at 60 dpi) per build, not every page. Fix validation and TeX errors from their messages, not from images.
- No layout experiments in a run: `scripts/` and `assets/` are tested; a cosmetic gap is reported, not chased.
- Committee rounds: the committee agent gets remarks + `rubric.json` + agent files only (≈ 15K), never inputs.

## Privacy

Student pages exist only in `<work>\inputs\submissions` and are deleted at the end. Nothing in the delivered files
names a student: submissions only by 4-digit number. Never open `Key - number to student.csv`.
