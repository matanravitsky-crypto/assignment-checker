"""עלות הבדיקה לאתר: מסכמים את יומן השימוש של Claude Code, מספרים בלבד."""
from __future__ import annotations

import json

from dashboard import actions, usage


def row(**kw):
    base = {"at": "2026-10-23T10:00:00", "model": "claude-opus-5-5", "input": 5, "output": 6000,
            "cache_read": 80000, "cache_write": 20000, "turns": 2, "cost_usd": 1.0}
    return json.dumps({**base, **kw})


def test_no_log_means_no_summary(tmp_path):
    assert usage.summary(tmp_path) is None


def test_sums_runs_cost_and_cache_share(tmp_path):
    (tmp_path / "Grading usage.jsonl").write_text(
        "\n".join([row(), row(cost_usd=0.5, cache_read=0, cache_write=0, input=100, model="claude-sonnet-5-5")]) + "\n", encoding="utf-8")
    s = usage.summary(tmp_path)
    assert s["runs"] == 2 and s["costUsd"] == 1.5 and s["avgUsd"] == 0.75
    assert s["cacheReadShare"] == round(80000 / (80000 + 20005 + 100), 2)
    assert s["models"] == {"claude-opus-5-5": {"runs": 1, "costUsd": 1.0}, "claude-sonnet-5-5": {"runs": 1, "costUsd": 0.5}}
    assert s["since"] == s["last"] == "2026-10-23T10:00:00"


def test_bad_lines_and_missing_numbers_do_not_break_it(tmp_path):
    (tmp_path / "Grading usage.jsonl").write_text(
        "not json\n\n[1, 2]\n" + row(cost_usd=None, cache_read=None, cache_write=None, input=None) + "\n", encoding="utf-8")
    s = usage.summary(tmp_path)
    assert s["runs"] == 1 and s["costUsd"] == 0 and s["cacheReadShare"] is None


def test_a_line_in_a_sync_copy_counts_once(tmp_path):
    line = row() + "\n"
    (tmp_path / "Grading usage.jsonl").write_text(line, encoding="utf-8")
    (tmp_path / "Grading usage-DESKTOP-ABC.jsonl").write_text(line + row(at="2026-10-23T11:00:00") + "\n", encoding="utf-8")
    s = usage.summary(tmp_path)
    assert s["runs"] == 2 and s["last"] == "2026-10-23T11:00:00"


def test_state_carries_the_usage_without_names(root):
    assert actions.state(root)["usage"] is None
    (root / "Grading usage.jsonl").write_text(row() + "\n", encoding="utf-8")
    st = actions.state(root)
    assert st["usage"]["runs"] == 1 and st["usage"]["costUsd"] == 1.0
