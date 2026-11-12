"""website/rubric-points.js: the rubric as a written list, a question with its sections under it.

The component is pure (items in, text or HTML out), so these tests load it in Node and call it directly."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="needs Node.js")

SCRIPT = Path(__file__).resolve().parents[2] / "website" / "rubric-points.js"


def lines(items):
    code = ("const R = require(process.argv[1]); const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
            "process.stdout.write(JSON.stringify(R.lines(items)));")
    out = subprocess.run([NODE, "-e", code, str(SCRIPT)], input=json.dumps(items), capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    return json.loads(out)


def test_question_total_then_its_sections():
    items = [{"req": "קבוצות 11א", "pts": 3}, {"req": "קבוצות 11ב", "pts": 3}, {"req": "קבוצות 11ג", "pts": 8}]
    assert lines(items) == [
        "שאלה 11 (קבוצות) - 14 נקודות סך הכל",
        "שאלה 11 סעיף א - 3 נקודות",
        "שאלה 11 סעיף ב - 3 נקודות",
        "שאלה 11 סעיף ג - 8 נקודות",
    ]


def test_label_without_topic_and_question_without_sections():
    items = [{"req": "8א", "pts": 7}, {"req": "8ב", "pts": 8}, {"req": "16", "pts": 8}]
    assert lines(items) == ["שאלה 8 - 15 נקודות סך הכל", "שאלה 8 סעיף א - 7 נקודות", "שאלה 8 סעיף ב - 8 נקודות",
                            "שאלה 16 - 8 נקודות"]


def test_same_number_in_two_topics_stays_two_questions():
    items = [{"req": "קבוצות 6א", "pts": 2}, {"req": "מרוכבים 6א", "pts": 4}]
    assert lines(items) == ["שאלה 6 (קבוצות) - 2 נקודות סך הכל", "שאלה 6 סעיף א - 2 נקודות",
                            "שאלה 6 (מרוכבים) - 4 נקודות סך הכל", "שאלה 6 סעיף א - 4 נקודות"]


def test_label_that_does_not_fit_is_shown_as_written():
    assert lines([{"req": "בונוס", "pts": 5}]) == ["בונוס - 5 נקודות"]


def test_one_point_is_singular():
    assert lines([{"req": "3", "pts": 1}]) == ["שאלה 3 - 1 נקודה"]
