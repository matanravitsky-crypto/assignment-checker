"""website/plain-math.js: a comment with LaTeX as a readable Hebrew sentence (math left-to-right, same line, no $).

The component is pure (text in, text or HTML out), so these tests load it in Node and call it directly. The examples
are real "common mistake" texts from the grading notes (each was cut at 80 characters when saved)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="needs Node.js")

SCRIPT = Path(__file__).resolve().parents[2] / "website" / "plain-math.js"


def run(fn: str, texts: list[str]):
    code = (f"const P = require(process.argv[1]); const texts = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
            f"process.stdout.write(JSON.stringify(texts.map((t) => P.{fn}(t))));")
    out = subprocess.run([NODE, "-e", code, str(SCRIPT)], input=json.dumps(texts), capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    return json.loads(out)


def plain(*texts):
    return run("plain", list(texts))


def test_latex_symbols_become_plain_symbols():
    assert plain(r"כתב $\{0,0\}$ במקום $\{(0,0)\}$ (בפעם הראשונה במטלה; אחר כך הערה בלבד)") == [
        "כתב {0,0} במקום {(0,0)} (בפעם הראשונה במטלה; אחר כך הערה בלבד)"]
    assert plain(r"קיבל $t=t+1$ וענה $\varnothing$", r"כתב $\{\infty\}$ במקום המילה") == [
        "קיבל t=t+1 וענה ∅", "כתב {∞} במקום המילה"]


def test_relations_get_spaces_and_display_math_is_the_same_line():
    assert plain(r"ענה $$2a\neq 6a$$ באותה אות", r"ענה $A\neq B$ אבל") == ["ענה 2a ≠ 6a באותה אות", "ענה A ≠ B אבל"]


def test_blackboard_sets_and_powers():
    assert plain(r"במרחב $\mathbb{R}^3$ ובמישור $\mathbb{R}^2$", r"חישב $x^2$ במקום $x^{-1}$") == [
        "במרחב ℝ³ ובמישור ℝ²", "חישב x² במקום x⁻¹"]


def test_a_formula_cut_in_the_middle_ends_with_dots_not_with_code():
    cut_in_formula = r'כתב במילים במקום הקבוצה, כמו "קבוצה אינסופית", "אינסוף פתרונות", "ישר" או $\{\in'
    assert plain(cut_in_formula) == ['כתב במילים במקום הקבוצה, כמו "קבוצה אינסופית", "אינסוף פתרונות", "ישר" או…']
    cut_after_formulas = r"טעות חשבון בקבוע או בשורת הסתירה, כמו $0=3-i$ או $2+2i$ שהפך ל-$3+2i$, ואז $\var"
    assert plain(cut_after_formulas) == ["טעות חשבון בקבוע או בשורת הסתירה, כמו 0=3-i או 2+2i שהפך ל-3+2i, ואז…"]


def test_a_text_cut_at_80_characters_says_so_and_a_whole_one_does_not():
    cut = "כתב במילים במקום הקבוצה, כמו " + "ל" * 51  # 80 characters, no ending
    assert len(cut) == 80 and plain(cut) == [cut + "…"]
    whole = "נימוק לא פורמלי"
    assert plain(whole) == [whole]


def test_html_isolates_each_formula_left_to_right_and_uses_the_sites_escape():
    code = ("const P = require(process.argv[1]); const esc = (s) => String(s).replace(/</g, '&lt;');"
            "process.stdout.write(P.html('כתב $a<b$ ו-<i>', esc));")
    html = subprocess.run([NODE, "-e", code, str(SCRIPT)], capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout
    assert html == 'כתב <bdi class="pm" dir="ltr">a&lt;b</bdi> ו-&lt;i>'
    assert "$" not in html
