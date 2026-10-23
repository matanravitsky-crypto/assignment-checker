---
name: place-comments
description: Write red grading comments onto a student's PDF without covering their handwriting. Use whenever you mark, annotate or draw comments, boxes or arrows on a submission page, instead of choosing positions or drawing yourself.
---

# Comments on a student's page: where to write them

Don't pick positions for comments, and don't draw lines or text on a submission yourself. The bot in
`grading/placement.py` does it with no Claude call and no tokens:
- a red box around the faulty step (you give the box),
- the comment in the nearest **empty** spot, never on the writing,
- a line with an arrowhead from the comment to the box that **never crosses ink**: it bends around the writing as much as it needs to.
  With no clean way out, the comment goes in the least written spot, with no line.

The rules, how it works and what it costs: `grading/COMMENTS_PROTOCOL.md`.

## How

1. Write the marks as JSON: a box per mistake, in **thousandths** of the page as it is shown (0,0 top left, 1000,1000 bottom right),
   tight around the relevant lines, plus a short Hebrew comment (up to about 12 words, plain math like `A^-1`, no LaTeX):
   ```json
   [{"page": 1, "x0": 120, "y0": 300, "x1": 610, "y1": 345, "text": "טעות בסימן: צריך t_A=4t_B"}]
   ```
   A `Grading notes/0001.json` file works as is (its `"marks"` are in this format).
2. Run:
   ```bash
   python -m grading.placement in.pdf marks.json out.pdf
   ```
3. It prints one line, for example `2 סימונים ב-1 עמודים: 2 עם קו נקי, 0 צמודים, 0 בלי קו ... -> out.pdf`.
   That line is enough. Open the page image only if it reports marks with no line and you need to know why.

Inside the grading code, `grade.mark_pdf` already calls `placement.draw`, so the grader doesn't need this command.

## Rules
- Grade only from `1 - Submissions to grade`. Never print or copy names, ID numbers (ת"ז) or emails from a page into chat, commits or logs.
- Write `out.pdf` outside the repo (student data never goes into git).
