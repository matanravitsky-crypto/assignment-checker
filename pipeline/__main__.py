"""שורת הפקודה של האתר המחובר.

  python -m pipeline serve        מפעיל את האתר המחובר לתיקייה (כמו start.bat)
  python -m pipeline where        מראה איפה נמצאת תיקיית המערכת
  python -m pipeline list         הקורסים והמטלות, עם מספר ההגשות

המשיכה וההחזרה עצמן: python -m moodle ingest|upload <מזהה מטלה> (ראו CLAUDE.md).
"""
from __future__ import annotations

import argparse
import sys

from . import config, settings as cfg, team


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cfg.load_env()
    p = argparse.ArgumentParser(prog="python -m pipeline", description="בודק העבודות")
    sub = p.add_subparsers(dest="cmd", required=True)
    s_serve = sub.add_parser("serve", help="מפעיל את האתר המחובר לתיקייה")
    s_serve.add_argument("--port", type=int, default=8765)
    s_serve.add_argument("--no-open", action="store_true", help="לא לפתוח דפדפן")
    sub.add_parser("where", help="איפה נמצאת תיקיית המערכת")
    sub.add_parser("list", help="קורסים ומטלות")
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
    elif args.cmd == "list":
        for course_dir in team.courses(root):
            print(f"{course_dir.name} ({team.course_title(course_dir)})")
            items = team.assignments(course_dir)
            for a in items:
                numbers = {r.get("number") for r in a.key_rows()}
                print(f"  {a.dir.name} (מזהה {a.details().get('id')}): {len(numbers)} הגשות")
            if not items:
                print("  עוד אין מטלות")
    return 0


if __name__ == "__main__":
    sys.exit(main())
