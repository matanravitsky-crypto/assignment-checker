"""שורת הפקודה של בודק העבודות.

  python -m pipeline serve                 מפעיל את האתר המחובר ל-OneDrive (כמו start.bat)
  python -m pipeline where                 מראה איפה נמצאת תיקיית הקורס
  python -m pipeline init                  מארגן את התיקייה: הגדרות, הסבר ותיקייה לכל מטלה
  python -m pipeline pull "קורס" "מטלה"    מושך הגשות למטלה (ממודל ומקובצי ZIP בקליטה)
  python -m pipeline demo                  יוצר קורס "הדגמה" עם הגשות לדוגמה, כדי לראות איך זה עובד
"""
from __future__ import annotations

import argparse
import sys

from . import config, service, settings as cfg


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cfg.load_env()
    p = argparse.ArgumentParser(prog="python -m pipeline", description="בודק העבודות")
    sub = p.add_subparsers(dest="cmd", required=True)
    s_serve = sub.add_parser("serve", help="מפעיל את האתר המחובר ל-OneDrive")
    s_serve.add_argument("--port", type=int, default=8765)
    s_serve.add_argument("--no-open", action="store_true", help="לא לפתוח דפדפן")
    sub.add_parser("where", help="איפה נמצאת תיקיית הקורס")
    sub.add_parser("init", help="מארגן את התיקייה")
    s_pull = sub.add_parser("pull", help="מושך הגשות למטלה")
    s_pull.add_argument("course")
    s_pull.add_argument("assignment")
    s_demo = sub.add_parser("demo", help="קורס הדגמה עם הגשות לדוגמה")
    s_demo.add_argument("--count", type=int, default=6)
    args = p.parse_args(argv)

    if args.cmd == "serve":
        from .server import serve
        serve(args.port, not args.no_open)
        return 0

    try:
        root = config.find_root()
    except config.FolderNotFound as e:
        print(e)
        return 2

    if args.cmd == "where":
        print(root)
        return 0
    try:
        service.check_ownership(root)
    except service.ForeignStructure as e:
        print(e)
        return 3
    if False:
        pass
    elif args.cmd == "init":
        s = service.init(root)
        print(f"התיקייה מוכנה: {root}")
        for c in s.courses:
            print(f"  {c.name}: {', '.join(a.name for a in c.assignments)}")
    elif args.cmd == "pull":
        _print_report(service.pull(root, args.course, args.assignment))
    elif args.cmd == "demo":
        from .demo import moodle_zip
        from .workspace import Workspace
        ws = Workspace(root, "הדגמה", "תרגיל לדוגמה")
        ws.ensure()
        (ws.inbox / "DEMO-תרגיל לדוגמה-1.zip").write_bytes(moodle_zip("תרגיל לדוגמה", count=args.count))
        _print_report(service.pull(root, "הדגמה", "תרגיל לדוגמה"))
        print(f"\nאפשר למחוק את התיקייה {ws.dir.parent} כשמסיימים.")
    return 0


def _print_report(rep: service.PullReport) -> None:
    print(f"{rep.course} / {rep.assignment}: {rep.result.summary()}")
    for line in rep.notes:
        print(f"  {line}")
    for line in rep.result.problems:
        print(f"  דורשת טיפול: {line}")


if __name__ == "__main__":
    sys.exit(main())
