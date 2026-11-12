"""בדיקת העתקות משורת הפקודה, כמו `python -m grading`:

  python -m copying <מזהה מטלה>       משווה את כל ההגשות של המטלה וכותב Copying check.json
  python -m copying <תיקיית המטלה>    אותו דבר, לתיקייה שנותנים (או לתיקיית "1 - Submissions to grade" שבה)

את תיקיית המטלה מוצאים לפי המזהה, דרך ASSIGNMENT_DATA (ראו moodle/paths.py). הסקיל copying-check מריץ את הקובץ הזה.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from moodle import paths, shared_folder

from . import check


def find(what: str) -> Path:
    """תיקיית המטלה: לפי נתיב (תיקיית המטלה, או "1 - Submissions to grade" שבתוכה), ואחרת לפי מזהה המטלה במודל."""
    given = Path(what).expanduser()
    if given.is_dir():
        folder = given.parent if given.name == paths.TO_GRADE else given
        if not (folder / paths.TO_GRADE).is_dir():
            raise FileNotFoundError(f'בתיקייה {folder} אין "{paths.TO_GRADE}"')
        return folder
    return paths.assignment_dir(what)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    shared_folder.use_for_commands()
    p = argparse.ArgumentParser(prog="python -m copying", description="חשד להעתקה בין הגשות (בלי Claude)")
    p.add_argument("assignment_id", help="מזהה המטלה במודל (id ב-Assignment details.json), או הנתיב של תיקיית המטלה")
    args = p.parse_args(argv)
    try:
        folder = find(args.assignment_id)
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
