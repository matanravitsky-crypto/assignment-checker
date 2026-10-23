"""ניקוד לפי סעיפים (grading/parts.py): Claude מסווג, הקוד מנקד לפי §6 במחוון."""
from __future__ import annotations

import json

from grading import grade as grading, parts
from tests.grading.test_grade import LABELS, asg, root, save_details  # noqa: F401 (root הוא fixture)

RUBRIC = r"""# מחוון

| שאלה | נק' | סעיפים |
|---|---|---|
| קבוצות 11 | 20 | א 3 · ב 3 · **ג 8** · ד 3 · ה 3 |
| קבוצות 12 | 24 | א 3 · ב 4 · ג 4 · ד 4 · ה 5 · ו 4 |
| מרוכבים 6 | 12 | א 6 · ב 6 |
| מרוכבים 7 | 20 | א 5 · ב 2 · ג 5 · ד 8 |
| מרוכבים 8 | 24 | 24 בלי סעיפים |

#### 11א (3): כן.

| # | מה כתוב | נק' | הערה |
|---|---|---|---|
| 11א-1 | כן | 3 | ✓ |
| 11א-7 | כן + טענה שגויה | 2 (כולל SIDE) | |

#### 12א (3): ריק.

| # | מה כתוב | נק' | הערה |
|---|---|---|---|
| 12א-1 | $\varnothing$ | 3 | ✓ |
| 12א-3 | $\{\varnothing\}$ | 3 · EMPTYSET (=2) | |
| 12א-6 | נימוק עיוור-סוג | 2 (כולל FALSE-STEP) | |

| 12ב-7 | "$A=B$" | 4 · W−1 (=3) | |
| 12ד-4 | אותה אות | 3 (כולל FALSE-STEP) | |
| 6-8 | בלי עבודה | 5 | |
| 6-1 | נכון | 6 | |

#### 7ג (5): $2$ (2) + $-1+2i$ (2) + צורה (1)

| 7ג-7 | ערכים הוחלפו | חצי לכל חסר: 1 + 1 | |
"""
LABELS3 = ["דף קבוצות 11", "דף קבוצות 12", "דף מספרים מרוכבים 6", "דף מספרים מרוכבים 7", "דף מספרים מרוכבים 8"]


def split():
    return parts.parse_parts(RUBRIC, LABELS3, [20, 24, 12, 20, 24])


def test_parts_and_rows_come_from_the_rubric_tables():
    qs = split()
    assert [p.id for p in qs[0]] == ["11א", "11ב", "11ג", "11ד", "11ה"] and qs[0][2].points == 8
    assert qs[4] == []  # בלי חלוקה לסעיפים: השאלה נשארת שאלה
    assert [p.by_components for p in qs[3]] == [False, False, True, False]
    rows = parts.parse_rows(RUBRIC)
    assert rows["11א-7"] == parts.Row(2, [], ["SIDE"])
    assert rows["12א-3"] == parts.Row(3, ["EMPTYSET"], []) and rows["12ב-7"].tags == ["W"]
    assert rows["7ג-7"].base is None  # לא מספר אחד: הערך של Claude
    # סכום הסעיפים שונה מהניקוד של השאלה: לא מחלקים
    assert parts.parse_parts(RUBRIC, LABELS3, [21, 24, 12, 20, 24])[0] == []


def got(**by_part):
    return [{"part": k, "status": "graded", "row_id": v[0], "base": v[1], "adjusters": v[2] if len(v) > 2 else [],
             "tags": v[3] if len(v) > 3 else [], "final_answer": "", "unsure": False} for k, v in by_part.items()]


def test_the_code_takes_the_row_value_and_drops_what_the_rules_forbid():
    rows = parts.parse_rows(RUBRIC)
    answer = got(**{"11א": ("11א-7", 3, ["FALSE-STEP"], ["SIDE"]),   # ערך השורה 2, SIDE כבר כלול, מתאם בשורה חלקית
                    "12א": ("12א-6", 2, ["FALSE-STEP"]),              # FALSE-STEP כבר כלול בשורה
                    "12ב": ("12ב-7", 4),                               # התגית W מהשורה עצמה
                    "12ד": ("12ד-4", 3, [], ["TUPLESET"])})           # תגית צורה בשורה חלקית לא נרשמת
    scored, fixes, absent = parts.score(answer, split(), rows)
    by = {s.part: s for s in scored}
    assert by["11א"].points == 2 and by["11א"].tags == [] and by["11א"].adjusters == []
    assert by["12א"].points == 2 and by["12ב"].points == 3 and by["12ד"].points == 3
    assert len(fixes) == 5 and "11ב" in absent and by["11ב"].points == 0


def test_global_deductions_have_caps():
    rows = parts.parse_rows(RUBRIC)
    full = {p.id: (p.id + "-x", p.points) for q in split() for p in q}
    # EMPTYSET בשלושה סעיפים: התקרה −2; DOMAIN פעמיים: −1; סימון בשלושה סעיפים: −1
    tags = {"11א": ["EMPTYSET", "N1"], "11ב": ["EMPTYSET", "DOMAIN", "N3"], "11ג": ["EMPTYSET", "DOMAIN", "N4"], "12א": ["SIDE"],
            "12ב": ["SIDE"], "12ג": ["SIDE"]}
    answer = got(**{k: (*v, [], tags.get(k, [])) for k, v in full.items()})
    scored, fixes, absent = parts.score(answer, split(), rows)
    assert not absent
    total = sum(p.points for q in split() for p in q)
    assert total - sum(s.points for s in scored) == 2 + 1 + 1 + 2  # EMPTYSET 2, DOMAIN 1, סימון 1, SIDE 2
    assert all(s.points >= 0 for s in scored)


def test_grading_by_parts_end_to_end(root):
    a = asg(root)
    save_details(a, {**a.details(), "rubric": None})
    (a.dir / "פדגוגי").mkdir()
    (a.dir / "פדגוגי" / "Rubric.md").write_text(RUBRIC, encoding="utf-8")
    ctx = grading.load_context(a.dir)
    assert ctx.by_parts and "parts" in grading.schema_for(ctx)["required"]
    assert "points" not in grading.schema_for(ctx)["properties"]["questions"]["items"]["properties"]
    assert "11א (3)" in grading.context_text(ctx)
    full = {p.id: (p.id + "-x", p.points) for q in ctx.questions for p in q.parts}
    full["12א"] = ("12א-3", 3)  # {∅}: −1
    text = json.dumps({"questions": [{"label": l, "comment": "", "mistakes": [], "unsure": False} for l in LABELS],
                       "parts": got(**full), "feedback": "יפה", "annotations": [],
                       "needs_review": False, "review_reason": "", "review_kind": ""}, ensure_ascii=False)
    g = grading.parse_answer(text, ctx, pages=1)
    assert g.points[:4] == [20, 23, 12, 20]  # 12א ירד נקודה בגלל EMPTYSET
    assert g.points[4] == 0  # שאלה 8 בלי סעיפים ובלי ניקוד בתשובה
    assert {p["part"]: p["points"] for p in g.parts}["12א"] == 2 and g.parts[0]["row_id"] == "11א-x"
