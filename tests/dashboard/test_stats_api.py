"""GET /api/stats: the statistics database through the dashboard, and the site reloads when a statistics file changes."""
from __future__ import annotations

import json
from urllib.parse import quote

from dashboard import actions
from moodle import grades, paths
import stats

from tests.dashboard.helpers import COURSE, HDR, HW, call


def grade_two(root):
    a = root / COURSE / HW
    grades.write_file(a / paths.GRADES_BY.format("מתן"), {
        "0001": {"number": "0001", "grade": "90", "points": "", "approved": "", "review": "", "graded_at": "2026-11-01T10:00:00", "graded_by": "מתן"},
        "0002": {"number": "0002", "grade": "70", "points": "", "approved": "", "review": "לא בטוח", "graded_at": "2026-11-01T10:01:00", "graded_by": "מתן"},
    })
    return a


def test_api_stats_returns_every_assignment_and_filters_by_course(root, server):
    grade_two(root)
    status, data = call(server, "GET", "/api/stats", headers=HDR)
    assert status == 200 and isinstance(data, list)
    la = next(s for s in data if s["course"] == COURSE)
    assert la["key"] == f"{COURSE}/Assignment 0" and la["counts"]["graded"] == 2 and la["grade"]["mean"] == 80
    assert la["counts"]["needs_review"] == 1 and la["graders"]["by"] == [{"name": "מתן", "graded": 2}]
    # it was saved in Statistics/, and the file is what the next call returns
    f = root / paths.STATISTICS / COURSE / "Assignment 0.json"
    assert f.is_file() and json.loads(f.read_text(encoding="utf-8")) == la
    status, only = call(server, "GET", f"/api/stats?course={quote(COURSE)}", headers=HDR)
    assert status == 200 and [s["course"] for s in only] == [COURSE]
    status, none = call(server, "GET", "/api/stats?course=Nope", headers=HDR)
    assert status == 200 and none == []


def test_statistics_folder_is_not_a_course_and_its_changes_reload_the_site(root, server):
    grade_two(root)
    call(server, "GET", "/api/stats", headers=HDR)
    _, state = call(server, "GET", "/api/state", headers=HDR)
    assert paths.STATISTICS not in [c["folder"] for c in state["courses"]]
    sig = actions.changes(root)
    # another computer's statistics file arrives through OneDrive: the signature changes, so the site reloads
    f = root / paths.STATISTICS / COURSE / "Assignment 0.json"
    f.write_text(f.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert actions.changes(root) != sig


def test_nothing_in_api_stats_names_a_student(root, server):
    grade_two(root)
    _, data = call(server, "GET", "/api/stats", headers=HDR)
    text = json.dumps(data, ensure_ascii=False)
    key = (root / COURSE / HW / paths.KEY).read_text(encoding="utf-8-sig")
    for line in key.splitlines()[1:]:
        number, _, pid, folder, *_ = line.split(",")
        assert pid not in text and folder.split("_")[0] not in text and f'"{number}"' not in text


def test_a_broken_assignment_does_not_hide_the_others(root, server, monkeypatch):
    grade_two(root)
    real = stats.read

    def flaky(a):
        if a.name == HW:
            raise RuntimeError("boom")
        return real(a)
    monkeypatch.setattr(stats, "read", flaky)
    _, data = call(server, "GET", "/api/stats", headers=HDR)
    la = next(s for s in data if s["course"] == COURSE)
    assert la["error"] == "boom" and la["key"] == f"{COURSE}/Assignment 0"
