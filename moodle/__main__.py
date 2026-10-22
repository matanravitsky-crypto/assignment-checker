"""Command line for the Moodle steps. Assignments are named by their Moodle id.

    python -m moodle ingest <assignment id> [--course "Linear Algebra" --name "Assignment 1 - Vectors"] [--zip PATH] [--parts]
        Downloaded ZIP -> the assignment's folder, numbered for grading.
        --course and --name (folder names) are needed the first time an assignment comes in.
        --parts takes every ZIP of the assignment in Downloads, for one downloaded 100 submissions at a time.

    python -m moodle status <assignment id>
        What's done for the assignment, and any file names OneDrive would refuse.

    python -m moodle upload <assignment id> [--worksheet PATH] [--for-claude]
        Grades and marked files -> "3 - Ready to upload to Moodle", with upload steps.

    python -m moodle guide
        Rewrites the README files (in Hebrew).
"""

import argparse
from pathlib import Path

from moodle import guide, ingest, paths, status, upload


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m moodle")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest_cmd = commands.add_parser("ingest", help="prepare a downloaded submissions ZIP")
    ingest_cmd.add_argument("assignment_id")
    ingest_cmd.add_argument("--course", help="course folder name in English, for a new assignment")
    ingest_cmd.add_argument("--name", help="assignment folder name in English, for a new assignment")
    ingest_cmd.add_argument("--zip", type=Path, help="default: newest matching ZIP in Downloads")
    ingest_cmd.add_argument("--parts", action="store_true",
                            help="the assignment was downloaded in parts: take all its ZIPs in Downloads")

    status_cmd = commands.add_parser("status", help="show what's done for an assignment")
    status_cmd.add_argument("assignment_id")

    upload_cmd = commands.add_parser("upload", help="build what goes back to Moodle")
    upload_cmd.add_argument("assignment_id")
    upload_cmd.add_argument("--worksheet", type=Path, help="default: newest matching CSV in Downloads")
    upload_cmd.add_argument("--max-mb", type=int, default=upload.MAX_ZIP_BYTES // 1_000_000,
                            help="largest ZIP Moodle takes (default: %(default)s)")
    upload_cmd.add_argument("--for-claude", action="store_true",
                            help="split for Claude in Chrome, which uploads up to 10 MB per file")

    commands.add_parser("guide", help="rewrite the README files")

    args = parser.parse_args()

    if args.command == "guide":
        for path in guide.write_guides(paths.data_dir()):
            print(path)
        return

    if args.command == "ingest":
        zips = ingest.find_parts(args.assignment_id) if args.parts else args.zip
        rows = ingest.ingest(args.assignment_id, zips, args.course, args.name)
        students = len({row["number"] for row in rows})
        print(f"{students} submissions, {len(rows)} files -> {paths.assignment_dir(args.assignment_id) / paths.TO_GRADE}")
        return

    target = paths.assignment_dir(args.assignment_id)

    if args.command == "status":
        report = status.status(target)
        key_rows, grades_rows = report["key_rows"], report["grades_rows"]
        print(f"Folder: {target}")
        print(f"Downloads from Moodle: {', '.join(report['downloads']) or 'none'}")
        print(f"To grade ({paths.TO_GRADE}): {report['to_grade']}")
        print(f"Key ({paths.KEY}): {'missing' if key_rows is None else f'{key_rows} rows'}")
        print(f"Grades ({paths.GRADES}): {'not yet' if grades_rows is None else f'{grades_rows} rows'}")
        print(f"Marked ({paths.MARKED}): {report['marked']}")
        print(f"Ready to upload ({paths.UPLOAD}): {report['upload_files']} files")
        if report["unsafe_names"]:
            print(f"OneDrive may refuse {len(report['unsafe_names'])} names: {', '.join(report['unsafe_names'][:10])}")
        else:
            print("All file names are safe to sync")
        return

    worksheet = args.worksheet or upload.find_worksheet(args.assignment_id)
    if args.for_claude:
        args.max_mb = upload.CLAUDE_MAX_ZIP_BYTES // 1_000_000
    report = upload.prepare_upload(target, worksheet, args.max_mb * 1_000_000)
    print(f"Submissions: {report['submissions']}, grades: {report['results']}")
    if report["missing_results"]:
        print(f"No grade yet for {len(report['missing_results'])}: {', '.join(report['missing_results'][:20])}")
    if report["unknown_numbers"]:
        print(f"Grades for numbers not in the key table: {', '.join(report['unknown_numbers'])}")
    if report["grades_filled"] is None:
        print("No grading worksheet found: download it from Moodle to fill in the grades")
    else:
        print(f"{upload.GRADES_FOR_MOODLE}: {report['grades_filled']} grades filled")
    print(f"ZIPs: {len(report['feedback_zips'])}")
    if report["too_big"]:
        limit = "Claude in Chrome" if args.for_claude else "Moodle"
        print(f"Too big for {limit} ({args.max_mb} MB), save smaller: {', '.join(report['too_big'])}")
    print(f"-> {target / paths.UPLOAD} (steps in '{upload.INSTRUCTIONS_FILE}')")


if __name__ == "__main__":
    main()
