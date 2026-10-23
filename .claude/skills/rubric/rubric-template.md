# The structure of every Rubric.md

Every assignment's rubric has exactly these sections, in this order, so a TA who knows one rubric knows them all.
Hebrew text, math in `$...$`, section numbers as below. Write the rubric itself in Hebrew; this file is the spec.

**No length limit.** TAs don't read the rubric end to end; they ask their Claude about it, and the grading
bot applies it. So completeness beats brevity: every case, caveat and exception goes in (Assignment 0's
rubric is about 1,200 lines). Depth goes into the per-part tables and the global rules, not into prose.
A case that applies to many parts (notation, copy error, crossed-out work, out-of-scope method) is written
**once** as a global rule (§3) and referenced by its code in the tables, never repeated in each table.

## Header (≤ 8 lines)
Title `# <Hebrew title> – מחוון (0–100)`, course and semester, Moodle id, the questions (sheet + numbers),
the status line (`טיוטה, ממתינה לאישור המרצה. החלטות פתוחות מסומנות ⚠ (§7).`), and the companion files
(`Solutions.md`, `Solution methods.md`, and `Working notes/findings.md`). Privacy line: submissions only by 4-digit number.

## §0 עמוד אחד לבודק
1. **Points per part** table, the **first table in the file**: | שאלה | נק' | סעיפים |, one row per question,
   the question as "<sheet> <number>" (e.g. `| קבוצות 11 | 20 | א 3 · ב 3 ... |`). Grading reads the points per
   question from this table, so keep the format exactly. Then one line on why the weights (what each part tests,
   where students failed in the sample). Sums to exactly 100.
2. **Answer key** table: every part → final answer, in the exact form expected.
3. **Common deductions at a glance**: ≤ 12 rows | מצב | כמה יורד | איפה מפורט |.

## §1 עקרונות (numbered ע1, ע2...)
Must cover: what counts as a final answer and that every equivalent correct form gets full credit;
error carried forward (one mistake costs once); no double penalty; how notation is penalized
(closed list, once per assignment, capped); answers without work; out-of-scope methods; that the
tables are the operational rule and the rubric wins over `Solution methods.md` on any conflict.

## §2 סדר הבדיקה (numbered steps)
Mechanical order a TA or the grading bot follows for one submission: triage (wrong file, blank,
illegible → human), locate each part, read the final answer, pick the table row, apply tags, sum.

## §3 כללים גלובליים
Numbered subsections (3.1, 3.2...), each a short table | מצב | נקודות | הערה |. At least: copy error of the
question data; arithmetic slip; crossed-out work and two answers; answer in another part's place; missing part
or question; wrong file / illegible; out-of-scope method; notation (with its codes, e.g. TUPLESET, EMPTYSET,
DOMAIN); answers in words instead of the requested object. Each rule has a short UPPERCASE code the tables use.

## §4 טבלאות לפי סעיף
One subsection per question, then one per part:
`#### <part> (<points>): <answer>`
| קוד | מה כתוב | נק' | הערה לסטודנט |
- Codes `<part>-1`, `<part>-2`... Rows ordered full credit → partial → zero.
- As many rows as the part needs. First row(s): every equivalent correct form (full). Then each mistake seen in the
  sample and each plausible case the council added, with exact points. Last row: blank / missing = 0.
- The student comment is one line, kind and specific, says what to do next time. ✓ for full credit.
- A row may reference a global rule by code instead of restating it.

## §5 לבודק אנושי
The list of situations where the bot does not grade and flags the submission for a person.

## §6 פלט הבוט
How points are recorded per part, how tags reduce points (never below 0, never above the part's maximum),
and that nothing goes to `Grades.csv` or Moodle while any ⚠ in §7 is open.

## §7 החלטות המועצה ⚠
One subsection per decision: the recommendation, who was for and against (dissent recorded in one line
each), and one line saying exactly what the lecturer must approve or choose.

## §8 מבחן שדה
The two TAs' totals per submission, how many parts they disagreed on, and which rules changed because of it.
