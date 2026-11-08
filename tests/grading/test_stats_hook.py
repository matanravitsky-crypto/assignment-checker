"""Grading and the manual approval update the statistics database (stats/) by themselves."""
from __future__ import annotations

import json

from grading import grade as grading
from moodle import paths
import stats

from tests.grading.test_grade import asg, detailed, root  # noqa: F401  (fixtures and helpers of the grading tests)


def stats_file(root):
    a = asg(root)
    return a.dir.parent.parent / paths.STATISTICS / a.dir.parent.name / "Assignment 0.json"


def test_grading_writes_the_statistics_and_approval_updates_them(root):
    a = asg(root)
    rep = grading.grade_assignment(a.dir, ask=lambda req: detailed(review="שאלה 8 לא נמצאה", kind="missing", unsure=(4,)), parallel=1)
    f = stats_file(root)
    assert f.is_file()
    s = json.loads(f.read_text(encoding="utf-8"))
    assert s["counts"]["graded"] == len(rep.graded) and s["counts"]["needs_review"] == len(rep.graded)
    assert s["counts"]["review_kinds"] == {"missing": len(rep.graded)} and s["counts"]["approved"] == 0
    assert s["per_question"][1]["mistakes"][0]["text"] == "חסר נימוק"
    assert stats.is_fresh(a.dir, s)
    n = rep.graded[0]
    grading.save_review(a.dir, n, [20, 15, 20, 20, 10], ["", "", "", "", ""], "מאושר", by="מתן")
    s2 = json.loads(f.read_text(encoding="utf-8"))
    assert s2["counts"]["approved"] == 1 and s2["counts"]["needs_review"] == len(rep.graded) - 1
    assert s2["graders"]["by"][0]["graded"] >= 1


def test_a_statistics_failure_does_not_stop_the_grading(root, monkeypatch, capsys):
    a = asg(root)
    monkeypatch.setattr(stats, "build", lambda *args, **kw: (_ for _ in ()).throw(RuntimeError("disk full")))
    rep = grading.grade_assignment(a.dir, ask=lambda req: detailed(), parallel=1)
    assert rep.graded and "disk full" in capsys.readouterr().err
    assert not stats_file(root).exists()
