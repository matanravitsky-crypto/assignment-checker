"""בדיקה עם Claude משורת הפקודה, כמו `python -m moodle ingest`:

  python -m grading <מזהה מטלה>                 בודק את כל מה שעוד לא נבדק
  python -m grading <מזהה מטלה> --ids 0001 0002  בודק רק את ההגשות האלה (גם שוב)

את תיקיית המטלה מוצאים לפי המזהה, דרך ASSIGNMENT_DATA (ראו moodle/paths.py).

כאן הבדיקה לא מחוברת לטבלת הציונים למודל (Grades for Moodle.csv), ליומן האירועים ולסטטיסטיקה: grading לא מייבא
אותם, והדשבורד מחבר אותם בהפעלה (web_server.connect_stores). זה בטוח: ההעלאה בונה את הטבלה מחדש לפני שהיא
ממלאת את גיליון מודל, והעלאת הציונים קוראת את הציונים עצמם. כדי לראות אותה עכשיו: python -m moodle table <id>.

הגשה אחת מחוץ למערכת (הסקיל exercise-grader, grading/one_submission.py):
  python -m grading prepare|rules|rubric|mark ...
"""
from __future__ import annotations

import argparse
import sys

from moodle import paths, shared_folder

from . import grade, grade_edit, one_submission


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in one_submission.COMMANDS:  # הסקיל exercise-grader: הגשה אחת, בלי תיקיית מטלה
        return one_submission.main(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    shared_folder.use_for_commands()
    p = argparse.ArgumentParser(prog="python -m grading", description="בדיקת הגשות עם Claude",
                                epilog="הגשה אחת מחוץ למערכת: python -m grading prepare|rules|rubric|mark")
    p.add_argument("assignment_id", help="מזהה המטלה במודל (id ב-Assignment details.json)")
    p.add_argument("--ids", nargs="*", help="מספרי הגשות לבדיקה (ברירת מחדל: כל מה שעוד לא נבדק)")
    p.add_argument("--model", default=None, help="ברירת מחדל: GRADING_MODEL ב-.env, ובלעדיו " + grade.DEFAULT_MODEL)
    p.add_argument("--parallel", type=int, default=grade.DEFAULT_PARALLEL, help="כמה עבודות במקביל")
    args = p.parse_args(argv)

    labels = {"graded": "נבדקה", "failed": "נכשלה", "skipped": "כבר אושרה", "taken": "שמורה לבודק אחר"}
    try:
        folder = paths.assignment_dir(args.assignment_id)
        rep = grade.grade_assignment(folder, args.ids or None, model=args.model or grade.default_model(), parallel=args.parallel,
                                     on_progress=lambda n, what: print(f"  {n}: {labels[what]}"))
    except (FileNotFoundError, grade.NoApiKey, grade.NoRubric, grade.ClaudeLimit) as e:
        print(e)
        return 2
    print(rep.summary())
    for line in rep.notes + [f"{n}: {why}" for n, why in sorted(rep.failed.items())]:
        print(f"  {line}")
    if rep.review:
        print(f"  לבדיקה ידנית: {', '.join(rep.review)}")
    if rep.graded and grade_edit.moodle_table_builder() is None:
        print(f"  {paths.MOODLE_TABLE} לא נבנתה מחדש כאן (ההעלאה בונה אותה לפני שהיא שולחת). "
              f"כדי לראות אותה עכשיו: python -m moodle table {args.assignment_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
