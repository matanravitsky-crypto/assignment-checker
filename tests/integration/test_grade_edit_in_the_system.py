"""עריכת ציון בתוך המערכת כולה: הדשבורד מחבר ל-grading את יומן האירועים (datastore/ledger.py) ואת מסד הנתונים
הסטטיסטי (stats/) בהפעלה (web_server.connect_stores), כי grading לא מייבא אותם בעצמו.

הועבר מ-tests/grading/test_grade_edit.py ב-2026-11-12 (tests/test_modularity.py): שם נבדקת העריכה של grading לבד.
"""
from __future__ import annotations

from urllib.parse import quote

import pytest

from dashboard import actions, web_server
from datastore import ledger
from grading import grade as grading, grade_edit
from tests.grading.test_grade_edit import FULL, graded
from tests.grading.test_grade import COURSE, HW, no_real_claude, root  # noqa: F401  (fixtures)
from tests.integration.test_grading_in_the_dashboard import call, server  # noqa: F401  (fixtures)


@pytest.fixture
def system():
    """המערכת כמו שהדשבורד מפעיל אותה: היומן והסטטיסטיקה מחוברים לעריכת ציונים, ומנותקים בסוף."""
    web_server.connect_stores()
    yield
    grade_edit.connect_database(None)
    grade_edit.connect_stats(None)

def test_the_dashboard_connects_the_ledger_and_an_edit_is_intent_then_done(root, server, system):
    a = graded(root)
    (db,) = [t for t in grade_edit.TARGETS if isinstance(t, grade_edit.DatabaseTarget)]
    assert db.enabled() and isinstance(db.store, ledger.LedgerStore)
    out = grading.save_review(a.dir, "0001", FULL, [], "", by="dana", reason="ערעור")
    assert out["updated"][0] == "database"
    acts = [e["action"] for e in ledger.history(a.dir, "0001")]
    assert acts == ["grade_set", "grade_edit_intent", "grade_edit"]
    assert ledger.incomplete_edits(a.dir) == [] and ledger.compare(a.dir) == []
    p = ledger.projection(a.dir)["0001"]
    assert p["grade"] == "100" and p["approved"] and p["by"] == "dana"
    # ה-API נותן גם את כל ההיסטוריה (לעמוד הבדיקה הידנית), לצד רשימת העריכות
    q = f"course={quote(COURSE)}&assignment={quote(HW)}&number=0001"
    st, got = call(server, "GET", f"/api/grade-log?{q}")
    assert st == 200 and [e["action"] for e in got["history"]] == acts
    assert [(e["from"], e["to"]) for e in got["entries"]] == [("85", "100")]
    assert all(e.get("grade") in (None, 85, "85") for e in got["history"] if e["action"] == "grade_set")


def test_the_server_asks_for_a_reason_and_shows_the_history(root, server):
    a = graded(root)
    body = {"course": COURSE, "assignment": HW, "number": "0001", "points": FULL, "comments": [], "feedback": ""}
    st, out = call(server, "POST", "/api/review", body)
    assert st == 422 and out["needReason"] and "סיבה" in out["error"]
    st, out = call(server, "POST", "/api/review", {**body, "reason": "ערעור"})
    assert st == 200 and out["grade"] == 100 and out["from"] == "85"
    q = f"course={quote(COURSE)}&assignment={quote(HW)}&number=0001"
    st, out = call(server, "GET", f"/api/grade-log?{q}")
    assert st == 200 and [(e["from"], e["to"], e["reason"]) for e in out["entries"]] == [("85", "100", "ערעור")]
    assert call(server, "GET", f"/api/grade-log?course={quote(COURSE)}&assignment={quote(HW)}&number=../1")[0] == 400
    assert call(server, "GET", f"/api/grade-log?course={quote(COURSE)}&assignment=..&number=1")[0] == 404
    assert actions.grade_history(root, COURSE, HW, "0001")[0]["to"] == "100"
    # ובעמוד "יומן פעילות" של האתר
    log = [r for r in actions.state(root)["assignments"][0]["log"] if "ציון עבודה 0001" in r["text"]]
    assert log and "85 ← 100: ערעור" in log[0]["text"] and log[0]["kind"] == "grade"


def test_an_edit_updates_the_statistics_database_in_the_drive_as_a_target(root, system):
    """מסד הנתונים הסטטיסטי (Statistics/ בתיקייה המשותפת) הוא יעד ברשימה: מתעדכן בכל עריכה ונרשם ב-updated."""
    import json

    import stats
    a = graded(root)
    path = stats.file_for(a.dir)
    assert path.is_file()  # the grading run built it: the statistics are connected to the end of a run too
    before = json.loads(path.read_text(encoding="utf-8"))
    out = grading.save_review(a.dir, "0001", FULL, [], "", by="dana (PC)", reason="ערעור")
    after = json.loads(path.read_text(encoding="utf-8"))
    assert out["updated"][-1] == "stats_db" and "not_updated" not in out
    assert before["counts"]["approved"] == 0 and after["counts"]["approved"] == 1
    assert stats.is_fresh(a.dir, after)  # משקף את קובץ הציונים אחרי העריכה
    assert grade_edit.history(a.dir, "0001")[-1]["updated"][-1] == "stats_db"


def test_a_statistics_failure_keeps_the_edit_and_is_logged(root, monkeypatch, system):
    import stats
    a = graded(root)
    monkeypatch.setattr(stats, "build", lambda *a_, **k: (_ for _ in ()).throw(OSError("OneDrive נעל את הקובץ")))
    out = grading.save_review(a.dir, "0001", FULL, [], "", by="x", reason="ערעור")
    assert out["grade"] == 100 and out["not_updated"] == ["מסד הנתונים הסטטיסטי בדרייב"]
    assert grading.read_grades(a.dir)["0001"]["grade"] == "100"  # הציון נשמר בכל השאר
    e = grade_edit.history(a.dir, "0001")[-1]
    assert e["action"] == "grade_edit" and e["not_updated"][0]["target"] == "stats_db" and "OneDrive" in e["not_updated"][0]["error"]
