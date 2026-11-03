"""rubric-builder's scripts refuse what would break the PDF or mislead the bot, and say so in Hebrew.
Based on the robustness audit of 2026-10-29. No xelatex needed: the compile itself is not run here."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "rubric-builder" / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


validate = load("validate_rubric")
render_tex = load("render_tex")
render_md = load("render_md")
build_pdf = load("build_pdf")

GOOD = {
    "course": "אלגברה לינארית", "code": "214", "term": "א", "date": "01/01/2026",
    "questions": [
        {"n": "קבוצות 11", "points": 60, "sections": [
            {"letter": "א", "points": 40, "answer": "כן", "steps": [{"desc": "הכלה אחת", "points": 20}, {"desc": "הכלה שנייה", "points": 20}],
             "errors": [{"desc": "רק הכלה אחת", "type": "חוסר", "regular": "20", "strict": "21"},
                        {"desc": "ענה לא", "type": "הבנה", "regular": "40", "strict": "40"}]},
            {"letter": "ב, ג", "points": 10, "count": 2, "answer": "לא", "steps": [{"desc": "איבר", "points": 10}]},
        ]},
        {"n": "מרוכבים 6", "points": 40, "sections": [
            {"letter": "א", "points": 40, "answer": "$z=1+i$", "steps": [{"desc": "חישוב", "points": 40}],
             "errors": [{"desc": "טעות סימן", "type": "חישוב", "regular": "2–4", "strict": "3 – 5"}]},
        ]},
    ],
}


def mutate(**changes):
    r = copy.deepcopy(GOOD)
    for path, value in changes.items():
        node = r
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[int(k)] if k.isdigit() else node[k]
        last = keys[-1]
        if value is ...:
            del node[int(last) if last.isdigit() else last]
        else:
            node[int(last) if last.isdigit() else last] = value
    return r


def test_the_good_rubric_passes():
    assert validate.problems(GOOD) == []


@pytest.mark.parametrize("changes, word", [
    ({"course": ""}, "קורס"),
    ({"questions": []}, "אין שאלות"),
    ({"questions.0.n": 11}, "מחרוזת"),
    ({"questions.0.n": "11"}, "מספר בלבד"),
    ({"questions.0.points": 60.5}, "שלם"),
    ({"questions.0.sections.0.points": 40.5}, "שלם"),
    ({"questions.0.sections": []}, "אין סעיפים"),
    ({"questions.0.sections.1.letter": "א"}, "פעמיים"),
    ({"questions.0.sections.1.count": 3}, "count=3"),
    ({"questions.0.sections.0.steps.0.points": 19}, "שלבים מסתכמים"),
    ({"questions.0.sections.0.steps": []}, "אין שלבים"),
    ({"questions.0.sections.0.answer": ""}, "אין תשובה"),
    ({"questions.0.sections.0.errors.0.type": "קשה"}, "סוג טעות לא מוכר"),
    ({"questions.0.sections.0.errors.0.regular": "4–2"}, "טווח הפוך"),
    ({"questions.0.sections.0.errors.0.strict": "19"}, "מחמיר קטן מרגיל"),
    ({"questions.0.sections.0.errors.0.strict": "20"}, "מחמיר שווה לרגיל"),
    ({"questions.0.sections.0.errors.0.strict": "23"}, "ביותר מנקודה"),
    ({"questions.0.sections.0.errors.0.regular": "41"}, "גדול מהסעיף"),
    ({"questions.0.sections.0.errors.0.desc": "כתב **אינסוף**"}, "Markdown"),
    ({"questions.0.sections.0.answer": "$x+1"}, "אי-זוגי"),
    ({"questions.1.points": 50}, "סך הנקודות"),
    ({"questions.0.sections.0.errors.0.desc": ...}, "בלי תיאור"),
    ({"questions.0.sections.0.steps.0.desc": ...}, "בלי תיאור"),
])
def test_bad_rubrics_are_refused_with_a_hebrew_reason(changes, word):
    problems = validate.problems(mutate(**changes))
    assert problems, changes
    assert any(word in p for p in problems), problems


def test_natural_deduction_notations_are_accepted():
    r = mutate(**{"questions.1.sections.0.errors.0.regular": "0 / 1", "questions.1.sections.0.errors.0.strict": "1 / 2"})
    assert validate.problems(r) == []


def test_a_bom_and_a_missing_file_give_messages_not_tracebacks(tmp_path):
    p = tmp_path / "rubric.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps(GOOD, ensure_ascii=False).encode("utf-8"))
    assert validate.load(p) == GOOD
    with pytest.raises(SystemExit) as ex:
        validate.load(tmp_path / "nope.json")
    assert "לא נמצא" in str(ex.value)
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit) as ex:
        validate.load(tmp_path / "bad.json")
    assert "JSON" in str(ex.value)


def test_tex_specials_are_escaped_outside_math_only():
    assert render_tex.fix("50% & more_stuff #1") == r"50\% \& more\_stuff \#1"
    assert render_tex.fix(r"already \% escaped") == r"already \% escaped"
    assert render_tex.fix("$a_1 & b$") == "$a_1 & b$"  # inside math nothing is touched


def test_unicode_math_symbols_become_commands_inside_and_outside_math():
    assert render_tex.fix("A ∩ B ⊆ ℝ") == r"A $\cap$ B $\subseteq$ $\mathbb{R}$"
    assert render_tex.fix("$x ≤ y$") == r"$x \le  y$"
    assert render_tex.fix("$A ∩ B$") == r"$A \cap  B$"
    assert "\\not\\in" in render_tex.fix("$x \\notin A$")


def test_the_bot_rubric_has_the_default_rules_when_none_are_given():
    md = render_md.render(GOOD)
    assert "## כללי בדיקה" in md
    assert md.split("## כללי בדיקה")[1].count("- **") >= 5  # the defaults from assets/default-rules.json


def test_missing_characters_in_the_log_are_detected():
    log = ("Missing character: There is no ∩ in font David CLM/OT:script=hebr;language=dflt;!\n"
           "Missing character: There is no ℝ in font cmmi10!\nMissing character: There is no ∩ in font David CLM!")
    assert build_pdf.missing_chars(log) == ["ℝ", "∩"]


def test_a_compile_error_is_explained_with_the_tex_line():
    log = ["! Misplaced \\noalign.", "\\rowcolor ->\\noalign", "   {\\ifnum 0=`}\\fi", "l.88 \\rowcolor{rowgrey} 50% done"]
    tex = ["line %d" % i for i in range(1, 100)]
    out = build_pdf.explain(log, tex)
    assert out[0].startswith("!")
    assert any("שורה 88" in l and "line 88" in l for l in out)


def test_onedrive_conflict_copies_in_the_pedagogy_folder_are_not_sent(tmp_path):
    from grading import grade
    from moodle import paths
    ped = tmp_path / paths.PEDAGOGY[0]
    ped.mkdir()
    for name in ("Rubric.md", "Rubric-DESKTOP-ABC12.md", "Solutions-LAPTOP-X9.md", "Solutions.md", "Manual review rules.md"):
        (ped / name).write_text("x", encoding="utf-8")
    sent = [p.name for p in grade.pedagogy_files(tmp_path)]
    assert sent == ["Rubric.md", "Manual review rules.md", "Solutions.md"]


def test_the_example_in_format_md_validates():
    import re
    text = (SCRIPTS.parent / "references" / "format.md").read_text(encoding="utf-8")
    block = re.search(r"```json\n(.*?)```", text, re.S).group(1)
    assert validate.problems(json.loads(block)) == []
