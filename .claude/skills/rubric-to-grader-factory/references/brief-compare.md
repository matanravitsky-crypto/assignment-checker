# Brief: the judge between two grading skills (the comparison loop)

Two skills graded the same works. You decide, section by section, which one graded by the rubric, and how good each
one's marking and feedback is. Work slowly and thoroughly: this is the step the loop relies on. Nothing is official.

**Inputs** (the orchestrator fills them in):
- the rubric: `<RUBRIC>` (an assignment folder: `Assignment details.json` and every `.md` in `פדגוגי\`). Read it
  fully once. Where `Grading notes.md` and the system's "כללים לכל מחוון" disagree, Grading notes decides.
- arm X = `<X_NAME>`: `<X_ROUND>\runs\NNNN\out\NNNN - graded.pdf` and `.json`
- arm Y = `<Y_NAME>`: `<Y_ROUND>\runs\NNNN\out\NNNN - graded.pdf` and `.json`
- the student's files: `<IN>\runs\NNNN\in\`
- the works: `<NUMBERS>`
- a grader to make page images: `<GRADER>\scripts\run.py` (`prepare`, `zoom`, `preview`)

**For every work** (in a folder of your own under `%TEMP%\judge-<LETTER>\`, outside OneDrive):
1. `py -3 "<GRADER>\scripts\run.py" prepare <folder> <the student's files>`; read every page.
2. Put the two JSONs side by side: points per section, mistakes (tags), comments, marks (page, box, text, deduct).
3. **Every section where the points differ:** find the student's lines on the page; when a symbol is unclear, use
   `run.py zoom <folder> <page> <x0 y0 x1 y1>` and read the lines before and after. Decide which rubric row applies,
   what it gives, and which arm is right (or neither). Write the evidence: what is written, which row, which price.
4. **Every section where the points agree but the tag, the comment or a mark differs in substance:** which one tells
   the student the truth, in the rubric's own wording, at the right spot.
5. **Both PDFs:** `run.py preview` of each arm's marked PDF, the pages with marks; check that marks sit on the
   right spot and section, that "-N" adds up to what was lost, and the summary page (grade, Moodle grade by
   questions handed in).
6. Score each arm for this work: `points_right` (sections whose points the rubric supports), `marking` 0-3,
   `feedback` 0-3.

**Each finding:** `{"work", "section", "kind": "G" | "R" | "P", "severity": 1-3, "better": "X" | "Y" | "neither",
"what", "evidence", "fix"}`. G = the grading skeleton (steps, engine, marking: it would happen with any rubric); R =
the rubric lets two readings through or lacks a row; P = team policy. Severity 3 = a grade wrong by ≥ 2 points or a
false statement to the student; 2 = a wrong spot, tag or wording the student sees; 1 = cosmetic.

**Privacy:** 4-digit numbers only; never a name or ID number.

**Write** `<OUT>\judge-<LETTER>.json`: `{"works": [...], "sections": <all>, "X_points_right": n, "Y_points_right": n,
"X_marking": avg, "Y_marking": avg, "X_feedback": avg, "Y_feedback": avg, "findings": [...],
"worth_another_round": true | false, "why": "..."}`. `worth_another_round` is false only when no G finding of
severity ≥ 2 against arm X is left that a change of the skeleton could fix.

Reply in at most 10 lines, in Hebrew: per arm, sections right out of all, marking and feedback scores; the G findings
against X by severity; your verdict.
