"""GET /api/integrity and POST /api/integrity/fix: the doctor through the dashboard, numbers only."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from urllib.parse import quote

from moodle import grades, lock, paths

from tests.dashboard.helpers import COURSE, HDR, HW, call


def test_integrity_lists_every_assignment_and_filters_to_one(root, server):
    a = root / COURSE / HW
    grades.write_file(a / paths.GRADES_BY.format("מתן"), {"0001": {"number": "0001", "grade": "abc", "points": "", "approved": "", "review": "",
                                                                   "graded_at": "2026-11-01T10:00:00", "graded_by": "מתן"}})
    status, data = call(server, "GET", "/api/integrity", headers=HDR)
    assert status == 200 and isinstance(data, list)
    la = next(r for r in data if r["folder"] == HW)
    assert la["summary"]["reject"] >= 1 and any(p["code"] == "grade_not_numeric" and p["number"] == "0001" for p in la["problems"])
    status, one = call(server, "GET", f"/api/integrity?course={quote(COURSE)}&assignment={quote(HW)}", headers=HDR)
    assert status == 200 and len(one) == 1 and one[0]["folder"] == HW
    status, _ = call(server, "GET", f"/api/integrity?course={quote(COURSE)}&assignment=Nope", headers=HDR)
    assert status == 404
    text = json.dumps(data, ensure_ascii=False)
    key = (a / paths.KEY).read_text(encoding="utf-8-sig")
    for line in key.splitlines()[1:]:
        _, _, pid, folder, *_ = line.split(",")
        assert pid not in text and folder.split("_")[0] not in text


def test_fix_is_a_dry_run_by_default_and_repairs_on_request(root, server):
    a = root / COURSE / HW
    stuck = a / paths.PULL_LOCK
    stuck.write_text("דנה (PC) pid=5", encoding="utf-8")
    t = (datetime.now() - timedelta(minutes=lock.LOCK_MINUTES + 2)).timestamp()
    os.utime(stuck, (t, t))
    body = {"course": COURSE, "assignment": HW}
    status, out = call(server, "POST", "/api/integrity/fix", body, HDR)
    assert status == 200 and out["dryRun"] is True and len(out["done"]) == 1 and stuck.exists()
    status, out = call(server, "POST", "/api/integrity/fix", {**body, "dryRun": False}, HDR)
    assert status == 200 and out["dryRun"] is False and not stuck.exists()
    assert "stale_lock" not in out["report"]["fixable"]
    status, out = call(server, "POST", "/api/integrity/fix", {}, HDR)
    assert status == 400
