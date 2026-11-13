"""rubric-builder: "כללים לכל מחוון" (assets/universal-rules.json) reach every rubric, the rendered one and a hand-built one."""
import copy
import importlib.util
import json
from pathlib import Path

from grading import grade

SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "rubric-builder"
UNIVERSAL = json.loads((SKILL / "assets" / "universal-rules.json").read_text(encoding="utf-8-sig"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SKILL / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RUBRIC = {
    "course": "קורס", "term": "הגשה 1", "code": "", "date": "",
    "general_rules": [{"label": "שלמות", "text": "ניסיון אמיתי = מלא."}],
    "questions": [{"n": "וקטורים 1", "points": 100, "sections": [
        {"letter": "א", "points": 60, "title": "", "answer": "1", "steps": [{"desc": "הכול", "points": 60}],
         "errors": [{"desc": "n-יה בלי סוגריים", "example": "$1,2$ במקום $(1,2)$", "type": "סימון", "regular": "1", "strict": "2"}]},
        {"letter": "ב", "points": 40, "title": "", "answer": "2", "steps": [{"desc": "הכול", "points": 40}],
         "errors": [{"desc": "n-יה בלי סוגריים", "type": "סימון", "regular": "2", "strict": "3"}]}]}],
}


def test_the_universal_rules_say_how_to_apply_a_rubric_not_how_many_points():
    assert UNIVERSAL["heading"] == "כללים לכל מחוון" and 3 <= len(UNIVERSAL["rules"]) <= 8
    labels = [g["label"] for g in UNIVERSAL["rules"]]
    assert {"אין פטור שלא כתוב", "סימן או ספרה לא ברורים", "סעיף שהתחיל"} <= set(labels)
    assert all(len(g["text"]) < 400 for g in UNIVERSAL["rules"])


def test_every_rendered_rubric_carries_them_after_its_own_rules():
    md = load("render_md").render(RUBRIC)
    own, universal = md.index("## כללי בדיקה"), md.index("## " + UNIVERSAL["heading"])
    assert own < universal < md.index("## וקטורים 1")
    assert all(g["label"] in md for g in UNIVERSAL["rules"])
    # also with no rules of its own (the defaults), and the bot reads them once
    bare = copy.deepcopy(RUBRIC)
    bare.pop("general_rules")
    assert load("render_md").render(bare).count("## " + UNIVERSAL["heading"]) == 1


def test_an_example_has_its_own_column_so_the_tag_stays_short():
    md = load("render_md").render(RUBRIC)
    assert "| n-יה בלי סוגריים | $1,2$ במקום $(1,2)$ | סימון | 1 | 2 |" in md
    assert "| n-יה בלי סוגריים | סימון | 2 | 3 |" in md  # a section with no example keeps four columns


def test_the_pdf_has_them_in_a_box_of_their_own(tmp_path):
    tex = tmp_path / "r.tex"
    src = tmp_path / "r.json"
    src.write_text(json.dumps(RUBRIC, ensure_ascii=False), encoding="utf-8")
    load("render_tex").main(str(src), str(tex))
    t = tex.read_text(encoding="utf-8")
    assert "<<UNIVERSAL>>" not in t and t.count("tcolorbox}") >= 4 and UNIVERSAL["heading"] in t
    assert t.index("שלמות") < t.index(UNIVERSAL["heading"])


def test_the_validator_warns_on_a_long_tag_and_one_form_error_with_two_prices():
    v = load("validate_rubric")
    assert v.problems(RUBRIC) == []  # warnings never stop a build
    w = v.warnings(RUBRIC)
    assert any("מחיר שונה" in x and "n-יה בלי סוגריים" in x for x in w)
    long = copy.deepcopy(RUBRIC)
    long["questions"][0]["sections"][0]["errors"][0]["desc"] = "כתב " + "מילה " * 30
    assert any("ארוך" in x for x in v.warnings(long))


def test_grading_adds_them_to_a_hand_built_rubric_once():
    hand = "# מחוון שנכתב ביד\n\n| שאלה | נק' |\n|---|---|\n| 1 | 100 |\n"
    added = grade.universal_rules_text(hand)
    assert added.startswith("## " + UNIVERSAL["heading"]) and all(g["label"] in added for g in UNIVERSAL["rules"])
    assert grade.universal_rules_text(load("render_md").render(RUBRIC)) == ""  # a rendered rubric already has them


def test_the_grading_context_carries_them(tmp_path):
    a = tmp_path / "Assignment 1"
    (a / "פדגוגי").mkdir(parents=True)
    (a / "פדגוגי" / "Rubric.md").write_text("# מחוון\n\n| שאלה | נק' |\n|---|---|\n| שאלה 1 | 100 |\n", encoding="utf-8")
    (a / "Assignment details.json").write_text(json.dumps({"questions": [{"sheet": "שאלה", "numbers": [1]}]}), encoding="utf-8")
    ctx = grade.load_context(a, send_solution=False)
    assert ctx.rubric_text.count(UNIVERSAL["heading"]) == 1
    assert UNIVERSAL["heading"] in grade.context_text(ctx)


def test_grading_swaps_an_old_rules_block_for_the_current_one():
    # 2026-11-13: a fix in a rule reached a rubric only after it was rebuilt and delivered; now grading puts the
    # current wording in place of the block the rubric was rendered with, and keeps everything after it
    old = "# מחוון\n\n## כללים לכל מחוון\n\nנוסח ישן\n- **x:** y\n\n## שאלה 1\nשורה"
    new = grade.with_universal_rules(old)
    assert new.count("## כללים לכל מחוון") == 1 and "נוסח ישן" not in new
    assert "סעיף שהתחיל" in new and new.startswith("# מחוון") and new.endswith("## שאלה 1\nשורה")
    assert grade.with_universal_rules("מחוון ביד").count("## כללים לכל מחוון") == 1
