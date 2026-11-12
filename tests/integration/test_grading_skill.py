"""grading/ taken out to a skill, exercise-grader (tools/extract_skill.py, docs/Modularity.md): the skill holds the part,
activity_log and only the core it needs, runs with no repo on the path, and grades one submission exactly like the
system: the same page images go to Claude, and the same answer gives the same grade, points, marks and marked PDF."""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys

import pymupdf
import pytest

from grading import grade as grading
from moodle import paths
from tests.grading.test_grade import HW, answer, asg, no_real_claude, root  # noqa: F401  (fixtures)
from tests.grading.test_render_crop import scan_with_margins
from tests.sample_files import homework_pdf
from tools import extract_skill, modules as M

# the return to Moodle: grading must not take it out to the skill (grade_edit.connect_moodle_table)
RETURN = {"moodle.moodle_table", "moodle.upload", "moodle.anonymize", "moodle.pull_check", "moodle.send",
          "moodle.send_grades", "moodle.claude_driver"}
# on the scan's ink (thousandths of the cropped image Claude sees), on the photo, and one on an empty corner
MARKS = [{"page": 1, "x0": 300, "y0": 400, "x1": 700, "y1": 460, "text": "חסר נימוק"},
         {"page": 2, "x0": 60, "y0": 60, "x1": 900, "y1": 200, "text": "לא נכון"},
         {"page": 2, "x0": 950, "y0": 950, "x1": 990, "y1": 990, "text": "אין כאן כתב"}]


def run_skill(skill, *args, cwd):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "ASSIGNMENT_CHECKER_ROOT", "ASSIGNMENT_DATA")}
    env["PYTHONIOENCODING"] = "utf-8"
    # -I: no PYTHONPATH, no user site, no current folder: only the skill's own scripts/ (run.py puts it on the path)
    return subprocess.run([sys.executable, "-I", str(skill / "scripts" / "run.py"), *map(str, args)], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)


def files(folder) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def pixels(pdf: bytes) -> list[bytes]:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return [page.get_pixmap(dpi=40).samples for page in doc]


@pytest.fixture
def submission(root):
    """0004: a phone scan with white margins (cropped before Claude sees it, so the marks are mapped back) and a photo
    of a page as its second file (0004-2.png)."""
    a = asg(root)
    (a.submissions / "0004.pdf").write_bytes(scan_with_margins())
    with pymupdf.open(stream=homework_pdf("x", HW, pages=1), filetype="pdf") as doc:
        (a.submissions / "0004-2.png").write_bytes(doc[0].get_pixmap(dpi=72).tobytes("png"))
    return a


def test_the_skill_takes_grading_activity_log_and_only_the_core():
    taken = {M.module_name(f) for f in extract_skill.files_for("grading")}
    assert {M.part_of(m) for m in taken} == {"grading", "activity_log", "moodle"}
    assert {m for m in taken if M.part_of(m) == "moodle"} <= set(M.CORE)
    assert not taken & RETURN
    assert {"grading.one_submission", "grading.grade", "grading.render", "moodle.paths"} <= taken


def test_the_skill_runs_alone_and_grades_like_the_system(tmp_path, submission):
    a = submission
    skill = extract_skill.build("grading", tmp_path / "skills" / "exercise-grader")
    assert (skill / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: exercise-grader\n")
    assert (skill / "scripts" / "install.ps1").is_file()  # a teammate who gets it as a ZIP installs it with this
    built = {p.relative_to(skill / "scripts").parts[0] for p in (skill / "scripts").rglob("*.py")}
    assert built == {"grading", "activity_log", "moodle", "run.py"}  # nothing of the dashboard, stats, datastore...
    assert extract_skill.stale(skill) == []
    reply = answer(points=(20, 15, 22, 20, 10), marks=MARKS)  # 22 > 20: cut to the rubric and flagged, like the system

    # the system: grading 0004 of the assignment, with Claude answering `reply`
    requests = []
    rep = grading.grade_assignment(a.dir, ["0004"], ask=lambda req: requests.append(req) or reply, parallel=1)
    assert rep.graded == ["0004"]
    sent = [base64.b64decode(b["source"]["data"]) for b in requests[0]["messages"][0]["content"] if b["type"] == "image"]
    row, note = grading.read_grades(a.dir)["0004"], grading.read_notes(a.dir, "0004")
    marked = (a.dir / paths.MARKED / "0004.pdf").read_bytes()
    before = files(a.dir)

    # the skill, from a folder that is not the repo, on the same files and the same answer
    work, out_pdf = tmp_path / "work", tmp_path / "Desktop" / "עבודות בדוקות" / "0004 - graded.pdf"
    got = run_skill(skill, "rubric", a.dir, cwd=tmp_path)
    assert got.returncode == 0, got.stderr
    rubric = json.loads(got.stdout)
    assert [q["points"] for q in rubric["questions"]] == [20] * 5
    assert rubric["context"] == grading.context_text(grading.load_context(a.dir, send_solution=False))
    got = run_skill(skill, "prepare", work, *grading.submission_files(a.dir)["0004"], cwd=tmp_path)
    assert got.returncode == 0, got.stderr
    pages = json.loads(got.stdout)["pages"]
    assert [open(p["image"], "rb").read() for p in pages] == sent  # exactly the images the system sends Claude
    assert pages[0]["clip"] is not None  # the scan was cropped
    rules = run_skill(skill, "rules", cwd=tmp_path)
    assert rules.returncode == 0 and rules.stdout.startswith(grading.SYSTEM)
    (work / "answer.json").write_text(reply, encoding="utf-8")
    got = run_skill(skill, "mark", work, a.dir, work / "answer.json", out_pdf, cwd=tmp_path)
    assert got.returncode == 0, got.stderr
    summary = json.loads(got.stdout)

    assert summary["grade"] == float(row["grade"]) == 85
    assert [q["points"] for q in summary["questions"]] == note["points"] == [20, 15, 20, 20, 10]
    assert summary["review"] == note["review"] == row["review"] and "נחתך למחוון" in summary["review"]
    assert summary["review_kind"] == note["review_kind"] == "uncertain"
    assert summary["marks"] == note["marks"] and len(summary["marks"]) == 2
    assert summary["notes_moved_to_summary"] == ["עמוד 2: אין כאן כתב"]
    assert summary["output"] == str(out_pdf.resolve()) and out_pdf.with_suffix(".json").is_file()
    assert pixels(out_pdf.read_bytes()) == pixels(marked)  # the same marked PDF, page by page
    assert files(a.dir) == before  # the skill wrote nothing into the assignment folder

    again = run_skill(skill, "mark", work, a.dir, work / "answer.json", out_pdf, cwd=tmp_path)
    assert json.loads(again.stdout)["output"].endswith("0004 - graded (2).pdf")  # never overwrites a graded file


def test_the_skill_never_loads_code_from_the_repo(tmp_path):
    skill = extract_skill.build("grading", tmp_path / "exercise-grader")
    probe = ("import runpy, sys; sys.argv = ['run.py', 'rules']\n"
             "try:\n    runpy.run_path(sys.argv_path, run_name='__main__')\nexcept SystemExit:\n    pass\n"
             "import json; print(json.dumps(sorted({m.__file__ for m in list(sys.modules.values())"
             " if getattr(m, '__file__', None) and m.__name__.split('.')[0] in ('grading', 'moodle', 'activity_log')})))")
    probe = probe.replace("sys.argv_path", repr(str(skill / "scripts" / "run.py")))
    out = subprocess.run([sys.executable, "-I", "-c", probe], cwd=tmp_path, capture_output=True, text=True,
                         encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=120)
    loaded = json.loads(out.stdout.strip().splitlines()[-1])
    assert loaded and all(str(skill) in f for f in loaded), loaded
    assert any(f.endswith("one_submission.py") for f in loaded)
