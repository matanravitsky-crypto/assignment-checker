"""Command line for the Moodle steps.

    python -m moodle pending
        Assignments in assignments.json past their due date and not yet
        downloaded on this computer, one id per line.

    python -m moodle ingest <assignment id> [--zip PATH]
        Downloads ZIP -> data folder, extracted and numbered for grading.

    python -m moodle upload <assignment id> [--worksheet PATH]
        results.csv + marked/ -> upload/grades.csv and upload/feedback-N.zip.
"""

import argparse
from pathlib import Path

from moodle import ingest, paths, schedule, upload


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m moodle")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("pending", help="list assignments to download now")

    ingest_cmd = commands.add_parser("ingest", help="prepare a downloaded submissions ZIP")
    ingest_cmd.add_argument("assignment_id")
    ingest_cmd.add_argument("--zip", type=Path, help="default: newest matching ZIP in Downloads")

    upload_cmd = commands.add_parser("upload", help="build grades.csv and feedback.zip")
    upload_cmd.add_argument("assignment_id")
    upload_cmd.add_argument("--worksheet", type=Path, help="default: newest matching CSV in Downloads")

    args = parser.parse_args()

    if args.command == "pending":
        for assignment in schedule.pending(schedule.load_assignments()):
            print(f"{assignment['id']}\t{assignment['course']} - {assignment['name']}")
        return

    target = paths.assignment_dir(args.assignment_id)

    if args.command == "ingest":
        rows = ingest.ingest(args.assignment_id, args.zip)
        students = len({row["number"] for row in rows})
        print(f"{students} submissions, {len(rows)} files -> {target / 'anon'}")
    else:
        worksheet = args.worksheet or upload.find_worksheet(args.assignment_id)
        report = upload.prepare_upload(target, worksheet)
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
            print(f"Too big for the extension, upload by hand: {', '.join(report['too_big'])}")
        print(f"-> {target / 'upload'}")


if __name__ == "__main__":
    main()
