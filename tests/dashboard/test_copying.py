"""The site's "העתקות" page: POST /api/copying runs copying/check.py in the background, the state shows the pairs."""
from __future__ import annotations

import time

from moodle import paths

from tests.dashboard.helpers import BODY, COURSE, HDR, HW, call


def wait_done(port):
    for _ in range(300):
        status, job = call(port, "GET", "/api/copying")
        if not job["running"]:
            return job
        time.sleep(0.05)
    raise AssertionError("the copying check never finished")


def copying_of(port):
    _, state = call(port, "GET", "/api/state")
    return next(a for a in state["assignments"] if a["folder"] == HW)["copying"]


def test_copying_check_through_the_site(root, server):
    a = root / COURSE / HW
    (a / paths.TO_GRADE / "0003.pdf").write_bytes((a / paths.TO_GRADE / "0001.pdf").read_bytes())
    assert copying_of(server) is None  # not checked yet

    status, job = call(server, "POST", "/api/copying", BODY, HDR)
    assert status == 202
    job = wait_done(server)
    assert not job["error"] and job["total"] == 4

    c = copying_of(server)
    pair = next(p for p in c["pairs"] if (p["a"], p["b"]) == ("0001", "0003"))
    assert pair["level"] == "strong" and "file" in {r["kind"] for r in pair["reasons"]}
    assert not any(p["a"] == p["b"] for p in c["pairs"])  # 0002 and 0002-2 are one submission
    assert c["checked"] == 3 and not c["stale"]

    (a / paths.TO_GRADE / "0004.pdf").write_bytes(b"%PDF-1.4 new")
    assert copying_of(server)["stale"]


def test_copying_check_needs_a_known_assignment(root, server):
    status, body = call(server, "POST", "/api/copying", {"course": COURSE, "assignment": "nope"}, HDR)
    assert status == 404
    status, _ = call(server, "POST", "/api/copying", BODY)  # no X-Assignment-Checker header
    assert status == 403
