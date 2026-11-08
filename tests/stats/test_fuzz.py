"""Try to break stats/compute.py: thousands of random assignments, hostile input, duplicates and conflict copies.

The number of random assignments comes from STATS_FUZZ_SEEDS (default 400). `STATS_FUZZ_SEEDS=100000 python -m pytest
tests/stats/test_fuzz.py` runs for a long time and must still be green.
"""
from __future__ import annotations

import json
import math
import os
import random
import string
import time
from pathlib import Path

import pytest

from moodle import grades, paths
from stats import compute as sc
import stats

SEEDS = int(os.environ.get("STATS_FUZZ_SEEDS", "400"))
HEBREW = "אבגדהוזחטיכלמנסעפצקרשת"
NAMES = ["נועה כהן", "איתי לוי", "מאיה מזרחי", "יונתן פרץ", "Dana Barak", "Ωmega Ünïcode"]
JUNK = [None, "", " ", "abc", "nan", "inf", "-inf", "1e400", "-5", "0", "100.5", "١٢", [], {}, True, 1e308, -0.0, "12;13", "‏", "😀"]


def strings(x) -> list[str]:
    """Every text value anywhere in the statistics (not the numbers)."""
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [t for v in x.values() for t in strings(v)]
    if isinstance(x, list):
        return [t for v in x for t in strings(v)]
    return []


def rnd_text(r: random.Random, k=12) -> str:
    return "".join(r.choice(HEBREW + " ∈∉{}∅n-יה,.") for _ in range(r.randint(1, k))).strip() or "טעות"


def rnd_questions(r: random.Random) -> list[dict]:
    qs = []
    for i in range(r.randint(0, 8)):
        pts = r.choice([0, 0.5, 5, 12, 20, 24, 25, 33.3, 50, 100, r.choice(JUNK)])
        deds = [{"text": rnd_text(r), "points": r.choice([0, 1, 2.5, 5, r.choice(JUNK)])} for _ in range(r.randint(0, 3))]
        if r.random() < 0.1:
            deds.append("not a dict")  # type: ignore[arg-type]
        qs.append({"label": r.choice([rnd_text(r), "", None, 7]), "points": pts, "deductions": deds})
    return qs


def rnd_points(r: random.Random, qs: list[dict]) -> str:
    if r.random() < 0.15:
        return r.choice(["", "abc", "1;2;x", "nan;1", "1e400;2", ";", "5"])
    n = len(qs) if r.random() < 0.85 else r.randint(0, 9)
    out = []
    for i in range(n):
        top = sc._num(qs[i].get("points")) if i < len(qs) else None
        top = top if top is not None and top > 0 else 20
        out.append(str(round(r.uniform(-2, top * 1.3) if r.random() < 0.1 else r.uniform(0, top), r.choice([0, 1, 2]))))
    return ";".join(out)


def rnd_rows(r: random.Random, qs: list[dict], max_grade) -> dict[str, dict]:
    rows = {}
    for i in range(r.randint(0, 60)):
        n = f"{r.randint(1, 1200):04d}" if r.random() < 0.95 else r.choice(["7", "abc", "0001 ", "٠٠٠١"])
        top = sc._num(max_grade) or 100
        grade = r.choice([str(round(r.uniform(0, top), r.choice([0, 1]))), str(top), "0", r.choice(JUNK)]) if r.random() < 0.9 else ""
        rows[n] = {"number": n, "grade": "" if grade is None else str(grade), "feedback": rnd_text(r, 40),
                   "points": rnd_points(r, qs),
                   "approved": r.choice(["", "", "", "אורי 2026-11-02 09:00", "yes", "לא", "0", "1"]),
                   "review": r.choice(["", "", "לא בטוח", "חסר עמוד"]),
                   "special": r.choice(["", "", "missing_page", "other_assignment", "garbage"]),
                   "graded_at": r.choice(["2026-11-01T10:00:00", "2026-11-02T10:00:00", "", "junk"]),
                   "graded_by": r.choice(["אורי", "מתן", "ori34 (OriLaptop)", "", " "])}
        if r.random() < 0.05:
            rows[n] = {k: v for k, v in rows[n].items() if k not in ("points", "special", "graded_by")}
    return rows


def rnd_note(r: random.Random, qs: list[dict]) -> dict | object:
    if r.random() < 0.05:
        return r.choice([None, [], "text", 5, {"mistakes": "not a list"}, {"mistakes": None}, {"unsure": "x"}])
    n = len(qs) if r.random() < 0.8 else r.randint(0, 9)
    mistakes = []
    for _ in range(n):
        if r.random() < 0.08:
            mistakes.append(r.choice([None, "text", 3, {"a": 1}]))
            continue
        texts = [rnd_text(r) for _ in range(r.randint(0, 3))]
        if texts and r.random() < 0.3:
            texts.append(texts[0])  # the same mistake twice in one work
        if r.random() < 0.05:
            texts.append(r.choice([None, 4, {"x": 1}, ""]))  # type: ignore[arg-type]
        mistakes.append(texts)
    d = {"mistakes": mistakes, "unsure": [r.choice([True, False, 1, 0, None, "x"]) for _ in range(r.randint(0, n + 1))],
         "review_kind": r.choice(["", "uncertain", "missing", "weird", None]), "comments": [rnd_text(r) for _ in range(n)]}
    if r.random() < 0.15:
        d["error"] = r.choice(["Claude refused", "boom", " "])
    if r.random() < 0.1:
        d["reviewed"] = {"by": "אורי", "at": "2026-11-02T09:00:00"}
    return d


def rnd_assignment(seed: int) -> dict:
    r = random.Random(seed)
    qs = rnd_questions(r)
    max_grade = r.choice([100, 100, 100, 50, 120, 0, None, "abc", -10, 7.5, 1e308, 1e-9, float("inf"), float("nan")])
    rows = rnd_rows(r, qs, max_grade)
    numbers = list(rows) + [f"{r.randint(1, 1200):04d}" for _ in range(r.randint(0, 10))]
    notes = {n: rnd_note(r, qs) for n in numbers if r.random() < 0.8}
    marked = {n for n in numbers if r.random() < 0.3} | ({f"{r.randint(1, 1200):04d}"} if r.random() < 0.3 else set())
    return dict(course=r.choice(["Linear Algebra", "Discrete Mathematics", "קורס"]),
                folder=r.choice(["Assignment 0", "Assignment 3 - Vectors", "Assignment 12 - X", "Assignment", "Other"]),
                moodle_id=r.choice(["3438636", 3438636, None, ""]), title=rnd_text(r, 30), max_grade=max_grade,
                questions=qs, rows=rows, notes=notes, submitted=r.choice([len(numbers), 0, 1078, r.randint(0, 2000)]),
                marked=marked, copying_pairs=r.choice([None, 0, 3]), computed_at="2026-11-08T12:00:00", computed_by="אורי")


def check_invariants(args: dict, s: dict) -> None:
    text = json.dumps(s, ensure_ascii=False, allow_nan=False)  # no NaN or inf anywhere
    assert json.loads(text) == s
    c, g = s["counts"], s["grade"]
    assert all(v >= 0 for v in c.values() if isinstance(v, int))
    assert c["pending"] == max(0, c["submitted"] - c["graded"])
    assert sum(c["review_kinds"].values()) >= c["needs_review"]
    assert c["approved"] <= c["graded"] and c["needs_review"] <= len(args["rows"])
    assert sum(g["histogram"]["counts"]) == g["n"] and len(g["histogram"]["counts"]) == sc.HISTOGRAM_BINS
    bins = g["histogram"]["bins"]
    assert bins[0]["from"] == 0 and bins[-1]["to"] == s["max_grade"]
    assert all(b["from"] < b["to"] for b in bins) and all(bins[i]["to"] == bins[i + 1]["from"] for i in range(len(bins) - 1))
    assert 0 < s["max_grade"] <= sc.MAX_GRADE_LIMIT
    for q in s["per_question"]:
        assert 0 <= q["points"] <= s["max_grade"]
        assert all(m["deduction"] is None or 0 <= m["deduction"] <= max(q["points"], 1) * 2 for m in q["mistakes"])
    if g["n"]:
        assert g["min"] <= g["median"] <= g["max"] and g["min"] <= g["mean"] <= g["max"]
        assert 0 <= g["pass_pct"] <= 100 and 0 <= g["full_marks"] <= g["n"]
        assert g["sd"] is None or g["sd"] >= 0
        assert g["min"] >= 0 and g["max"] <= s["max_grade"]
    else:
        assert g["mean"] is None and g["median"] is None and g["pass_pct"] is None and g["full_marks"] == 0
    assert g["out_of_range"] >= 0
    assert len(s["per_question"]) == len(args["questions"])
    keys = [q["key"] for q in s["per_question"]]
    assert len(set(keys)) == len(keys) and all(k.startswith(s["key"] + "/q") for k in keys)
    for q in s["per_question"]:
        assert isinstance(q["label"], str) and q["graded"] <= g["n"]
        for f in ("success_pct", "full_marks_pct", "zero_pct"):
            assert q[f] is None or 0 <= q[f] <= 100
        assert q["unsure"] <= q["graded"]
        texts = [m["text"] for m in q["mistakes"]]
        assert len(set(texts)) == len(texts) and all(t and isinstance(t, str) for t in texts)
        counts = [m["count"] for m in q["mistakes"]]
        assert counts == sorted(counts, reverse=True) and all(1 <= x <= g["n"] for x in counts)
        assert all(m["pct"] is None or 0 <= m["pct"] <= 100 for m in q["mistakes"])
        assert all(m["deduction"] is None or math.isfinite(m["deduction"]) for m in q["mistakes"])
    assert s["graders"]["count"] == len(s["graders"]["by"]) and all(x["name"].strip() for x in s["graders"]["by"])
    assert sum(x["graded"] for x in s["graders"]["by"]) <= g["n"] + len(args["rows"])
    # nothing that identifies a work: no submission number from the rows and no name inside any text value
    # (numbers in the output are counts and averages; a leak could only be a text)
    leaves = [t for t in strings(s) if t != s["computed_at"]]
    for n in args["rows"]:
        if n.strip().isdigit() and len(n.strip()) >= 4:
            assert not any(n.strip() in t for t in leaves), n
    for name in NAMES:
        assert name not in text


@pytest.mark.parametrize("seed", range(SEEDS))
def test_random_assignment_holds_the_invariants(seed):
    args = rnd_assignment(seed)
    s = sc.compute(**args)
    check_invariants(args, s)
    # idempotent, and independent of the order of rows and notes
    assert sc.compute(**args) == s
    r = random.Random(seed + 1)
    rows = list(args["rows"].items())
    notes = list(args["notes"].items())
    r.shuffle(rows)
    r.shuffle(notes)
    assert sc.compute(**{**args, "rows": dict(rows), "notes": dict(notes)}) == s


def test_duplicate_rows_across_graders_files_count_once(tmp_path, monkeypatch):
    """The same number in two graders' files, in Grades.csv and in an OneDrive conflict copy: one row, one count."""
    a = _folder(tmp_path, monkeypatch)
    rows = {f"{i:04d}": {"number": f"{i:04d}", "grade": str(60 + i), "points": f"{10 + i};{20 + i}", "graded_at": "2026-11-01T10:00:00",
                         "graded_by": "אורי", "approved": "", "review": ""} for i in range(1, 11)}
    grades.write_file(a / paths.GRADES_BY.format("אורי"), rows)
    one = stats.compute_assignment(a)
    grades.write_file(a / paths.GRADES_BY.format("מתן"), {n: {**r, "graded_by": "מתן", "graded_at": "2026-10-01T10:00:00"} for n, r in rows.items()})
    grades.write_file(a / "Grades by אורי-DESKTOP-ABC.csv", rows)  # an OneDrive conflict copy
    grades.write_file(a / paths.GRADES, {n: {**r, "graded_at": ""} for n, r in list(rows.items())[:3]})
    many = stats.compute_assignment(a)
    for s in (one, many):
        s.pop("sources")
        s.pop("computed_at")
    assert many == one  # the newest row per number wins everywhere; nothing is counted twice
    assert many["counts"]["graded"] == 10 and many["graders"]["by"] == [{"name": "אורי", "graded": 10}]


def test_hostile_files_do_not_crash_gather(tmp_path, monkeypatch):
    a = _folder(tmp_path, monkeypatch)
    (a / paths.NOTES).mkdir(exist_ok=True)
    (a / paths.NOTES / "0001.json").write_text("{not json", encoding="utf-8")
    (a / paths.NOTES / "0002.json").write_text("[1, 2, 3]", encoding="utf-8")
    (a / paths.NOTES / "0003.json").write_bytes(b"\xff\xfe\x00garbage")
    (a / paths.NOTES / "README.json").write_text("{}", encoding="utf-8")
    (a / paths.NOTES / "0004.json").write_text(json.dumps({"mistakes": "x", "unsure": 5, "error": None}), encoding="utf-8")
    (a / paths.GRADES_BY.format("אורי")).write_text("number,grade\n0001,\n,5\n0002,abc\n0003,1e400\n", encoding="utf-8-sig")
    (a / paths.GRADES_BY.format("ריק")).write_text("", encoding="utf-8")
    (a / paths.GRADES_BY.format("קידוד")).write_bytes("number,grade\n0005,90\n".encode("utf-8-sig") + "0006,80,שלום\n".encode("cp1255"))
    (a / paths.COPYING).write_text("{broken", encoding="utf-8")
    s = stats.compute_assignment(a)
    check_invariants({"rows": {}, "questions": s["per_question"] and [{}] * len(s["per_question"]) or []}, s)
    # 0002 "abc", 0003 "1e400", 0005, 0006 have something in the grade column, so they count as graded (like the site),
    # but only the two real grades enter the statistics
    assert s["counts"]["graded"] == 4 and s["grade"]["n"] == 2 and s["grade"]["mean"] == 85 and s["copying"] is None


def test_folder_without_optional_parts(tmp_path, monkeypatch):
    a = _folder(tmp_path, monkeypatch, rubric=False)
    for sub in (paths.TO_GRADE, paths.MARKED):
        (a / sub).rmdir()
    s = stats.compute_assignment(a)
    assert s["counts"] == {"submitted": 0, "graded": 0, "pending": 0, "approved": 0, "needs_review": 0, "failed": 0, "review_kinds": {}}


def test_two_thousand_rows_in_well_under_two_seconds():
    r = random.Random(7)
    qs = [{"label": f"q{i}", "points": 20, "deductions": []} for i in range(5)]
    rows = {f"{i:04d}": {"number": f"{i:04d}", "grade": str(r.randint(0, 100)), "points": ";".join(str(r.randint(0, 20)) for _ in qs),
                         "approved": "", "review": "", "graded_at": "2026-11-01T10:00:00", "graded_by": "אורי"} for i in range(1, 2001)}
    notes = {n: {"mistakes": [[rnd_text(r, 6) for _ in range(r.randint(0, 2))] for _ in qs], "unsure": [False] * 5} for n in rows}
    t = time.perf_counter()
    s = sc.compute(course="Linear Algebra", folder="Assignment 1", moodle_id="1", title="t", max_grade=100, questions=qs,
                   rows=rows, notes=notes, submitted=2000)
    assert time.perf_counter() - t < 2.0
    assert s["grade"]["n"] == 2000 and sum(s["grade"]["histogram"]["counts"]) == 2000


def _folder(tmp_path, monkeypatch, rubric=True) -> Path:
    root = tmp_path / "Exercise Checking System"
    a = root / "Linear Algebra" / "Assignment 2 - Matrices"
    for sub in (paths.TO_GRADE, paths.MARKED):
        (a / sub).mkdir(parents=True)
    info = {"id": "555", "course": "Linear Algebra", "name": a.name, "questions": [{"sheet": "דף", "numbers": [1, 2]}]}
    if rubric:
        info["rubric"] = {"questions": [{"label": "א", "points": 40}, {"label": "ב", "points": 60}]}
    (a / paths.INFO).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("ASSIGNMENT_DATA", str(root))
    return a
