# Brief: audit works a rubric's grading skill graded (the improvement round)

You review, silently and strictly, works that the skill `<SKILL>` graded in a test round. Nothing here is official:
no grade goes anywhere. Your job is to find what to fix so the next round grades better, and to say when nothing is
left that is worth fixing.

**Inputs** (the orchestrator fills them in):
- the skill: `<SKILL_DIR>` (its `SKILL.md`; its rubric is the folder `<SKILL_DIR>\assignment`: `Assignment details.json`
  and every `.md` in `פדגוגי\`; read them once, fully)
- the works: `<ROUND>\runs\NNNN\` for NNNN in `<NUMBERS>`: `in\` (the student's files), `out\NNNN - graded.pdf` and
  `out\NNNN - graded.json` (grade, points, comments, mistakes, marks, review)
- the system's grade of the same work, when there is one: `<SYSTEM>` (a JSON list `{number: {"grade", "points"}}`);
  where it differs from the skill's by more than 2 points, find out which one the rubric supports

**How to look at a work** (in a work folder of your own under `%TEMP%\audit\`, outside OneDrive):
1. `py -3 "<SKILL_DIR>\scripts\run.py" prepare <work folder> <the files of in\>` → page images; read every page once.
2. `py -3 "<SKILL_DIR>\scripts\run.py" preview <work folder> "<out\NNNN - graded.pdf>" <pages with marks>` → small
   images of the marked pages; read them.
3. For every section: what the student wrote, which rubric row applies, the points the rubric gives, and what the
   skill gave. Check the marks: on the right spot, the right section, "-N" matching what was lost. Check the student
   text: Hebrew, the rubric's fixed wording where it has one, no "כתבו"/"רשמו", no grader's words, no names.

**A finding** is something you can show on the page and in the rubric, never a taste. For each one:
`{"work": "NNNN", "section": "...", "kind": "G" | "R" | "P", "severity": 1-3, "what": "...", "evidence": "page N:
what is written; rubric: the row", "fix": "..."}`
- **G** (the skeleton: the grading steps, the engine, the marking, cost): it would happen with any rubric.
- **R** (this rubric): a row missing, two rows that fit the same thing, a price that contradicts another row, a
  wording students misread. Never change points yourself; say what the rubric should decide.
- **P** (the team's policy): half points, unreadable work, when a person checks, what Moodle gets.
- severity 3 = the grade is wrong by ≥ 2 points or a student is told something false; 2 = a wrong spot, tag or
  wording the student sees; 1 = cosmetic or statistics only.

**Privacy:** works by 4-digit number only; never write a name or an ID number, even if it is on the page.

**Write** `<ROUND>\audit\audit-<YOUR LETTER>.json`:
`{"works": [...], "agree_with_rubric": <how many sections of all were right>, "sections": <all>, "findings": [...],
"worth_another_round": true | false, "why": "one sentence"}`
`worth_another_round` is false only when no finding of severity ≥ 2 is left that a change could fix.

Reply in at most 8 lines: sections right out of all, the findings by kind and severity, and your verdict.
