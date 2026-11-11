"""onedrive/sync.js decides what to upload from a computer's local copy to the lecturer's OneDrive (`plan`).

Old test grading that was moved in OneDrive to "<assignment>/Old test grading/" (2026-11-03) must not come back from a
local copy that still has it in the old place; grading done after the move uploads as usual. The script runs in a
browser tab, so these tests load it in Node with a page that has just enough of a DOM, and call window.__ecsPlan."""
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
const { local, remote, snap, busy } = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(window.__ecsPlan(local, remote, snap || {}, busy || [])));
"""

A = "Assignment 0 - Propositional Logic"
MOVED = 1_793_740_000_000          # when the old grading was moved (the archive README's time), ms
BEFORE, AFTER = MOVED - 10 * 86_400_000, MOVED + 3_600_000


def plan(local: list[dict], remote: dict, snap: dict | None = None, busy: list[str] | None = None) -> dict:
    r = subprocess.run([NODE, "-e", HARNESS, str(SCRIPT)], input=json.dumps({"local": local, "remote": remote, "snap": snap, "busy": busy}),
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def f(path, mtime=BEFORE, size=100):
    return {"path": path, "size": size, "mtime": mtime}


ARCHIVED = {f"{A}/Old test grading/README.txt": {"size": 900, "mtime": MOVED},
            f"{A}/Old test grading/2 - Graded with comments/0001.pdf": {"size": 100, "mtime": BEFORE},
            f"{A}/2 - Graded with comments/README.txt": {"size": 226, "mtime": BEFORE}}


def uploaded(p):
    return sorted(x["path"] for x in p["upload"])


def test_old_grading_that_was_moved_in_onedrive_does_not_come_back():
    old = [f"{A}/2 - Graded with comments/0001.pdf", f"{A}/2 - Graded with comments/0002.pdf",
           f"{A}/Grading notes/0001.json", f"{A}/Who grades what/אורי.json",
           f"{A}/Grades by אורי.csv", f"{A}/Grades.csv", f"{A}/Grades - part 1.csv"]
    p = plan([f(x) for x in old], ARCHIVED)
    assert sorted(p["archived"]) == sorted(old) and p["upload"] == []


def test_grading_done_after_the_move_uploads_as_usual():
    new = [f"{A}/2 - Graded with comments/0001.pdf", f"{A}/Grading notes/0001.json", f"{A}/Grades by אורי.csv"]
    p = plan([f(x, mtime=AFTER, size=222) for x in new], ARCHIVED)
    assert uploaded(p) == sorted(new) and p["archived"] == []
    assert {x["why"] for x in p["upload"]} == {"new"}


def test_only_grading_files_are_held_back():
    # submissions, the key, a pull log and the README of the marked folder are not grading, whatever their age
    others = [f"{A}/1 - Submissions to grade/0070.pdf", f"{A}/Key - number to student.csv", f"{A}/Pull log.csv",
              f"{A}/Grading notes/sub/0001.json"]
    p = plan([f(x) for x in others] + [f(f"{A}/2 - Graded with comments/README.txt", size=226)], ARCHIVED)
    assert uploaded(p) == sorted(others) and p["archived"] == []
    assert p["same"] == [f"{A}/2 - Graded with comments/README.txt"]


def test_an_assignment_without_an_archive_uploads_old_grading_as_before():
    other = "Assignment 1"
    p = plan([f(f"{other}/2 - Graded with comments/0001.pdf"), f(f"{other}/Grades by אורי.csv")], ARCHIVED)
    assert uploaded(p) == [f"{other}/2 - Graded with comments/0001.pdf", f"{other}/Grades by אורי.csv"]
    assert plan([f(f"{A}/Grades by אורי.csv")], {})["upload"][0]["why"] == "new"


def test_a_file_still_in_its_place_in_onedrive_is_compared_as_usual():
    remote = {**ARCHIVED, f"{A}/Grades by אורי.csv": {"size": 100, "mtime": BEFORE}}
    p = plan([f(f"{A}/Grades by אורי.csv"), f(f"{A}/Grading notes/0009.json", mtime=AFTER)], remote)
    assert p["same"] == [f"{A}/Grades by אורי.csv"] and uploaded(p) == [f"{A}/Grading notes/0009.json"]


def test_files_inside_the_archive_upload_like_any_file():
    p = plan([f(f"{A}/Old test grading/Grading notes/0001.json")], ARCHIVED)
    assert uploaded(p) == [f"{A}/Old test grading/Grading notes/0001.json"] and p["archived"] == []


# ---------- שני הכיוונים: המחשב, הענן, ומה שני הצדדים היו בסנכרון הקודם (snap: {path: {l, ls, r, rs}}) ----------
def seen(l, ls, r=None, rs=None):
    return {"l": l, "ls": ls, "r": l if r is None else r, "rs": ls if rs is None else rs}


def test_a_file_only_in_onedrive_is_downloaded_but_not_the_keys_history_nor_a_lock():
    remote = {f"{A}/Grades by נועה.csv": {"size": 50, "mtime": AFTER}, f"{A}/Key history/2026.csv": {"size": 9, "mtime": AFTER},
              f"{A}/Pull in progress.txt": {"size": 9, "mtime": BEFORE}, f"{A}/Removed from OneDrive/x/y.txt": {"size": 1, "mtime": AFTER}}
    p = plan([], remote)
    assert [d["path"] for d in p["download"]] == [f"{A}/Grades by נועה.csv"] and p["download"][0]["why"] == "new"
    assert p["download"][0]["expect"] is None and p["upload"] == [] and p["remove"] == []
    assert sorted(p["skipped"]) == [f"{A}/Pull in progress.txt", f"{A}/Removed from OneDrive/x/y.txt"]
    assert f"{A}/Key history/2026.csv" in p["skipped"] or f"{A}/Key history/2026.csv" not in [d["path"] for d in p["download"]]


def test_a_file_the_cloud_had_last_time_and_lost_is_moved_aside_not_uploaded():
    path = f"{A}/2 - Graded with comments/0001.pdf"
    # המחשב לא נגע בו מאז: הועבר או נמחק בענן → Removed from OneDrive
    p = plan([f(path)], {}, {path: seen(BEFORE, 100)})
    assert [r["path"] for r in p["remove"]] == [path] and p["upload"] == [] and p["archived"] == []
    # המחשב כן שינה אותו מאז: עבודה חדשה, עולה
    p = plan([f(path, mtime=AFTER, size=120)], {}, {path: seen(BEFORE, 100)})
    assert uploaded(p) == [path] and p["remove"] == []
    # בלי סנכרון קודם: כמו פעם (עולה, או נעצר בגלל הארכיון)
    assert uploaded(plan([f(path, mtime=AFTER)], {})) == [path]
    assert plan([f(path)], ARCHIVED)["archived"] == [path]


def test_changed_on_one_side_only_goes_that_way_and_both_sides_is_a_conflict():
    path, snap = f"{A}/Assignment details.json", {f"{A}/Assignment details.json": seen(BEFORE, 100, BEFORE + 5000, 100)}
    same = plan([f(path)], {path: {"size": 100, "mtime": BEFORE + 5000}}, snap)
    assert same["same"] == [path]
    up = plan([f(path, mtime=AFTER, size=130)], {path: {"size": 100, "mtime": BEFORE + 5000}}, snap)
    assert uploaded(up) == [path] and up["upload"][0]["why"] == "changed"
    down = plan([f(path)], {path: {"size": 130, "mtime": AFTER}}, snap)
    assert [d["path"] for d in down["download"]] == [path] and down["download"][0] == {"path": path, "size": 130, "mtime": AFTER, "why": "changed", "expect": BEFORE}
    both = plan([f(path, mtime=AFTER, size=120)], {path: {"size": 130, "mtime": AFTER + 1000}}, snap)
    assert [c["path"] for c in both["conflict"]] == [path] and both["upload"] == both["download"] == []
    # התנגשות שאדם פתר: שני הצדדים זהים עכשיו, גם אם הסנכרון הקודם אומר אחרת
    solved = plan([f(path, mtime=AFTER, size=130)], {path: {"size": 130, "mtime": AFTER + 1000}}, snap)
    assert solved["same"] == [path] and solved["conflict"] == []


def test_without_a_previous_sync_the_newer_side_wins_and_the_cloud_never_overwrites_a_same_size_file():
    path = f"{A}/Grades.csv"
    assert uploaded(plan([f(path, mtime=AFTER, size=120)], {path: {"size": 100, "mtime": BEFORE}})) == [path]
    p = plan([f(path, mtime=BEFORE, size=100)], {path: {"size": 120, "mtime": AFTER}})
    assert [d["path"] for d in p["download"]] == [path] and p["download"][0]["keep"] is True  # the local copy is archived first
    # אותו גודל, הענן חדש יותר: לא נוגעים (כמו פעם). גודל שונה באותו זמן: התנגשות
    assert plan([f(path, mtime=BEFORE, size=100)], {path: {"size": 100, "mtime": AFTER}})["same"] == [path]
    assert [c["path"] for c in plan([f(path, size=100)], {path: {"size": 101, "mtime": BEFORE + 1000}})["conflict"]] == [path]


def test_an_assignment_being_graded_or_pulled_waits_for_the_next_round():
    other = "Assignment 1"
    local = [f(f"{A}/Grades by אורי.csv", mtime=AFTER), f(f"{other}/Grades by אורי.csv", mtime=AFTER)]
    p = plan(local, {f"{A}/Grading notes/0001.json": {"size": 5, "mtime": AFTER}}, {}, [A])
    assert sorted(p["held"]) == [f"{A}/Grades by אורי.csv", f"{A}/Grading notes/0001.json"]
    assert uploaded(p) == [f"{other}/Grades by אורי.csv"] and p["download"] == []
