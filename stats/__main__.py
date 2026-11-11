"""python -m stats show <מזהה מטלה> | show --all | show --course "Linear Algebra" [--brief] [--fresh]
python -m stats build <מזהה מטלה>      מחשב ושומר את המטלה ב-Statistics/
python -m stats rebuild                 כל המטלות, וה-CSV
python -m stats export [--csv <path>] [--sqlite <path>]
python -m stats report <מזהה מטלה> [--pdf <path>] [--preview <png>]   דוח PDF לצוות (stats/report.py)

זו הדרך של Claude ושל שורת הפקודה לקרוא את המסד: לא פותחים את הקבצים בעצמנו. `show` קורא דרך `stats.read`: הקובץ
השמור אם הוא עדיין משקף את תיקיית המטלה, אחרת חישוב מחדש ושמירה. `--fresh` מחשב בלי לקרוא ובלי לשמור.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from moodle import paths

from . import assignment_dirs, build, compute_assignment, export_csv, export_sqlite, read, rebuild
from .store import stats_dir


def _targets(args) -> list[Path]:
    if getattr(args, "id", None):
        a = paths.find_assignment(args.id)
        if a is None:
            raise SystemExit(f"אין מטלה עם מזהה מודל {args.id} בתוך {paths.data_dir()}")
        return [a]
    dirs = assignment_dirs(paths.data_dir())
    if getattr(args, "course", None):
        dirs = [d for d in dirs if d.parent.name == args.course]
        if not dirs:
            raise SystemExit(f"אין קורס \"{args.course}\" בתוך {paths.data_dir()}")
    return dirs


def _brief(s: dict) -> str:
    c, g = s["counts"], s["grade"]
    pct = "—" if g["pass_pct"] is None else f"{g['pass_pct']}%"
    return (f"{s['key']}: נבדקו {c['graded']}/{c['submitted']}, ממוצע {g['mean']}, חציון {g['median']}, עוברים {pct}, "
            f"לבדיקה ידנית {c['needs_review']}, אושרו {c['approved']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m stats", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="הסטטיסטיקה של מטלה אחת, של קורס או של הכול, כ-JSON")
    s.add_argument("id", nargs="?", help="מזהה המטלה במודל")
    s.add_argument("--all", action="store_true", help="כל המטלות בכל הקורסים")
    s.add_argument("--course", help='קורס אחד, בשם התיקייה שלו ("Linear Algebra")')
    s.add_argument("--brief", action="store_true", help="שורה אחת למטלה במקום JSON מלא")
    s.add_argument("--fresh", action="store_true", help="לחשב עכשיו בלי לקרוא מהקובץ ובלי לשמור")
    b = sub.add_parser("build", help="מחשב ושומר מטלה אחת ב-Statistics/")
    b.add_argument("id")
    sub.add_parser("rebuild", help="מחשב ושומר את כל המטלות, וכותב את All assignments.csv")
    e = sub.add_parser("export", help="ייצוא לניתוח: CSV (ברירת מחדל ב-Statistics/) ו/או SQLite מקומי")
    e.add_argument("--csv", help="נתיב ל-CSV (ברירת מחדל: Statistics/All assignments.csv)")
    e.add_argument("--sqlite", help="נתיב לקובץ SQLite (במחשב שלך, לא בתיקייה המשותפת)")
    r = sub.add_parser("report", help="דוח PDF של מטלה אחת לצוות: היקף, זמן, עלות, ציונים, סעיפים, טעויות, תובנות")
    r.add_argument("id")
    r.add_argument("--pdf", help='נתיב ל-PDF (ברירת מחדל: "Statistics/<קורס>/Assignment N - grading report <תאריך>.pdf")')
    r.add_argument("--preview", help="לשמור גם תמונת PNG של העמוד הראשון בנתיב הזה")
    args = p.parse_args(argv)
    from dashboard import shared_folder  # the same folder as the site and the other commands: the synced one
    shared_folder.use_for_commands()

    if args.cmd == "show":
        if not (args.id or args.all or args.course):
            p.error("צריך מזהה מטלה, או --all, או --course")
        out = [(compute_assignment if args.fresh else read)(a) for a in _targets(args)]
        if args.brief:
            for s_ in out:
                print(_brief(s_))
        else:
            json.dump(out[0] if args.id else out, sys.stdout, ensure_ascii=False, indent=1)
            print()
        return 0
    if args.cmd == "build":
        s_ = build(_targets(args)[0])
        print(_brief(s_))
        print(f"נשמר ב-{stats_dir(paths.data_dir())}")
        return 0
    if args.cmd == "rebuild":
        for s_ in rebuild(paths.data_dir()):
            print(_brief(s_))
        print(f"נשמר ב-{stats_dir(paths.data_dir())} (וגם {paths.STATS_EXPORT})")
        return 0
    if args.cmd == "report":
        from . import report as _report

        out = _report.build_report(_targets(args)[0], args.pdf)
        print(f"PDF: {out}")
        if args.preview:
            print(f"PNG: {_report.preview_png(out, Path(args.preview))}")
        return 0
    if args.cmd == "export":
        root = paths.data_dir()
        if not args.sqlite or args.csv:
            print(f"CSV: {export_csv(root, args.csv)}")
        if args.sqlite:
            print(f"SQLite: {export_sqlite(root, args.sqlite)}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
