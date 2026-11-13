# Brief: verify the auditors' claims (one agent, a list of claims)

Auditors read graded student works and made claims ("the grader missed X on page 3", "this box sits on the wrong
line", "this deduction has no rubric row"). An auditor can be wrong: misread handwriting, a rubric row it did not
find, a page it skimmed. You check each claim yourself, from the page and the rubric, without the auditor's reasoning:
you get the claim and where to look, nothing else. Be adversarial: a claim is CONFIRMED only when you see it yourself.

## Privacy
Never write a name or ID from a page. Works by their 4-digit number only. Modify no file except your output.

## Input
`R\verify-input.json`: a list of `{"id": "NNNN:<n>", "work": "NNNN", "tag": "...", "section": "...", "page": p,
"claim": "<one sentence>"}`. Pages: `R\pages\NNNN\pNN.jpg` (p01 = summary page; the student's page p is pNN with
NN = p + 1). Grading: `A\Grading notes\NNNN.json`. Rubric: `A\פדגוגי\Rubric.md`.

## For each claim
Look at the page (and zoom by reading the image again only if the claim depends on one symbol), and at the rubric row
when the claim is about one. Then:
- CONFIRMED: you see it, exactly as claimed.
- REJECTED: you see that it is not so (say what is there instead, in one sentence).
- UNSURE: the page does not settle it.

## Output: `R\verify.json`
`{"NNNN:<n>": {"verdict": "CONFIRMED|REJECTED|UNSURE", "why": "<one sentence>"}, ...}`, one entry per claim, nothing
else. Then a 3-line summary: how many of each verdict, and the auditor mistake you saw most.
