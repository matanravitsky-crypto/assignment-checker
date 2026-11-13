# The report, and where each approved item goes

## The report: `docs/Meta-evaluator report - <course> <הגשה N> <round>.md` (numbers only)
Hebrew, for the user. In this order:
1. **How it was checked** (3-5 lines): which works and why (the sample's rule), which grading they had (date, model,
   rubric version), how many claims the verifier checked and how many it confirmed (`tally.json → verified`).
2. **Bottom line** (a small table): grade right / off by 1-3 / off by more / system failure; confirmed hallucinations,
   missed mistakes, boxes off, notes lost; the manual-review rate against its 5-6% target; drift between works
   (`mechanical.json → inconsistent_tags`); length bias (grade by page count).
3. **Part A `[RUBRIC-OPT]` R1..Rn**: per item the problem, the works (numbers) and confirmed findings it rests on, the
   proposed wording for `rubric.json` (or `universal-rules.json` when it is about every rubric), and ⚠ when it changes
   points (the TA decides those, not this skill).
4. **Part B `[GRADER-OPT]` G1..Gn**: per item the failure, one concrete example (work, section, page), the change
   (prompt text, or which function), its priority (🔴 a wrong grade or a wrong page for the student · 🟠 an inaccurate
   comment · 🟡 style) and its token cost (text added to the shared context, cached once per work).
5. **Training examples** (FEWSHOT_GOOD / FEWSHOT_BAD), at most 6 of each, each 2-3 lines.
6. **What was not found**, said plainly (no double penalties, no drift...), so the user knows what is solid.
7. **What the loop did**: per iteration the items implemented, the works re-graded offline, closer/same/further,
   the cost and seconds per work before and after, and what was undone. Each R/G item says `[בוצע בלופ]`,
   `[ממתין: נקודות/מיזוג/תיקייה משותפת]` or `[בוטל: הרחיק]`.
8. **הצעות חדשות** (at most 3, often none): only ideas the user never raised, each with why, cost, risk and how to
   test. Nothing here was implemented.

Then `me.py check-report <id> --round R <report>`: numbered in order, every item cites a work of the sample, no item
rests on a claim the verifier rejected. Fix the report until it passes.

## Where an approved item goes
| Item | Goes to | How it reaches everyone |
|---|---|---|
| A rule about how any rubric is applied (not points) | `.claude/skills/rubric-builder/assets/universal-rules.json` | rendered into every rubric built from `rubric.json`; grading adds it to a hand-built one (`grade.universal_rules_text`). Merged to main → every computer at its next start |
| A row, a wording or a decision for one assignment | that assignment's `פדגוגי\Working notes\rubric.json`, through rubric-builder (archive the old json first, `make_pdf.py`, deliver as its Step 5, a line in `Rubric PDF changelog.md`) | the shared folder (OneDrive) |
| ⚠ A change of points | nowhere, until the TA approves it in words | — |
| How the grader reads, decides, tags or writes | `SYSTEM` in `grading/grade.py` (short; every line is paid for in every work) | branch + PR + `pytest`; merged to main → every computer |
| Boxes, notes, circles, the summary page | `grading/grade.py` (`_place_marks`, `_note_rect`, `_place_checks`, `_summary_page`), `grading/locate.py` (the zoom pass), `grading/render.py` | same |
| A training example | a short block in `SYSTEM` (one section's JSON, not a whole work), only after the user approves it | same |

Never edit `Rubric.md` by hand (it is rendered), never change points without the TA, never commit student data.

## After implementing: measure, then keep or undo
1. `me.py backup` on the works the change is meant to fix (from the round's sample), then re-grade only them
   (`python -m grading <id> --ids ...`, about $1 a work: say how many and the cost before starting).
2. `me.py compare --against <the round with the targets>`: works closer to the auditors' target grade, the same,
   further. A work that moved further is read (its new notes and pages) before anything else.
3. The re-graded works get a re-audit (`brief-recheck.md`) when the change was about marking or wording: the numbers
   can't see a box.
4. A change that moved works further, or made new HALLUCINATION/MISSED, is undone or fixed before it is merged.
