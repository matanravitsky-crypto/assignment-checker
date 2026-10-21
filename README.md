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
| `docs/db.js` | Shared database (Supabase): GitHub sign-in, load, save, live updates, who is online |
| `docs/config.js` | Supabase project URL and publishable key. Empty means demo mode |
| `docs/styles.css` | Styles, light and dark |
| `supabase/schema.sql` | Tables, team-only access rules, live updates and file storage |

## Shared database

Team members sign in with GitHub and see and edit the same data, live. Only GitHub users on the team list can read or write; the rule is enforced in the database itself (Row Level Security), not just in the site. Visitors who don't sign in see the demo data.

Setup steps (Hebrew): [SETUP.md](SETUP.md).

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
