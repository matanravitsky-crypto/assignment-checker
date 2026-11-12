"""המודולריות: כל חלק במערכת עצמאי, כך שאפשר להוציא אותו (למשל לסקיל) בלי לשבור את השאר. ההסבר: docs/Modularity.md.

הכללים, ומה שכל בדיקה כאן שומרת:
1. אין תלות מעגלית: חלק משתמש רק בחלקים שלפניו ב-LAYERS (tools/modules.py), אף פעם לא באחד שאחריו.
2. הליבה (CORE: השמות והכללים של התיקייה המשותפת) לא משתמשת בשום דבר מחוץ לעצמה, אז כל חלק יכול לקחת אותה איתו.
3. חלק לוקח מחלק אחר רק את מה שהחלק האחר הצהיר עליו ב-INTERFACE שב-__init__.py שלו, ואף פעם לא שם פרטי (_x).
4. לכל חלק README שאומר מה נכנס אליו ומה יוצא ממנו (כותרת "## ממשק").
5. הבדיקות של חלק (tests/<חלק>/) לא צריכות שום חלק שמעליו. בדיקות של איך חלקים מתחברים נמצאות ב-tests/integration/.
הבדיקות קוראות את הקוד (ast) ולא מריצות אותו, חוץ מבדיקה 3 שמוודאת שכל שם בממשק באמת קיים.
"""
from __future__ import annotations

import ast
import importlib
from collections import defaultdict
from pathlib import Path

import pytest

from tools import modules as M

ALL_PARTS = M.LAYERS + ["website", "onedrive"]  # שני האחרונים בלי פייתון: מדברים עם הדשבורד דרך HTTP


def production_files():
    for part in M.LAYERS:
        for f in M.part_files(part):
            if M.module_name(f) not in M.ALIASES:
                yield part, f


def where(use: M.Use) -> str:
    return f"{M.module_name(Path(use.file))}:{use.line}"


def interface(part: str) -> dict:
    tree = ast.parse((M.REPO / part / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        target = node.targets[0] if isinstance(node, ast.Assign) else getattr(node, "target", None)
        if isinstance(target, ast.Name) and target.id == "INTERFACE":
            return ast.literal_eval(node.value)
    raise AssertionError(f"ב-{part}/__init__.py אין INTERFACE")


def test_every_python_part_has_a_place_in_the_layers():
    found = sorted(p.parent.name for p in M.REPO.glob("*/__init__.py") if p.parent.name not in ("tests", "tools"))
    assert sorted(M.LAYERS) == found, "חלק חדש? צריך לשים אותו ב-LAYERS (tools/modules.py), מעל כל מה שהוא משתמש בו"


def test_a_part_uses_only_parts_below_it():
    wrong = []
    for part, f in production_files():
        for imp in M.imports(f):
            other = M.part_of(imp.module)
            if M.ours(imp.module) and other != part and M.LAYERS.index(other) > M.LAYERS.index(part):
                wrong.append(f"{where(imp)} -> {imp.module} ({part} מתחת ל-{other})")
    assert not wrong, "חלק משתמש בחלק שמעליו:\n" + "\n".join(wrong)


def test_no_two_parts_depend_on_each_other():
    """אם A תלוי ב-B, אז B לא תלוי ב-A, גם לא דרך חלק שלישי."""
    graph: dict[str, set[str]] = defaultdict(set)
    for part, f in production_files():
        graph[part] |= {M.part_of(i.module) for i in M.imports(f) if M.ours(i.module) and M.part_of(i.module) != part}

    def reaches(a: str, b: str, seen=()) -> bool:
        return any(n == b or (n not in seen and reaches(n, b, (*seen, n))) for n in graph[a])

    cycles = sorted(f"{a} <-> {b}" for a in graph for b in graph[a] if reaches(b, a))
    assert not cycles, "תלות מעגלית: " + ", ".join(cycles)


def test_the_core_needs_nothing_outside_itself():
    wrong = []
    for m in M.CORE:
        for imp in M.imports(M.module_file(m)):
            if M.ours(imp.module) and imp.module not in M.CORE:
                wrong.append(f"{where(imp)} -> {imp.module}")
    assert not wrong, "הליבה משתמשת במשהו שלא בליבה:\n" + "\n".join(wrong)


def test_a_part_takes_from_another_only_what_it_declared():
    wrong = []
    for part, f in production_files():
        for use in M.uses(f):
            other = M.part_of(use.module)
            if other == part:
                continue
            sub = use.module[len(other) + 1:]
            declared = interface(other)
            if sub not in declared:
                wrong.append(f"{where(use)}: {use.module} לא בממשק של {other}")
            elif use.name.startswith("_"):
                wrong.append(f"{where(use)}: {use.module}.{use.name} הוא שם פרטי")
            elif use.name and declared[sub] != "*" and use.name not in declared[sub]:
                wrong.append(f"{where(use)}: {use.module}.{use.name} לא בממשק של {other}")
    assert not wrong, "חלק לוקח מחלק אחר משהו שלא בממשק שלו (INTERFACE ב-__init__.py):\n" + "\n".join(sorted(set(wrong)))


@pytest.mark.parametrize("part", M.LAYERS)
def test_every_name_in_an_interface_exists(part):
    for sub, names in interface(part).items():
        module = importlib.import_module(f"{part}.{sub}" if sub else part)
        if names == "*":
            assert f"{part}.{sub}" in M.CORE, f"{part}.{sub}: רק הליבה פתוחה כולה"
            continue
        missing = [n for n in names if not hasattr(module, n)]
        assert not missing, f"{module.__name__} מצהיר על {missing} ואין לו"
        assert not [n for n in names if n.startswith("_")], f"{module.__name__}: שם פרטי בממשק"


@pytest.mark.parametrize("part", ALL_PARTS)
def test_every_part_says_what_goes_in_and_what_comes_out(part):
    readme = M.REPO / part / "README.md"
    assert readme.is_file(), f"ל-{part}/ אין README.md"
    assert "## ממשק" in readme.read_text(encoding="utf-8"), f"ב-{part}/README.md אין \"## ממשק\" (מה נכנס, מה יוצא, במה תלוי)"


HELPERS = {"tests", "tests.sample_files", "tests.fakes"}  # עזרים של כל הבדיקות; fakes משתמש רק ב-moodle


@pytest.mark.parametrize("part", M.LAYERS)
def test_a_parts_tests_need_nothing_above_it(part):
    wrong = []
    for f in sorted((M.REPO / "tests" / part).glob("*.py")):
        for imp in M.imports(f):
            if imp.module.startswith("tests"):
                if imp.module not in HELPERS and not imp.module.startswith(f"tests.{part}"):
                    wrong.append(f"{where(imp)} -> {imp.module}")
            elif M.ours(imp.module) and M.LAYERS.index(M.part_of(imp.module)) > M.LAYERS.index(part):
                wrong.append(f"{where(imp)} -> {imp.module}")
    assert not wrong, (f"הבדיקות של {part} צריכות חלק שמעליו. בדיקה של איך חלקים מתחברים עוברת ל-tests/integration/:\n"
                       + "\n".join(wrong))
