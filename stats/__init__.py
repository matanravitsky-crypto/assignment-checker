"""מסד הנתונים הסטטיסטי: הדלת היחידה לסטטיסטיקה של המטלות (ראו docs/Statistics database plan.md והסקיל stats-db).

- `compute.py` מחשב (בלי קבצים), `store.py` שומר וקורא (בלי חישוב). כאן: מה שמחבר אותם.
- `read(assignment_dir)` היא מה שהאתר ו-Claude קוראים: הקובץ מ-`Statistics/` אם הוא עדיין משקף את הקבצים
  בתיקיית המטלה (`sources`: hash של קובצי הציונים וההערות), ואחרת חישוב מחדש, שמירה, והטרי.
- `build` אחרי כל בדיקה ואישור (grading קורא לה), `rebuild` לכל המטלות, `export_csv` / `export_sqlite` לניתוח.
האתר, Claude ושורת הפקודה קוראים דרך המודול הזה ולא פותחים קבצים בעצמם.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from moodle import claims, grades, paths

from . import compute as _compute
from . import store

# הממשק: מה שחלקים אחרים מותר להם לקחת מכאן. כל השאר פנימי, ואפשר לשנות אותו בלי לשאול אף חלק אחר.
# tests/test_modularity.py נופל כשקוד מחוץ לחלק לוקח משהו שלא ברשימה. "*" = כל מה שלא מתחיל ב-_ (הליבה).
INTERFACE = {
    "": ["read", "build", "rebuild", "read_all", "assignment_dirs", "is_fresh", "file_for", "export_csv",
         "export_sqlite"],
    "compute": ["assignment_key", "slot"],
}


def gather(assignment_dir: Path) -> dict:
    """כל מה ש-`compute.compute` צריך, מתיקיית המטלה: המחוון (דרך grading, כולל הניקוד מתיקיית "פדגוגי"),
    הציונים הממוזגים, הערות הבדיקה, כמה הגשות וכמה מסומנות, וזוגות ההעתקה. מספרים בלבד."""
    from grading import grade as grading  # טוען PyMuPDF: רק כאן, לא בחישוב עצמו

    a = Path(assignment_dir)
    d = paths.read_info(a)
    ctx = grading.load_context(a, send_solution=False)
    notes = {}
    for p in sorted((a / paths.NOTES).glob("*.json")) if (a / paths.NOTES).is_dir() else []:
        if not p.stem.isdigit():
            continue
        note = grading.read_notes(a, p.stem)
        if grading.is_limit(str(note.get("error") or "")):  # נגמרה המכסה: העבודה עוד לא נבדקה
            note = {k: v for k, v in note.items() if k != "error"}
        notes[grades.number_key(p.stem)] = note
    copying = a / paths.COPYING
    pairs = None
    if copying.is_file():
        try:
            data = json.loads(copying.read_text(encoding="utf-8"))
            pairs = len(data.get("pairs") or []) if isinstance(data, dict) else None
        except (OSError, ValueError):
            pairs = None
    return {
        "course": a.parent.name, "folder": a.name, "moodle_id": d.get("id"),
        "title": str(d.get("title") or d.get("name") or a.name), "max_grade": ctx.max_grade,
        "questions": [{"label": q.label, "points": q.points, "deductions": q.deductions} for q in ctx.questions],
        "rows": grades.read(a), "notes": notes,
        "submitted": len(paths.files_by_number(a / paths.TO_GRADE)),
        "marked": set(paths.files_by_number(a / paths.MARKED, "*.pdf")),
        "copying_pairs": pairs,
        "sources": sources(a),
    }


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _file_sha(p: Path) -> str:
    try:
        return _sha(p.read_bytes())
    except OSError:
        return "-"


def sources(assignment_dir: Path) -> dict:
    """ממה הסטטיסטיקה חושבה: hash של תוכן קובצי הציונים וההערות, ורשימת שמות ההגשות והמסומנות. תוכן ולא זמני
    שינוי, כדי ששני מחשבים (שאצלם OneDrive נותן זמנים אחרים) יסכימו שהקובץ טרי ולא יכתבו אותו זה על זה."""
    a = Path(assignment_dir)
    notes = sorted((a / paths.NOTES).glob("*.json")) if (a / paths.NOTES).is_dir() else []
    names = lambda folder, pattern: _sha("\n".join(sorted(paths.files_by_number(folder, pattern))).encode("utf-8", "surrogatepass"))  # noqa: E731
    return {
        "version": _compute.VERSION,
        "grades": [{"name": p.name, "size": p.stat().st_size, "sha256": _file_sha(p)} for p in grades.files(a)],
        "notes": {"count": len(notes), "sha256": _sha("\n".join(f"{p.name}:{_file_sha(p)}" for p in notes).encode("utf-8", "surrogatepass"))},
        "submitted": {"count": len(paths.files_by_number(a / paths.TO_GRADE)), "sha256": names(a / paths.TO_GRADE, "*")},
        "marked": {"count": len(paths.files_by_number(a / paths.MARKED, "*.pdf")), "sha256": names(a / paths.MARKED, "*.pdf")},
        "copying": _file_sha(a / paths.COPYING) if (a / paths.COPYING).is_file() else "",
        "details": _file_sha(a / paths.INFO),
    }


def _root_of(assignment_dir: Path) -> Path:
    return Path(assignment_dir).parent.parent


def compute_assignment(assignment_dir: Path, by: str | None = None) -> dict:
    """הסטטיסטיקה של מטלה אחת, מחושבת עכשיו מהתיקייה (בלי לשמור)."""
    data = gather(assignment_dir)
    return _compute.compute(**data, computed_at=datetime.now().isoformat(timespec="seconds"),
                            computed_by=by or claims.me() or os.environ.get("USERNAME", ""))


def file_for(assignment_dir: Path) -> Path:
    a = Path(assignment_dir)
    return store.file_for(_root_of(a), a.parent.name, a.name)


def build(assignment_dir: Path, by: str | None = None) -> dict:
    """מחשב עכשיו ושומר ב-Statistics/ (רק אם משהו השתנה). מוחק עותקים מתנגשים של הקובץ הזה. מחזיר את הסטטיסטיקה."""
    a = Path(assignment_dir)
    data = compute_assignment(a, by)
    path = file_for(a)
    store.ensure_readme(_root_of(a))
    store.remove_conflict_copies(path)
    if not store.write(path, data):
        kept = store.read_file(path)
        if kept is not None:
            return kept  # אותו תוכן: משאירים את מתי ומי של הקובץ, כדי שכולם יראו אותו דבר
    return data


def is_fresh(assignment_dir: Path, data: dict | None) -> bool:
    return bool(data) and data.get("version") == _compute.VERSION and data.get("sources") == sources(assignment_dir)


def read(assignment_dir: Path) -> dict:
    """הסטטיסטיקה של המטלה, מהקובץ אם הוא עדיין משקף את התיקייה, אחרת מחושבת מחדש ונשמרת."""
    a = Path(assignment_dir)
    data = store.read_file(file_for(a))
    if is_fresh(a, data):
        return data
    return build(a)


def assignment_dirs(root: Path) -> list[Path]:
    """כל תיקיות המטלות בתיקיית הנתונים (קורס/מטלה עם פרטי מטלה), בלי Statistics עצמה."""
    root = Path(root)
    return sorted(p.parent for p in root.glob(f"*/*/{paths.INFO}") if p.parent.parent.name != paths.STATISTICS)


def rebuild(root: Path) -> list[dict]:
    """מחשב ושומר את כל המטלות, וכותב את ה-CSV."""
    out = [build(a) for a in assignment_dirs(root)]
    export_csv(root)
    return out


def read_all(root: Path, course: str | None = None) -> list[dict]:
    return [read(a) for a in assignment_dirs(root) if course is None or a.parent.name == course]


# ---------- ייצוא לניתוח ----------
CSV_COLUMNS = ["course", "slot", "moodle_id", "title", "question", "label", "points", "submitted", "graded", "pending",
               "approved", "needs_review", "failed", "mean", "median", "sd", "min", "max", "pass_pct", "full_marks",
               "success_pct", "full_marks_pct", "zero_pct", "unsure", "top_mistake", "top_mistake_count", "top_mistake_pct",
               "graders", "computed_at"]


def csv_rows(all_stats: list[dict]) -> list[dict]:
    """שורה לכל מטלה (question ריק) ושורה לכל שאלה. מפתח ייחודי: (course, slot, question)."""
    rows = []
    for s in all_stats:
        c, g = s["counts"], s["grade"]
        base = {"course": s["course"], "slot": s["slot"], "moodle_id": s["moodle_id"], "title": s["title"],
                "submitted": c["submitted"], "graded": c["graded"], "pending": c["pending"], "approved": c["approved"],
                "needs_review": c["needs_review"], "failed": c["failed"], "graders": s["graders"]["count"],
                "computed_at": s["computed_at"]}
        rows.append({**base, "question": "", "label": "", "points": s["max_grade"], "mean": g["mean"], "median": g["median"],
                     "sd": g["sd"], "min": g["min"], "max": g["max"], "pass_pct": g["pass_pct"], "full_marks": g["full_marks"]})
        for q in s["per_question"]:
            top = q["mistakes"][0] if q["mistakes"] else None
            rows.append({**base, "question": q["index"], "label": q["label"], "points": q["points"], "graded": q["graded"],
                         "mean": q["mean"], "success_pct": q["success_pct"], "full_marks_pct": q["full_marks_pct"],
                         "zero_pct": q["zero_pct"], "unsure": q["unsure"],
                         "top_mistake": top["text"] if top else "", "top_mistake_count": top["count"] if top else "",
                         "top_mistake_pct": top["pct"] if top else ""})
    return rows


def export_csv(root: Path, path: Path | None = None, all_stats: list[dict] | None = None) -> Path:
    root = Path(root)
    path = Path(path) if path else store.stats_dir(root) / paths.STATS_EXPORT
    rows = csv_rows(all_stats if all_stats is not None else read_all(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as fh:  # BOM: אקסל מציג עברית
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, lineterminator="\r\n", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    os.replace(tmp, path)
    return path


def export_sqlite(root: Path, path: Path, all_stats: list[dict] | None = None) -> Path:
    """מסד SQLite לניתוח, במחשב של מי שמנתח (לא בתיקייה המשותפת). מפתחות ייחודיים: אותה מטלה פעמיים = שורה אחת."""
    path = Path(path)
    stats_list = all_stats if all_stats is not None else read_all(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS assignments (key TEXT PRIMARY KEY, course TEXT, slot INTEGER, moodle_id TEXT, title TEXT,
                max_grade REAL, submitted INTEGER, graded INTEGER, pending INTEGER, approved INTEGER, needs_review INTEGER,
                failed INTEGER, mean REAL, median REAL, sd REAL, min REAL, max REAL, pass_pct INTEGER, full_marks INTEGER,
                out_of_range INTEGER, graders INTEGER, copying_pairs INTEGER, computed_at TEXT, computed_by TEXT);
            CREATE TABLE IF NOT EXISTS questions (key TEXT PRIMARY KEY, assignment_key TEXT, idx INTEGER, label TEXT, points REAL,
                graded INTEGER, mean REAL, success_pct INTEGER, full_marks_pct INTEGER, zero_pct INTEGER, unsure INTEGER);
            CREATE TABLE IF NOT EXISTS mistakes (question_key TEXT, text TEXT, count INTEGER, pct INTEGER, in_rubric INTEGER,
                deduction REAL, PRIMARY KEY (question_key, text));
            CREATE TABLE IF NOT EXISTS histogram (assignment_key TEXT, bin INTEGER, from_grade REAL, to_grade REAL, count INTEGER,
                PRIMARY KEY (assignment_key, bin));
            CREATE TABLE IF NOT EXISTS review_kinds (assignment_key TEXT, kind TEXT, count INTEGER, PRIMARY KEY (assignment_key, kind));
        """)
        for s in stats_list:
            c, g = s["counts"], s["grade"]
            con.execute("DELETE FROM questions WHERE assignment_key = ?", (s["key"],))
            con.execute("DELETE FROM mistakes WHERE question_key LIKE ?", (s["key"] + "/q%",))
            con.execute("DELETE FROM histogram WHERE assignment_key = ?", (s["key"],))
            con.execute("DELETE FROM review_kinds WHERE assignment_key = ?", (s["key"],))
            con.execute("INSERT OR REPLACE INTO assignments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (s["key"], s["course"], s["slot"], s["moodle_id"], s["title"], s["max_grade"], c["submitted"], c["graded"],
                         c["pending"], c["approved"], c["needs_review"], c["failed"], g["mean"], g["median"], g["sd"], g["min"],
                         g["max"], g["pass_pct"], g["full_marks"], g["out_of_range"], s["graders"]["count"],
                         (s.get("copying") or {}).get("pairs"), s["computed_at"], s["computed_by"]))
            for q in s["per_question"]:
                con.execute("INSERT OR REPLACE INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (q["key"], s["key"], q["index"], q["label"], q["points"], q["graded"], q["mean"], q["success_pct"],
                             q["full_marks_pct"], q["zero_pct"], q["unsure"]))
                for m in q["mistakes"]:
                    con.execute("INSERT OR REPLACE INTO mistakes VALUES (?,?,?,?,?,?)",
                                (q["key"], m["text"], m["count"], m["pct"], int(m["in_rubric"]), m["deduction"]))
            for i, (b, n) in enumerate(zip(g["histogram"]["bins"], g["histogram"]["counts"])):
                con.execute("INSERT OR REPLACE INTO histogram VALUES (?,?,?,?,?)", (s["key"], i, b["from"], b["to"], n))
            for kind, n in c["review_kinds"].items():
                con.execute("INSERT OR REPLACE INTO review_kinds VALUES (?,?,?)", (s["key"], kind, n))
        con.commit()
    finally:
        con.close()
    return path
