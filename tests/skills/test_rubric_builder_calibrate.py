"""calibrate.py turns the bot's grading reports into the committee's calibration input: covered mistakes are
counted against the rubric's rows, uncovered ones are listed per question with counts, numbers only."""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "rubric-builder" / "scripts"
spec = importlib.util.spec_from_file_location("calibrate", SCRIPTS / "calibrate.py")
calibrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calibrate)

RUBRIC = {"questions": [
    {"n": "קבוצות 12", "points": 24, "sections": [
        {"letter": "ה", "points": 4, "errors": [
            {"desc": "כתב \"אינסוף\" או $\\{\\infty\\}$ במקום הקבוצה, עם עבודה נכונה", "type": "הבנה", "regular": "2", "strict": "3"},
            {"desc": "השתמש באותה אות לשתי הקבוצות", "type": "הבנה", "regular": "2", "strict": "3"}]}]},
    {"n": "מרוכבים 6", "points": 12, "sections": [{"letter": "א", "points": 12, "errors": []}]},
]}
LABELS = ["דף קבוצות 12", "דף מספרים מרוכבים 6"]


def note(points, mistakes, unsure=(False, False), review=""):
    return {"points": points, "mistakes": mistakes, "unsure": list(unsure), "review": review, "review_kind": "uncertain" if review else ""}


def test_covered_mistakes_count_as_hits_and_uncovered_ones_are_listed():
    notes = [
        note([22, 12], [["כתב אינסוף במקום הקבוצה"], []]),
        note([22, 12], [["כתב \"אינסוף פתרונות\" במקום הקבוצה"], []]),
        note([20, 10], [["אותה אות פרמטר לשתי הקבוצות"], ["טעות סימן ב-i^2"]], unsure=(True, False)),
        note([24, 12], [[], ["טעות סימן ב-i^2"]], review="שאלה 6: לא קריא"),
    ]
    md = calibrate.build(notes, RUBRIC, LABELS)
    assert "4 עבודות שנבדקו" in md
    assert "| דף קבוצות 12 | 4 | 22.0 | 24 | 1 (25%) | 0 |" in md
    assert "| דף מספרים מרוכבים 6 | 4 | 11.5 | 12 | 0 (0%) | 2 |" in md
    assert "- (2) טעות סימן ב-i^2" in md
    assert "(2) דף קבוצות 12 ה: כתב \"אינסוף\"" in md
    assert "עבודות שנשלחו לבדיקה ידנית: 1" in md
    assert "[uncertain] שאלה 6: לא קריא" in md


def test_rows_never_used_are_reported():
    md = calibrate.build([note([24, 12], [[], []])], RUBRIC, LABELS)
    assert "שורות שלא שימשו אף פעם: 2 מתוך 2" in md


def test_word_matching_ignores_small_words_and_prefixes():
    a = calibrate.words("כתב אינסוף במקום הקבוצה")
    b = calibrate.words("כתב \"אינסוף פתרונות\" במקום הקבוצה, עם עבודה נכונה")
    assert calibrate.similarity(a, b) >= 0.34
    assert calibrate.similarity(calibrate.words("טעות סימן ב-i^2"), b) < 0.34
