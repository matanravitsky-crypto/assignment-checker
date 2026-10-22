"""Command line for the Moodle steps. Assignments are named by their Moodle id.

    python -m moodle ingest <assignment id> [--course "Linear Algebra" --name "Assignment 1 - Vectors"] [--zip PATH]
        Downloaded ZIP -> the assignment's folder, numbered for grading.
        --course and --name (folder names) are needed the first time an assignment comes in.

    python -m moodle status <assignment id>
        What's done for the assignment, and any file names OneDrive would refuse.

    python -m moodle upload <assignment id> [--worksheet PATH] [--for-claude]
        Grades and marked files -> "3 - Ready to upload to Moodle", with upload steps.

    python -m moodle send <assignment id> [--dry-run] [--yes] [--simulate]
        Marked files -> Moodle, through Claude in Chrome. Prepares the batch (new or changed work only), prints
        its summary (numbers only), asks "להעלות למודל? (y/N)" unless --yes, uploads ZIP by ZIP and logs each one.
        --dry-run only checks the page and attaches the file, then cancels (Moodle imports at once): nothing is imported or logged; --simulate never touches Moodle.
        Exit code 1 if it stopped before the end.

    python -m moodle record <assignment id> "<zip name>"
        After uploading a ZIP by hand: writes its files to "Upload log.csv".

    python -m moodle guide
        Rewrites the README files (in Hebrew).
"""

import argparse
import sys
from pathlib import Path

from moodle import guide, ingest, lock, paths, send, status, upload, upload_log


def make_driver(simulate: bool) -> send.MoodleDriver:
    """The real driver starts Claude in Chrome, so it is built (and imported) only when it is going to be used."""
    if simulate:
        return send.SimulatedDriver()
    from moodle import claude_driver
    return claude_driver.ClaudeChromeDriver()


def print_summary(summary: send.BatchSummary) -> None:
    """The batch in numbers only: no names."""
    print(f"מטלה {summary.assignment_id}: {summary.title}")
    print(f"{summary.students} סטודנטים, {summary.files} קבצים, {len(summary.zips)} ZIP")
    for zip_info in summary.zips:
        print(f"  {zip_info['name']}: {zip_info['count']} קבצים, {zip_info['mb']} MB")
    if summary.too_big:
        print(f"גדולים מדי, לא נכללו ({len(summary.too_big)}): {', '.join(summary.too_big)}")
    if summary.resubmitted:
        print(f"הוגשו מחדש אחרי הבדיקה, לא נכללו ({len(summary.resubmitted)}): {', '.join(summary.resubmitted)}")
    if summary.not_approved:
        print(f"עדיין לא אושרו, ויעלו בכל זאת: {len(summary.not_approved)}")


def run_send(target: Path, args) -> int:
    """Returns the exit code."""
    try:
        summary = send.prepare_batch(target)
    except ValueError as blocked:  # includes BatchBlocked
        print(blocked)
        return 1
    if not summary.zips:
        print("אין עבודות חדשות להעלאה")
        return 0
    print_summary(summary)
    if not args.yes:
        try:
            answer = input("להעלות למודל? (y/N) ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("לא הועלה כלום")
            return 0
    if args.dry_run:
        print("ריצת ניסיון: בודקים את הדף ומצרפים את הקובץ, ואז מבטלים. שום דבר לא יובא ולא נרשם ביומן")
    report = send.run_batch(
        target, summary.id, make_driver(args.simulate), dry_run=args.dry_run,
        on_progress=lambda index, total, name: print(f"{index}/{total} {name}"))
    print(f"הושלמו {len(report.done_zips)} מתוך {report.total_zips} ZIP, נרשמו ביומן {report.recorded} קבצים")
    if report.stopped is not None:
        print(f"נעצר ({report.stopped}): {report.message}")
        return 1
    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Hebrew messages, even when the output is piped
    parser = argparse.ArgumentParser(prog="python -m moodle")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest_cmd = commands.add_parser("ingest", help="prepare a downloaded submissions ZIP")
    ingest_cmd.add_argument("assignment_id")
    ingest_cmd.add_argument("--course", help="course folder name in English, for a new assignment")
    ingest_cmd.add_argument("--name", help="assignment folder name in English, for a new assignment")
    ingest_cmd.add_argument("--zip", type=Path, help="default: newest matching ZIP in Downloads")

    status_cmd = commands.add_parser("status", help="show what's done for an assignment")
    status_cmd.add_argument("assignment_id")

    upload_cmd = commands.add_parser("upload", help="build what goes back to Moodle")
    upload_cmd.add_argument("assignment_id")
    upload_cmd.add_argument("--worksheet", type=Path, help="default: newest matching CSV in Downloads")
    upload_cmd.add_argument("--max-mb", type=int, default=upload.MAX_ZIP_BYTES // 1_000_000,
                            help="largest ZIP Moodle takes (default: %(default)s)")
    upload_cmd.add_argument("--for-claude", action="store_true",
                            help="split for Claude in Chrome, which uploads up to 10 MB per file")

    send_cmd = commands.add_parser("send", help="upload the marked files to Moodle with Claude in Chrome")
    send_cmd.add_argument("assignment_id")
    send_cmd.add_argument("--dry-run", action="store_true", help="check the page and attach the file, then cancel: import and log nothing")
    send_cmd.add_argument("--yes", action="store_true", help="don't ask before uploading")
    send_cmd.add_argument("--simulate", action="store_true", help="don't touch Moodle (for trying it out)")

    record_cmd = commands.add_parser("record", help="log a ZIP that was uploaded by hand")
    record_cmd.add_argument("assignment_id")
    record_cmd.add_argument("zip_name")

    commands.add_parser("guide", help="rewrite the README files")

    args = parser.parse_args()

    if args.command == "guide":
        for path in guide.write_guides(paths.data_dir()):
            print(path)
        return

    if args.command == "ingest":
        rows = ingest.ingest(args.assignment_id, args.zip, args.course, args.name)
        students = len({row["number"] for row in rows})
        print(f"{students} submissions, {len(rows)} files -> {paths.assignment_dir(args.assignment_id) / paths.TO_GRADE}")
        return

    target = paths.assignment_dir(args.assignment_id)

    if args.command == "send":
        raise SystemExit(run_send(target, args))

    if args.command == "record":
        try:
            rows = upload_log.record_zip(target, args.zip_name, lock.me())
        except ValueError as unknown:
            print(unknown)
            raise SystemExit(1)
        print(f"{rows} קבצים נרשמו ביומן")
        return

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
