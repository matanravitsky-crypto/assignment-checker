"""Prepare one assignment for work, without Claude: its folder and details, the exercise sheet, the official solution.

Run by the `start-assignment` skill (.claude/skills/start-assignment/SKILL.md) from the repo root:

    python .claude/skills/start-assignment/scripts/prepare.py status    --course "Linear Algebra" --slot 3
    python .claude/skills/start-assignment/scripts/prepare.py details   --course "Linear Algebra" --slot 3 --from details.json
    python .claude/skills/start-assignment/scripts/prepare.py add-sheet --course "Linear Algebra" --sheet 9 --topic "Vector spaces" \
                                                                        --file ~/Downloads/sheet09.pdf --solutions ~/Downloads/sol09.pdf
    python .claude/skills/start-assignment/scripts/prepare.py materials --course "Linear Algebra" --slot 3 --sheet 3 [--pages 10-14]
    python .claude/skills/start-assignment/scripts/prepare.py readme

Everything code can do is done here, so the skill spends tokens only on Moodle (Claude in Chrome) and on judgement:
- `status`: what the assignment already has (folder, details, פדגוגי files, submissions) and which exercise sheets the
  course has locally (`<course>/Course material/Sheets/Sheet N - <topic>.pdf` and `... - solutions.pdf`), as JSON.
- `details`: creates the slot folder (`Assignment N`, as the site's first pull would) and writes `Assignment details.json`
  from a JSON Claude copied off the assignment's Moodle page (id, title, due, questions, rules). Refuses a Moodle id
  that another folder has. Appends the page's text to the course's `Moodle - assignments, quizzes and pages.md`.
- `add-sheet`: files a sheet and its solutions downloaded from Moodle under the standard names in `Course material/Sheets/`.
- `materials`: copies the sheet into `פדגוגי/`, cuts the pages of the assigned questions out of the solutions PDF into
  the assignment's `Official solution.pdf` (grading sends it to Claude with every submission), copies the course's
  `Manual review rules.md`, creates `Working notes/`. The pages are found in the PDF's text layer: a question heading
  is ".N" at the start of a line (or at its end: Hebrew lines come out reversed), and questions are numbered in order.
- `readme`: rewrites the README.txt files (`python -m moodle guide`).

Student data never passes through here: this touches the assignment's details and the course material only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # scripts/ → start-assignment/ → skills/ → .claude/ → the repo
sys.path.insert(0, str(ROOT))

from moodle import guide, paths  # noqa: E402
from dashboard import folder_view  # noqa: E402

COURSE_MATERIAL = "Course material"
SHEETS = "Sheets"
MOODLE_PAGES = "Moodle - assignments, quizzes and pages.md"
SOLUTION = "Official solution.pdf"  # grading/grade.py SOLUTION, in the assignment folder
REVIEW_RULES = "Manual review rules.md"
WORKING_NOTES = "Working notes"
SHEET_RE = re.compile(r"^Sheet (\d+) - (.+?)( - solutions)?\.pdf$")
# A question heading in the text layer: ".7" at the start of a line, or " .7" at the end of a reversed RTL line.
# Whitespace (or the line start) must come right before the dot, so "0.5" and "x.12" don't count.
QUESTION_RE = re.compile(r"(?:^|(?<=\s))\.(\d{1,2})(?=\s|$)")
DUE_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2})?")
MONTHS = {"ינואר": 1, "פברואר": 2, "מרץ": 3, "מרס": 3, "אפריל": 4, "מאי": 5, "יוני": 6, "יולי": 7, "אוגוסט": 8,
          "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12}
MOODLE_DATE_RE = re.compile(r"(\d{1,2}) (\S+) (\d{4}),? (\d{1,2}):(\d{2})\s*(AM|PM)?", re.IGNORECASE)
DETAIL_FIELDS = ("id", "course_id", "course_title", "title", "due", "questions", "submission_rules", "grading_instructions")


class Problem(Exception):
    """Something the skill must tell the user (a Hebrew message), not a crash."""


# ---------- where things are ----------

def course_dir(course: str) -> Path:
    d = paths.data_dir() / course
    if not d.is_dir():
        raise Problem(f"אין תיקיית קורס בשם {course} ב-{paths.data_dir()}")
    return d


def assignment_dir(course: str, slot: int) -> Path | None:
    """The folder of הגשה <slot> in the course ("Assignment N" or "Assignment N - <words>"), if it exists."""
    found = [p for p in course_dir(course).iterdir() if p.is_dir() and folder_view.slot(p.name) == slot]
    if len(found) > 1:
        raise Problem(f"להגשה {slot} של {course} יש שתי תיקיות: " + ", ".join(p.name for p in found))
    return found[0] if found else None


def pedagogy_dir(assignment: Path) -> Path:
    for name in paths.PEDAGOGY:
        if (assignment / name).is_dir():
            return assignment / name
    return assignment / paths.PEDAGOGY[-1]  # "פדגוגי", the name the team uses


def sheets(course: str) -> dict[int, dict]:
    """The course's exercise sheets saved locally: number → {"topic", "sheet", "solutions"} (paths or None)."""
    folder = course_dir(course) / COURSE_MATERIAL / SHEETS
    out: dict[int, dict] = {}
    if not folder.is_dir():
        return out
    for p in sorted(folder.glob("*.pdf")):
        m = SHEET_RE.match(p.name)
        if not m:
            continue
        entry = out.setdefault(int(m.group(1)), {"topic": m.group(2), "sheet": None, "solutions": None})
        entry["solutions" if m.group(3) else "sheet"] = str(p)
    return out


def review_rules_source(course: str) -> Path | None:
    """The newest assignment (this course first, then any) that has a Manual review rules.md: the file is general."""
    candidates = []
    for folder in paths.assignment_dirs():
        f = pedagogy_dir(folder) / REVIEW_RULES
        if f.is_file():
            candidates.append((folder.parent.name == course, folder_view.slot(folder.name) or -1, f))
    return max(candidates)[2] if candidates else None


# ---------- details ----------

def moodle_date(text: str) -> str | None:
    """"יום שני, 2 נובמבר 2026, 11:59 PM" → "2026-11-02T23:59:00+02:00". An ISO date comes back as it is."""
    if not isinstance(text, str):
        return None
    m = DUE_RE.search(text)
    if m:
        iso = m.group(0)
        return iso if m.group(2) else iso + _offset(datetime.fromisoformat(iso[:16]))
    m = MOODLE_DATE_RE.search(text)
    if not m or m.group(2) not in MONTHS:
        return None
    day, month, year, hour, minute = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)), int(m.group(4)), int(m.group(5))
    if m.group(6):
        hour = hour % 12 + (12 if m.group(6).upper() == "PM" else 0)
    local = datetime(year, month, day, hour, minute)
    return local.strftime("%Y-%m-%dT%H:%M:00") + _offset(local)


def _offset(local: datetime) -> str:
    """Israel's UTC offset at that local time. zoneinfo when the computer has the tz database, else the DST rule
    (the last Friday before the last Sunday of March, until the last Sunday of October)."""
    try:
        from zoneinfo import ZoneInfo
        off = ZoneInfo("Asia/Jerusalem").utcoffset(local) or timedelta(hours=2)
    except Exception:  # no tzdata on this Windows
        off = timedelta(hours=3) if _dst_start(local.year) <= local < _dst_end(local.year) else timedelta(hours=2)
    minutes = int(off.total_seconds() // 60)
    return f"{'+' if minutes >= 0 else '-'}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def _last_sunday(year: int, month: int) -> datetime:
    d = datetime(year, month + 1, 1) - timedelta(days=1) if month < 12 else datetime(year, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _dst_start(year: int) -> datetime:
    return _last_sunday(year, 3) - timedelta(days=2) + timedelta(hours=2)  # the Friday before, 02:00


def _dst_end(year: int) -> datetime:
    return _last_sunday(year, 10) + timedelta(hours=2)


def merge_details(existing: dict, new: dict, *, course: str, folder_name: str) -> dict:
    """What Moodle says wins (title, due, questions, rules); what people typed stays (max_grade, rubric, notes).
    An existing Moodle id never changes."""
    info = dict(existing)
    info.setdefault("id", None)
    info["course"] = course
    info["name"] = folder_name
    for field in DETAIL_FIELDS:
        value = new.get(field)
        if value in (None, "", [], {}):
            continue
        if field == "id":
            value = str(value).strip()
            if info.get("id") and str(info["id"]) != value:
                raise Problem(f"ל-{folder_name} כבר שמור מזהה מודל אחר ({info['id']}), והדף במודל אומר {value}.")
        if field == "due":
            value = moodle_date(value)
            if not value:
                raise Problem(f"לא הצלחתי לקרוא את מועד ההגשה: {new.get('due')!r}")
        info[field] = value
    if not info.get("id") or not re.fullmatch(r"\d{4,12}", str(info["id"])):
        raise Problem("חסר מזהה המטלה במודל (המספר שאחרי id= בכתובת של עמוד המטלה).")
    info.setdefault("max_grade", None)
    info.setdefault("rubric", None)
    ordered = {k: info[k] for k in ("id", "course", "course_id", "name", "title", "course_title", "due", "questions",
                                   "submission_rules", "max_grade", "rubric", "grading_instructions", "notes") if k in info}
    ordered.update({k: v for k, v in info.items() if k not in ordered})
    return ordered


def write_details(course: str, slot: int, new: dict) -> Path:
    folder = assignment_dir(course, slot)
    folder_name = folder.name if folder else folder_view.slot_folder(slot)
    existing = paths.read_info(folder) if folder and (folder / paths.INFO).is_file() else {}
    info = merge_details(existing, new, course=course, folder_name=folder_name)
    taken = paths.find_assignment(info["id"])
    target = course_dir(course) / folder_name
    if taken and taken.resolve() != target.resolve():
        raise Problem(f"מזהה המודל {info['id']} כבר שייך ל-{taken.relative_to(paths.data_dir())}.")
    target.mkdir(exist_ok=True)
    for sub in (paths.TO_GRADE, paths.MARKED, paths.UPLOAD):
        (target / sub).mkdir(exist_ok=True)
    (pedagogy_dir(target) / WORKING_NOTES).mkdir(parents=True, exist_ok=True)
    (target / paths.INFO).write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if new.get("page_text"):
        record_page(course, info, str(new["page_text"]))
    return target


def record_page(course: str, info: dict, page_text: str) -> bool:
    """Keep the assignment's Moodle page in the course's "Moodle - assignments, quizzes and pages.md": one section per
    Moodle id, replaced when the page changed (a question added, a date moved) and left alone when it didn't."""
    folder = course_dir(course) / COURSE_MATERIAL
    folder.mkdir(exist_ok=True)
    path = folder / MOODLE_PAGES
    marker = f"מזהה במודל: {info['id']}"
    old = path.read_text(encoding="utf-8") if path.is_file() else "# מטלות, מבדקים ודפי הנחיות במודל\n"
    section = (f"## {info.get('title') or info['name']}\n\nסוג: assign, {marker}\n"
               f"https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id={info['id']}\n"
               f"הועתק ממודל ב-{datetime.now():%d/%m/%Y}.\n\n{page_text.strip()}\n")
    parts = re.split(r"(?m)^---\s*$", old)
    for i, part in enumerate(parts):
        if marker in part:
            if part.strip().split("\n\n", 2)[-1].strip() == page_text.strip():  # heading, source lines, then the text
                return False
            parts[i] = "\n\n" + section + "\n"
            path.write_text("---".join(parts), encoding="utf-8")
            return True
    path.write_text(old.rstrip("\n") + "\n\n---\n\n" + section, encoding="utf-8")
    return True


# ---------- the solution's pages ----------

def question_starts(texts: list[str]) -> dict[int, int]:
    """Question number → the page (0-based) where its heading first appears. Questions are numbered in order, so after
    the first heading a number counts only when it continues the sequence (a gap of one is allowed: a heading the text
    layer lost). A lone first match that a smaller number follows was a stray (a formula on the cover), not a heading."""
    starts: dict[int, int] = {}
    last: int | None = None
    for i, text in enumerate(texts):
        for m in QUESTION_RE.finditer(text):
            n = int(m.group(1))
            if last is None or n in (last + 1, last + 2):
                starts[n] = i
                last = n
            elif len(starts) == 1 and n < last:
                starts = {n: i}
                last = n
    return starts


def top_headings(texts: list[str], starts: dict[int, int]) -> set[int]:
    """The questions whose heading is at the top of its page (among the first three lines with text): the page holds
    nothing of the question before it. Otherwise the previous question runs into that page."""
    at_top = set()
    for n, page in starts.items():
        lines = [line for line in texts[page].splitlines() if line.strip()][:3]
        if any(int(m.group(1)) == n for line in lines for m in QUESTION_RE.finditer(line)):
            at_top.add(n)
    return at_top


def page_ranges(starts: dict[int, int], wanted: list[int], n_pages: int,
                at_top: set[int] = frozenset()) -> tuple[list[tuple[int, int, int]], list[int]]:
    """(question, first page, last page) for each wanted question, 0-based inclusive, and the questions not found.
    A question runs until the next question's heading (any question, assigned or not), or the last page; the page
    where the next question begins is included unless that heading is at its top (`at_top`)."""
    numbers = sorted(starts)
    found, missing = [], []
    for q in wanted:
        if q not in starts:
            missing.append(q)
            continue
        later = [n for n in numbers if n > q]
        end = (starts[later[0]] - (1 if later[0] in at_top else 0)) if later else n_pages - 1
        found.append((q, starts[q], max(end, starts[q])))
    return found, missing


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Overlapping or touching page ranges become one, so a page two questions share is written once."""
    merged: list[tuple[int, int]] = []
    for first, last in sorted(ranges):
        if merged and first <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], last))
        else:
            merged.append((first, last))
    return merged


def parse_pages(spec: str, n_pages: int) -> list[tuple[int, int]]:
    """"10-14,20" (1-based, as a PDF viewer shows them) → [(9, 13), (19, 19)]."""
    out = []
    for part in spec.split(","):
        a, _, b = part.strip().partition("-")
        first, last = int(a), int(b or a)
        if not 1 <= first <= last <= n_pages:
            raise Problem(f"עמודים {part.strip()} לא קיימים: ב-PDF יש {n_pages} עמודים.")
        out.append((first - 1, last - 1))
    return out


def page_texts(pdf: Path) -> list[str]:
    import pymupdf
    with pymupdf.open(pdf) as doc:
        return [page.get_text(sort=True) for page in doc]


def cut_pdf(src: Path, ranges: list[tuple[int, int]], out: Path, *, append: bool) -> int:
    import pymupdf
    result = pymupdf.open(out) if append and out.is_file() else pymupdf.open()
    with pymupdf.open(src) as doc:
        for first, last in ranges:
            result.insert_pdf(doc, from_page=first, to_page=last)
    tmp = out.with_suffix(".tmp.pdf")
    result.save(tmp, garbage=3, deflate=True)
    result.close()
    tmp.replace(out)
    with pymupdf.open(out) as doc:
        return doc.page_count


def materials(course: str, slot: int, sheet: int | None, numbers: list[int] | None, pages: str | None,
              *, replace: bool, append: bool) -> dict:
    folder = assignment_dir(course, slot)
    if not folder or not (folder / paths.INFO).is_file():
        raise Problem(f"להגשה {slot} של {course} עוד אין תיקייה עם פרטים: קודם `details`.")
    info = paths.read_info(folder)
    questions = info.get("questions") or []
    if sheet is None:
        sheet = guess_sheet(questions)
    if sheet is None:
        raise Problem("איזה דף תרגילים? --sheet N (המספר של הדף בחוברת; ראו `status`).")
    have = sheets(course).get(sheet)
    if not have:
        raise Problem(f"דף {sheet} לא נמצא ב-{COURSE_MATERIAL}/{SHEETS}: מורידים אותו ממודל ושומרים עם `add-sheet`.")
    if numbers is None:
        if len(questions) == 1:
            numbers = [int(n) for n in questions[0]["numbers"]]
        else:
            raise Problem("המטלה מכמה דפים: --numbers עם השאלות של הדף הזה (ואז `--append` לדף הבא).")
    pedagogy = pedagogy_dir(folder)
    pedagogy.mkdir(exist_ok=True)
    (pedagogy / WORKING_NOTES).mkdir(exist_ok=True)
    report: dict = {"assignment": str(folder), "sheet": sheet, "numbers": numbers, "written": [], "warnings": []}

    if have["sheet"]:
        target = pedagogy / f"Exercise sheet {sheet} - {have['topic']}.pdf"
        if not target.is_file() or replace:
            shutil.copyfile(have["sheet"], target)
            report["written"].append(str(target))
    else:
        report["warnings"].append(f"לדף {sheet} יש פתרונות אבל אין את הדף עצמו ב-{SHEETS}.")

    solution = folder / SOLUTION
    if not have["solutions"]:
        report["warnings"].append(f"אין פתרונות לדף {sheet} ב-{SHEETS}: אין {SOLUTION}.")
    elif solution.is_file() and not (replace or append):
        report["warnings"].append(f"{SOLUTION} כבר קיים; --replace כדי לבנות מחדש, --append כדי להוסיף דף.")
    else:
        src = Path(have["solutions"])
        texts = page_texts(src)
        if pages:
            ranges = parse_pages(pages, len(texts))
            report["pages"] = {"given": pages}
        else:
            starts = question_starts(texts)
            found, missing = page_ranges(starts, numbers, len(texts), top_headings(texts, starts))
            report["pages"] = {"found": {q: f"{a + 1}-{b + 1}" for q, a, b in found},
                               "headings_seen": {q: p + 1 for q, p in starts.items()}}
            if missing:
                report["pages"]["missing"] = missing
                report["warnings"].append(f"לא מצאתי בשכבת הטקסט את הכותרת של שאלות {missing}: "
                                          f"בודקים את העמודים ומריצים שוב עם --pages.")
            ranges = [(a, b) for _, a, b in found]
        ranges = merge_ranges(ranges)
        if ranges:
            count = cut_pdf(src, ranges, solution, append=append)
            report["written"].append(f"{solution} ({count} עמודים)")

    rules = pedagogy / REVIEW_RULES
    if not rules.is_file():
        source = review_rules_source(course)
        if source:
            shutil.copyfile(source, rules)
            report["written"].append(f"{rules} (עותק של {source.parent.parent.name})")
        else:
            report["warnings"].append(f"אין {REVIEW_RULES} באף מטלה להעתיק ממנה.")
    return report


def guess_sheet(questions: list[dict]) -> int | None:
    """"דף תרגילים 0 (תחשיב הפסוקים)" names its number; "דף וקטורים..." doesn't (then --sheet)."""
    if len(questions) != 1:
        return None
    m = re.search(r"(?:דף תרגילים|דף|Sheet)\s*(\d{1,2})\b", str(questions[0].get("sheet", "")))
    return int(m.group(1)) if m else None


def add_sheet(course: str, sheet: int, topic: str, file: Path | None, solutions: Path | None, *, replace: bool) -> list[str]:
    folder = course_dir(course) / COURSE_MATERIAL / SHEETS
    folder.mkdir(parents=True, exist_ok=True)
    topic = topic.strip().strip("-").strip()
    if not topic or "/" in topic or "\\" in topic:
        raise Problem("--topic: שם הנושא באנגלית, כמו 'Vector spaces'.")
    written = []
    for src, name in ((file, f"Sheet {sheet} - {topic}.pdf"), (solutions, f"Sheet {sheet} - {topic} - solutions.pdf")):
        if src is None:
            continue
        if not src.is_file() or src.stat().st_size < 100 or not src.open("rb").read(5).startswith(b"%PDF"):
            raise Problem(f"{src} אינו קובץ PDF שלם.")
        target = folder / name
        if target.is_file() and not replace:
            raise Problem(f"{target.name} כבר קיים ב-{SHEETS} (--replace כדי להחליף).")
        shutil.copyfile(src, target)
        written.append(str(target))
    return written


# ---------- status ----------

def status(course: str, slot: int) -> dict:
    folder = assignment_dir(course, slot)
    out: dict = {"data_dir": str(paths.data_dir()), "shared_folder": paths.in_shared_folder(paths.data_dir()),
                 "course": course, "slot": slot, "folder": str(folder) if folder else None,
                 "sheets": sheets(course),
                 "course_pages": str(course_dir(course) / COURSE_MATERIAL / MOODLE_PAGES)
                 if (course_dir(course) / COURSE_MATERIAL / MOODLE_PAGES).is_file() else None}
    if folder:
        info = paths.read_info(folder) if (folder / paths.INFO).is_file() else {}
        out["details"] = {k: info.get(k) for k in ("id", "title", "due", "questions", "notes") if k in info}
        pedagogy = pedagogy_dir(folder)
        out["pedagogy"] = sorted(p.name for p in pedagogy.iterdir()) if pedagogy.is_dir() else []
        out["official_solution"] = (folder / SOLUTION).is_file()
        subs = folder / paths.TO_GRADE
        out["submissions"] = len(paths.files_by_number(subs)) if subs.is_dir() else 0
        log = folder / paths.PULL_LOG
        out["last_pull"] = log.read_text(encoding="utf-8").strip().splitlines()[-1] if log.is_file() and log.stat().st_size else None
    others = [a.dir.name for a in folder_view.assignments(course_dir(course))]
    out["course_assignments"] = others
    return out


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--course", required=True, help='the course folder, e.g. "Linear Algebra"')
        p.add_argument("--slot", required=True, type=int, help="the assignment's number: הגשה N")

    common(sub.add_parser("status", help="what the assignment and the course already have"))
    p = sub.add_parser("details", help="create the folder and write Assignment details.json from a JSON file")
    common(p)
    p.add_argument("--from", dest="source", required=True, type=Path, help="JSON: id, title, due, questions, submission_rules, page_text")
    p = sub.add_parser("add-sheet", help="file a sheet and its solutions (downloaded from Moodle) under Course material/Sheets")
    p.add_argument("--course", required=True)
    p.add_argument("--sheet", required=True, type=int)
    p.add_argument("--topic", required=True, help='in English, e.g. "Vector spaces"')
    p.add_argument("--file", type=Path, help="the sheet's PDF")
    p.add_argument("--solutions", type=Path, help="the solutions' PDF")
    p.add_argument("--replace", action="store_true")
    p = sub.add_parser("materials", help="sheet into פדגוגי, Official solution.pdf, Manual review rules.md")
    common(p)
    p.add_argument("--sheet", type=int, help="which sheet (its number in the booklet)")
    p.add_argument("--numbers", type=int, nargs="+", help="the assigned questions of that sheet (default: from the details)")
    p.add_argument("--pages", help="the solution's pages by hand, 1-based: 10-14,20")
    p.add_argument("--replace", action="store_true", help="rebuild an existing Official solution.pdf")
    p.add_argument("--append", action="store_true", help="add this sheet's pages to the existing Official solution.pdf")
    sub.add_parser("readme", help="rewrite the README.txt files (python -m moodle guide)")
    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            result = status(args.course, args.slot)
        elif args.command == "details":
            new = json.loads(args.source.read_text(encoding="utf-8-sig"))
            folder = write_details(args.course, args.slot, new)
            result = {"folder": str(folder), "details": paths.read_info(folder)}
        elif args.command == "add-sheet":
            result = {"written": add_sheet(args.course, args.sheet, args.topic, args.file, args.solutions, replace=args.replace)}
        elif args.command == "materials":
            result = materials(args.course, args.slot, args.sheet, args.numbers, args.pages, replace=args.replace, append=args.append)
        else:
            result = {"written": len(guide.write_guides(paths.data_dir()))}
    except Problem as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
