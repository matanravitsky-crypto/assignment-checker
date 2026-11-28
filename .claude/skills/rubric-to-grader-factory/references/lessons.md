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
- 2026-11-27, LA1 comparison, grade-linear-1 vs the pedagogical package run with exercise-grader, 20 works (15
  judged, 210 sections): points by the rubric 208 vs 205, marking 2.47 vs 2.33, feedback 2.67 vs 2.47; grades equal
  on 16 of 20, mean gap 0.25. Where they differed the rubric backed grade-linear-1, or the rubric itself let two
  readings through (8ב "בכל סדר כתיבה" vs 8ב.7). The package's run invented a deduction with no row (0511 8ב) and
  explained the Moodle grade by sections. Lessons for graders: (1) the rubric's 0-point rows and fixed notes
  (§G.14: "L=", a mis-copied given) were missed in 4 of 5 works: a last pass over them, with their tags; (2) a
  "missing" note when the thing is there in another form (t,s∈ℝ³) is false: look again first; (3) a 0-point note
  still gets its tag in `mistakes`, or the statistics miss it.
- 2026-11-27, decisiveness (Ori: "שההחלטיות תשתפר"): LA1 0586 went to a person with 9 points of ranges, mostly 14א
  with no row, while another grader priced the same slip in 0485 by 15א's row and decided. The skeleton now says:
  a mistake with no row in its section takes the row of the same mistake elsewhere, with no range; a range only for
  one real doubt. Judges: a range that a row elsewhere would have closed is a G finding (severity 2).
- 2026-11-27, finish: notes' white backdrop lowered from 0.8 to 0.55 so handwriting shows through (judges in 4
  works, and the pedagogical team's request).
- 2026-11-27, round 3 judges (judge 4-5): a rule stated in words without the computation the step asks for
  ("same ratio, so parallel") got full points (0645 11ב): a step is earned only when done on the page. A deduction
  with no tag in `mistakes` is invisible to the statistics (0586 14א). Re-grade of 0586 with the decisiveness rule:
  80 with 9 points of ranges and manual review became 82 with no range and no review, the same grade as the
  pedagogical package's run.
- 2026-11-28, the rubric PDF path (grade-linear-1-pdf, LA1): the transcription lost nothing (the judge compared it word
  for word with the pedagogical package in every disputed section; 100 error rows in both). Round 1, 10 works: 7
  matched the settled grade, and 0762 8ב was right where both earlier skills had erred. The miss: 0232 8א, three
  points on one line priced as "did not show they are not on a line" (−1 instead of −4): the grader never computed it.
  Skeleton fix: compute a checkable claim on the student's own numbers before choosing the row; a missing step is
  tagged in the step's own words, not by another section's row.
- 2026-11-28, the manual queue measured against people (LA0, 1,099 works, 33 queued = 3%; a TA approved all 33).
  Of the 30 with a grade, the system's own grade was within 2 points of the TA's in 26 (10 identical, mean gap 1.2).
  The queue's reasons: which of two rows applies (most), a symbol read two ways, a mistake no row names, and 3 works
  photographed as one long page (259 px wide at MAX_SIDE: unreadable; one got 100 where the TA gave 92). Fixes: the
  engine cuts a page more than twice as tall as wide into about-A4 pages on blank rows (`grade.split_tall`, in
  `submission_pdf`, so grading, the marked PDF and the site agree); the rules' decision order (סדר ההכרעה): the row
  whose condition matches the page most literally, then the smaller deduction; a reading by what the student did
  with it next, then in the student's favour; a mistake with no row by the same mistake's row elsewhere; one number,
  no range; a self-check of every deduction before answering.
- 2026-11-28, decisive round 1 (the 32 queued works + 8 controls, agents, grade-linear-0): queue 32 → 0, but against
  the TA the mean gap rose from 1.2 to 2.2, always upward (46 sections above the TA, 28 below). "The smaller
  deduction when tied" and "in the student's favour" were wrong: the TAs took the row that names the mistake even
  when it deducts more (11ג: set equal to a point, same parameter), deducted a conclusion not written (A=B after one
  inclusion, "ℝ" for A∩B) and gave nothing for a computation whose result cannot be seen. Fixed in the decision
  order; never infer a tie-break from which way people moved the bot without reading their notes.
- 2026-11-28, decisive round 2 (the 30 works with a TA grade): queue 0, mean gap to the TA 2.2, now downward (-1.1).
  The same work graded in rounds 1 and 2 differed by 2.4 on average: the gap is mostly a grader's own noise. The
  bias left: two deductions in one section for one mistake (a wrong pair, then the A≠B it cost; 11ג in 12 works).
  Rule 6 of the decision order: one mistake, one deduction; a missing conclusion is deducted only by its own row.
