# What the loop has learned (read before grading or judging; add at the end of every round)

Every agent of the loop (grader, judge) reads this file first. It is the experience of earlier rounds, so the next
round starts where the last one stopped. Keep each lesson to what it teaches and the evidence; newest at the end of
its part. Never a student's name; works by number only.

## Grading (for the grader agents)
- **Grade in batches of 5 per agent** (the skill's own step 6: `rubric` and `rules` once). Measured 2026-11-27:
  ~65K tokens and ~2.5-3 min per work, against ~224K and ~5 min for one work per agent, at the same level.
- **Each work in its own work folder**, named after the work; delete only your own (a parallel run lost a folder to
  another's cleanup).
- **Before writing answer.json:** for every full-points section, compare the final answer with the line it was copied
  from, sign by sign (LA1 0488: a minus lost on the way to the boxed answer got 7/7).
- **One-sided operations** are the most missed reading (LA0 0926 8ד: only the left side multiplied by (1+i)): read
  each line against the one before, both sides.
- **The rubric's rows, word for word, as tags**; the code snaps a shortened row back, but a paraphrase splits the
  statistics.
- **Two rows that fit:** take the more specific one (LA1 0762 8ב: "circular reasoning" −3, not "missing" −4).
- **Notes the student reads:** "יש ל..." for an instruction, never a plural imperative ("בדקו", "הציבו").
- **Without the zoom pass** (no signed-in Claude Code) marks on two-column pages and notes near handwriting land
  badly; check those pages in `preview` and fix the spots by hand.

## Judging (for the judge agents)
- **Run-to-run noise is 1-4 points** for the same grader on the same work; a single 1-point difference is not a
  finding, the same choice in two works is.
- **Measured levels** (2026-11-27): the dressed skill vs the system on LA0: mean gap 0.95 then 0.4 points, 19 of 30
  identical; on LA1, 270 of 280 sections by the rubric. A round far below this is a regression: say so first.
- **Where gaps come from, in order of frequency:** (1) the rubric lets two readings through (step table vs error
  rows, LA1 8א; two rows fit, LA1 8ב; LA0 7א/7ד); (2) a missing row (a slip the next line corrects, LA1 15א; a
  wrong point after a correct t, LA1 14א); (3) a reading miss; (4) marking only. Classify honestly: an R finding is
  not fixed by the skeleton.
- **A TA's grade is gold only where it follows the rubric**: LA0 0954, the TA gave 8/8 where the rubric gives 2/8.
  Report such a case as P, not as an error of the skill.
- **Check the summary page** every time: the grade, and the Moodle grade's basis (by questions handed in when
  `per_question` is "any").

## Cost (for the orchestrator)
- The system itself: ~$0.52 grading + ~$0.07 zoom per work (Opus; 18-19/11).
- A calibration round of 10 works in 2 batches ≈ 650K tokens; a judge on 5 works ≈ 250-300K tokens.
- Re-grade only the works a change touches; never a whole sample again for one fix.

## Rounds
- 2026-11-27, LA0 (grade-linear-0) rounds 1-2, LA1 (grade-linear-1, the pedagogical package) rounds 1-2: the
  lessons above. Skeleton fixes: tags snapped to rows, numbered part names, imperatives (also before ":"), Moodle
  grade per question and its wording, final copy check, own work folder only.
