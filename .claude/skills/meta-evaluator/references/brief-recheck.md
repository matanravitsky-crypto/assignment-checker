# Brief: re-audit of re-graded works (one agent, about 5 works)

These works were audited in an earlier round (logs below) and have since been graded again, after changes to the
grader, the marking or the rubric. Say what got better, what is still wrong, and what is newly wrong. Same privacy
rules and the same tags as `brief-audit.md` (read its "Privacy" and "For each work" sections once).

## Paths (filled in by whoever launches you)
- A = the assignment folder · R = this round · P = the earlier round
- `P\logs\log-NNNN.md`: the earlier findings · `R\before\notes\NNNN.json`: the grading those findings were about
- `A\Grading notes\NNNN.json`: the new grading · `R\compare.json` → `works[NNNN]`: old/new grade, the auditors' target
  grade, the sections whose points changed, with the new comment and tags
- `A\פדגוגי\Rubric.md` (the rubric now) · `R\pages\NNNN\pNN.jpg`: the new marked pages

## For each work
1. Every earlier finding: [FIXED] / [STILL] / [CHANGED] (how) / [N/A], with section and page.
2. Every section whose points changed: [BETTER] / [WORSE] / [SAME_QUALITY], by the rubric and the page. Plus any new
   [HALLUCINATION], [MISSED], [NO_RUBRIC_ROW], [DOUBLE_PENALTY], [DISPROPORTIONATE].
3. The new marking, every box, note and circle, with the tags of `brief-audit.md` part C.
4. The summary page.

## Log: `R\logs\log-NNNN.md`
```
# עבודה NNNN · ציון ישן X · ציון חדש Y
## ממצאי הסבב הקודם
- [FIXED|STILL|CHANGED|N/A] ...
## הבדיקה החדשה
- [TAG] סעיף ... · עמוד ... · ...
## הסימון החדש
- ריבועים: N תקינים, M לא · [BOX_OFF] עמוד p · ...
- הערות: ... · עיגולים: ...
## שורה תחתונה
- הציון Y <נכון | גבוה מדי בכ-N | נמוך מדי בכ-N>; הסימון <טוב | בעייתי: ...>; הכי חשוב שעוד לא תקין: ...
```
Keep the bottom line's wording exactly ("נכון" / "גבוה מדי בכ-N" / "נמוך מדי בכ-N"): a script reads it.

## Economy
As in `brief-audit.md`. End with at most 12 lines: per work old→new grade, verdict, the main remaining issue; then the
3 most systematic remaining problems.
