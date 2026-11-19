"""Command line for the Moodle steps. Assignments are named by their Moodle id.

    python -m moodle ingest <assignment id> [--course "Linear Algebra" --name "Assignment 1 - Vectors"] [--zip PATH ...]
        Downloaded ZIP(s) -> the assignment's folder, numbered for grading. By default every ZIP of the assignment
        waiting in Downloads: one "download all", or a ZIP per page of the grading table downloaded by hand.
        --course and --name (folder names) are needed the first time an assignment comes in.

    python -m moodle status <assignment id>
        What's done for the assignment, and any file names OneDrive would refuse.

    python -m moodle upload <assignment id> [--worksheet PATH] [--max-mb N] [--per-zip N]
        The return by hand: marked files that are new or changed since their last upload -> ZIPs of Moodle's size in
        "3 - Ready to upload to Moodle/Upload batch <id>/", the batch list (so `record` works), the grades filled into
        Moodle's worksheet when one was downloaded, and "Upload steps.txt". Nothing here touches Moodle.

    python -m moodle send <assignment id> [--dry-run] [--yes]
        Marked files -> Moodle, through Claude in Chrome. Prepares the batch (new or changed work only), prints
        its summary (numbers only), asks "להעלות למודל? (y/N)" unless --yes, uploads ZIP by ZIP and logs each one.
        --dry-run only checks the page and attaches the file, then cancels (Moodle imports at once): nothing is imported or logged.
        Files only: the grades go up only with send-grades.
        Refused while an upload or a pull of the assignment runs (the lock files). Exit code 1 if it stopped before the end.

    python -m moodle send-grades <assignment id> [--dry-run] [--yes]
        Grades -> Moodle, only when asked: the numbers whose marked files are in Moodle, through Moodle's grading
        worksheet (moodle/send_grades.py). Confirmed in Moodle only when its preview matches; --dry-run stops there.

    python -m moodle record <assignment id> "<zip name>"
        After uploading a ZIP of the current batch by hand (from its "Upload batch <id>" folder): writes its files to
        "Upload log.csv". Refused when the ZIP there is missing or changed since the batch was prepared.

    python -m moodle guide
        Rewrites the README files (in Hebrew).
"""

import argparse
import re
import sys
from pathlib import Path

from moodle import guide, ingest, lock, paths, send, send_grades, status, upload, upload_log


def make_driver() -> send.MoodleDriver:
    """The real driver starts Claude in Chrome, so it is built (and imported) only when it is going to be used."""
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


def print_list(only_id: str | None = None) -> None:
    """The data folder (the synced shared one, or a local copy) and one line per assignment: course, folder, Moodle id,
    Hebrew title, and the counts. Numbers only. This is how a person (or Claude) tells which assignment is meant."""
    data = paths.data_dir()
    where = "התיקייה המשותפת המסונכרנת" if paths.in_shared_folder(data / "x") else "עותק מקומי (ASSIGNMENT_DATA או ~)"
    print(f"תיקיית הנתונים: {data}  [{where}]")
    if not data.is_dir():
        print("התיקייה לא קיימת במחשב הזה. צריך את התיקייה המשותפת (OneDrive: YallaLinearit, \"Add shortcut to My files\") "
              "או ASSIGNMENT_DATA ב-.env שמצביע על עותק של \"Exercise Checking System\".")
        return
    found = 0
    for folder in paths.assignment_dirs():
        info = paths.read_info_or_none(folder) or {}
        mid = str(info.get("id") or "")
        if only_id and mid != str(only_id):
            continue
        found += 1
        rep = status.status(folder)
        returned = len({r["number"] for r in upload_log.read_log(folder)})
        pulled = ingest.pulls(folder)
        slot = re.match(r"Assignment (\d+)", folder.name)
        print(f"{folder.parent.name} / {folder.name}" + (f"  (הגשה {slot.group(1)})" if slot else ""))
        print(f"    מזהה מודל: {mid or 'עוד אין'}   כותרת: {info.get('title') or '-'}   מועד: {(info.get('due') or '-')[:16].replace('T', ' ')}")
        print(f"    נמשכו: {rep['to_grade']}   בדוקות: {rep['marked']}   הוחזרו: {returned}   "
              f"משיכה אחרונה: {pulled[-1] if pulled else 'אף פעם'}")
    if only_id and not found:
        print(f"אין מטלה עם מזהה מודל {only_id} בתיקייה הזו.")


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
        target, summary.id, make_driver(), dry_run=args.dry_run,
        on_progress=lambda index, total, name: print(f"{index}/{total} {name}"))
    print(f"הושלמו {len(report.done_zips)} מתוך {report.total_zips} ZIP, נרשמו ביומן {report.recorded} קבצים")
    if report.stopped is not None:
        print(f"נעצר ({report.stopped}): {report.message}")
        return 1
    return 0


def run_send_grades(target: Path, args) -> int:
    """Only when asked: the grades of the numbers whose files are in Moodle. Returns the exit code."""
    todo = send_grades.pending(target)
    if not todo:
        print("אין ציונים חדשים להעלאה")
        return 0
    print(f"{len(todo)} ציונים יעלו למודל, דרך גיליון הציונים של מודל")
    if not args.yes:
        try:
            answer = input("להעלות את הציונים? (y/N) ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("לא הועלה כלום")
            return 0
    report = send_grades.send_grades(target, make_driver(), dry_run=args.dry_run)
    print(report.message)
    return 0 if report.status in ("done", "nothing", "dry_run_ok") else 1


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Hebrew messages, even when the output is piped
    from . import shared_folder  # the same folder as the site: the synced one, unless ASSIGNMENT_DATA says
    shared_folder.use_for_commands()
    parser = argparse.ArgumentParser(prog="python -m moodle")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest_cmd = commands.add_parser("ingest", help="prepare a downloaded submissions ZIP")
    ingest_cmd.add_argument("assignment_id")
    ingest_cmd.add_argument("--course", help="course folder name in English, for a new assignment")
    ingest_cmd.add_argument("--name", help="assignment folder name in English, for a new assignment")
    ingest_cmd.add_argument("--expected", type=int, help="how many submitted, as Moodle's page shows (the report compares)")
    ingest_cmd.add_argument("--zip", type=Path, action="append", dest="zips",
                            help="a ZIP downloaded by hand; repeat it for several. Default: every ZIP of the assignment "
                                 "waiting in Downloads (or the list of parts the site's download left there)")

    status_cmd = commands.add_parser("status", help="show what's done for an assignment")
    status_cmd.add_argument("assignment_id")

    upload_cmd = commands.add_parser("upload", help="build what goes back to Moodle")
    upload_cmd.add_argument("assignment_id")
    upload_cmd.add_argument("--worksheet", type=Path, help="default: newest matching CSV in Downloads")
    upload_cmd.add_argument("--max-mb", type=int, default=upload.MAX_ZIP_BYTES // 1_000_000,
                            help="largest ZIP Moodle takes, as its upload page says (default: %(default)s)")
    upload_cmd.add_argument("--per-zip", type=int, default=upload.PER_ZIP,
                            help=f"at most this many students in a ZIP (default {upload.PER_ZIP}; 0 = no limit): lighter imports")

    send_cmd = commands.add_parser("send", help="upload the marked files to Moodle with Claude in Chrome")
    send_cmd.add_argument("assignment_id")
    send_cmd.add_argument("--dry-run", action="store_true", help="check the page and attach the file, then cancel: import and log nothing")
    send_cmd.add_argument("--yes", action="store_true", help="don't ask before uploading")
    grades_cmd = commands.add_parser("send-grades", help="upload the grades to Moodle (only when asked)")
    grades_cmd.add_argument("assignment_id")
    grades_cmd.add_argument("--dry-run", action="store_true", help="stop at Moodle's preview and cancel: nothing changes")
    grades_cmd.add_argument("--yes", action="store_true", help="don't ask before uploading")

    record_cmd = commands.add_parser("record", help="log a ZIP that was uploaded by hand")
    record_cmd.add_argument("assignment_id")
    record_cmd.add_argument("zip_name")

    table_cmd = commands.add_parser("table", help="build Grades for Moodle.csv: each grade next to its Moodle participant")
    table_cmd.add_argument("assignment_id")

    commands.add_parser("guide", help="rewrite the README files")

    list_cmd = commands.add_parser("list", help="where the data folder is, and every assignment with its id and state")
    list_cmd.add_argument("assignment_id", nargs="?", help="only this assignment")

    args = parser.parse_args()

    if args.command == "guide":
        for path in guide.write_guides(paths.data_dir()):
            print(path)
        return

    if args.command == "ingest":
        downloads = args.zips or ingest.find_downloads(args.assignment_id)
        print(f"לוקח {len(downloads)} קבצים מההורדות:")  # Moodle's names: course code and the assignment's title, no student
        for path in downloads:
            print(f"  {path.name}  ({path.stat().st_size / 1_000_000:.1f} MB)")
        rows = ingest.ingest(args.assignment_id, downloads, args.course, args.name, expected=args.expected)
        students = len({row["number"] for row in rows})
        target = paths.assignment_dir(args.assignment_id)
        print(f"{students} submissions, {len(rows)} files -> {target / paths.TO_GRADE}")
        if (target / paths.PULL_REPORT).exists():
            print((target / paths.PULL_REPORT).read_text(encoding="utf-8-sig"))
        return

    if args.command == "list":
        print_list(args.assignment_id)
        return

    target = paths.assignment_dir(args.assignment_id)

    if args.command == "send":
        raise SystemExit(run_send(target, args))
    if args.command == "send-grades":
        raise SystemExit(run_send_grades(target, args))

    if args.command == "record":
        try:
            zip_path = upload_log.batch_zip(target, args.zip_name)  # in the current batch's folder, unchanged since prepared
            rows = upload_log.record_zip(target, zip_path.name, lock.me())
        except ValueError as unknown:
            print(unknown)
            raise SystemExit(1)
        print(f"{rows} קבצים נרשמו ביומן")
        return

    if args.command == "table":
        from moodle import moodle_table
        rep = moodle_table.build(target)
        print(f"{paths.MOODLE_TABLE}: {rep['rows']} ציונים, כל אחד ליד מזהה המשתתף שלו במודל"
              + ("" if rep["written"] else " (לא השתנה)"))
        why = {"no_participant": "אין להם מזהה משתתף בטבלת המפתח", "key_problem": "טבלת המפתח לא חד-משמעית לגביהם",
               "invalid_grade": "הציון לא חוקי"}
        for kind, numbers in rep["left_out"].items():
            print(f"לא נכנסו ({why[kind]}): {', '.join(numbers[:30])}" + (" ועוד" if len(numbers) > 30 else ""))
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

    # upload: the return by hand. A batch like the automatic one (only work that is new or changed since its last
    # upload, a batch list so `record` works), in ZIPs of Moodle's size, plus the grades in Moodle's worksheet
    worksheet = args.worksheet or upload.find_worksheet(args.assignment_id)
    try:
        summary = send.prepare_batch(target, args.max_mb * 1_000_000, worksheet=worksheet, per_zip=args.per_zip)
    except ValueError as blocked:  # includes BatchBlocked
        print(blocked)
        raise SystemExit(1)
    print_summary(summary)
    if not summary.zips:
        print("אין עבודות בדוקות חדשות להעלאה (מה שכבר נרשם ביומן ההעלאה לא נארז שוב)")
    else:
        print(f"אומת מחדש מהדיסק: {summary.verified['students']} סטודנטים, {summary.verified['files']} קבצים, "
              f"כל קובץ מול טבלת המפתח והעבודה המסומנת ({paths.RETURN_REPORT})")
    if worksheet is None:
        print(f"לא נמצא גיליון ציונים של מודל בהורדות: הציונים לא מולאו. מורידים אותו במודל (פעולות ← הורדת גיליון ציונים; "
              f"צריך ש\"גיליון ציונים לא מקוון\" יהיה דלוק) ומריצים שוב, או נותנים --worksheet")
    else:
        print(f"{upload.GRADES_FOR_MOODLE}: {summary.grades_filled} ציונים מולאו מתוך {summary.worksheet_students} בגיליון "
              f"({worksheet.name})")
    print(f"-> {target / paths.UPLOAD} (השלבים ב-'{upload.INSTRUCTIONS_FILE}')")
    if summary.zips:
        print(f"דף ההעלאה במודל (לגרור לשם כל ZIP, לפי הסדר): {paths.MOODLE_UPLOAD_ZIP_PAGE.format(id=summary.assignment_id)}")
    if summary.grades_filled:
        print(f"דף העלאת הציונים (אחרי ה-ZIP-ים): {paths.MOODLE_UPLOAD_GRADES_PAGE.format(id=summary.assignment_id)}")


if __name__ == "__main__":
    main()
