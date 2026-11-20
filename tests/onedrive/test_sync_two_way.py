"""onedrive/sync.js in both directions (`plan2`, 2026-11-20): what goes up, what comes down, and what is left alone.

On a Mac the OneDrive app can't sync the lecturer's folder (the team are guests in BGU, and BGU's MFA prompt never shows
in the sync app), so the browser tab also brings down what is new in OneDrive. `base` is what this computer synced
last time, per file: with it the plan knows which side changed. Loaded in Node like test_sync_plan.py."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="needs Node.js")

SCRIPT = Path(__file__).resolve().parents[2] / "onedrive" / "sync.js"
HARNESS = """
const fs = require("fs");
const el = () => ({ style: {}, remove() {}, click() {}, querySelector: () => el(), appendChild() {} });
global.window = {};
global.document = { getElementById: () => null, createElement: () => el(), body: { appendChild() {} } };
eval(fs.readFileSync(process.argv[1], "utf8"));
const a = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(window.__ecsPlan2(a.local, a.remote, a.base, a.opts)));
"""

A = "Assignment 0"
T = 1_793_740_000_000
HOUR = 3_600_000
NOW = T + 100 * HOUR


def plan2(local, remote, base=None, **opts) -> dict:
    opts.setdefault("now", NOW)
    r = subprocess.run([NODE, "-e", HARNESS, str(SCRIPT)],
                       input=json.dumps({"local": local, "remote": remote, "base": base or {}, "opts": opts}),
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def loc(path, size=100, mtime=T):
    return {"path": path, "size": size, "mtime": mtime}


def rem(size=100, mtime=T):
    return {"size": size, "mtime": mtime}


def paths(items):
    return sorted(x["path"] if isinstance(x, dict) else x for x in items)


def test_an_empty_mac_downloads_everything_but_locks():
    remote = {f"{A}/1 - Submissions to grade/0001.pdf": rem(5000), f"{A}/Key - number to student.csv": rem(300),
              "README.txt": rem(50), f"{A}/Pull in progress.txt": rem(20, T)}
    p = plan2([], remote)
    assert paths(p["download"]) == sorted([f"{A}/1 - Submissions to grade/0001.pdf", f"{A}/Key - number to student.csv",
                                           "README.txt"])
    assert {d["expect"] for d in p["download"]} == {"none"} and {d["why"] for d in p["download"]} == {"new"}
    d = next(x for x in p["download"] if x["path"].endswith("0001.pdf"))
    assert d["size"] == 5000 and d["mtime"] == T


def test_with_base_only_the_side_that_changed_moves():
    g, n, s, c = f"{A}/Grades by נועה.csv", f"{A}/Grading notes/0001.json", f"{A}/Grades.csv", f"{A}/Copying check.json"
    base = {x: {"local": [100, T], "remote": [100, T + 60_000]} for x in (g, n, s, c)}
    local = [loc(g, 101, T + HOUR), loc(n), loc(s), loc(c, 120, T + HOUR)]
    # the same length after an edit (85 -> 90) is still a change, because the time moved
    remote = {g: rem(100, T + 60_000), n: rem(100, T + 2 * HOUR), s: rem(100, T + 60_000), c: rem(130, T + 2 * HOUR)}
    p = plan2(local, remote, base)
    assert paths(p["upload"]) == [g] and paths(p["download"]) == [n] and p["same"] == [s] and p["conflict"] == [c]
    assert p["download"][0]["expect"] == f"100:{T}"


def test_a_file_synced_once_and_then_removed_on_one_side_does_not_come_back():
    gone_there, gone_here = f"{A}/2 - Graded with comments/0003.pdf", f"{A}/Grading notes/0004.json"
    base = {x: {"local": [100, T], "remote": [100, T]} for x in (gone_there, gone_here)}
    p = plan2([loc(gone_there)], {gone_here: rem()}, base)
    assert p["upload"] == [] and p["download"] == []
    assert p["goneRemote"] == [gone_there] and p["goneLocal"] == [gone_here]


def test_without_base_the_newer_side_wins_and_a_tie_is_a_conflict():
    up, down, tie, same = (f"{A}/{x}" for x in ("up.csv", "down.csv", "tie.csv", "same.pdf"))
    local = [loc(up, 120, T + HOUR), loc(down, 120), loc(tie, 120, T + 60_000), loc(same)]
    remote = {up: rem(100), down: rem(100, T + HOUR), tie: rem(100), same: rem(100, T + HOUR)}
    p = plan2(local, remote)
    assert paths(p["upload"]) == [up] and paths(p["download"]) == [down] and p["conflict"] == [tie]
    # the same size, newer in OneDrive (that is how every upload looks afterwards): left alone and recorded as synced
    assert p["same"] == [same] and p["record"][same] == {"local": [100, T], "remote": [100, T + HOUR]}


def test_upload_only_keeps_the_old_behaviour():
    down, new_there = f"{A}/down.csv", f"{A}/only there.pdf"
    p = plan2([loc(down, 120)], {down: rem(100, T + HOUR), new_there: rem()}, down=False)
    assert p["download"] == [] and p["remoteNewer"] == [down]
    p = plan2([loc(f"{A}/new.pdf")], {}, up=False)
    assert p["upload"] == [] and p["localNewer"] == [f"{A}/new.pdf"]


def test_nothing_comes_down_into_an_assignment_that_is_being_pulled_elsewhere():
    """A synced computer uploads its lock to OneDrive: while it is fresh, the key and the submissions are in flux."""
    busy = {f"{A}/Pull in progress.txt": rem(20, NOW - 60_000), f"{A}/1 - Submissions to grade/0001.pdf": rem(),
            f"Assignment 1/Grading part 2 in progress.txt": rem(20, NOW - 2 * HOUR),
            f"Assignment 1/1 - Submissions to grade/0001.pdf": rem()}
    p = plan2([], busy)
    assert p["busy"] == [f"{A}/1 - Submissions to grade/0001.pdf"]
    assert paths(p["download"]) == ["Assignment 1/1 - Submissions to grade/0001.pdf"]  # a lock over 30 minutes old is stuck


def test_skipped_files_never_come_down():
    p = plan2([], {f"{A}/.DS_Store": rem(), f"{A}/Moodle download.zip": rem(), f"{A}/x.tmp": rem(), f"{A}/ok.pdf": rem()})
    assert paths(p["download"]) == [f"{A}/ok.pdf"]
