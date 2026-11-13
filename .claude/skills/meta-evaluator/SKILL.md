---
name: meta-evaluator
description: מבקר-על לבדיקה ולמחוון (Meta-Evaluator, QA of the grading). Audits works the system already graded - the grades, the comments, the boxes, notes and ✓/✗ on the page - against the rubric and the page itself, verifies its own findings, and returns a numbered report of improvements for the rubric (R1..Rn) and for the grader (G1..Gn); then, only on the user's word, implements the approved ones and measures by re-grading whether works got closer to the right grade. Use when someone says "סרוק N עבודות בדוקות", "בקרת איכות לבדיקה", "תבדוק את הבדיקה", "מבקר-על", "עוד סבב", "סבב נוסף", "מה לא טוב בבדיקה", "הטמע R2, G5", "רוץ על כל המחוונים", "meta-evaluator", "audit the grading". Not for building a rubric (rubric-builder) or grading one work (exercise-grader).
---

# Meta-Evaluator: an audit loop on the grading, that checks itself

**The loop (Ori, 2026-11-13):** scan graded works silently → find what is wrong → **a short self-improvement loop**
on everything the user already asked for → a report → the user decides only what is new. Write everything the user
reads in Hebrew.

Two kinds of items, and they are handled differently:
- **Inside what the user asked for** (grading quality: right grade, rubric rows, consistency between works; marking:
  boxes, notes, ✓/✗, the summary page; rubric wording without points; cost no higher than today; speed): improved
  inside the loop, without asking per item. Its quota: 75% quality, 15% cost, 10% time, and **no change may raise the
  cost per work** (a costlier change must pay for itself elsewhere in the same iteration).
- **New ideas** the user never raised (a new feature, a new workflow, another model or tool, anything that changes what
  the system is): never implemented. At most 3, in the report's "הצעות חדשות", each thought through: why, what it
  costs, the risk, how it would be tested. An idea that does not survive that thinking is left out.

**The bounded loop** (Step 6): at most 3 iterations per round; each one = implement the confirmed items → re-grade
offline (`offline.py`, never the shared folder) only the works they target → `compare` + re-audit → keep or undo.
Stop early when an iteration brings no measured gain. Budget per iteration: at most 10 works (~$12), said in chat
before it starts. Still gated on the user: changes of points (the TA), merge to main, and anything written to the
shared folder (re-grading its works, rubric delivery).

**It checks itself three times:** (1) every claim that something is wrong goes to a verifier agent that sees only the
claim and the page, and only confirmed claims reach the report (`brief-verify.md`); (2) the report is linted by a
script (`me.py check-report`); (3) every implemented change is measured by re-grading the works it should fix against
the auditors' target grades (`me.py compare`), and re-audited when it is about the page. A change that moves works
away from the right grade is undone.

## Where things are
| What | Where |
|---|---|
| Scripts | `scripts/me.py` (one command per step, no Claude, no tokens): `sample`, `mechanical`, `backup`, `render`, `targets`, `claims`, `tally`, `compare`, `check-report`. Run from the repo root: `python ".claude/skills/meta-evaluator/scripts/me.py" <cmd> <moodle id> --round <name>` |
| A round's folder | `~/.meta-eval/<id>/<round>/` (the script refuses the repo and OneDrive: student pages). `sample.json`, `mechanical.json`, `pages/NNNN/pNN.jpg`, `logs/log-NNNN.md`, `targets.json`, `verify-input.json`, `verify.json`, `tally.json`, `before/`, `compare.json`. Round names: `batch-1`, `round-2`, ... |
| Agent briefs | `references/brief-audit.md` (first look), `brief-recheck.md` (after a change), `brief-verify.md` (the verifier) |
| Report and implementation | `references/report-and-implement.md`: the report's parts, where each kind of item goes, the measurement |
| The grading under audit | `grading/grade.py` (`SYSTEM`, marking), `grading/locate.py` (zoom pass), `grading/render.py`; the rubric skill `rubric-builder` (`rubric.json` → `Rubric.md` + PDF, `assets/universal-rules.json` = "כללים לכל מחוון") |
| Earlier rounds | `docs/Meta-evaluator plan.md`, `docs/Meta-evaluator report - *.md` |

## Hard rules
- **Privacy:** works by 4-digit number only. Never open the key table or the originals, never write a name or ID
  (agents' briefs say so too). Student pages live only in `~/.meta-eval`.
- **Never pull, never make a new sample of submissions on your own** (memory: sample size is the user's call). The
  user names the assignment and N ("סרוק 20 עבודות בדוקות של הגשה 0"); with no N, ask once.
- **Re-grading costs:** about $1.1 a work (Opus) + $0.1 (zoom pass), counted against the subscription. Say how many
  and the cost before a re-grade; re-grade only works of a round's sample, and back them up first (`me.py backup`).
  Re-grading writes the shared folder's grades and marked PDFs: say so in the report.
- **Points are the TA's:** a rubric item that changes points is marked ⚠ and never implemented without the TA's word.
- **Token economy:** agents get only their works and the files they need; ~5 works per agent; pages are read once.

## Step 0 (when asked): grade fresh works without saving them anywhere
For works nobody graded yet ("תבדוק 20 עבודות חדשות מהגשה 1 שלא ישמרו בשום מקום"): the system's engine
(`grade.grade_one` + the zoom pass, as the exercise-grader skill uses it) writes only into the round folder:
```
python ".claude/skills/meta-evaluator/scripts/offline.py" <id> --round <R> --n 20
```
It writes `R/notes/`, `R/marked/`, `R/grades.json` and `R/usage.jsonl` (cost, turns and seconds per work). No grade,
note, marked PDF, claim, usage line or statistic reaches the shared folder: a fingerprint of the assignment folder
and the data folder's files before and after proves it (`R/offline-check.json`). Grading by another computer or run at
the same time shows there too, so say whose it is. Every later command reads an offline round from its own folder.
Skip `sample`, because offline already picked the works, spread over submission sizes.

## Step 1: sample and mechanical pass
```
python ".claude/skills/meta-evaluator/scripts/me.py" sample <id> --round <R> --n <N> [--fresh] [--include 0443]
python ".claude/skills/meta-evaluator/scripts/me.py" mechanical <id> --round <R>
python ".claude/skills/meta-evaluator/scripts/me.py" render <id> --round <R>
```
`sample` takes a third from each third of the grades, plus works in the manual queue, the most marked ones and any the
user named; `--fresh` skips works an earlier round audited. `mechanical` runs over every graded work (not only the
sample): tags with different deductions, deductions with no tag, grader words in student text, box heights, the
review rate, deductions per section. Read its summary; it tells the agents where to look.

## Step 2: audit (agents, silent)
One general-purpose agent per ~5 works, all launched in one message, each with `brief-audit.md` and the paths filled
in (A, R) — or `brief-recheck.md` (and P, the earlier round) when the works were audited before and re-graded since.
Each writes `R\logs\log-NNNN.md` and a ≤12-line summary. Don't read their transcripts.

## Step 3: verify (the skill checks its auditors)
```
python ".claude/skills/meta-evaluator/scripts/me.py" claims <id> --round <R> --max 40
```
Then one agent with `brief-verify.md` (sonnet is enough for boxes and notes; opus when the list is mostly about
mathematics or rubric rows) writes `R\verify.json`. Then:
```
python ".claude/skills/meta-evaluator/scripts/me.py" targets <id> --round <R>
python ".claude/skills/meta-evaluator/scripts/me.py" tally <id> --round <R>
```
A claim the verifier REJECTED never reaches the report; UNSURE ones may, marked as such. When fewer than 70% of the
checked claims are confirmed, say so first in the report: the auditors misread, and their unchecked findings are weak.

## Step 4: across the works (you)
From the logs, `tally.json`, `mechanical.json`: grading drift (one tag, several prices), length bias (grade by page
count), rubric loopholes (NO_RUBRIC_ROW and TWO_ROWS grouped by section), double penalties, the manual queue against
5-6%, and anything systematic on the page (boxes, notes, circles, the summary page). Read 2-3 page images yourself for
the most important claims before you rely on them.

## Step 5: sort the confirmed findings
Every confirmed finding becomes an item R (rubric) or G (grader), sorted into one of three:
- **Loop**: inside what the user asked for → Step 6 implements it.
- **Gated**: points, merge, or the shared folder → waits for the user's word.
- **New**: "הצעות חדשות", at most 3, each thought through → proposals only.

## Step 6: the bounded loop (at most 3 iterations)
Each iteration has three steps.
1. **Implement the loop items** where `report-and-implement.md` says.
   - Code goes on the round's branch, with tests and `python -m pytest`.
   - A rule for every rubric goes to `universal-rules.json`.
   - A rubric wording for one assignment is prepared in a local copy of its `rubric.json`. Delivering it is gated.
2. **Re-grade offline** (`offline.py --numbers ...`) only the works the items target, at most 10.
   - Then `me.py compare --against <the round with targets>`.
   - Re-audit with `brief-recheck.md` when the change is about the page.
3. **Keep or undo.**
   - Keep what moved works closer or fixed confirmed page problems.
   - Undo what moved works further, made a new HALLUCINATION/MISSED, or raised the cost per work.

**Noise first:** the same work graded twice moves 1-4 points (LA0 round 2: 13 of 15 works). A 1-point move is not a
gain or a loss by itself. A gain counts only when it is larger than that work's run-to-run spread, or when it fixes a
confirmed finding.

## Step 7: the report, and stop
Write the report as `references/report-and-implement.md` says, run `me.py check-report`, and fix it until it passes.
In chat, keep it short:
- what the loop changed, with before/after numbers and the cost per work;
- what waits for a word;
- "הצעות חדשות", if there are any.

Then **stop**. Commit, push and PR are pre-approved when a task is done (memory). Merging is the user's call. The next
round starts at Step 1 with `--fresh`, or at Step 2 on the same works.

## "רוץ על כל המחוונים והעבודות"
Only after an explicit go. Rules for every rubric are already everywhere through `universal-rules.json`. Per
assignment with a `rubric.json`: rebuild and deliver through rubric-builder (no points changes). Re-grading
everything is the team's call (cost, and grades already sent to Moodle): propose it with the number of works and the
cost, never start it unasked. End with a summary of what changed where.
