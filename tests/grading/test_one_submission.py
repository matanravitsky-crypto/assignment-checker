"""One submission outside the system (grading/one_submission.py, the exercise-grader skill): the rubric is read by
grading's own load_context whatever form it comes in, no points means no grade, and nothing is overwritten."""
from __future__ import annotations

import json

import pytest

from grading import __main__ as grading_cli, grade, one_submission as one
from moodle import paths
from tests.grading.test_grade import LABELS, RUBRIC, asg, no_real_claude, root, save_details  # noqa: F401 (fixtures)


def write(path, data) -> str:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def points(ctx) -> list[float]:
    return [q.points for q in ctx.questions]


def test_the_skills_rubric_json_is_read_like_the_systems_rubric(tmp_path):
    f = write(tmp_path / "rubric.json", {"title": "הגשה 0", "course": "בדידה", "max_grade": 50,
                                         "questions": [{"label": "שאלה 4", "points": 25, "criteria": "שני כיוונים",
                                                        "deductions": [{"text": "חסר נימוק", "points": 5}]},
                                                       {"label": "שאלה 5", "points": 75}], "notes": "בלי LaTeX"})
    ctx = one.context(f)
    assert (ctx.title, ctx.course, ctx.max_grade) == ("הגשה 0", "בדידה", 50)
    assert [(q.label, q.points) for q in ctx.questions] == [("שאלה 4", 25), ("שאלה 5", 75)]
    assert ctx.questions[0].deductions == [{"text": "חסר נימוק", "points": 5}] and ctx.rubric_text.startswith("בלי LaTeX")
    assert ctx.rubric_text.count("## כללים לכל מחוון") == 1  # like the system: every rubric gets the universal rules
    assert ctx.official_key is None
    out = one.rubric(f)
    assert out["total_points"] == 100 and out["read_first"] == [] and out["context"] == grade.context_text(ctx)


def test_no_points_for_a_question_means_no_grade(tmp_path):
    for data in ({"questions": [{"label": "שאלה 1", "points": 10}, {"label": "שאלה 2"}]}, {"questions": []}, [1, 2]):
        with pytest.raises(grade.NoRubric):
            one.context(write(tmp_path / "rubric.json", data))
    (tmp_path / "Rubric.pdf").write_bytes(b"%PDF-1.7 ...")
    with pytest.raises(grade.NoRubric):  # not JSON: Claude reads it and writes rubric.json
        one.context(tmp_path / "Rubric.pdf")
    with pytest.raises(OSError):  # a file that isn't there is not "no rubric"
        one.context(tmp_path / "missing.json")
    assert one.main(["rubric", write(tmp_path / "r.json", {"questions": [{"label": "שאלה 1"}]})]) == 2


def test_an_assignment_folder_and_its_details_file_alone_give_the_same_rubric(root):
    a = asg(root)
    folder, alone = one.context(a.dir), one.context(a.dir / paths.INFO)
    assert [(q.label, q.points) for q in alone.questions] == [(q.label, q.points) for q in folder.questions]
    assert points(folder) == [20] * 5 and alone.title == folder.title == "הגשה 0 - קבוצות ומרוכבים"
    assert alone.course == folder.course == "אלגברה לינארית להנדסה"
    assert one.context(a.dir).solution is None  # Claude reads the official solution itself (read_first)


def test_the_official_key_points_win_in_a_folder_and_in_a_details_file_alone(root):
    a = asg(root)
    d = json.loads((a.dir / paths.INFO).read_text(encoding="utf-8"))
    save_details(a, {**d, "official_key_points": {LABELS[0]: 30, LABELS[4]: 10}})
    (a.dir / paths.OFFICIAL_KEY_TEXT).write_text("המכוון: 30 לשאלה 11", encoding="utf-8")
    (a.dir / grade.SOLUTION).write_bytes(b"%PDF-1.7")
    folder = one.context(a.dir)
    assert points(folder) == [30, 20, 20, 20, 10] and folder.official_key.text == "המכוון: 30 לשאלה 11"
    assert one.rubric(a.dir)["read_first"] == [str((a.dir / n).resolve()) for n in (paths.OFFICIAL_KEY_TEXT, grade.SOLUTION)]
    alone = one.context(a.dir / paths.INFO)  # the key's points were saved only because a key was uploaded
    assert points(alone) == [30, 20, 20, 20, 10] and alone.official_key is not None
    assert one.rubric(a.dir / paths.INFO)["official_key"] is True


def test_the_marked_pdf_never_overwrites_a_file(tmp_path):
    first = tmp_path / "0001 - graded.pdf"
    assert one._free(first) == first
    first.write_bytes(b"x")
    assert one._free(first).name == "0001 - graded (2).pdf"
    (tmp_path / "0001 - graded (2).pdf").write_bytes(b"x")
    assert one._free(first).name == "0001 - graded (3).pdf"


def test_python_m_grading_runs_the_skills_commands_without_an_assignment(capsys, monkeypatch):
    monkeypatch.setattr(grading_cli.shared_folder, "use_for_commands",
                        lambda: pytest.fail("the skill's commands need no shared folder"))
    assert grading_cli.main(["rules"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(grade.SYSTEM) and '"review_kind"' in out
    assert grading_cli.main(["prepare"]) == 1  # not enough arguments: the usage, not an assignment id
    assert "python -m grading prepare" in capsys.readouterr().out
