---
name: grading-skill-maker
description: Build the grading skill of one assignment from its approved rubric (מחוון), so the whole team can grade that assignment's works with one sentence and without passing the rubric around - the rubric team's weekly step, right after rubric-builder's "מאושר". Use when someone says "תכין סקיל בדיקה להגשה X", "סקיל בדיקה לדף X", "תבנה סקיל למטלה", "המחוון מאושר, תעשה ממנו סקיל", "תעדכן את סקיל הבדיקה", "המחוון השתנה", "איזה סקילי בדיקה יש", "grading skill for assignment N". Not for building the rubric itself (rubric-builder) or for grading (exercise-grader, or the assignment's own grade-<course>-<N> skill).
---

# Grading-skill maker: one grading skill per assignment, every week

Decided at the team meeting of 2026-11-15: each assignment gets its own grading skill, built from its rubric. The
rubric team builds the rubric with `rubric-builder`; once the TA says "מאושר", this skill turns it into
`grade-<course>-<N>` (say `grade-linear-1`), which every teammate's Claude then uses when someone says
"תבדוק עבודה של הגשה 1 בלינארית" and drops a work in.

**Talk to the user in Hebrew.** Never open `Key - number to student.csv`, never print names or ID numbers.

## How it works (say it in two sentences if the user asks)

`tools/assignment_skill.py` (in this repo) does all the building; you only check, ask and report:
- The new skill holds a **frozen copy of exactly what the system's grading reads** from the assignment folder
  (`Assignment details.json`, the files of `פדגוגי` that grading sends, the official key, `Official solution.pdf`),
  plus a `SKILL.md` that says: grade with `exercise-grader` (the system's own grading code, on every computer that
  runs the system), with this copy as the rubric. Before writing, the tool checks that the copy gives the grading the
  same text and the same points as the folder itself, and refuses otherwise.
- It is saved in the shared folder, `<course>\Grading skills\<name>\`, and installed on this computer. **Every
  teammate's computer copies it by itself** at the next start of the system (`dashboard/skills.py`), or now with
  `python tools/assignment_skill.py install`.
- **The rubric is the one source.** A grading instruction for this assignment ("in 11ג accept also X") goes into the
  rubric through `rubric-builder`, never only into the skill: otherwise the site's grading and the skill would grade
  differently. After the rubric changes, build the skill again (same name, next version).

## Step 1: which assignment

From the user's words ("הגשה 1 בלינארית", "דף תרגילים 3", a Moodle id): `python -m moodle list` shows every
assignment with its id. "דף X" → the assignment whose `questions` in `Assignment details.json` name that sheet. Two
match, or none → ask; never guess. Run every command from the repo's root (this checkout).

## Step 2: is the rubric ready (in one message, side by side)

- `python tools/assignment_skill.py check <id>`: is there a skill already, and is it behind the rubric?
- `python -c "from moodle import paths; from grading import one_submission as o; import json; r=o.rubric(paths.assignment_dir('<id>')); print(json.dumps({k: r[k] for k in ('title','max_grade','total_points','questions','official_key')}, ensure_ascii=False))"`
  (the questions and points exactly as the grading sees them; an error = no rubric with points)
- read the last 15 lines of `<assignment>\פדגוגי\Working notes\Rubric PDF changelog.md`, if it exists.

Then:
- **No rubric, or a question without points:** say which, and that the rubric comes first (`rubric-builder`). Stop.
- **The changelog doesn't say "מאושר"** (or there is none): show the points table and ask "המחוון מאושר לבדיקה?".
  Build only after a yes from the user in this chat.
- **A skill already exists and is up to date:** say so (name, version, date, by whom) and stop, unless the user asks
  to build again anyway.
- Show the user one short table (שאלה | נקודות, and the total) before building.

## Step 3: build

`python tools/assignment_skill.py build <id> --by "<the user's GRADER_NAME, or their name>"`
- The name is `grade-<course>-<N>` by itself (`linear`, `discrete`); `--name` only when the user asks for another.
- `--triggers "<phrase>"` (repeatable) adds phrases that start the skill, beyond the defaults ("תבדוק עבודה של הגשה N
  ב<course>", "בדיקה של <title>", "תבדוק לפי המחוון של הגשה N"): add the ones the user uses, e.g. the sheet's
  name ("דף וקטורים").
- It prints the skill's folder, its version, the questions and whether it was installed here.

## Step 4: try it (only if the user wants, and on as many works as the user says)

Ask: "לנסות את הסקיל על עבודה אחת או שתיים לפני שמפרסמים לצוות? כמה?". The number is the user's call; never pick
works or a sample on your own. Grade the works they name (a number in `1 - Submissions to grade`, or a file they
drop in) **following the new skill's own `SKILL.md`** (at `<home>\.claude\skills\<name>\SKILL.md`), exactly as a
teammate's Claude would. Report the grade and points per question next to what the site's grading gave the same
work, if it has one (`python -c "from moodle import grades, paths; print(grades.read(paths.assignment_dir('<id>')).get('<number>'))"`:
the merged grade row of that number only), and the path of the marked PDF. A difference that comes from the rubric → back to `rubric-builder`, then build again.

## Step 5: tell the team

In Hebrew, short: the skill's name, the assignment, the version, the total points, where it is
(`<course>\Grading skills\<name>`), and the sentence a teammate says to use it
("תבדוק עבודה של הגשה N ב<course>" + the work). Teammates get it at the next start of the system; a teammate who
doesn't run the system copies the folder `<course>\Grading skills\<name>` from the shared folder into
`%USERPROFILE%\.claude\skills\` (it needs `exercise-grader` there too).

## Other requests

- **"איזה סקילי בדיקה יש"**: `python tools/assignment_skill.py list` (name, assignment, version, date, up to date or
  behind the rubric).
- **"המחוון השתנה" / "תעדכן את הסקיל"**: Step 2 (check shows which files changed), then Step 3 again.
- **Delete a skill:** only on the user's explicit word, and only the folder in `<course>\Grading skills\` (each
  computer keeps its copy until removed by hand from `.claude\skills`). Say that.
