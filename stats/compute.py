"""החישוב של הסטטיסטיקה למטלה אחת: מספרים בלבד, בלי קבצים.

מקבל את מה שכבר נשמר בתיקיית המטלה (שורות הציונים הממוזגות של כל הבודקים, הערות הבדיקה לכל מספר, המחוון)
ומחזיר מילון אחד: ממוצע והתפלגות, ניקוד וטעויות נפוצות לכל שאלה, כמה מחכות לאדם ולמה, מי בדק כמה.
אותן נוסחאות כמו באתר (`website/app.js`: `statsRowHTML`, `distHTML`, `mistakeStats`, `perQuestionHTML`), כדי שהאתר
יראה מספר אחד ולא שניים.

מה אין כאן ולא יהיה: מספרי הגשה, מזהי משתתף, שמות של סטודנטים, ציון של עבודה בודדת (`tests/stats` נופל אם משהו
כזה מופיע). שמות הבודקים הם חברי הצוות, שכבר מופיעים באתר.

כפילויות: שורות הציונים כבר ממוזגות לפי מספר (`moodle/grades.py`: שורה אחת לכל מספר, המאושרת או האחרונה גוברת),
ההערות הן קובץ אחד לכל מספר, וטעות נספרת פעם אחת לכל עבודה גם אם Claude רשם אותה פעמיים. לכל רשומה יש מפתח
ייחודי: המטלה `"<קורס>/Assignment N"`, השאלה `"<קורס>/Assignment N/qK"`, הטעות `(K, הניסוח)`.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timedelta

from moodle import grades

VERSION = 2                 # 2: timing ו-usage (זמן לעבודה ועלות לפי מודל), earlier (בדיקה ישנה שהועברה הצידה)
MAX_GRADE_LIMIT = 1000      # ציון מרבי מעל זה הוא טעות בפרטי המטלה
PASS_SHARE = 0.6            # עוברים: ציון של 60% מהציון המרבי ומעלה, כמו באתר
HISTOGRAM_BINS = 10         # 10 תאים של 10 נקודות (0-9, 10-19, ..., 90-100), לפי ההחלטה של אורי (2026-11-08)
REVIEW_KINDS = ("missing_question", "missing_page", "other_assignment", "unreadable_file",
                "unreadable", "missing", "uncertain", "format", "failed", "other")
SESSION_GAP_S = 30 * 60     # שתי עבודות שנגמרו במרווח גדול מזה שייכות לריצות (sessions) שונות
USAGE_LEAD_S = 15 * 60      # ריצת Claude של עבודה נגמרת עד כך וכך לפני שההערות שלה נכתבות: החלון לשיוך לפי זמן


def slot(folder: str) -> int | None:
    """"Assignment 3 - Vectors" → 3, כמו dashboard.folder_view.slot (לא מייבאים את הדשבורד בשביל שורה אחת)."""
    m = re.match(r"Assignment (\d+)(?: - |$)", folder)
    return int(m.group(1)) if m else None


def assignment_key(course: str, folder: str) -> str:
    """המפתח הייחודי של מטלה במסד: לפי מספר המקום, לא לפי שם התיקייה (השם משתנה כשנכנסת הכותרת העברית)."""
    n = slot(folder)
    return f"{course}/Assignment {n}" if n is not None else f"{course}/{folder}"


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _round(x: float | None, digits: int = 1) -> float | int | None:
    if x is None:
        return None
    v = round(x + 0.0, digits)
    return int(v) if float(v).is_integer() else v


def _pct(part: int, whole: int) -> int | None:
    return _half_up(100 * part / whole) if whole else None


def _half_up(x: float) -> int:
    return int(math.floor(x + 0.5))  # כמו Math.round ב-JS; round של Python מעגל לזוגי


def _half(x: float) -> float:
    return _half_up(x * 2) / 2  # לחצי נקודה, כמו `half` באתר


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _sd(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _points(row: dict) -> list[float] | None:
    raw = (row.get("points") or "").strip()
    if not raw:
        return None
    vals = [_num(x) for x in raw.split(";")]
    return vals if all(v is not None for v in vals) else None  # "abc", "nan" או "inf" = אין ניקוד לפי שאלה


def histogram(scores: list[float], max_grade: float) -> dict:
    """10 תאים שווים מ-0 עד הציון המרבי. כל תא הוא [from, to): ציון של 90 נכנס לתא האחרון, 89.5 לזה שלפניו;
    התא האחרון סגור משני הצדדים, כך שהציון המרבי עצמו בתוכו. (האתר מציג "90–100", "80–89" לפי from ו-to.)"""
    width = max_grade / HISTOGRAM_BINS
    bins = [{"from": _round(i * width), "to": _round((i + 1) * width)} for i in range(HISTOGRAM_BINS)]
    counts = [0] * HISTOGRAM_BINS
    for s in scores:
        counts[min(HISTOGRAM_BINS - 1, max(0, int(s // width)))] += 1
    return {"bins": bins, "counts": counts}


def compute(*, course: str, folder: str, moodle_id: str | None, title: str, max_grade: float,
            questions: list[dict], rows: dict[str, dict], notes: dict[str, dict], submitted: int,
            marked: set[str] | None = None, copying_pairs: int | None = None,
            usage_rows: list[dict] | None = None, earlier: list[dict] | None = None,
            computed_at: str = "", computed_by: str = "", sources: dict | None = None) -> dict:
    """הסטטיסטיקה של מטלה אחת.

    questions: המחוון, `[{"label", "points", "deductions": [{"text", "points"}]}]` (ריק = אין מחוון).
    rows: הציונים הממוזגים לפי מספר (grades.read). notes: הערות הבדיקה לפי מספר (Grading notes/NNNN.json),
    אחרי ש-`error` של "נגמרה המכסה" הוסר (עבודה כזו עוד לא נבדקה). submitted: כמה הגשות יש בתיקייה.
    marked: מספרים שיש להם קובץ מסומן (נחשבים בדוקים גם בלי שורת ציון, כמו באתר).
    usage_rows: השורות של יומן השימוש של Claude Code (`Grading usage*.jsonl`, כל המטלות): כאן נבחרות אלה של
    המטלה הזו (ראו `usage_of`). earlier: בדיקות ישנות של המטלה שהועברו הצידה, כבר מחושבות (`compute` על התיקייה שלהן).
    """
    max_grade = _num(max_grade) or 100.0
    if not 1 <= max_grade <= MAX_GRADE_LIMIT:  # 0, שלילי, זעיר או עצום = פרטי מטלה פגומים: ברירת המחדל
        max_grade = 100.0
    marked = marked or set()
    # שורה אחת לכל מספר מנורמל ("7" ו-"0007" הם אותו מספר): המאושרת או האחרונה גוברת, כמו במיזוג של grades.read,
    # ובשוויון לפי המפתח הגולמי, כדי שהתוצאה לא תלויה בסדר הקלט
    by_number: dict[str, dict] = {}
    for n, r in sorted(rows.items(), key=lambda kv: str(kv[0])):
        if isinstance(r, dict) and (grades.number_key(n) not in by_number or grades.rank(r) >= grades.rank(by_number[grades.number_key(n)])):
            by_number[grades.number_key(n)] = r
    # הערות: רק מילונים, לפי מספר מנורמל (קובץ פגום או מבנה אחר = אין הערות לעבודה הזו)
    notes = {grades.number_key(n): v for n, v in sorted(notes.items(), key=lambda kv: str(kv[0])) if isinstance(v, dict)}
    graded = {n: r for n, r in by_number.items() if (r.get("grade") or "").strip()}
    graded_numbers = set(graded) | {grades.number_key(n) for n in marked}
    failed = {n for n, note in notes.items()
              if grades.number_key(n) not in graded_numbers and str(note.get("error") or "").strip()}

    # לממוצע נכנסים רק ציונים בטווח 0 עד הציון המרבי: ציון מחוצה לו (שורה ישנה, זבל) נספר ב-out_of_range ולא נעלם בשקט
    all_scores = {n: s for n, r in graded.items() if (s := _num(r.get("grade"))) is not None}
    valid = {n: graded[n] for n, s in all_scores.items() if 0 <= s <= max_grade}
    scores = [all_scores[n] for n in valid]
    approved = sum(1 for r in graded.values() if grades.is_approved(r))
    queue = {n: r for n, r in by_number.items() if (r.get("review") or "").strip() and not grades.is_approved(r)}
    kinds = Counter()
    for n, r in queue.items():
        note = notes.get(n) or {}
        kind = "failed" if n in failed else str(r.get("special") or note.get("review_kind") or "other")
        kinds[kind if kind in REVIEW_KINDS else "other"] += 1
    for n in failed:
        if n not in queue:
            kinds["failed"] += 1

    # לכל שאלה: רק עבודות עם ניקוד לכל שאלה ובתוך המחוון (ניקוד מעל המחוון = נבדקה לפי חלוקה אחרת, לא נספרת;
    # ניקוד שלילי = זבל), מתוך העבודות שהציון שלהן בטווח
    q_points = [p if 0 <= (p := _num(q.get("points")) or 0.0) <= max_grade else 0.0 for q in questions]
    with_q = {n: p for n, r in valid.items() if (p := _points(r)) is not None and len(p) == len(questions)}
    fits = {n: p for n, p in with_q.items() if all(0 <= x <= qp for x, qp in zip(p, q_points))}
    per_question = []
    for i, q in enumerate(questions):
        pts = q_points[i]
        vals = [p[i] for p in fits.values()]
        unsure = sum(1 for n in fits if _flag(notes.get(n), "unsure", i))
        per_question.append({
            "key": f"{assignment_key(course, folder)}/q{i + 1}", "index": i + 1,
            "label": str(q.get("label") or f"שאלה {i + 1}"), "points": _round(pts),
            "graded": len(vals), "mean": _round(_mean(vals)),
            # אחוז ההצלחה כמו באתר: ממוצע של האחוז המעוגל של כל עבודה, לא יותר מ-100
            "success_pct": min(100, _half_up(_mean([_half_up(100 * v / pts) for v in vals]))) if vals and pts else None,
            "full_marks_pct": _pct(sum(1 for v in vals if v >= pts), len(vals)) if pts else None,
            "zero_pct": _pct(sum(1 for v in vals if v <= 0), len(vals)),
            "unsure": unsure,
            "mistakes": _mistakes(i, q, pts, valid, fits, notes),
        })

    graders = Counter(str(r.get("graded_by") or "").strip() for r in graded.values())
    graders.pop("", None)
    timing = timing_of(notes, by_number)
    usage = usage_of(usage_rows or [], assignment_key(course, folder), timing)
    return {
        "version": VERSION, "key": assignment_key(course, folder), "course": course, "slot": slot(folder),
        "folder": folder, "moodle_id": str(moodle_id) if moodle_id is not None else None, "title": title,
        "max_grade": _round(max_grade), "computed_at": computed_at, "computed_by": computed_by,
        "sources": sources or {},
        "counts": {
            "submitted": submitted, "graded": len(graded_numbers), "pending": max(0, submitted - len(graded_numbers)),
            "approved": approved, "needs_review": len(queue), "failed": len(failed),
            "review_kinds": {k: kinds[k] for k in REVIEW_KINDS if kinds[k]},
        },
        "grade": {
            "n": len(scores), "mean": _round(_mean(scores)), "median": _round(_median(scores)),
            "sd": _round(_sd(scores)), "min": _round(min(scores)) if scores else None,
            "max": _round(max(scores)) if scores else None,
            "pass_pct": _pct(sum(1 for s in scores if s >= PASS_SHARE * max_grade), len(scores)),
            "full_marks": sum(1 for s in scores if s >= max_grade),
            "out_of_range": len(all_scores) - len(scores),
            "histogram": histogram(scores, max_grade),
        },
        "per_question": per_question,
        "over_rubric": len(with_q) - len(fits),  # עבודות עם ניקוד מחוץ למחוון (מעליו, או שלילי), שלא נספרות לפי שאלה
        "graders": {"count": len(graders),
                    "by": [{"name": n, "graded": c} for n, c in sorted(graders.items(), key=lambda kv: (-kv[1], kv[0]))]},
        "copying": {"pairs": copying_pairs} if copying_pairs is not None else None,
        "timing": timing,
        "usage": usage,
        "earlier": [_earlier_summary(e) for e in earlier or []],
    }


# ---------- זמן ועלות ----------

def _when(x) -> datetime | None:
    try:
        return datetime.fromisoformat(str(x)).replace(tzinfo=None) if x else None
    except ValueError:
        return None


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def sessions(times: list[datetime], gap_s: float = SESSION_GAP_S) -> list[list[datetime]]:
    """מחלק זמני סיום של עבודות לריצות: מרווח של יותר מ-gap_s בין שתי עבודות פותח ריצה חדשה."""
    out: list[list[datetime]] = []
    for t in sorted(times):
        if out and (t - out[-1][-1]).total_seconds() <= gap_s:
            out[-1].append(t)
        else:
            out.append([t])
    return out


def timing_of(notes: dict[str, dict], rows: dict[str, dict]) -> dict:
    """מתי נבדקה המטלה וכמה זמן לקחה כל עבודה, מחותמות הזמן שהבדיקה כבר כותבת: `graded_at` (או `failed_at`) בהערות
    של כל מספר, ובלעדיהן `graded_at` בשורת הציון. ריצה (session) = עבודות שנגמרו ברצף, בלי הפסקה של חצי שעה.
    הזמן לעבודה הוא זמן קיר: אורך הריצה חלקי העבודות שנגמרו בה אחרי הראשונה (הבדיקה רצה כמה עבודות במקביל,
    והראשונה פותחת את השעון). ריצה של עבודה אחת היא בלי אורך. מספרים בלבד."""
    times: list[datetime] = []
    for n in set(notes) | set(rows):
        note = notes.get(n) or {}
        t = _when(note.get("graded_at")) or _when(note.get("failed_at")) or _when((rows.get(n) or {}).get("graded_at"))
        if t is not None:
            times.append(t)
    runs = sessions(times)
    out_runs = []
    for run in runs:
        secs = (run[-1] - run[0]).total_seconds()
        out_runs.append({"started": _iso(run[0]), "finished": _iso(run[-1]), "works": len(run),
                         "seconds": _round(secs, 0) if len(run) > 1 else None,
                         "seconds_per_work": _round(secs / (len(run) - 1), 0) if len(run) > 1 else None})
    timed = [r for r in out_runs if r["seconds"] is not None]
    wall = sum(r["seconds"] for r in timed)
    works = sum(r["works"] - 1 for r in timed)
    return {
        "first": _iso(runs[0][0]) if runs else None, "last": _iso(runs[-1][-1]) if runs else None,
        "works": len(times), "sessions": out_runs,
        "wall_seconds": _round(wall, 0) if timed else None,
        "seconds_per_work": _round(wall / works, 0) if works else None,
    }


def usage_of(rows: list[dict], key: str, timing: dict) -> dict:
    """הטוקנים והעלות של המטלה הזו מיומן השימוש של Claude Code. שורה שייכת למטלה כשה-`key` שלה הוא המטלה; שורה
    בלי `key` (יומן ישן) שייכת כשה-`at` שלה בתוך אחת הריצות (מ-USAGE_LEAD_S לפני העבודה הראשונה שנגמרה ועד
    האחרונה). העלות היא שוות ערך ל-API, לא חיוב: הבדיקה רצה במנוי של הצוות. `seconds` (אורך הריצה של עבודה
    אחת, ביומן מגרסה 2) נותן את הזמן האמיתי לעבודה, חציון וממוצע."""
    windows = []
    for r in timing.get("sessions") or []:
        a, b = _when(r.get("started")), _when(r.get("finished"))
        if a and b:
            windows.append((a - timedelta(seconds=USAGE_LEAD_S), b))
    mine = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        k = str(r.get("key") or "")
        if k:
            if k == key:
                mine.append(r)
            continue
        t = _when(r.get("at"))
        if t is not None and any(a <= t <= b for a, b in windows):
            mine.append(r)
    by_model: dict[str, dict] = {}
    for r in mine:
        name = str(r.get("model") or "?")
        m = by_model.setdefault(name, {"model": name, "runs": 0, "input": 0, "output": 0, "cache_read": 0,
                                       "cache_write": 0, "cost_usd": 0.0})
        m["runs"] += 1
        for f in ("input", "output", "cache_read", "cache_write"):
            m[f] += int(_num(r.get(f)) or 0)
        m["cost_usd"] += _num(r.get("cost_usd")) or 0.0
    models = sorted(by_model.values(), key=lambda m: (-m["cost_usd"], m["model"]))
    for m in models:
        m["cost_per_run"] = _round(m["cost_usd"] / m["runs"], 3) if m["runs"] else None
        m["cost_usd"] = _round(m["cost_usd"], 2)
    secs = [v for r in mine if (v := _num(r.get("seconds"))) is not None and v >= 0]
    total = {f: sum(m[f] for m in models) for f in ("runs", "input", "output", "cache_read", "cache_write")}
    cost = sum(_num(r.get("cost_usd")) or 0.0 for r in mine)
    read, fresh = total["cache_read"], total["input"] + total["cache_write"]
    return {
        **total, "cost_usd": _round(cost, 2), "cost_per_run": _round(cost / total["runs"], 3) if total["runs"] else None,
        "cache_read_share": _round(read / (read + fresh), 2) if read + fresh else None,
        "by_model": models,
        "run_seconds": {"n": len(secs), "median": _round(_median(secs), 0), "mean": _round(_mean(secs), 0)} if secs else None,
    }


def _earlier_summary(e: dict) -> dict:
    """בדיקה ישנה של המטלה, בקיצור: מתי, כמה, ציונים, זמן ועלות. בלי שאלות: המחוון שלה היה אחר."""
    return {"folder": e.get("title"), "counts": e.get("counts"), "grade": e.get("grade"),
            "timing": e.get("timing"), "usage": e.get("usage")}


def _flag(note: dict | None, field: str, i: int) -> bool:
    xs = (note or {}).get(field)
    return isinstance(xs, list) and i < len(xs) and bool(xs[i])


def _mistakes(i: int, q: dict, pts: float, graded: dict, fits: dict, notes: dict) -> list[dict]:
    """הטעויות של שאלה i: כמה עבודות עשו כל אחת, ובכמה בדרך כלל ירד עליה (כמו `mistakeStats` באתר).

    האחוז הוא מתוך העבודות הבדוקות שיש להן הערות בדיקה עם רשימת טעויות (גם ריקה: עבודה נקייה נספרת במכנה, כמו
    באתר). "כמה ירד בדרך כלל": כשהטעות היא היחידה בשאלה, כל מה שירד בשאלה הוא בגללה (חציון, לחצי נקודה). טעות
    שבמחוון (`deductions`) מקבלת את הניקוד שכתוב שם.
    """
    with_notes = [n for n in graded if isinstance((notes.get(n) or {}).get("mistakes"), list) and notes[n]["mistakes"]]
    counts: dict[str, int] = {}
    losses: dict[str, list[float]] = {}
    for n in with_notes:
        ms = (notes[n].get("mistakes") or [])
        texts = [t.strip() for t in ms[i] if isinstance(t, str)] if i < len(ms) and isinstance(ms[i], list) else []
        for text in dict.fromkeys(t for t in texts if t):  # פעם אחת לכל עבודה
            counts[text] = counts.get(text, 0) + 1
            if len(texts) == 1 and n in fits and pts:  # רק ניקוד בתוך המחוון, אז ההפסד בין 0 לניקוד השאלה
                losses.setdefault(text, []).append(pts - fits[n][i])
    known = {str(d.get("text") or "").strip(): dp for d in q.get("deductions") or [] if isinstance(d, dict)
             if (dp := _num(d.get("points"))) is None or 0 <= dp <= pts}  # הורדה מעל ניקוד השאלה = מחוון פגום
    out = []
    for text, c in counts.items():
        typical = _half(_median(losses[text])) if losses.get(text) else None
        out.append({"text": text, "count": c, "pct": _pct(c, len(with_notes)),
                    "in_rubric": text in known,
                    "deduction": _round(known[text]) if text in known and known[text] is not None else _round(typical)})
    return sorted(out, key=lambda m: (-m["count"], m["text"]))
