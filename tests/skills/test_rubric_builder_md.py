"""rubric-builder: Rubric.md (the bot's rubric) is rendered from rubric.json, and grading reads its points table."""
import importlib.util
import json
from pathlib import Path

from grading import grade

SCRIPT = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "rubric-builder" / "scripts" / "render_md.py"


def _render_md():
    spec = importlib.util.spec_from_file_location("render_md", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RUBRIC = {
    "course": "אלגברה לינארית להנדסה", "term": "הגשה 0", "code": "", "date": "",
    "general_rules": [{"label": "ערך ולא צורה", "text": "כל צורה סופית שקולה מקבלת מלא."}],
    "questions": [
        {"n": "קבוצות 11", "points": 20, "sections": [
            {"letter": "א, ב, ד, ה", "points": 3, "count": 4, "title": "האם $A=B$", "answer": "כן",
             "steps": [{"desc": "מסקנה", "points": 2}, {"desc": "אין טענה שקרית", "points": 1}],
             "errors": [{"desc": "ענה לא", "type": "הבנה", "regular": "3", "strict": "3"}]},
            {"letter": "ג", "points": 8, "title": "דוגמה נגדית", "answer": "לא; $(1,1)\\in B$",
             "steps": [{"desc": "מסקנה", "points": 2}, {"desc": "זוג תקף", "points": 6}],
             "errors": [{"desc": "בלי איבר", "type": "חוסר", "regular": "6", "strict": "7"}],
             "note": "שייכות שנייה חסרה: נסלח."}]},
        {"n": "מרוכבים 6", "points": 12, "sections": [
            {"letter": "א, ב", "points": 6, "count": 2, "title": "חילוק", "answer": "$3-i$",
             "steps": [{"desc": "כפל בצמוד", "points": 6}],
             "errors": [{"desc": "$i^2=1$", "type": "הבנה", "regular": "4", "strict": "5"}],
             "alt_methods": [{"name": "השוואת חלקים", "steps": [{"desc": "מערכת ממשית", "points": 6}]}]}]},
    ],
}


def test_grading_reads_the_points_per_question_from_the_rendered_markdown(tmp_path: Path) -> None:
    md = _render_md().render(RUBRIC)
    labels = grade.question_labels({"questions": [{"sheet": "דף קבוצות", "numbers": [11]},
                                                  {"sheet": "דף מספרים מרוכבים", "numbers": [6]}]})
    assert grade.pedagogy_points(md, labels) == {"דף קבוצות 11": 20.0, "דף מספרים מרוכבים 6": 12.0}


def test_the_markdown_carries_every_part_of_the_rubric() -> None:
    md = _render_md().render(RUBRIC)
    assert md.startswith("# אלגברה לינארית להנדסה: הגשה 0 – מחוון")
    for text in ("rubric.json", "## חלוקת הנקודות", "| **סה\"כ** | **32** |", "## כללי בדיקה", "ערך ולא צורה",
                 "### סעיפים א, ב, ד, ה (3 נק' כל אחד): האם $A=B$", "### סעיף ג (8 נק'): דוגמה נגדית",
                 "_שייכות שנייה חסרה: נסלח._", "| ענה לא | הבנה | 3 | 3 |", "**דרך חלופית: השוואת חלקים**",
                 "| מערכת ממשית | 6 |"):
        assert text in md, text


def test_the_rendered_file_is_the_one_grading_sends(tmp_path: Path) -> None:
    ped = tmp_path / "פדגוגי"
    ped.mkdir()
    (ped / "Rubric.md").write_text(_render_md().render(RUBRIC), encoding="utf-8")
    (ped / "Working notes").mkdir()
    (ped / "Working notes" / "Rubric v3.0 (council).md").write_text("old", encoding="utf-8")
    (ped / "Rubric v2 old.md").write_text("old", encoding="utf-8")
    assert [p.name for p in grade.pedagogy_files(tmp_path)] == ["Rubric.md"]
    json.dumps(RUBRIC, ensure_ascii=False)  # the fixture stays valid JSON
