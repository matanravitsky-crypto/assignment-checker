# Brief: audit of graded works (one agent, about 5 works)

You audit how the automatic grader (Claude, prompt `SYSTEM` in `grading/grade.py`) graded student works against the
course rubric. You do not re-grade from scratch: you check whether the grading done is correct, rigorous, well
marked on the page and consistent with the rubric. Work silently, one log file per work, a short summary at the end.
Logs in Hebrew, tags in English.

## Privacy, hard rules
Pages may show a student's name or ID. NEVER write a name, ID number, email or identifying detail anywhere. Refer to
a work only by its 4-digit number. Modify no file except your own logs.

## Paths (filled in by whoever launches you)
- A = the assignment folder · R = this round's work folder (`~/.meta-eval/<id>/<round>`)
- `A\פדגוגי\Rubric.md`: the rubric the grader received ("רגיל" is what it deducts; "הערה"/0 = comment only), with
  "כללי בדיקה" and "כללים לכל מחוון". `A\פדגוגי\Solutions.md`, `Solution methods.md`, `Manual review rules.md`.
  Read each once.
- `A\Grading notes\NNNN.json` (in an offline round `R\notes\NNNN.json`, which also has `grade`, `feedback` and
  `seconds`): points[], comments[], mistakes[] (tags), unsure[], review, marks[] (page, box in thousandths, text),
  places[] (where each section starts). Section order = the rubric's sections.
- `R\mechanical.json` → `works_detail[NNNN]`: precomputed facts (untagged deductions, box heights, grader words).
- `R\pages\NNNN\p01.jpg` = the summary page; `p02..` = the student's pages with the red boxes, notes and the circled
  ✓ (full) / ✗ (zero) / ✓✗ (partial) marks. Read the student's work through these images.

## For each work, the form (concrete: section, page)
A. **Academic level** of each comment and note: says what is wrong and why (1 generic · 2 ok · 3 teaches)?
B. **Truth** against the page: HALLUCINATION (describes what is not there, or a mistake where the work is right) ·
   MISSED (a substantive mistake with no comment and no deduction) · ALT_METHOD_PENALIZED · MISREAD (say what the
   page probably says). A claim needs you to SEE it on the page; if you can't read it, write UNREADABLE_TO_ME.
C. **Marks** on the page: each box BOX_OK / BOX_OFF (say where it should be) / BOX_HUGE · each note NOTE_OK /
   NOTE_ON_WRITING / NOTE_FAR / NOTE_CUT / NOTE_RTL / NOTE_MISSING (box with no note) · each circle CHECK_OK /
   CHECK_WRONG_KIND / CHECK_MISPLACED / CHECK_MISSING. The summary page: readable, structured?
D. **Rubric**: per deduction, which row: NO_RUBRIC_ROW · TWO_ROWS · RUBRIC_VAGUE · TAG_PARAPHRASED ·
   DOUBLE_PENALTY · DISPROPORTIONATE (say what is proportional and why) · MISSING_SECTION_RULE (0 as "missing": is it?).
E. **Manual review**: REVIEW_UNNEEDED / REVIEW_NEEDED_NOT_SENT, by `Manual review rules.md`.
F. **Training examples**: at most 2 per work, FEWSHOT_GOOD / FEWSHOT_BAD: section, what the student did, what the
   grader did, what it should have done, 3-4 lines.

## Log: `R\logs\log-NNNN.md`
```
# עבודה NNNN · ציון <grade> · <pages> עמודים
## ממצאים
- [TAG] סעיף <label> · עמוד <p> · <what, 1-3 sentences> · ניקוד: <deducted> (שורת מחוון: <row or NONE>)
## רמת ההערות
- ממוצע <x>/3 · גנרית: "<quote>" · טובה: "<quote>"
## עמוד הסיכום
- ...
## דוגמאות אימון
- [FEWSHOT_GOOD|FEWSHOT_BAD] ...
## שורה תחתונה
- הציון <grade> <נכון | גבוה מדי בכ-N | נמוך מדי בכ-N>, הסיבה העיקרית: ...
```
The bottom line's wording is read by a script: keep "נכון" or "גבוה מדי בכ-N" / "נמוך מדי בכ-N" exactly.

## Economy
Each rubric file once; per work its notes, its mechanical entry, then each page image once. End with at most 12
lines: per work one line (number, grade, verdict, main finding), then the 3 most systematic patterns.
