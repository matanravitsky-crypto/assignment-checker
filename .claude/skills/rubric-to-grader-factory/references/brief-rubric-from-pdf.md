# Brief: a rubric PDF in, a rubric package out

A person gave a rubric as a PDF (or an image, a Word file). Turn it into the package the grading skeleton reads,
**without changing a word of its meaning**. You are a careful transcriber, not an editor.

**Inputs:** the file `<PDF>`; the assignment it is for `<ASSIGNMENT>` (course, title, Moodle id when known); the
folder to write `<SOURCE>` (outside OneDrive; create it).

1. **Read every page** of the file with the Read tool, page by page (`pages`), as images. Never trust extracted PDF
   text for Hebrew (it comes out reversed) or for formulas.
2. **Write `<SOURCE>\פדגוגי\Rubric.md`**: the whole rubric in Markdown, in its own order and wording.
   - Every table as a Markdown table, every row, every number.
   - Math in `$...$`.
   - Headings by question and section.
   - Every general rule, note and fixed wording (« ... ») as written.
   - Nothing summarized, nothing added. If a word or number is unclear, write `[?]` and list it.
   - First, a table "| שאלה | נק' |" with the points of every question (the grading reads points from it).
3. **Write `<SOURCE>\Assignment details.json`**:
   `{"title": ..., "course_title": ..., "max_grade": <total>, "questions": [...as the rubric numbers them...],
   "rubric": {"questions": [{"label": "8א", "points": 7}, ...], "notes": "see פדגוגי/Rubric.md"}}`
   - One entry per section that has its own points, with the labels exactly as in the rubric. Points must add up to
     the total the rubric states.
   - If the rubric states a Moodle-grade rule ("by questions handed in"), add
     `"moodle_grade": {"basis": "submission", "per_question": "any"}`, or `"share"` when it counts sections.
4. **Check before you finish:**
   - The points table sums to the total.
   - Every section in the rubric is in `questions`.
   - Every error-table row of the PDF is in Rubric.md: count rows per section, both in the PDF and in your file.

**Reply in Hebrew, at most 8 lines:**
- the points table (question: points, and the total);
- how many sections and error rows were transcribed;
- every `[?]`;
- anything in the PDF that the grading cannot use.
