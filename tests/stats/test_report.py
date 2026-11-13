"""stats/report.py: the PDF report for the team, built from the statistics only, with nothing that names a student."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pymupdf

import stats
from moodle import paths
from stats import __main__ as cli
from stats import report
from tests.stats.test_compute import NAMES, folder  # noqa: F401  (the fixture: an assignment folder full of names)


def test_groups_sections_by_question_and_strips_latex():
    assert report._group("קבוצות 11א") == "קבוצות 11" and report._group("מרוכבים 8ד") == "מרוכבים 8"
    assert report._group("שאלה 3") == "שאלה 3" and report._group("קבוצות") == "קבוצות"
    qs = [{"label": l} for l in ("קבוצות 11א", "קבוצות 11ב", "קבוצות 12א", "מרוכבים 6א")]
    assert [(g, len(items)) for g, items in report.groups(qs)] == [("קבוצות 11", 2), ("קבוצות 12", 1), ("מרוכבים 6", 1)]
    assert report._plain(r"כתב $A\neq B$ או $a\in\mathbb R$, $\varnothing$") == "כתב A≠ B או a∈ℝ, ∅"
    assert report._short("א" * 80, 20).endswith("…") and len(report._short("א" * 80, 20)) == 20


def test_insights_come_from_the_numbers(folder):  # noqa: F811
    s = stats.compute_assignment(folder)
    lines = report.insights(s)
    assert any("76" in x and "80" in x for x in lines)             # mean and median
    assert any("מרוכבים 6" in x for x in lines)                      # the weakest question is named
    assert any("מחכות לבודק אנושי" in x for x in lines)
    assert all(name not in " ".join(lines) for name in NAMES.values())


def test_report_pdf_has_the_sections_and_names_nobody(folder, tmp_path):  # noqa: F811
    out = report.build_report(folder, tmp_path / "r.pdf", today=date(2026, 11, 11))
    assert out.is_file()
    doc = pymupdf.open(str(out))
    text = "\n".join(p.get_text() for p in doc).replace("\xa0", " ")
    assert 2 <= doc.page_count <= 8
    doc.close()
    for pid, name in NAMES.items():
        assert pid not in text and name not in text and name.split()[0] not in text
    assert "assignsubmission" not in text
    for n in ("0001", "0002", "0003", "0004", "0005", "0006", "0007"):
        assert n not in text
    for heading in ("דוח בדיקה", "ציונים", "היקף וזמן", "עלות וטוקנים", "טעויות נפוצות", "תובנות לצוות", "11/11/2026"):
        assert heading in text


def test_default_path_is_next_to_the_json_and_the_cli_builds_it(folder, capsys, tmp_path):  # noqa: F811
    root = folder.parent.parent
    (root / paths.USAGE_LOG).write_text(json.dumps({"at": "2026-11-01T09:59:00", "model": "claude-opus-5-5", "input": 5, "output": 100,
                                                    "cache_read": 1000, "cache_write": 200, "turns": 3, "cost_usd": 0.5}) + "\n", encoding="utf-8")
    assert report.report_path(folder, date(2026, 11, 11)) == root / paths.STATISTICS / "Linear Algebra" / "Assignment 0 - grading report 2026-11-11.pdf"
    assert cli.main(["report", "3438636", "--preview", str(tmp_path / "p.png")]) == 0
    printed = capsys.readouterr().out
    pdf = Path(printed.split("PDF: ", 1)[1].splitlines()[0])
    assert pdf.is_file() and pdf.parent == root / paths.STATISTICS / "Linear Algebra" and (tmp_path / "p.png").is_file()
    text = "\n".join(p.get_text() for p in pymupdf.open(str(pdf))).replace("\xa0", " ")
    assert "claude-opus-5-5" in text.replace("\n", "").replace("\xad", "-") and "$0.50" in text  # Story extracts hyphens as soft hyphens
