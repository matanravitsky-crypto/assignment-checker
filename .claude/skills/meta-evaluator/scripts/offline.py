"""Grade works into the round's folder only: the shared folder is not touched (no grades, notes, marked PDFs, claims,
usage log or statistics). For a quality round on submissions nobody graded yet, so the team's real grading later
finds nothing of it (Ori, 2026-11-13: "שלא ישמרו בשום מקום חוץ מאצלך"). The same engine as the system and the
exercise-grader skill (grading.grade.grade_one + the zoom pass); it proves itself with a fingerprint of the shared
files before and after.

    python offline.py <assignment> --round R --n 20 [--numbers 0012 0040 ...] [--parallel 4]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402


def fingerprint(a: Path) -> dict[str, list]:
    """Size and mtime of every file the grading could write: the assignment folder (all of it) and the data folder's
    own files and statistics."""
    from moodle import paths
    roots = [a]
    data = paths.data_dir()
    out: dict[str, list] = {}
    for root in roots:
        for p in root.rglob("*"):
            if p.is_file():
                s = p.stat()
                out[str(p)] = [s.st_size, s.st_mtime_ns]
    for p in list(data.glob("*")) + list((data / "Statistics").rglob("*")):
        if p.is_file():
            s = p.stat()
            out[str(p)] = [s.st_size, s.st_mtime_ns]
    return out


def changed(before: dict, after: dict) -> list[str]:
    return sorted({k for k in set(before) | set(after) if before.get(k) != after.get(k)})


def pick(a: Path, n: int, seed: int) -> list[str]:
    """n submissions spread over page counts (short, middle, long), seeded so a round can be repeated."""
    from grading import grade
    files = grade.submission_files(a)
    nums = sorted(files)
    rnd = random.Random(seed)
    sizes = {x: sum(f.stat().st_size for f in files[x]) for x in nums}
    nums.sort(key=lambda x: sizes[x])
    k = len(nums)
    thirds = [nums[: k // 3], nums[k // 3: 2 * k // 3], nums[2 * k // 3:]]
    chosen: list[str] = []
    for i, third in enumerate(thirds):
        want = (n - len(chosen)) // (3 - i) if i < 2 else n - len(chosen)
        chosen += rnd.sample(third, min(want, len(third)))
    return sorted(chosen)


def run(a: Path, r: Path, numbers: list[str], parallel: int = 4) -> dict:
    from grading import claude_cli, grade, locate
    before = fingerprint(a)
    (r / "notes").mkdir(exist_ok=True)
    (r / "marked").mkdir(exist_ok=True)
    usage = r / "usage.jsonl"
    current = threading.local()
    lock = threading.Lock()

    def log_usage(stdout: str, model: str, purpose: str = "grade") -> None:  # instead of the data folder's log
        try:
            d = json.loads(stdout)
            u = d.get("usage") or {}
            row = {"work": getattr(current, "n", ""), "purpose": purpose, "model": model, "turns": d.get("num_turns"),
                   "cost_usd": d.get("total_cost_usd"), "input": u.get("input_tokens"), "output": u.get("output_tokens"),
                   "cache_read": u.get("cache_read_input_tokens"), "cache_write": u.get("cache_creation_input_tokens"),
                   "seconds": round((d.get("duration_ms") or 0) / 1000, 1)}
            with lock, usage.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except Exception:  # noqa: BLE001
            pass

    claude_cli.log_usage = log_usage
    ctx = grade.load_context(a)
    files = grade.submission_files(a)
    ask = grade.claude_ask()
    zoom = grade.claude_ask(locate.SCHEMA, locate.EFFORT) if locate.enabled() else None
    model = grade.default_model()
    rows: dict[str, dict] = {}

    def one(n: str):
        current.n = n
        t = time.time()
        pdf, skipped = grade.submission_pdf(files[n])
        g, out = grade.grade_one(pdf, ctx, ask, model, [], locate_ask=zoom)
        (r / "marked" / f"{n}.pdf").write_bytes(out)
        note = grade.graded_notes(g, model)
        note.update({"grade": g.grade, "feedback": g.feedback, "seconds": round(time.time() - t, 1), "skipped_files": skipped})
        c.dump(note, r / "notes" / f"{n}.json")
        return n, {"number": n, "grade": g.grade, "feedback": g.feedback, "review": g.review,
                   "points": ";".join(f"{p:g}" for p in g.points), "seconds": note["seconds"]}

    failed = {}
    with ThreadPoolExecutor(parallel) as ex:
        futs = {ex.submit(one, n): n for n in numbers}
        for f in as_completed(futs):
            n = futs[f]
            try:
                _, row = f.result()
                rows[n] = row
                c.say(f"  {n}: {row['grade']:g} ({row['seconds']:.0f} שניות)")
            except Exception as e:  # noqa: BLE001
                failed[n] = str(e)[:300]
                c.say(f"  {n}: נכשלה: {str(e)[:120]}")
    c.dump(rows, r / "grades.json")
    after = fingerprint(a)
    touched = changed(before, after)
    c.dump({"before": len(before), "after": len(after), "changed": touched, "failed": failed}, r / "offline-check.json")
    if touched:
        c.say("אזהרה: קבצים בתיקייה המשותפת השתנו בזמן הריצה (אולי סנכרון של מחשב אחר):", *touched[:10])
    else:
        c.say(f"לא נכתב שום דבר בתיקייה המשותפת ({len(before)} קבצים נבדקו לפני ואחרי).")
    return {"graded": len(rows), "failed": failed, "touched": touched}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("assignment")
    ap.add_argument("--round", required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--numbers", nargs="*")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20261113)
    x = ap.parse_args(argv)
    a = c.assignment_dir(x.assignment)
    r = c.round_dir(a, x.round)
    numbers = x.numbers or pick(a, x.n, x.seed)
    c.dump({"assignment": str(a), "sample": numbers, "seed": x.seed, "offline": True}, r / "sample.json")
    c.say(f"בודק {len(numbers)} עבודות לתיקייה {r} בלבד:", " ".join(numbers))
    res = run(a, r, numbers, x.parallel)
    return 1 if res["touched"] else 0


if __name__ == "__main__":
    sys.exit(main())
