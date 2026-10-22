"""שורת הפקודה של האתר המחובר.

  python -m dashboard serve        מפעיל את האתר המחובר לתיקייה (כמו start.bat)
  python -m dashboard where        מראה איפה נמצאת תיקיית המערכת
  python -m dashboard list         הקורסים והמטלות, עם מספר ההגשות

המשיכה וההחזרה עצמן: python -m moodle ingest|upload <מזהה מטלה> (ראו CLAUDE.md).
"""
from __future__ import annotations

import argparse
import sys

from . import folder_view, settings as cfg, shared_folder


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cfg.load_env()
    p = argparse.ArgumentParser(prog="python -m dashboard", description="בודק חכם")
    sub = p.add_subparsers(dest="cmd", required=True)
    s_serve = sub.add_parser("serve", help="מפעיל את האתר המחובר לתיקייה")
    s_serve.add_argument("--port", type=int, default=8765)
    s_serve.add_argument("--no-open", action="store_true", help="לא לפתוח דפדפן")
    sub.add_parser("where", help="איפה נמצאת תיקיית המערכת")
    sub.add_parser("list", help="קורסים ומטלות")
    args = p.parse_args(argv)

    if args.cmd == "serve":
        from .web_server import serve
        serve(args.port, not args.no_open)
        return 0

    try:
        root = shared_folder.find_root()
    except shared_folder.FolderNotFound as e:
        print(e)
        return 2

    if args.cmd == "where":
        print(root)
    elif args.cmd == "list":
        for course_dir in folder_view.courses(root):
            print(f"{course_dir.name} ({folder_view.course_title(course_dir)})")
            items = folder_view.assignments(course_dir)
            for a in items:
                numbers = {r.get("number") for r in a.key_rows()}
                print(f"  {a.dir.name} (מזהה {a.details().get('id')}): {len(numbers)} הגשות")
            if not items:
                print("  עוד אין מטלות")
    return 0


if __name__ == "__main__":
    sys.exit(main())
