"""בדיקת העתקות משורת הפקודה, כמו `python -m grading`:

  python -m copying <מזהה מטלה>    משווה את כל ההגשות של המטלה וכותב Copying check.json

את תיקיית המטלה מוצאים לפי המזהה, דרך ASSIGNMENT_DATA (ראו moodle/paths.py).
"""
from __future__ import annotations

import argparse
import sys

from moodle import paths

from . import check


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m copying", description="חשד להעתקה בין הגשות (בלי Claude)")
    p.add_argument("assignment_id", help="מזהה המטלה במודל (id ב-Assignment details.json)")
    args = p.parse_args(argv)
    try:
        folder = paths.assignment_dir(args.assignment_id)
    except FileNotFoundError as e:
        print(e)
        return 2
    rep = check.check_assignment(folder, on_progress=lambda i, n: print(f"\r  {i}/{n} קבצים", end="", flush=True))
    print()
    print(rep.summary())
    for pair in rep.pairs:
        why = "; ".join(check.KIND_TEXT[r["kind"]] + (f" (עמודים {', '.join(f'{a}↔{b}' for a, b, _ in r['pages'])})"
                                                       if "pages" in r else "") for r in pair["reasons"])
        print(f"  {'!' if pair['level'] == 'strong' else '?'} {pair['a']} ↔ {pair['b']}: {why}")
    for group in rep.repeated:
        where = ", ".join(f"{n}/{p}" for n, p in group["pages"][:8]) + (" ..." if len(group["pages"]) > 8 else "")
        print(f"  עמוד שחוזר אצל {group['numbers']} הגשות (דף שאלות, או פתרון שעבר?): {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
