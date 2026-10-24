"""עלות הבדיקה, מתוך `Grading usage*.jsonl` שכל ריצה של Claude Code כותבת בתיקייה המשותפת (`grading/claude_cli.py`).

מספרים בלבד: ריצות, טוקנים ועלות. העלות היא שווה ערך ל-API, לא חיוב: הבדיקה רצה במנוי של הצוות.
קוראים גם עותקים שנוצרו בסנכרון (`Grading usage-<PC>.jsonl`), וכל שורה נספרת פעם אחת גם אם היא בשני עותקים.
"""
from __future__ import annotations

import json
from pathlib import Path

PATTERN = "Grading usage*.jsonl"


def _num(x) -> float:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else 0.0


def summary(root: Path) -> dict | None:
    """הסיכום לאתר, או None כשעוד לא נכתבה אף ריצה."""
    seen: set[str] = set()
    rows: list[dict] = []
    for f in sorted(root.glob(PATTERN)):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line in seen:
                continue
            seen.add(line)
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    if not rows:
        return None
    cost = sum(_num(r.get("cost_usd")) for r in rows)
    read = sum(_num(r.get("cache_read")) for r in rows)
    fresh = sum(_num(r.get("input")) + _num(r.get("cache_write")) for r in rows)
    models: dict[str, dict] = {}
    for r in rows:
        m = models.setdefault(str(r.get("model") or "?"), {"runs": 0, "costUsd": 0.0})
        m["runs"] += 1
        m["costUsd"] += _num(r.get("cost_usd"))
    for m in models.values():
        m["costUsd"] = round(m["costUsd"], 2)
    times = sorted(str(r["at"]) for r in rows if r.get("at"))
    return {"runs": len(rows), "costUsd": round(cost, 2), "avgUsd": round(cost / len(rows), 3),
            "cacheReadShare": round(read / (read + fresh), 2) if read + fresh else None,
            "models": models, "since": times[0] if times else None, "last": times[-1] if times else None}
