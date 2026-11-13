"""meta-evaluator: the mechanical half of a round (no Claude, no tokens). Numbers only, never a name.

    python me.py sample   <assignment> --round R --n 20 [--include 0443 ...] [--fresh]
    python me.py mechanical <assignment> --round R
    python me.py backup   <assignment> --round R          (before re-grading the sample)
    python me.py render   <assignment> --round R          (the marked PDFs of the sample, as page images)
    python me.py targets  <assignment> --round R          (each work's correct grade, from the auditors' logs)
    python me.py claims   <assignment> --round R [--max 40] (the claims in the logs that the verifier must check)
    python me.py tally    <assignment> --round R          (tags across the logs, and how many the verifier confirmed)
    python me.py compare  <assignment> --round R          (old grading vs new, against the targets: did it get closer?)
    python me.py check-report <assignment> --round R <report.md>

<assignment> is a Moodle id or the assignment folder. The round's folder is ~/.meta-eval/<id>/<R>.
"""
from __future__ import annotations

import argparse
import random
import re
import shutil
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

TAGS = ["HALLUCINATION", "MISSED", "ALT_METHOD_PENALIZED", "MISREAD", "BOX_OK", "BOX_OFF", "BOX_HUGE", "NO_BOX",
        "NOTE_OK", "NOTE_ON_WRITING", "NOTE_FAR", "NOTE_OVERLAP", "NOTE_MISSING", "NOTE_CUT", "NOTE_RTL",
        "CHECK_OK", "CHECK_WRONG_KIND", "CHECK_MISPLACED", "CHECK_MISSING",
        "NO_RUBRIC_ROW", "TWO_ROWS", "RUBRIC_VAGUE", "TAG_PARAPHRASED", "DOUBLE_PENALTY", "DISPROPORTIONATE",
        "MISSING_SECTION_RULE", "REVIEW_UNNEEDED", "REVIEW_NEEDED_NOT_SENT", "FEWSHOT_GOOD", "FEWSHOT_BAD",
        "FIXED", "STILL", "CHANGED", "BETTER", "WORSE", "SAME_QUALITY"]
# the tags that claim the grading or the page is wrong: each one goes to the verifier before it reaches a report
CLAIMS = {"HALLUCINATION", "MISSED", "ALT_METHOD_PENALIZED", "MISREAD", "BOX_OFF", "BOX_HUGE", "NOTE_ON_WRITING",
          "NOTE_MISSING", "NOTE_CUT", "NOTE_RTL", "CHECK_WRONG_KIND", "CHECK_MISPLACED", "NO_RUBRIC_ROW", "TWO_ROWS",
          "DOUBLE_PENALTY", "DISPROPORTIONATE", "MISSING_SECTION_RULE", "WORSE", "STILL"}


def is_offline(r: Path) -> bool:
    """A round graded by offline.py: its grading lives in the round folder, never in the shared one."""
    return bool((c.load(r / "sample.json", {}) or {}).get("offline"))


def src_rows(a: Path, r: Path) -> dict[str, dict]:
    return (c.load(r / "grades.json", {}) or {}) if is_offline(r) else c.grades(a)


def src_notes(a: Path, r: Path, n: str) -> dict:
    return (c.load(r / "notes" / f"{n}.json", {}) or {}) if is_offline(r) else c.notes(a, n)


def src_numbers(a: Path, r: Path) -> list[str]:
    return sorted(src_rows(a, r)) if is_offline(r) else c.graded_numbers(a)


def src_marked(a: Path, r: Path, n: str) -> Path:
    return (r / "marked" / f"{n}.pdf") if is_offline(r) else (a / "2 - Graded with comments" / f"{n}.pdf")


def sample(a: Path, r: Path, n: int, include: list[str], fresh: bool, seed: int) -> list[str]:
    """Stratified by grade (a third from each third), plus every work in the manual queue, the most marked ones and
    the ones asked for. fresh: skip works an earlier round of this assignment already audited."""
    rows = c.grades(a)
    graded = [x for x in c.graded_numbers(a) if x in rows and rows[x].get("grade") not in (None, "")]
    if fresh:
        done = set()
        for logs in r.parent.glob("*/logs"):
            if logs.parent != r:
                done |= {p.stem.split("-")[-1] for p in logs.glob("log-*.md")}
        graded = [x for x in graded if x not in done]
    graded.sort(key=lambda x: float(rows[x]["grade"]))
    must = [x for x in include if x in graded]
    must += [x for x in graded if rows[x].get("review")][: max(1, n // 10)]
    marks = sorted(graded, key=lambda x: -len(c.notes(a, x).get("marks", [])))
    must += marks[: max(1, n // 5)]
    chosen = list(dict.fromkeys(must))[:n]
    k = len(graded)
    thirds = [graded[: k // 3], graded[k // 3: 2 * k // 3], graded[2 * k // 3:]]
    rnd = random.Random(seed)
    for i, third in enumerate(thirds):
        want = (n - len(chosen)) // (3 - i) if i < 2 else n - len(chosen)
        pool = [x for x in third if x not in chosen]
        chosen += rnd.sample(pool, min(max(want, 0), len(pool)))
    chosen = sorted(chosen)[:n]
    c.dump({"assignment": str(a), "sample": chosen, "seed": seed}, r / "sample.json")
    c.say(f"{len(chosen)} עבודות (מתוך {k} שנבדקו):", " ".join(chosen))
    return chosen


def the_sample(r: Path) -> list[str]:
    s = c.load(r / "sample.json")
    if not s:
        raise SystemExit("אין sample.json בתיקיית הסבב: קודם me.py sample")
    return s["sample"]


def mechanical(a: Path, r: Path) -> dict:
    """Over every graded work: the same mistake tag with different deductions, deductions with no tag, generic
    comments, box sizes, grader words in student text, the review rate, deductions per section."""
    labels, full = c.labels(a)
    rows = src_rows(a, r)
    by_tag: dict[str, list] = {}
    works = {}
    for n in src_numbers(a, r):
        d = src_notes(a, r, n)
        pts = d.get("points") or []
        w = {"grade": rows.get(n, {}).get("grade"), "deduction_no_tag": [], "generic": [], "box_h": [], "grader_words": []}
        for i, (p, m) in enumerate(zip(pts, full)):
            tags = (d.get("mistakes") or [[]] * len(pts))[i] if i < len(d.get("mistakes") or []) else []
            comment = (d.get("comments") or [""] * len(pts))[i]
            for t in tags:
                if m - p < m:  # a whole section lost ("סעיף חסר") costs its own size: not a price to compare
                    by_tag.setdefault(t, []).append((n, labels[i], m - p))
            if m - p > 0 and not tags:
                w["deduction_no_tag"].append(labels[i])
            if len(str(comment).split()) <= 2:
                w["generic"].append(labels[i])
        w["box_h"] = [round(b["y1"] - b["y0"]) for b in d.get("marks", [])]
        texts = list(d.get("comments") or []) + [b.get("text", "") for b in d.get("marks", [])] + [rows.get(n, {}).get("feedback", "")]
        w["grader_words"] = [x for x in c.GRADER_WORDS if any(x in str(t) for t in texts)]
        works[n] = w
    per_section = {l: 0 for l in labels}
    for n in works:
        for i, (p, m) in enumerate(zip(src_notes(a, r, n).get("points") or [], full)):
            if p < m:
                per_section[labels[i]] += 1
    inconsistent = {t: v for t, v in by_tag.items() if len({x[2] for x in v}) > 1}
    boxes = [h for w in works.values() for h in w["box_h"]]
    out = {
        "works": len(works),
        "review_rate": round(sum(1 for n in works if rows.get(n, {}).get("review")) / max(len(works), 1), 3),
        "distinct_tags": len(by_tag),
        "inconsistent_tags": {t: sorted({x[2] for x in v}) for t, v in inconsistent.items()},
        "box_height_median": st.median(boxes) if boxes else None,
        "boxes_over_15pct": sum(1 for h in boxes if h > 150),
        "works_with_grader_words": sorted(n for n, w in works.items() if w["grader_words"]),
        "works_with_untagged_deduction": sorted(n for n, w in works.items() if w["deduction_no_tag"]),
        "per_section_deducted": per_section,
        "works_detail": works,
    }
    c.dump(out, r / "mechanical.json")
    c.say(f"{out['works']} עבודות · בתור הידני {out['review_rate']:.1%} · {out['distinct_tags']} תגיות טעות, "
          f"{len(inconsistent)} עם ניכוי לא אחיד · גובה מלבן חציוני {out['box_height_median']} אלפיות, "
          f"{out['boxes_over_15pct']} מעל 15% · מילות בודק אצל {len(out['works_with_grader_words'])} עבודות")
    for t, v in list(inconsistent.items())[:15]:
        c.say(f"  לא אחיד: {t[:60]} → {sorted({x[2] for x in v})}")
    return out


def backup(a: Path, r: Path) -> None:
    b = r / "before"
    (b / "notes").mkdir(parents=True, exist_ok=True)
    (b / "marked").mkdir(exist_ok=True)
    rows = c.grades(a)
    keep = {}
    for n in the_sample(r):
        for src, dst in ((a / "Grading notes" / f"{n}.json", b / "notes"), (a / "2 - Graded with comments" / f"{n}.pdf", b / "marked")):
            if src.is_file():
                shutil.copy2(src, dst / src.name)
        keep[n] = rows.get(n, {})
    c.dump(keep, b / "grades.json")
    c.say(f"גובו {len(keep)} עבודות ל-{b}")


def render(a: Path, r: Path, numbers: list[str] | None = None) -> None:
    import pymupdf
    for n in numbers or the_sample(r):
        pdf = src_marked(a, r, n)
        if not pdf.is_file():
            continue
        out = r / "pages" / n
        out.mkdir(parents=True, exist_ok=True)
        with pymupdf.open(pdf) as d:
            for i, p in enumerate(d):
                z = 1.6 if i == 0 else 1.4
                p.get_pixmap(matrix=pymupdf.Matrix(z, z)).save(out / f"p{i + 1:02d}.jpg", jpg_quality=70)
    c.say("העמודים ב-", r / "pages")


BOTTOM = re.compile(r"(נמוך|גבוה)(?: מדי)? בכ-(\d+(?:\.\d+)?)")


def target_from(bottom: str, grade: float) -> float | None:
    """The auditor's verdict -> the grade it says is right. None when the line says neither 'נכון' nor 'גבוה/נמוך בכ-N'."""
    m = BOTTOM.search(bottom)
    if m:
        k = float(m.group(2))
        return grade + k if m.group(1) == "נמוך" else grade - k
    if re.search(r"(הציון|ציון)[^.,;]{0,20}נכון", bottom) or bottom.strip().startswith("נכון"):
        return grade
    return None


def targets(a: Path, r: Path) -> dict:
    out = {}
    for log in sorted((r / "logs").glob("log-*.md")):
        n = log.stem.split("-")[-1]
        text = log.read_text(encoding="utf-8")
        bottom = text.split("## שורה תחתונה")[-1].strip()
        m = re.search(r"ציון (?:חדש )?(\d+(?:\.\d+)?)", text.split("\n", 1)[0])
        graded = float(m.group(1)) if m else float(src_rows(a, r).get(n, {}).get("grade") or 0)
        out[n] = {"graded": graded, "target": target_from(bottom, graded), "bottom": bottom[:300]}
    c.dump(out, r / "targets.json")
    c.say(f"{len(out)} יומנים; פסק ברור ב-{sum(1 for v in out.values() if v['target'] is not None)}")
    return out


LINE = re.compile(r"^\s*-\s*((?:\[[A-Z_]+\]\s*)+)(.*)$")
PAGE = re.compile(r"עמוד\s*p?(\d+)")
SECTION = re.compile(r"סעיף\s+([^·]+?)\s*·")
# the order a verifier gets them in: what changes a grade first, then what a student sees on the page
PRIORITY = ["HALLUCINATION", "MISSED", "MISREAD", "MISSING_SECTION_RULE", "DISPROPORTIONATE", "DOUBLE_PENALTY", "WORSE",
            "NO_RUBRIC_ROW", "ALT_METHOD_PENALIZED", "STILL", "TWO_ROWS", "BOX_OFF", "CHECK_WRONG_KIND", "NOTE_RTL",
            "NOTE_MISSING", "NOTE_ON_WRITING", "CHECK_MISPLACED", "BOX_HUGE", "NOTE_CUT"]


def claims(r: Path, cap: int = 40) -> list[dict]:
    """Every log line whose tag claims something is wrong, as one sentence with where to look -> verify-input.json."""
    out = []
    for log in sorted((r / "logs").glob("log-*.md")):
        n = log.stem.split("-")[-1]
        for k, line in enumerate(log.read_text(encoding="utf-8").splitlines()):
            m = LINE.match(line)
            if not m:
                continue
            tags = re.findall(r"\[([A-Z_]+)\]", m.group(1))
            tag = next((t for t in PRIORITY if t in tags), None)
            if tag is None:
                continue
            body = m.group(2)
            page = PAGE.search(body)
            sec = SECTION.search(body)
            out.append({"id": f"{n}:{k}", "work": n, "tag": tag, "section": sec.group(1).strip() if sec else "",
                        "page": int(page.group(1)) if page else None, "claim": body.strip()[:400]})
    out.sort(key=lambda x: (PRIORITY.index(x["tag"]), x["work"]))
    chosen = out[:cap]
    c.dump(chosen, r / "verify-input.json")
    c.say(f"{len(out)} טענות ביומנים; {len(chosen)} נשלחות לאימות ({', '.join(sorted({x['tag'] for x in chosen}))})")
    return chosen


def tally(r: Path) -> dict:
    counts = {t: [0, 0] for t in TAGS}  # lines, works
    for log in (r / "logs").glob("log-*.md"):
        text = log.read_text(encoding="utf-8")
        for t in TAGS:
            k = text.count(f"[{t}]")
            if k:
                counts[t][0] += k
                counts[t][1] += 1
    verify = c.load(r / "verify.json", {}) or {}
    confirmed = sum(1 for v in verify.values() if str(v.get("verdict", "")).upper() == "CONFIRMED")
    out = {"tags": {t: {"lines": v[0], "works": v[1]} for t, v in counts.items() if v[0]},
           "verified": {"checked": len(verify), "confirmed": confirmed,
                        "precision": round(confirmed / len(verify), 2) if verify else None}}
    c.dump(out, r / "tally.json")
    for t, v in out["tags"].items():
        c.say(f"  {t:24} {v['lines']:>3} שורות · {v['works']:>2} עבודות")
    if verify:
        c.say(f"אומתו {len(verify)} טענות, אושרו {confirmed} ({out['verified']['precision']:.0%})")
    return out


def compare(a: Path, r: Path, against: Path | None = None) -> dict:
    """Old grading (r/before, saved by backup) vs the current one, against the targets the auditors set
    (against/targets.json, default this round's). The measure that keeps a change: did works get closer?"""
    tg = c.load((against or r) / "targets.json", {}) or {}
    old_rows = c.load(r / "before" / "grades.json", {}) or {}
    rows = c.grades(a)
    labels, full = c.labels(a)
    out, err = {}, []
    for n in the_sample(r):
        old = c.load(r / "before" / "notes" / f"{n}.json", {}) or {}
        new = c.notes(a, n)
        og = float(old_rows.get(n, {}).get("grade") or 0)
        ng = float(rows.get(n, {}).get("grade") or 0)
        t = (tg.get(n) or {}).get("target")
        changed = [{"section": labels[i], "old": x, "new": y, "new_comment": (new.get("comments") or [""] * len(full))[i],
                    "new_tags": (new.get("mistakes") or [[]] * len(full))[i]}
                   for i, (x, y) in enumerate(zip(old.get("points") or [], new.get("points") or [])) if x != y]
        hs = [b["y1"] - b["y0"] for b in new.get("marks", [])]
        texts = list(new.get("comments") or []) + [b.get("text", "") for b in new.get("marks", [])] + [rows.get(n, {}).get("feedback", "")]
        rec = {"old": og, "new": ng, "target": t, "changed": changed, "marks": len(new.get("marks", [])),
               "box_height_median": st.median(hs) if hs else None,
               "places": sum(1 for p in new.get("places", []) if p.get("page")), "sections": len(full),
               "grader_words": [x for x in c.GRADER_WORDS if any(x in str(s) for s in texts)],
               "review": rows.get(n, {}).get("review", "")}
        if t is not None:
            rec["verdict"] = "closer" if abs(ng - t) < abs(og - t) else "same" if abs(ng - t) == abs(og - t) else "further"
            err.append((abs(og - t), abs(ng - t)))
        out[n] = rec
    summary = {"works": len(out),
               "mean_error_old": round(st.mean(x for x, _ in err), 2) if err else None,
               "mean_error_new": round(st.mean(y for _, y in err), 2) if err else None,
               "closer": sum(1 for v in out.values() if v.get("verdict") == "closer"),
               "same": sum(1 for v in out.values() if v.get("verdict") == "same"),
               "further": sorted(n for n, v in out.items() if v.get("verdict") == "further"),
               "grader_words": sorted(n for n, v in out.items() if v["grader_words"]),
               "places_missing": sorted(n for n, v in out.items() if v["places"] < v["sections"])}
    c.dump({"summary": summary, "works": out}, r / "compare.json")
    c.say(f"{'עבודה':6} {'לפני':>5} {'אחרי':>5} {'יעד':>5}  פסק")
    for n, v in out.items():
        c.say(f"{n:6} {v['old']:>5g} {v['new']:>5g} {'' if v['target'] is None else format(v['target'], 'g'):>5}  "
              f"{v.get('verdict', '-')}  {len(v['changed'])} סעיפים השתנו")
    c.say(f"מרחק ממוצע מהיעד: {summary['mean_error_old']} → {summary['mean_error_new']} · "
          f"התקרבו {summary['closer']}, נשארו {summary['same']}, התרחקו {len(summary['further'])} {summary['further'] or ''}")
    return summary


ITEM = re.compile(r"^\s*(?:[-*|]\s*)?\**\[?([RG])(\d+)\]?\**", re.M)


def check_report(r: Path, report: Path) -> list[str]:
    """The report checks itself: R and G items numbered in order, each one citing a work of the round's sample and
    a tag, and every cited claim confirmed by the verifier when verify.json exists."""
    text = report.read_text(encoding="utf-8")
    sample_ = set(the_sample(r))
    verify = c.load(r / "verify.json", {}) or {}
    problems = []
    for kind in "RG":
        nums = [int(m.group(2)) for m in ITEM.finditer(text) if m.group(1) == kind]
        seen = list(dict.fromkeys(nums))
        if seen and seen != list(range(1, len(seen) + 1)):
            problems.append(f"{kind}: המספור לא רציף ({seen})")
    blocks = re.split(r"\n(?=\s*(?:[-*|]\s*)?\**\[?[RG]\d+)", text)
    for b in blocks:
        m = ITEM.match(b)
        if not m:
            continue
        item = f"{m.group(1)}{m.group(2)}"
        works = set(re.findall(r"\b\d{4}\b", b))
        if not works & sample_:
            problems.append(f"{item}: לא מצטט אף עבודה מהמדגם")
        if verify:
            rejected = [k for k, v in verify.items() if str(v.get("verdict", "")).upper() == "REJECTED" and k.split(":")[0] in works
                        and k.split(":")[-1] in b]
            if rejected:
                problems.append(f"{item}: נשען על טענה שהמאמת דחה ({', '.join(rejected[:3])})")
    c.say("הדוח תקין" if not problems else "בעיות בדוח:\n  " + "\n  ".join(problems))
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["sample", "mechanical", "backup", "render", "targets", "claims", "tally", "compare", "check-report"])
    ap.add_argument("assignment")
    ap.add_argument("report", nargs="?")
    ap.add_argument("--round", required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--include", nargs="*", default=[])
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--seed", type=int, default=20261113)
    ap.add_argument("--against", help="a round whose targets.json to measure against (default: this round)")
    ap.add_argument("--work-root", help=argparse.SUPPRESS)
    x = ap.parse_args(argv)
    a = c.assignment_dir(x.assignment)
    r = c.round_dir(a, x.round, Path(x.work_root) if x.work_root else None)
    if x.cmd == "sample":
        sample(a, r, x.n, x.include, x.fresh, x.seed)
    elif x.cmd == "mechanical":
        mechanical(a, r)
    elif x.cmd == "backup":
        backup(a, r)
    elif x.cmd == "render":
        render(a, r)
    elif x.cmd == "targets":
        targets(a, r)
    elif x.cmd == "claims":
        claims(r, x.max)
    elif x.cmd == "tally":
        tally(r)
    elif x.cmd == "compare":
        compare(a, r, c.round_dir(a, x.against, Path(x.work_root) if x.work_root else None) if x.against else None)
    elif x.cmd == "check-report":
        if not x.report:
            raise SystemExit("חסר נתיב לדוח")
        return 1 if check_report(r, Path(x.report)) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
