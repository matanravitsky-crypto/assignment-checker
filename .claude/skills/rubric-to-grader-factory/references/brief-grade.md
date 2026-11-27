# Brief: a grader agent of the loop

You are a teammate's Claude grading a few student works with the grading skill `<SKILL>`. Work exactly as that
skill says; nothing else decides.

0. Read `<MAKER>\references\lessons.md` first: what earlier rounds learned about grading.
1. Read `<SKILL_DIR>\SKILL.md` and follow it. `<skill>` = `<SKILL_DIR>`. The rubric is built in
   (`<skill>\assignment`); never look for another one, never open anything in OneDrive or the shared folder.
2. The works, one by one (the skill's step 6: `rubric` and `rules` once, then each work in its own work folder
   named after the work): `<NUMBERS>`. Work NNNN's files: `<IN>\runs\NNNN\in\`.
3. Python: `py -3` if `py -3 -c "import pymupdf, numpy"` works; otherwise the skill's step 1.
4. Output: `<OUT>\runs\NNNN\out\NNNN - graded.pdf`. `<ZOOM>` (either nothing, or `--no-zoom` at the end of every
   `mark` when Claude Code is not signed in here). No Explorer, no "What's new". Delete only your own work folders.
5. The skill's `preview` check for each work; fix wrong spots as it says.
6. Privacy: never write a name or ID number anywhere.

Reply in at most 6 lines: per work, its grade and whether it needs manual review.
