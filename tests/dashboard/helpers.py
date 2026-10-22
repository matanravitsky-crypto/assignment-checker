"""Constants and helpers shared by the dashboard tests (the fixtures are in conftest.py)."""
from __future__ import annotations

import csv
import http.client
import json

from moodle import paths

COURSE, HW, MID = "Linear Algebra", "Assignment 0 - Sets and Complex Numbers", "3438636"
NAMES = {"1001": "נועה כהן", "1002": "איתי לוי", "1003": "מאיה מזרחי", "2000": "יונתן פרץ"}


def write_key(a_dir, rows):
    with (a_dir / paths.KEY).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["number", "anon_file", "participant_id", "original_folder", "original_file"])
        w.writeheader()
        w.writerows(rows)


def call(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    h = {"Host": f"localhost:{port}", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    if data:
        h["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=h)
    r = conn.getresponse()
    raw = r.read()
    return r.status, (json.loads(raw) if r.getheader("Content-Type", "").startswith("application/json") else raw)


HDR = {"X-Assignment-Checker": "1"}
BODY = {"course": COURSE, "assignment": HW}


def mark(root, *numbers):
    """A small marked PDF per number in MARKED, written after the submissions (so it is the newer one)."""
    for n in numbers:
        (root / COURSE / HW / paths.MARKED / f"{n}.pdf").write_bytes(b"%PDF-1.4 marked " + n.encode())


def hw(state):
    """The tests' one real assignment in the dashboard state (the other courses' assignments are empty slots)."""
    return next(a for a in state["assignments"] if a["folder"] == HW)
