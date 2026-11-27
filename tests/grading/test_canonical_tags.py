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


def test_a_mark_finds_its_section_when_the_bot_numbered_or_shortened_it():
    labels = ["קבוצות 11ב", "קבוצות 11ג", "מרוכבים 6ב"]
    assert grade.part_label("3. קבוצות 11ג", labels) == "קבוצות 11ג"
    assert grade.part_label("11ג", labels) == "קבוצות 11ג"
    assert grade.part_label("קבוצות 11ב", labels) == "קבוצות 11ב"
    assert grade.part_label("6ב", labels) == "מרוכבים 6ב"
    assert grade.part_label("ב", labels) == "ב"          # the end of no label as a word: stays
    assert grade.part_label("", labels) == ""


def test_moodle_grade_per_question_any_gives_a_whole_question_for_one_part():
    from moodle import grades
    labels = ["8א", "8ב", "11א", "11ב", "11ג", "13א", "13ב", "13ג", "14א", "14ב", "14ג", "15א", "15ב", "16"]
    every = [True] * 14
    only_first = [l.endswith("א") or l == "16" for l in labels]
    no_14c = [l != "14ג" for l in labels]
    no_16 = [l != "16" for l in labels]
    assert grades.course_grade(labels, every, per_question="any") == 100
    assert grades.course_grade(labels, no_14c, per_question="any") == 100
    assert grades.course_grade(labels, only_first, per_question="any") == 100
    assert grades.course_grade(labels, no_16, per_question="any") == 83
    assert grades.course_grade(labels, no_14c) == 94                       # the default stays as it was (LA0)
    assert grades.course_grade(labels, every, zero=True, per_question="any") == 0


def test_imperatives_a_student_reads_both_ways_become_instructions():
    assert grade.plain("הציבו את הנקודה במשוואה") == "יש להציב את הנקודה במשוואה"
    assert grade.plain("שגוי: 3. בדקו את הסימן") == "שגוי: 3. יש לבדוק את הסימן"
    assert grade.plain("הסטודנט בדקו") == "הסטודנט בדקו"  # not at the start of a sentence: left alone


def test_the_summary_explains_a_per_question_course_grade_by_questions():
    from grading import summary
    ctx = grade.Context("הגשה 1", "לינארית", [grade.Question(l, 7) for l in ("8א", "8ב", "16")], policy={"basis": "submission", "per_question": "any"})
    g = grade.Graded([7, 0, 0], ["", "", ""], 50, "", [], submitted=[True, False, False])
    g.course = 50
    text = summary.course_text(g, ctx)
    assert "לפי השאלות שהוגשו" in text and "1 מתוך 2 שאלות" in text and "16" in text


def test_an_imperative_before_a_colon_or_at_the_end_is_an_instruction_too():
    assert grade.plain("בדקו: האם הכיוונים מקבילים") == "יש לבדוק: האם הכיוונים מקבילים"
    assert grade.plain("נקודה אחת לא נבדקה. בדקו") == "נקודה אחת לא נבדקה. יש לבדוק"
