# Merging the agent reports into rubric.json

Read all the agent files, then write the JSON section by section. Decide, do not average.

**When the assignment has a `Rubric.md` (the grading bot's rubric), it wins:** section points are its §0 table, and every
deduction in the error tables is its deduction as רגיל; מחמיר = רגיל + 1 on every row (a range: its upper end + 1), capped
at the section's points (Ori, 2026-10-29: the two columns must differ, מחמיר is the strict regime). An agent that disagrees with `Rubric.md` gets a ⚠ line in the report to
the lecturer, not a change in the JSON. The rules below then apply to what `Rubric.md` does not settle: the steps, their
split, the wording, the alternative methods, the order of the error rows.

**Steps** — take the TA's split. Change it only when: the lecturer marks a step as core and the TA under-weighted it; the student found a trap the split does not see; the solver has a valid alternative (then add it under `alt_methods` with its own split summing to the section).

**Points per step** — TA numbers, bent toward the lecturer's core/mechanical ratio. Whole numbers. A step under 1 point is merged into its neighbor.

**Errors** — graders' tables first (real errors beat predicted ones), then TA's conventions for deductions, then student's traps as predicted rows if not already there. Sort by severity, worst first, like the course sample. 3–8 rows per section; more than 8 means two rows should merge.

**Deductions** — follow the course conventions in roles.md §5 (or `Rubric.md`, see above). Same error, same cost across sections (lecturer's consistency note). A cascade is charged once; later rows say "בעקבות <step>" with 0 / 1 at most. Near-zero error: section points minus what the lecturer lets survive.

**Text** — a step names what to look for, not the answer ("משוואת המישור" not "$3x+5y+z=13$"; the answer lives in `answer`). Error text is concrete: the wrong object and the wrong value. ≤ 12 words each.

**answer** — the final answer only, one line, from the solution file. **solution** — at most two display lines of the key chain, optional; skip it when the answer is self-explanatory.

**general_rules** — defaults from `assets/default-rules.json`, plus at most 2 rules specific to this sheet (e.g. which questions are graded, how "choose 3 of 4" is handled). With a `Rubric.md`: its global rules (§3) condensed to ≤ 9 short rows instead of the defaults.

**Before building** run `validate_rubric.py`; a failure is a wrong number in the JSON, never a reason to change section points.
