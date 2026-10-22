"""Command line for the Moodle steps.

    python -m moodle status <assignment id>
        What's done for the assignment, and any file names OneDrive would refuse.

    python -m moodle guide
        Rewrites the Hebrew "read me" files in the data folder.

    python -m moodle ingest <assignment id> [--zip PATH]
        Downloads ZIP -> data folder, extracted and numbered for grading.

    python -m moodle upload <assignment id> [--worksheet PATH]
        results.csv + marked/ -> upload/grades.csv and upload/feedback-N.zip.
"""

import argparse
from pathlib import Path

from moodle import guide, ingest, paths, status, upload


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m moodle")
    commands = parser.add_subparsers(dest="command", required=True)

    status_cmd = commands.add_parser("status", help="show what's done for an assignment")
    status_cmd.add_argument("assignment_id")

    commands.add_parser("guide", help="rewrite the Hebrew read-me files in the data folder")

    ingest_cmd = commands.add_parser("ingest", help="prepare a downloaded submissions ZIP")
    ingest_cmd.add_argument("assignment_id")
    ingest_cmd.add_argument("--zip", type=Path, help="default: newest matching ZIP in Downloads")

    upload_cmd = commands.add_parser("upload", help="build grades.csv and feedback.zip")
    upload_cmd.add_argument("assignment_id")
    upload_cmd.add_argument("--worksheet", type=Path, help="default: newest matching CSV in Downloads")
    upload_cmd.add_argument("--max-mb", type=int, default=upload.MAX_ZIP_BYTES // 1_000_000,
                            help="largest ZIP Moodle takes (default: %(default)s)")
    upload_cmd.add_argument("--for-claude", action="store_true",
                            help="split for Claude in Chrome, which uploads up to 10 MB per file")

    args = parser.parse_args()

    if args.command == "guide":
        for path in guide.write_guides(paths.data_dir()):
            print(path)
        return

    target = paths.assignment_dir(args.assignment_id)

    if args.command == "status":
        report = status.status(target)
        print(f"Folder: {target}")
        print(f"Assignment details (assignment.json): {'yes' if report['assignment_info'] else 'missing'}")
        print(f"Questions and solutions (materials/): {report['materials']} files")
        print(f"Numbered submissions (anon/): {report['anon_files']}")
        mapping_rows, results_rows = report["mapping_rows"], report["results_rows"]
        print(f"Key (mapping.csv): {'missing' if mapping_rows is None else f'{mapping_rows} rows'}")
        print(f"Grades (results.csv): {'not yet' if results_rows is None else f'{results_rows} rows'}")
        print(f"Marked files (marked/): {report['marked_files']}")
        print(f"Ready to upload (upload/): {report['upload_files']} files")
        if report["unsafe_names"]:
            print(f"OneDrive may refuse {len(report['unsafe_names'])} names: {', '.join(report['unsafe_names'][:10])}")
        else:
            print("All file names are safe to sync")
        return

    if args.command == "ingest":
        rows = ingest.ingest(args.assignment_id, args.zip)
        students = len({row["number"] for row in rows})
        print(f"{students} submissions, {len(rows)} files -> {target / 'anon'}")
    else:
        worksheet = args.worksheet or upload.find_worksheet(args.assignment_id)
        if args.for_claude:
            args.max_mb = upload.CLAUDE_MAX_ZIP_BYTES // 1_000_000
        report = upload.prepare_upload(target, worksheet, args.max_mb * 1_000_000)
        print(f"Submissions: {report['submissions']}, results: {report['results']}")
        if report["missing_results"]:
            print(f"No result yet for {len(report['missing_results'])}: {', '.join(report['missing_results'][:20])}")
        if report["unknown_numbers"]:
            print(f"Results for numbers not in mapping.csv: {', '.join(report['unknown_numbers'])}")
        if report["grades_filled"] is None:
            print("No grading worksheet found: download it from Moodle to build grades.csv")
        else:
            print(f"grades.csv: {report['grades_filled']} grades filled")
        print(f"feedback ZIPs: {', '.join(z.name for z in report['feedback_zips']) or 'none'}")
        if report["too_big"]:
            limit = "Claude in Chrome" if args.for_claude else "Moodle"
            print(f"Too big for {limit} ({args.max_mb} MB), save smaller: {', '.join(report['too_big'])}")
        print(f"-> {target / 'upload'} (steps in '{upload.INSTRUCTIONS_FILE}')")


if __name__ == "__main__":
    main()
