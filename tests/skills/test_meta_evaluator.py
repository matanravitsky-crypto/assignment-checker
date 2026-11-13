"""meta-evaluator: the mechanical half of an audit round, and the offline grading that never touches the shared folder."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "meta-evaluator" / "scripts"
LABELS = ["שאלה 1", "שאלה 2", "שאלה 3"]


def load(name):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


me = load("me")
offline = load("offline")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """An assignment with 12 graded works (grades 40..95), one in the manual queue; and a round folder."""
    a = tmp_path / "data" / "Course" / "Assignment 1"
    (a / "Grading notes").mkdir(parents=True)
    (a / "1 - Submissions to grade").mkdir()
    (a / "Assignment details.json").write_text(json.dumps({"id": "777", "rubric": {"questions": [
        {"label": l, "points": p} for l, p in zip(LABELS, (30, 30, 40))]}}, ensure_ascii=False), encoding="utf-8")
    rows = ["number,grade,feedback,points,approved,review,graded_at,graded_by"]
    for i in range(12):
        n = f"{i + 1:04d}"
        g = 40 + 5 * i
        pts = [30, 30, g - 60] if g >= 60 else [g, 0, 0]
        marks = [{"page": 1, "x0": 100, "y0": 100, "x1": 300, "y1": 100 + 30 * (i % 4 + 1), "text": "טעות"}] * (i % 3)
        (a / "Grading notes" / f"{n}.json").write_text(json.dumps({
            "points": pts, "comments": ["נכון", "חסר נימוק להכלה", "x"], "mistakes": [[], ["חסר נימוק"] if pts[1] < 30 else [], []],
            "unsure": [False] * 3, "marks": marks, "places": []}, ensure_ascii=False), encoding="utf-8")
        rows.append(f"{n},{g},משוב,{';'.join(map(str, pts))},,{'לא קריא' if i == 4 else ''},2026-11-11T10:00:0{i % 10},x")
    (a / "Grades by x.csv").write_text("\n".join(rows) + "\n", encoding="utf-8-sig")
    monkeypatch.setattr(me.c, "HOME_WORK", tmp_path / "work")
    r = me.c.round_dir(a, "round-1")
    return a, r


def test_the_round_folder_is_never_in_the_repo_or_onedrive(setup, tmp_path):
    a, _ = setup
    with pytest.raises(SystemExit):
        me.c.round_dir(a, "x", root=me.c.REPO / "tmp-round")
    with pytest.raises(SystemExit):
        me.c.round_dir(a, "x", root=tmp_path / "OneDrive" / "work")


def test_the_sample_spreads_over_the_grades_and_keeps_the_queue_and_the_named(setup):
    a, r = setup
    s = me.sample(a, r, 6, include=["0012"], fresh=False, seed=1)
    assert len(s) == 6 and "0012" in s and "0005" in s  # named, and the one in the manual queue
    grades = sorted(40 + 5 * (int(x) - 1) for x in s)
    assert grades[0] < 60 and grades[-1] >= 80  # low and high thirds both there
    assert s == me.sample(a, r, 6, include=["0012"], fresh=False, seed=1)  # repeatable


def test_a_fresh_sample_skips_works_an_earlier_round_audited(setup):
    a, r = setup
    old = r.parent / "batch-1" / "logs"
    old.mkdir(parents=True)
    for n in ("0001", "0002", "0003", "0004"):
        (old / f"log-{n}.md").write_text("x", encoding="utf-8")
    s = me.sample(a, r, 6, include=[], fresh=True, seed=1)
    assert not set(s) & {"0001", "0002", "0003", "0004"}


def test_the_mechanical_pass_finds_tags_with_two_prices_and_grader_words(setup):
    a, r = setup
    for n, second in (("0007", 20), ("0008", 25)):  # the same tag, 10 points off in one work and 5 in another
        d = json.loads((a / "Grading notes" / f"{n}.json").read_text(encoding="utf-8"))
        d["points"][1], d["mistakes"][1] = second, ["חסר נימוק"]
        if n == "0007":
            d["comments"][2] = "נקבע לפי הקריאה הנמוכה"
        (a / "Grading notes" / f"{n}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    out = me.mechanical(a, r)
    assert out["works"] == 12 and out["works_with_grader_words"] == ["0007"]
    assert "חסר נימוק" in out["inconsistent_tags"]  # 30 points off in one work, fewer in another
    assert abs(out["review_rate"] - 1 / 12) < 0.01


@pytest.mark.parametrize("bottom,grade,target", [
    ("- הציון 90 נמוך מדי בכ-3, הסיבה: ...", 90, 93), ("- הציון 99 גבוה מדי בכ-1, ...", 99, 98),
    ("- הציון 72 נכון, הסיבה העיקרית ...", 72, 72), ("- הציון החדש 87 נכון; הסימון טוב", 87, 87),
    ("- לא ברור", 50, None)])
def test_the_auditors_verdict_becomes_a_target_grade(bottom, grade, target):
    assert me.target_from(bottom, grade) == target


def test_claims_go_to_the_verifier_most_important_first(setup):
    a, r = setup
    (r / "logs").mkdir()
    (r / "logs" / "log-0003.md").write_text("""# עבודה 0003 · ציון 50
## ממצאים
- [BOX_OFF] סעיף שאלה 2 · עמוד 3 · התיבה על השורה הבאה
- [BOX_OK] סעיף שאלה 1 · עמוד 2 · טוב
- [TAG_PARAPHRASED] [MISSED] סעיף שאלה 3 · עמוד 4 · חסר ניכוי על סימן
""", encoding="utf-8")
    out = me.claims(r, cap=10)
    assert [x["tag"] for x in out] == ["MISSED", "BOX_OFF"]
    assert out[0]["work"] == "0003" and out[0]["page"] == 4 and out[0]["section"] == "שאלה 3"
    assert json.loads((r / "verify-input.json").read_text(encoding="utf-8")) == out


def test_the_report_checks_itself(setup, tmp_path):
    a, r = setup
    me.sample(a, r, 6, include=["0012"], fresh=False, seed=1)
    good = tmp_path / "good.md"
    good.write_text("- **R1** מחוון עמום (0012, [TWO_ROWS])\n- **G1** תיבות (0012, [BOX_OFF])\n- **G2** עוד (0012)\n", encoding="utf-8")
    assert me.check_report(r, good) == []
    bad = tmp_path / "bad.md"
    bad.write_text("- **R1** בלי עבודה\n- **G1** x (0012)\n- **G3** קפיצה (0012)\n", encoding="utf-8")
    problems = me.check_report(r, bad)
    assert any("R1" in p and "לא מצטט" in p for p in problems) and any("G:" in p for p in problems)
    (r / "verify.json").write_text(json.dumps({"0012:4": {"verdict": "REJECTED"}}), encoding="utf-8")
    rej = tmp_path / "rej.md"
    rej.write_text("- **G1** תיבה (0012, שורה 4)\n", encoding="utf-8")
    assert any("דחה" in p for p in me.check_report(r, rej))


def test_compare_measures_whether_works_got_closer_to_the_target(setup):
    a, r = setup
    me.c.dump({"sample": ["0003", "0004"]}, r / "sample.json")
    me.backup(a, r)
    me.c.dump({"0003": {"target": 55}, "0004": {"target": 50}}, r / "targets.json")
    f = a / "Grades by x.csv"
    f.write_text(f.read_text(encoding="utf-8-sig").replace("0003,50,", "0003,54,").replace("0004,55,", "0004,60,"),
                 encoding="utf-8-sig")
    s = me.compare(a, r)
    assert s["closer"] == 1 and s["further"] == ["0004"] and s["mean_error_old"] == 5 and s["mean_error_new"] == 5.5


def test_offline_grading_writes_only_to_the_round_folder(setup, monkeypatch):
    from grading import grade, locate
    from moodle import paths
    a, r = setup
    for n in ("0001", "0002", "0003"):
        (a / "1 - Submissions to grade" / f"{n}.pdf").write_bytes(b"%PDF-1.4 " + n.encode() * 50)
    (a.parents[1] / "Grading usage.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(paths, "data_dir", lambda: a.parents[1])
    monkeypatch.setattr(grade, "claude_ask", lambda *x, **k: (lambda req: "{}"))
    monkeypatch.setattr(locate, "enabled", lambda: False)
    monkeypatch.setattr(grade, "submission_pdf", lambda files: (b"%PDF", []))
    seen = []

    def fake_one(pdf, ctx, ask, model, names, locate_ask=None):
        seen.append(locate_ask)
        return grade.Graded([30, 20, 40], ["a", "b", "c"], 90, "טוב", [grade.Mark(1, 1, 2, 3, 4, "x")]), b"%PDF marked"
    monkeypatch.setattr(grade, "grade_one", fake_one)
    before = offline.fingerprint(a)
    res = offline.run(a, r, ["0001", "0003"], parallel=2)
    assert res["touched"] == [] and offline.fingerprint(a) == before
    assert sorted(p.name for p in (r / "notes").iterdir()) == ["0001.json", "0003.json"]
    assert (r / "marked" / "0001.pdf").read_bytes() == b"%PDF marked"
    assert json.loads((r / "grades.json").read_text(encoding="utf-8"))["0003"]["grade"] == 90
    assert not (a / "Grading notes" / "0001.json").read_text(encoding="utf-8").count("טוב")  # the shared notes untouched


def test_the_offline_pick_spreads_over_sizes_and_repeats(setup):
    a, _ = setup
    for i in range(30):
        (a / "1 - Submissions to grade" / f"{i + 1:04d}.pdf").write_bytes(b"x" * (100 * (i + 1)))
    p = offline.pick(a, 6, 3)
    assert len(p) == 6 and p == offline.pick(a, 6, 3)
    sizes = sorted(int(x) for x in p)
    assert sizes[0] <= 10 and sizes[-1] > 20  # small and large submissions both


def test_fingerprint_sees_a_written_file(setup):
    a, _ = setup
    before = offline.fingerprint(a)
    (a / "Grading notes" / "0099.json").write_text("{}", encoding="utf-8")
    assert offline.changed(before, offline.fingerprint(a)) == [str(a / "Grading notes" / "0099.json")]


def test_an_offline_round_is_read_from_its_own_folder(setup):
    a, r = setup
    me.c.dump({"sample": ["0501"], "offline": True}, r / "sample.json")
    (r / "notes").mkdir()
    me.c.dump({"points": [30, 10, 40], "comments": ["a", "b", "c"], "mistakes": [[], ["x"], []], "marks": []}, r / "notes" / "0501.json")
    me.c.dump({"0501": {"grade": 80, "review": ""}}, r / "grades.json")
    out = me.mechanical(a, r)
    assert out["works"] == 1 and out["per_section_deducted"]["שאלה 2"] == 1  # the shared folder's 12 works are not read
