"""python -m stats show <מזהה מטלה> | show --all | show --course "Linear Algebra"

מדפיס את הסטטיסטיקה של מטלה (JSON, מספרים בלבד), מחושבת עכשיו מתיקיית המטלה. זו הדרך של Claude ושל שורת
הפקודה לקרוא את המסד: לא פותחים את הקבצים בעצמנו. השמירה בתיקייה המשותפת (`build`, `rebuild`, `export`) נוספת בשלב 2
של docs/Statistics database plan.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from moodle import paths

from . import compute_assignment


def _targets(args) -> list[Path]:
    if args.id:
        a = paths.find_assignment(args.id)
        if a is None:
            raise SystemExit(f"אין מטלה עם מזהה מודל {args.id} בתוך {paths.data_dir()}")
        return [a]
    dirs = paths.assignment_dirs()
    if args.course:
        dirs = [d for d in dirs if d.parent.name == args.course]
        if not dirs:
            raise SystemExit(f"אין קורס \"{args.course}\" בתוך {paths.data_dir()}")
    return dirs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m stats", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="הסטטיסטיקה של מטלה אחת, של קורס או של הכול, כ-JSON")
    s.add_argument("id", nargs="?", help="מזהה המטלה במודל")
    s.add_argument("--all", action="store_true", help="כל המטלות בכל הקורסים")
    s.add_argument("--course", help='קורס אחד, בשם התיקייה שלו ("Linear Algebra")')
    s.add_argument("--brief", action="store_true", help="שורה אחת למטלה במקום JSON מלא")
    args = p.parse_args(argv)
    if not (args.id or args.all or args.course):
        p.error("צריך מזהה מטלה, או --all, או --course")
    out = [compute_assignment(a) for a in _targets(args)]
    if args.brief:
        for s_ in out:
            c, g = s_["counts"], s_["grade"]
            print(f"{s_['key']}: נבדקו {c['graded']}/{c['submitted']}, ממוצע {g['mean']}, חציון {g['median']}, "
                  f"עוברים {'—' if g['pass_pct'] is None else str(g['pass_pct']) + '%'}, לבדיקה ידנית {c['needs_review']}, אושרו {c['approved']}")
        return 0
    json.dump(out[0] if args.id else out, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
