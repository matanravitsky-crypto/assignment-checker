"""חלוקת העבודות בצוות באתר: מי לקח מה, לקיחה והחזרה, והשם של הבודק."""
from __future__ import annotations

from moodle import claims, grades, paths
from dashboard import actions, settings

from tests.dashboard.helpers import BODY, COURSE, HDR, HW, call, hw


def test_state_shows_who_took_each_submission(root):
    a = root / COURSE / HW
    claims.take(a, ["0002"], who="אורי")
    st = actions.state(root)
    subs = {s["id"]: s for s in hw(st)["subs"]}
    assert subs["0002"]["claim"]["who"] == "אורי" and subs["0001"]["claim"] is None
    assert st["me"] == {"name": "מתן", "set": True}


def test_take_next_skips_what_others_took_and_what_is_graded(root, server):
    a = root / COURSE / HW
    claims.take(a, ["0001"], who="אורי")
    grades.write_file(grades.own_file(a, "אורי"), {"0002": {"number": "0002", "grade": "90"}})
    st, rep = call(server, "POST", "/api/claims", {**BODY, "next": 5}, HDR)
    assert st == 200 and rep["taken"] == ["0003"]
    assert {n: c["who"] for n, c in rep["claims"].items()} == {"0001": "אורי", "0003": "מתן"}
    assert rep["graded"] == ["0002"] and rep["me"] == "מתן"

    st, rep = call(server, "POST", "/api/claims", {**BODY, "take": ["0001", "0002", "9999"]}, HDR)
    assert rep["taken"] == ["0002"] and rep["others"] == {"0001": "אורי"}  # 9999 isn't a submission
    st, rep = call(server, "POST", "/api/claims", {**BODY, "release": ["0001", "0003"]}, HDR)
    assert rep["released"] == ["0003"]
    st, view = call(server, "GET", f"/api/claims?course={COURSE}&assignment={HW}".replace(" ", "%20"))
    assert st == 200 and {n: c["who"] for n, c in view["claims"].items()} == {"0001": "אורי", "0002": "מתן"}


def test_claims_requests_are_checked(root, server):
    assert call(server, "POST", "/api/claims", {**BODY, "take": ["0001"]})[0] == 403  # without the site's header
    assert call(server, "POST", "/api/claims", {**BODY, "take": ["../x"]}, HDR)[0] == 400
    assert call(server, "POST", "/api/claims", {**BODY, "next": -1}, HDR)[0] == 400
    assert call(server, "GET", "/api/claims?course=x")[0] == 400


def test_my_name_is_saved_on_this_computer_and_moves_my_claims(root, server, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REPO_DIR", tmp_path)  # לא נוגעים ב-.env האמיתי
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=x\nGRADER_NAME=old\n", encoding="utf-8")
    a = root / COURSE / HW
    claims.take(a, ["0001"])
    st, rep = call(server, "POST", "/api/me", {"name": "  מתן   רביצקי "}, HDR)
    assert st == 200 and rep == {"name": "מתן רביצקי", "set": True}
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "ANTHROPIC_API_KEY=x\nGRADER_NAME=מתן רביצקי\n"
    assert claims.read_all(a)["0001"]["who"] == "מתן רביצקי"
    assert not (a / paths.CLAIMS / "מתן.json").exists()
    assert call(server, "POST", "/api/me", {"name": "x" * 41}, HDR)[0] == 422
