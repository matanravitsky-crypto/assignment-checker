---
name: grading-skill-maker
description: Turn an approved rubric (מחוון) into the assignment's own grading skill - dress the rubric on the grading skeleton, run it on a few real works, run an improvement round (what to fix in the rubric, what in the grading), and only then publish it to the whole team, before it grades ~1,100 works. The rubric team's weekly step after rubric-builder's "מאושר". Use when someone says "תכין סקיל בדיקה להגשה X", "סקיל בדיקה לדף X", "המחוון מאושר, תעשה ממנו סקיל", "תלביש את המחוון על השלד", "מקצה שיפורים לבדיקה", "תעדכן את סקיל הבדיקה", "המחוון השתנה", "איזה סקילי בדיקה יש", "grading skill for assignment N". Not for building the rubric (rubric-builder) or for grading itself (the assignment's grade-<course>-<N> skill, or exercise-grader).
---

# Grading-skill maker: skeleton + rubric = the skill that grades rubric X

**The model (Ori, 2026-11-26):** one **skeleton** for every grading skill, a **rubric** dressed on it, and the result,
`grade-<course>-<N>`, is a self-contained skill that grades only that rubric.
- **The skeleton** = the system's grading, everything learned so far: the steps of `grading/skill/SKILL.md` (the same
  file exercise-grader is built from) and the grading engine itself (`grading/` and the core it needs: page images
  with the grid, the grading rules and the answer's schema, the zoom pass, the marked PDF, the summary page, the
  manual-review threshold, privacy). Nothing in it belongs to one assignment.
- **The rubric** = what the grading reads from the assignment folder (`Assignment details.json`, the files of
  `פדגוגי` that grading sends, the official key, the official solution), frozen when it is built.
- `SKILL.md` of the skeleton marks the places that belong to the rubric (`<!-- rubric-slot: ... -->`): "bring a
  rubric" becomes "the rubric is built in". Every other line of the skeleton is in the skill word for word, and the
  engine's files are byte-identical (`tests/skills/test_assignment_skill.py` checks both).
- **The rubric is frozen; the skeleton is not.** The shared folder holds only the rubric package
  (`<course>\Grading skills\<name>\`); every computer assembles the skill from its own skeleton at the system's start.
  A fix in the grading (G items below) reaches every rubric's skill by itself; a rubric changes only through a new build.

All of it is `tools/assignment_skill.py` in this repo. **Talk to the user in Hebrew.** Never open
`Key - number to student.csv`, never print names or ID numbers. Run commands from the repo's root.

## Why the round: 1,100 works

One assignment of Linear Algebra is ~1,100 works, at $0.36-1.2 a work by earlier measurements (Opus grading + the zoom
pass; the run's `usage.jsonl` gives this rubric's real number): what is wrong in
the rubric or the grading is wrong 1,100 times, and the manual queue may hold only ~5-6% (55-65 works). So the skill
goes to the team only after it graded a few real works and the round found nothing left to fix.

## Step 1: which rubric, and is it ready (in one message, side by side)

From the user's words ("הגשה 1 בלינארית", "דף 3", a Moodle id); `python -m moodle list` shows every assignment and
its id; "דף X" → the assignment whose `questions` name that sheet. Two or none → ask.
- `python tools/assignment_skill.py check <id>`: is there a skill already, and is it behind the rubric?
- `python -c "from moodle import paths; from grading import one_submission as o; import json; r=o.rubric(paths.assignment_dir('<id>')); print(json.dumps({k: r[k] for k in ('title','max_grade','total_points','questions','official_key')}, ensure_ascii=False))"`
- the last 15 lines of `<assignment>\פדגוגי\Working notes\Rubric PDF changelog.md`, if it exists.

No rubric or a question without points → say which; the rubric comes first (`rubric-builder`). Stop.
No "מאושר" in the changelog → show the points table and ask "המחוון מאושר לבדיקה?"; go on only after a yes.
Show the user one short table (שאלה | נקודות, total).

## Step 2: dress the rubric on the skeleton (a draft, this computer only)

`python tools/assignment_skill.py build <id> --draft --by "<GRADER_NAME or the user's name>" [--triggers "<phrase>"]`
- The package goes to `~/.grading-skill-drafts\<name>`, never the shared folder; the skill is assembled into this
  computer's `~/.claude/skills\<name>`. The team sees nothing yet.
- The build refuses a copy that would not grade exactly like the assignment folder (the same text and points reach
  the grading), so the run below, on the assignment folder, is the run of this skill.
- `--triggers` adds the phrases the user uses ("דף וקטורים"); the defaults are "תבדוק עבודה של הגשה N ב<course>",
  "תבדוק לפי המחוון של הגשה N", "בדיקה של <title>".

## Step 3: run it (the calibration run)

Ask once: "על כמה עבודות להריץ את מקצה השיפורים?" (with the cost range above). **The number is the user's** (never pick a
sample size yourself); 10-20 is what earlier rounds used. Then, saved nowhere in the shared folder:
```
python ".claude/skills/meta-evaluator/scripts/offline.py" <id> --round calibrate-<name>-v<version> --n <N>
```
It grades with the skeleton's engine and this rubric into `~/.meta-eval/<id>/<round>/` only, spread over submission
sizes, and proves with a fingerprint that the shared folder did not change. Report: the grades, how many went to
manual review (against 5-6%), cost and time per work (`usage.jsonl`), and the marked PDFs' folder.

## Step 4: the improvement round (מקצה שיפורים)

Follow the `meta-evaluator` skill on that round, from its Step 1 (`mechanical`, `render`; skip `sample`) through its
Step 5: auditors on ~5 works each, a verifier, `targets`, `tally`, then the findings across the works. Its two kinds
of items map onto the two halves:
- **R items → the rubric of this assignment** (a missing error row, a row that two readings fit, a deduction that
  drifts between works, a fixed comment that confuses). They go through `rubric-builder`'s loop (its Step 6), and any
  change of points only on the TA's word (⚠). Then build the draft again (Step 2): a new version.
- **G items → the skeleton** (marks in the wrong place, a rule of the grader that misfires, the summary page, cost).
  Code on a branch with tests and a PR, as meta-evaluator says. Once merged, every rubric's skill gets it.
- A finding that is about the policy shared by all rubrics (half points, unreadable work, when a person checks) is
  neither: list it under "החלטות לצוות הפדגוגי" in the report, never change it here.

Then meta-evaluator's bounded loop (its Step 6, at most 3 iterations): re-grade offline only the works the items
target (`offline.py --numbers ...`), `me.py compare`, keep or undo. A gain counts only above a work's run-to-run spread
(1-4 points).

## Step 5: the report, then publish

In Hebrew, short: the grades of the run, manual review rate, cost per work and the estimate for the whole assignment
(works pulled × cost), what the round changed (R and G, before/after), what waits for a word, and the decisions for
the pedagogical team. Then ask "לפרסם את הסקיל לצוות?". On a yes:
`python tools/assignment_skill.py build <id> --by "<name>"` (no `--draft`): the package goes to
`<course>\Grading skills\<name>\` and every teammate's computer assembles it at its next start (or now:
`python tools/assignment_skill.py install`). Tell the team the sentence that starts it: "תבדוק עבודה של הגשה N ב<course>" + the work.

## Other requests
- **"איזה סקילי בדיקה יש"**: `python tools/assignment_skill.py list`.
- **"המחוון השתנה"**: Step 1 (`check` lists what changed), then Steps 2-5 again; the round may be short (only the works
  the change touches).
- **Delete a skill:** only on the user's explicit word, only the package folder in `<course>\Grading skills\`; each
  computer's copy stays until removed from `.claude\skills` by hand. Say that.
