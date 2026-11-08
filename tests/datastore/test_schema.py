"""datastore/schema.py: hostile values for every record type, the reject/warn levels, and a fuzz pass that never raises
and never echoes a student's text."""
from __future__ import annotations

import json
import random

import pytest

from datastore import schema
from datastore.schema import INFO, REJECT, WARN, Invalid

NAME = "נועה כהן"


def codes(problems, level=None):
    return [p.code for p in problems if level is None or p.level == level]


def row(**kw):
    base = {"number": "0001", "grade": "85", "feedback": "", "points": "20;30;35", "approved": "", "review": "",
            "graded_at": "2026-11-01T10:00:00", "graded_by": "אורי"}
    base.update(kw)
    return base


Q = [20.0, 30.0, 50.0]


def test_a_good_row_has_no_problems():
    assert schema.check_grade_row(row(), max_grade=100, question_points=Q) == []
    assert schema.check_grade_row(row(grade="", points=""), max_grade=100, question_points=Q) == []  # not graded yet


@pytest.mark.parametrize("number", ["", "abc", "12a", " ", "١٢٣٤", "1234567"])  # "0001 " is trimmed, so it is fine
def test_bad_numbers_are_rejected(number):
    assert codes(schema.check_grade_row(row(number=number)), REJECT) == ["bad_number"]


@pytest.mark.parametrize("grade,code", [("abc", "grade_not_numeric"), ("nan", "grade_not_numeric"), ("inf", "grade_not_numeric"),
                                        ("1e400", "grade_not_numeric"), ("-5", "grade_out_of_range"), ("100.5", "grade_out_of_range"),
                                        ("1000", "grade_out_of_range"), (NAME, "grade_not_numeric")])
def test_bad_grades_are_rejected_and_not_echoed(grade, code):
    ps = schema.check_grade_row(row(grade=grade), max_grade=100, question_points=Q)
    assert codes(ps, REJECT) == [code]
    assert NAME not in ps[0].message and (grade not in ps[0].message or grade in ("inf", "nan"))  # values are never echoed


def test_grade_range_without_a_known_maximum_still_rejects_negatives():
    assert codes(schema.check_grade_row(row(grade="-1"))) == ["grade_out_of_range"]
    assert codes(schema.check_grade_row(row(grade="250"))) == []  # no maximum known: cannot judge


@pytest.mark.parametrize("points,code", [("a;b;c", "points_not_numeric"), ("10;20", "points_length"), ("10;20;30;40", "points_length"),
                                         ("25;10;10", "points_out_of_rubric"), ("-1;10;10", "points_out_of_rubric"), ("1e400;0;0", "points_not_numeric")])
def test_bad_points_are_rejected(points, code):
    assert codes(schema.check_grade_row(row(points=points), max_grade=100, question_points=Q), REJECT) == [code]


def test_points_without_a_rubric_only_reject_negatives_and_time_is_a_warning():
    assert codes(schema.check_grade_row(row(points="99;99"))) == []
    assert codes(schema.check_grade_row(row(points="-2;5"))) == ["points_out_of_rubric"]
    ps = schema.check_grade_row(row(graded_at="yesterday"))
    assert codes(ps, WARN) == ["bad_time"] and codes(ps, REJECT) == []
    assert codes(schema.check_grade_row(row(feedback="x" * 6000)), WARN) == ["feedback_too_long"]


def test_require_raises_only_on_reject():
    schema.require(schema.check_grade_row(row(graded_at="junk")))  # a warning passes
    with pytest.raises(Invalid) as e:
        schema.require(schema.check_grade_row(row(grade="abc")))
    assert "אינו מספר" in str(e.value) and e.value.problems[0].code == "grade_not_numeric"


def test_valid_grade_and_parse_points():
    assert schema.valid_grade(row(grade="85"), 100) == 85.0
    assert schema.valid_grade(row(grade="85"), None) == 85.0
    for g in ("abc", "", "-1", "101", "nan", "inf"):
        assert schema.valid_grade(row(grade=g), 100) is None
    assert schema.valid_grade(None, 100) is None
    assert schema.parse_points("1;2.5;0") == [1.0, 2.5, 0.0] and schema.parse_points("1;x") is None and schema.parse_points("") is None


# ---------- notes ----------
def test_notes_shapes():
    good = {"mistakes": [["א"], []], "unsure": [False, True], "points": [10, 20], "review_kind": "uncertain", "marks": [{"page": 1}]}
    assert schema.check_notes(good, number="0001", n_questions=2) == []
    assert codes(schema.check_notes([1, 2], number="0001"), REJECT) == ["notes_not_object"]
    assert codes(schema.check_notes({"mistakes": "x"}, number="0001"), REJECT) == ["notes_mistakes_shape"]
    assert codes(schema.check_notes({"mistakes": [["ok"], [3]]}, number="0001"), REJECT) == ["notes_mistakes_shape"]
    assert codes(schema.check_notes({"mistakes": [[], [], []]}, number="0001", n_questions=2), WARN) == ["notes_length"]
    assert codes(schema.check_notes({"unsure": "yes"}, number="0001"), WARN) == ["notes_unsure_shape"]
    assert codes(schema.check_notes({"points": ["a"]}, number="0001"), WARN) == ["notes_points_shape"]
    assert codes(schema.check_notes({"review_kind": "weird"}, number="0001"), WARN) == ["notes_review_kind"]
    assert codes(schema.check_notes({"marks": "x"}, number="0001"), WARN) == ["notes_marks_shape"]
    ps = schema.check_notes({"review_kind": NAME}, number="0001")
    assert NAME not in ps[0].message


# ---------- details ----------
def test_details_shapes():
    good = {"id": "3438636", "course": "Linear Algebra", "name": "Assignment 0", "max_grade": 100,
            "rubric": {"questions": [{"label": "א", "points": 40, "deductions": [{"text": "חסר", "points": 5}]}, {"label": "ב", "points": 60}]},
            "questions": [{"sheet": "דף", "numbers": [1]}]}
    assert schema.check_details(good) == []
    assert codes(schema.check_details("x"), REJECT) == ["details_not_object"]
    assert codes(schema.check_details({"id": "abc"}), REJECT) == ["details_id"]
    assert codes(schema.check_details({"course": 5}), REJECT) == ["details_type"]
    for mg in (0, -3, 5000, "abc", float("inf")):
        assert codes(schema.check_details({"max_grade": mg}), REJECT) == ["details_max_grade"], mg
    assert codes(schema.check_details({"rubric": {"questions": "x"}}), REJECT) == ["details_rubric"]
    assert codes(schema.check_details({"rubric": {"questions": ["x"]}}), REJECT) == ["details_rubric"]
    assert codes(schema.check_details({"rubric": {"questions": [{"points": -1}]}}), REJECT) == ["details_rubric_points"]
    assert codes(schema.check_details({"rubric": {"questions": [{"points": 70}, {"points": 70}]}}), WARN) == ["details_rubric_sum"]
    assert codes(schema.check_details({"rubric": {"questions": [{"points": 10, "deductions": ["x"]}]}}), WARN) == ["details_rubric_deduction"]
    assert codes(schema.check_details({"rubric": 7}), REJECT) == ["details_rubric"]
    assert codes(schema.check_details({"rubric": "free text"}), REJECT) == []
    assert codes(schema.check_details({"questions": {}}), REJECT) == ["details_questions"]


# ---------- key ----------
def krow(n, pid, folder=None):
    return {"number": n, "anon_file": f"{n}.pdf", "participant_id": pid,
            "original_folder": folder if folder is not None else f"{NAME}_{pid}_assignsubmission_file", "original_file": "hw.pdf"}


def test_key_rows():
    assert schema.check_key_rows([krow("0001", "1001"), krow("0001", "1001"), krow("0002", "1002")]) == []  # two files, one student
    ps = schema.check_key_rows([krow("0001", "1001"), krow("0001", "1002")])
    assert codes(ps) == ["key_number_two_participants"]
    ps = schema.check_key_rows([krow("0001", "1001"), krow("0002", "1001")])
    assert sorted(codes(ps)) == ["key_participant_two_numbers", "key_participant_two_numbers"]
    assert codes(schema.check_key_rows([krow("abc", "1001")])) == ["key_bad_number"]
    assert codes(schema.check_key_rows([krow("0001", "x1")])) == ["key_bad_participant"]
    assert codes(schema.check_key_rows([krow("0001", "1001", folder=f"{NAME}_9999_assignsubmission_file")])) == ["key_folder_mismatch"]
    for p in schema.check_key_rows([krow("0001", "1001"), krow("0002", "1001"), krow("0003", "1003", folder="Other_1_x")]):
        assert NAME not in p.message and "1001" not in p.message and "1003" not in p.message  # numbers of works only, never participants


def test_summarize_counts_levels():
    ps = [schema.Problem("a", "x", REJECT), schema.Problem("b", "y", WARN), schema.Problem("c", "z", INFO), schema.Problem("d", "w", WARN)]
    assert schema.summarize(ps) == {"reject": 1, "warn": 2, "info": 1}
    assert json.dumps([p.as_dict() for p in ps], ensure_ascii=False)


# ---------- fuzz: never an exception, never the planted text ----------
JUNK = [None, "", " ", "abc", "nan", "inf", "-inf", "1e400", "-5", "0", "100.5", "12;13", "‏", "😀", [], {}, True, 1e308, -0.0,
        NAME, f"x{NAME}y", "0001", "١٢", "1;2;3;4;5;6;7;8;9;10", "a" * 7000]


def test_fuzz_validators_never_raise_and_never_echo_the_planted_name():
    r = random.Random(11)
    for _ in range(3000):
        rw = {k: r.choice(JUNK) for k in ("number", "grade", "feedback", "points", "approved", "review", "graded_at", "graded_by")}
        for v in (rw, {"mistakes": r.choice(JUNK), "unsure": r.choice(JUNK), "points": r.choice(JUNK), "review_kind": r.choice(JUNK), "marks": r.choice(JUNK)},
                  {"id": r.choice(JUNK), "course": r.choice(JUNK), "max_grade": r.choice(JUNK), "rubric": r.choice(JUNK + [{"questions": r.choice(JUNK)}]), "questions": r.choice(JUNK)}):
            pass
        ps = schema.check_grade_row(rw, max_grade=r.choice([None, 100, 50]), question_points=r.choice([None, Q, []]))
        ps += schema.check_notes({"mistakes": r.choice(JUNK), "unsure": r.choice(JUNK), "points": r.choice(JUNK), "review_kind": r.choice(JUNK)}, number="0007")
        ps += schema.check_details({"id": r.choice(JUNK), "course": r.choice(JUNK), "max_grade": r.choice(JUNK),
                                    "rubric": r.choice(JUNK + [{"questions": r.choice(JUNK)}]), "questions": r.choice(JUNK)})
        ps += schema.check_key_rows([{"number": r.choice(JUNK), "participant_id": r.choice(JUNK), "original_folder": r.choice(JUNK)} for _ in range(3)])
        text = json.dumps([p.as_dict() for p in ps], ensure_ascii=False)
        assert NAME not in text
        assert all(p.level in (REJECT, WARN, INFO) for p in ps)
