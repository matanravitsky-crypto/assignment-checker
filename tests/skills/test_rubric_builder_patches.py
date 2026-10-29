"""apply_patches.py: the committee's patch list goes into rubric.json exactly, and nothing else moves."""
import copy
import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "rubric-builder" / "scripts"
spec = importlib.util.spec_from_file_location("apply_patches", SCRIPTS / "apply_patches.py")
ap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap)

RUBRIC = {"questions": [{"n": "קבוצות 12", "points": 4, "sections": [
    {"letter": "ה", "points": 4, "answer": "x", "steps": [{"desc": "s", "points": 4}], "note": "הערה קיימת.",
     "errors": [{"desc": "כתב אינסוף במקום הקבוצה", "type": "הבנה", "regular": "2", "strict": "3"}]}]}]}


def test_add_reword_and_note():
    r = copy.deepcopy(RUBRIC)
    lines = ap.apply(r, [
        {"q": "קבוצות 12", "letter": "ה", "action": "add", "desc": "כתב {∅} במקום ∅", "type": "סימון", "regular": "1", "strict": "2"},
        {"q": "קבוצות 12", "letter": "ה", "action": "reword", "old_desc": "כתב אינסוף במקום הקבוצה", "desc": "כתב \"אינסוף\" או {∞} במקום הקבוצה"},
        {"q": "קבוצות 12", "letter": "ה", "action": "note", "note": "תשובה במילים: לפי השורה, לא לבדיקה ידנית."},
    ])
    s = r["questions"][0]["sections"][0]
    assert [e["desc"] for e in s["errors"]] == ["כתב \"אינסוף\" או {∞} במקום הקבוצה", "כתב {∅} במקום ∅"]
    assert s["note"] == "הערה קיימת. תשובה במילים: לפי השורה, לא לבדיקה ידנית."
    assert s["points"] == 4 and len(lines) == 3


def test_a_duplicate_add_is_skipped_and_a_wrong_target_stops():
    r = copy.deepcopy(RUBRIC)
    lines = ap.apply(r, [{"q": "קבוצות 12", "letter": "ה", "action": "add", "desc": "כתב אינסוף במקום הקבוצה", "type": "הבנה", "regular": "2", "strict": "3"}])
    assert lines[0].startswith("=") and len(r["questions"][0]["sections"][0]["errors"]) == 1
    with pytest.raises(SystemExit):
        ap.apply(r, [{"q": "קבוצות 12", "letter": "ז", "action": "note", "note": "x"}])
    with pytest.raises(SystemExit):
        ap.apply(r, [{"q": "קבוצות 12", "letter": "ה", "action": "reword", "old_desc": "לא קיים", "desc": "y"}])


def test_patches_are_read_from_the_committee_markdown(tmp_path):
    md = tmp_path / "calibration-1.md"
    md.write_text("דיון...\n```json\n[{\"q\": \"קבוצות 12\", \"letter\": \"ה\", \"action\": \"note\", \"note\": \"n\"}]\n```\n", encoding="utf-8")
    assert ap.load_patches(str(md))[0]["action"] == "note"
