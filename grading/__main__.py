"""בדיקה עם Claude משורת הפקודה, כמו `python -m moodle ingest`:

  python -m grading <מזהה מטלה>                 בודק את כל מה שעוד לא נבדק
  python -m grading <מזהה מטלה> --ids 0001 0002  בודק רק את ההגשות האלה (גם שוב)

את תיקיית המטלה מוצאים לפי המזהה, דרך ASSIGNMENT_DATA (ראו moodle/paths.py).
"""
from __future__ import annotations

import argparse
import sys

from dashboard.settings import load_env
from moodle import paths

from . import grade


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    p = argparse.ArgumentParser(prog="python -m grading", description="בדיקת הגשות עם Claude")
    p.add_argument("assignment_id", help="מזהה המטלה במודל (id ב-Assignment details.json)")
    p.add_argument("--ids", nargs="*", help="מספרי הגשות לבדיקה (ברירת מחדל: כל מה שעוד לא נבדק)")
    p.add_argument("--model", default=grade.DEFAULT_MODEL)
    p.add_argument("--parallel", type=int, default=grade.DEFAULT_PARALLEL, help="כמה עבודות במקביל")
    args = p.parse_args(argv)

    labels = {"graded": "נבדקה", "failed": "נכשלה", "skipped": "כבר אושרה"}
    try:
        folder = paths.assignment_dir(args.assignment_id)
        rep = grade.grade_assignment(folder, args.ids or None, model=args.model, parallel=args.parallel,
                                     on_progress=lambda n, what: print(f"  {n}: {labels[what]}"))
    except (FileNotFoundError, grade.NoApiKey) as e:
        print(e)
        return 2
    print(rep.summary())
    for line in rep.notes + [f"{n}: {why}" for n, why in sorted(rep.failed.items())]:
        print(f"  {line}")
    if rep.review:
        print(f"  לבדיקה ידנית: {', '.join(rep.review)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
