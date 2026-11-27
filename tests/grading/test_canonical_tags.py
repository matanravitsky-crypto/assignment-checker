"""A tag the bot wrote shorter than the rubric's row becomes the row itself, so one mistake is counted under one name in
the statistics (LA0, 1,078 works, 2026-11-27: 37% of the tags were not the row word for word). A paraphrase is never
guessed: it stays as written."""
from grading import grade

RUBRIC = """### סעיף א

| טעות | סוג | רגיל | מחמיר |
|---|---|---|---|
| סעיף חסר לגמרי (אין עבודה גלויה, אחרי מעבר על כל העמודים) | חוסר | 3 | 3 |
| נימוק לא פורמלי, כמו "$B=3A$": כותבים הערה ולא מורידים (נראה ב-9 הגשות) | נימוק חסר | 0 | 1 |
| רישול סימון בהוכחה נכונה, כמו $a\in A$ במקום $a\in\mathbb R$: הערה בלבד | סימון | 0 | 1 |
| טעות חשבון אחת, למשל $3-2i$ | חישוב | 1 | 2 |
| טעות חשבון אחת עם המשך עקבי | חישוב | 2 | 3 |

| שלב | נק' |
|---|---|
| מסקנה | 2 |
"""


def test_the_rows_are_read_from_the_error_tables_only():
    rows = grade.rubric_rows(RUBRIC)
    assert len(rows) == 5 and "מסקנה" not in rows
    assert rows[1] == 'נימוק לא פורמלי, כמו "$B=3A$": כותבים הערה ולא מורידים'  # without "(נראה ב-9 הגשות)"


def test_a_shortened_row_becomes_the_row():
    rows = grade.rubric_rows(RUBRIC)
    assert grade.canonical_tag("רישול סימון בהוכחה נכונה", rows) == rows[2]
    assert grade.canonical_tag("נימוק לא פורמלי", rows) == rows[1]
    assert grade.canonical_tag("סעיף חסר לגמרי", rows) == rows[0]
    assert grade.canonical_tag(rows[1] + " (נראה ב-9 הגשות)", rows) == rows[1]


def test_an_ambiguous_start_or_a_paraphrase_stays_as_written():
    rows = grade.rubric_rows(RUBRIC)
    assert grade.canonical_tag("טעות חשבון אחת", rows) == "טעות חשבון אחת"  # the start of two rows
    assert grade.canonical_tag("שכח סוגריים", rows) == "שכח סוגריים"
    assert grade.canonical_tag("anything", ()) == "anything"
