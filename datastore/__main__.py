"""python -m datastore check <מזהה מטלה> | check --all      בדיקת שלמות (ראו doctor.py)
python -m datastore fix <מזהה מטלה> [--yes]                 תיקון של מה שבטוח; בלי --yes רק מראה מה היה נעשה
python -m datastore replay <מזהה מטלה> [--yes]              מה היומן אומר שאבד בקבצים, ושחזור (ledger.py)
python -m datastore history <מזהה מטלה> <מספר הגשה>         מי נתן לעבודה איזה ציון ומתי
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from moodle import paths

from . import doctor, ledger
from moodle.schema import INFO, REJECT, WARN

LEVEL_HE = {REJECT: "שגיאה", WARN: "אזהרה", INFO: "ידיעה"}


def _print(rep: doctor.Report) -> None:
    s = rep.as_dict()["summary"]
    print(f"== {rep.course}/{rep.folder} (מודל {rep.moodle_id}): {s['reject']} שגיאות, {s['warn']} אזהרות, {s['info']} ידיעות")
    for p in rep.problems:
        print(f"  [{LEVEL_HE.get(p.level, p.level)}] {p.message}")
    if rep.fixable:
        print(f"  אפשר לתקן לבד: {', '.join(sorted(set(rep.fixable)))}  (python -m datastore fix <id> --yes)")


def _target(mid: str) -> Path:
    a = paths.find_assignment(mid)
    if a is None:
        raise SystemExit(f"אין מטלה עם מזהה מודל {mid} בתוך {paths.data_dir()}")
    return a


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m datastore", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="בדיקת שלמות של מטלה או של הכול")
    c.add_argument("id", nargs="?")
    c.add_argument("--all", action="store_true")
    f = sub.add_parser("fix", help="תיקון של מה שבטוח לתקן לבד")
    f.add_argument("id")
    f.add_argument("--yes", action="store_true", help="לבצע באמת (בלי זה: רק מה היה נעשה)")
    r = sub.add_parser("replay", help="השוואת היומן לקבצים, ושחזור של מה שאבד")
    r.add_argument("id")
    r.add_argument("--yes", action="store_true")
    h = sub.add_parser("history", help="כל אירועי הציון של עבודה אחת")
    h.add_argument("id")
    h.add_argument("number")
    args = p.parse_args(argv)
    if args.cmd == "check":
        if not args.id and not args.all:
            p.error("צריך מזהה מטלה או --all")
        reps = doctor.check_all(paths.data_dir()) if args.all else [doctor.check(_target(args.id))]
        for rep in reps:
            _print(rep)
        return 1 if any(x.level == REJECT for rep in reps for x in rep.problems) else 0
    if args.cmd == "fix":
        for line in doctor.fix(_target(args.id), dry_run=not args.yes):
            print(line)
        if not args.yes:
            print("(בדיקה בלבד. עם --yes זה יבוצע)")
        return 0
    if args.cmd == "replay":
        lines = ledger.replay(_target(args.id), dry_run=not args.yes)
        for line in lines:
            print(line)
        if not lines:
            print("הקבצים תואמים ליומן.")
        elif not args.yes:
            print("(בדיקה בלבד. עם --yes זה יבוצע)")
        return 0
    if args.cmd == "history":
        for e in ledger.history(_target(args.id), args.number):
            what = e.get("grade", e.get("to", e.get("error", "")))
            print(f"{e.get('at', '')[:19]}  {e.get('action')}  {e.get('by')}  {what}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
