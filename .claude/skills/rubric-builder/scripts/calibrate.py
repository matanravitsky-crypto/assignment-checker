#!/usr/bin/env python3
"""The calibration input: what a real grading run found that the rubric doesn't cover.

Reads the assignment's `Grading notes/*.json` (the bot's per-work report: points, mistakes, unsure, review; numbers
only) and `rubric.json`, and writes a short Markdown the committee convenes on (SKILL Step 7):
- per question: how many works, average points, how often the bot was unsure, how often it asked for a person;
- the mistakes the bot described in its own words that match NO error row of the rubric, grouped and counted
  (word overlap with the rubric's rows; a mistake that matches a row is "covered" and not listed);
- the covered rows that were used a lot (the rubric's hit list) and the rows never used;
- every review reason, shortened.
Usage: calibrate.py <assignment id> <rubric.json> --out <work>/agents/calibration-input.md [--since YYYY-MM-DD]
Run from the repo root (it imports moodle.paths). Never names, never page images: text statistics only."""
import sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
import argparse, collections, json, re
from pathlib import Path

STOP = {"של", "את", "על", "עם", "בלי", "או", "לא", "כמו", "גם", "רק", "אבל", "זה", "זו", "יש", "אין", "כל", "בין", "ב", "ל", "מ", "ו", "the", "a", "of"}
HEB = re.compile(r"[֐-׿]+|[A-Za-z]+|\d+")


def words(s: str) -> set[str]:
    out = set()
    for w in HEB.findall(str(s)):
        w = w.lstrip("והבכלמש") if len(w) > 3 else w  # a crude Hebrew prefix strip
        if len(w) > 1 and w not in STOP:
            out.add(w)
    return out


def similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / max(len(a | b), 1)


def rubric_rows(rubric: dict) -> list[tuple[int, str, str, set[str]]]:
    """(question index, section letter, desc, words) for every error row."""
    rows = []
    for qi, q in enumerate(rubric.get("questions", [])):
        for s in q.get("sections", []):
            for er in s.get("errors", []) or []:
                rows.append((qi, s.get("letter", "?"), er["desc"], words(er["desc"])))
    return rows


def build(notes: list[dict], rubric: dict, labels: list[str], threshold: float = 0.34) -> str:
    rows = rubric_rows(rubric)
    nq = len(rubric.get("questions", []))
    per_q = [{"n": 0, "pts": 0.0, "unsure": 0, "max": int(q["points"])} for q in rubric.get("questions", [])]
    uncovered = [collections.Counter() for _ in range(nq)]
    hits = collections.Counter()
    reviews = []
    for d in notes:
        pts, uns, mis = d.get("points") or [], d.get("unsure") or [], d.get("mistakes") or []
        for i in range(min(nq, len(pts))):
            per_q[i]["n"] += 1; per_q[i]["pts"] += float(pts[i] or 0)
            if i < len(uns) and uns[i]: per_q[i]["unsure"] += 1
            for m in (mis[i] if i < len(mis) else []) or []:
                mw = words(m)
                best = max(((similarity(mw, rw), idx) for idx, (qi, _, _, rw) in enumerate(rows) if qi == i), default=(0, -1))
                if best[0] >= threshold:
                    hits[best[1]] += 1
                else:
                    key = re.sub(r"\s+", " ", str(m)).strip()[:90]
                    uncovered[i][key] += 1
        if d.get("review"):
            reviews.append((d.get("review_kind") or "?", re.sub(r"\s+", " ", str(d["review"]))[:160]))
    o = [f"# קלט לסבב כיול · {len(notes)} עבודות שנבדקו", "",
         "הבוט בדק את העבודות האלה לפי Rubric.md. כאן מה שהוא מצא ולא היה כתוב במחוון, ואיפה הוא לא היה בטוח. מספרי הגשה בלבד.", "",
         "## לפי שאלה", "", "| שאלה | נבדקו | ממוצע נק' | מתוך | לא בטוח | טעויות שאינן במחוון |", "|---|---|---|---|---|---|"]
    for i, pq in enumerate(per_q):
        label = labels[i] if i < len(labels) else rubric["questions"][i]["n"]
        n = pq["n"] or 1
        o.append(f"| {label} | {pq['n']} | {pq['pts']/n:.1f} | {pq['max']} | {pq['unsure']} ({100*pq['unsure']/n:.0f}%) | {sum(uncovered[i].values())} |")
    o += ["", "## טעויות שהבוט תיאר ואין להן שורה במחוון (לפי שאלה, עם ספירה)", "",
          "כל שורה כאן היא מועמדת לשורה חדשה בטבלת הטעויות, או סימן שהניסוח במחוון רחוק ממה שקורה בפועל.", ""]
    for i, c in enumerate(uncovered):
        if not c: continue
        label = labels[i] if i < len(labels) else rubric["questions"][i]["n"]
        o.append(f"### {label}")
        for text, cnt in c.most_common(12):
            o.append(f"- ({cnt}) {text}")
        o.append("")
    o += ["## שורות המחוון שהבוט השתמש בהן הכי הרבה", ""]
    for idx, cnt in hits.most_common(10):
        qi, letter, desc, _ = rows[idx]
        label = labels[qi] if qi < len(labels) else rubric["questions"][qi]["n"]
        o.append(f"- ({cnt}) {label} {letter}: {desc[:80]}")
    unused = [idx for idx in range(len(rows)) if idx not in hits]
    o += ["", f"## שורות שלא שימשו אף פעם: {len(unused)} מתוך {len(rows)}", ""]
    for idx in unused[:25]:
        qi, letter, desc, _ = rows[idx]
        label = labels[qi] if qi < len(labels) else rubric["questions"][qi]["n"]
        o.append(f"- {label} {letter}: {desc[:80]}")
    if len(unused) > 25: o.append(f"- … ועוד {len(unused) - 25}")
    o += ["", f"## עבודות שנשלחו לבדיקה ידנית: {len(reviews)}", ""]
    for kind, why in reviews[:20]:
        o.append(f"- [{kind}] {why}")
    return "\n".join(o) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description="קלט לסבב כיול של המחוון מתוך דוחות הבדיקה")
    p.add_argument("assignment_id"); p.add_argument("rubric"); p.add_argument("--out", required=True)
    p.add_argument("--since", help="רק דוחות מתאריך זה (YYYY-MM-DD)")
    a = p.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # the repo root: moodle.paths, grading.grade
    from moodle import paths
    from grading import grade
    folder = paths.assignment_dir(a.assignment_id)
    rubric = json.load(open(a.rubric, encoding="utf-8-sig"))
    labels = grade.question_labels(grade.read_details(folder))
    notes = []
    for f in sorted((folder / paths.NOTES).glob("*.json")):
        try: d = json.load(open(f, encoding="utf-8"))
        except Exception: continue
        if a.since and str(d.get("graded_at") or "")[:10] < a.since: continue
        if d.get("points"): notes.append(d)
    if not notes: sys.exit("אין דוחות בדיקה (Grading notes) למטלה הזאת; סבב כיול צריך בדיקה אמיתית קודם.")
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(notes, rubric, labels), encoding="utf-8")
    print(f"wrote {out} from {len(notes)} reports")


if __name__ == "__main__":
    main()
