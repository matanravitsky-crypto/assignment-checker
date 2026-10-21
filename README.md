# Assignment Checker

A university project for checking homework in Discrete Math and Linear Algebra automatically.

The pipeline has three stages:

1. **Pull**: fetch every submission of an assignment from Moodle, with the student's details and files.
2. **Grade**: send each submission to Claude with the rubric, grading notes and official solution. Claude marks mistakes on the page, scores each question and writes feedback.
3. **Return**: upload the grade, feedback and the marked PDF back to Moodle.

## Dashboard (skeleton)

Live: https://matanravitsky-crypto.github.io/assignment-checker/

`docs/` holds a static, Hebrew (RTL) dashboard prototype. Everything runs in demo mode: no Moodle or Claude keys are connected yet.

| File | What it is |
|---|---|
| `docs/index.html` | Page shell and navigation |
| `docs/app.js` | Screens: dashboard, one page per stage (works, instructions, connection), marked-submission view |
| `docs/api.js` | The connection layer. Today it simulates the pipeline; later each function becomes a call to the backend (`/api/pull`, `/api/grade`, `/api/return`) without changing the screens |
| `docs/data.js` | Demo courses, assignments, rubrics and sample submissions |
| `docs/styles.css` | Styles, light and dark |

Each stage page has a free-text "instructions" tab: that text is the spec for what the backend should do in that stage.

Run it locally through any static server, for example:

```bash
npx http-server docs
```

## Python

**Current stage:** a basic Hello World skeleton.

- Python 3.10+

```bash
python main.py
python test_main.py
```
