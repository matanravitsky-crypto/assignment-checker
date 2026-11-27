"""The bench: a rubric's grading skill against the system, work by work (grading-skill-maker, Step 3).

    python bench.py run <moodle id> --skill grade-linear-0 --round R (--numbers 0012 0040 ... | --n N) [--parallel 3]
    python bench.py run ... --arm generic          the same works through exercise-grader, the rubric given as Rubric.md
    python bench.py baseline <moodle id> --round R the system's engine on the round's works (when it has no grades)
    python bench.py summary <moodle id> --round R

`run` grades each work the way a teammate would: one headless `claude -p` that is asked, in Hebrew, to grade that work
with the skill, in a fresh folder outside OneDrive with only that work's files, and to save the marked PDF there. It
records what the run cost (Claude Code's own `total_cost_usd`, tokens, turns, seconds) plus the zoom pass that `mark`
starts (its usage line, written into the run's folder: ASSIGNMENT_DATA points there), and the grade and points per
question that `mark` wrote. Nothing is written to the shared folder: the grades of the system are only read.

`summary` sets them against the system's grade of the same work (the merged `Grades by` rows and `Grading notes`;
a TA-approved row is the gold): the difference in grade and per question, how often it is within the run-to-run noise
(1-4 points, measured in meta-evaluator rounds), how many would go to manual review, and cost and time per work against
the system's own (the median of `Grading usage.jsonl` for the same model). Numbers only, never a name.

Everything lives in ~/.skill-bench/<id>/<round>/ (student pages: never in the repo or OneDrive).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from moodle import claude_code, grades, paths, shared_folder  # noqa: E402

BENCH = Path.home() / ".skill-bench"
TIMEOUT_S = 30 * 60
BUDGET_USD = "6"
END = ("את העבודה הבדוקה שמור בתיקייה {out} (לא בשולחן העבודה), ואל תפתח את התיקייה בסייר. "
       "בסוף כתוב רק את הציון ואת הנתיב של ה-PDF.")
# the two arms: the rubric's own skill (the rubric built in), and the original skill with the rubric as a teammate
# gives it (the assignment's Rubric.md, a copy in the run's folder)
PROMPTS = {"skill": "תבדוק את העבודה שבתיקייה {inp} עם הסקיל {skill}. " + END,
           "generic": "תבדוק את העבודה שבתיקייה {inp} עם הסקיל exercise-grader, לפי המחוון {rubric}. " + END}
SYSTEM_ROUND = "{round}-system"  # the system's engine on the same works (meta-evaluator offline.py), when it has no grade


def _root() -> Path:
    try:
        shared_folder.use_for_commands()
    except Exception:  # noqa: BLE001  (no shared folder on this computer: ASSIGNMENT_DATA or the default)
        pass
    return paths.data_dir()


def round_dir(assignment_id: str, name: str) -> Path:
    d = BENCH / str(assignment_id) / name
    for bad in (REPO, Path.home() / "OneDrive"):
        try:
            d.resolve().relative_to(bad.resolve())
            raise SystemExit(f"{d} is inside {bad}: student pages never go there")
        except ValueError:
            pass
    return d


def _usage(folder: Path) -> list[dict]:
    return _usage_file(folder / paths.USAGE_LOG)


def _usage_file(f: Path) -> list[dict]:
    out = []
    if f.is_file():
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def run_one(assignment: Path, number: str, skill: str, rnd: Path, model: str | None, arm: str = "skill") -> dict:
    work = rnd / "runs" / number
    if work.exists():
        shutil.rmtree(work)
    inp, out = work / "in", work / "out"
    inp.mkdir(parents=True)
    out.mkdir()
    for f in paths.files_by_number(assignment / paths.TO_GRADE).get(number, []):
        shutil.copyfile(f, inp / f.name)
    rubric = work / "rubric" / "Rubric.md"
    if arm == "generic":
        src = next((assignment / d / "Rubric.md" for d in paths.PEDAGOGY if (assignment / d / "Rubric.md").is_file()), None)
        if src is None:
            raise SystemExit("the generic arm needs the assignment's Rubric.md")
        rubric.parent.mkdir()
        shutil.copyfile(src, rubric)
    exe = claude_code.find_claude()
    if not exe:
        raise SystemExit("Claude Code is not installed here")
    cmd = [exe, "-p", "--output-format", "json", "--no-session-persistence",
           "--allowedTools", "Bash Read Write Edit Glob Grep Skill", "--max-budget-usd", BUDGET_USD]
    if model:
        cmd += ["--model", model]
    env = {**os.environ, "ASSIGNMENT_DATA": str(work), "PYTHONIOENCODING": "utf-8"}
    started = time.monotonic()
    try:
        p = subprocess.run(cmd, input=PROMPTS[arm].format(inp=inp, out=out, skill=skill, rubric=rubric), cwd=work, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_S)
        raw, code = p.stdout, p.returncode
    except subprocess.TimeoutExpired:
        raw, code = "", "timeout"
    seconds = round(time.monotonic() - started, 1)
    try:
        res = json.loads(raw)
    except ValueError:
        res = {}
    usage = res.get("usage") or {}
    marked = sorted(out.glob("*.json"))
    summary = json.loads(marked[-1].read_text(encoding="utf-8")) if marked else None
    zoom = [u for u in _usage(work) if u.get("purpose") == "locate"]
    row = {"number": number, "arm": arm, "ok": bool(summary) and not res.get("is_error"), "exit": code, "seconds": seconds,
           "cost_usd": res.get("total_cost_usd"), "turns": res.get("num_turns"),
           "input": usage.get("input_tokens"), "cache_write": usage.get("cache_creation_input_tokens"),
           "cache_read": usage.get("cache_read_input_tokens"), "output": usage.get("output_tokens"),
           "zoom_cost_usd": round(sum(u.get("cost_usd") or 0 for u in zoom), 4),
           "grade": summary and summary.get("grade"), "review": summary and summary.get("review"),
           "points": summary and [q["points"] for q in summary["questions"]],
           "labels": summary and [q["label"] for q in summary["questions"]]}
    (work / "result.json").write_text(json.dumps({"row": row, "claude": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    with (rnd / "bench.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{number}: {'ok' if row['ok'] else 'FAILED'} grade={row['grade']} ${row['cost_usd']} +zoom ${row['zoom_cost_usd']} "
          f"{seconds}s {row['turns']} turns", flush=True)
    return row


def run(assignment_id: str, skill: str, name: str, numbers: list[str] | None, n: int | None, parallel: int,
        model: str | None, seed: int, arm: str = "skill") -> None:
    assignment = paths.assignment_dir(assignment_id)
    rnd = round_dir(assignment_id, name)
    rnd.mkdir(parents=True, exist_ok=True)
    have = grades.read(assignment)
    if not numbers:
        on_disk = paths.files_by_number(assignment / paths.TO_GRADE)  # one listing: the folder has ~1,100 files
        pool = sorted(n_ for n_ in (have or on_disk) if on_disk.get(n_))  # no grades yet (LA1): any submission
        numbers = sorted(random.Random(seed).sample(pool, min(n or 0, len(pool))))
    (rnd / "plan.json").write_text(json.dumps({"skill": skill, "arm": arm, "numbers": numbers, "model": model}, indent=1),
                                   encoding="utf-8")
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool_:
        list(pool_.map(lambda num: run_one(assignment, num, skill, rnd, model, arm), numbers))


def baseline(assignment_id: str, name: str, parallel: int) -> int:
    """The system's engine on the round's works, into ~/.meta-eval/<id>/<round>-system (nothing in the shared folder)."""
    plan = json.loads((round_dir(assignment_id, name) / "plan.json").read_text(encoding="utf-8"))
    offline = Path(__file__).resolve().parents[2] / "meta-evaluator" / "scripts" / "offline.py"
    return subprocess.run([sys.executable, str(offline), str(assignment_id), "--round",
                           SYSTEM_ROUND.format(round=name), "--parallel", str(parallel), "--numbers", *plan["numbers"]],
                          cwd=REPO).returncode


def _offline(assignment_id: str, name: str) -> tuple[dict, dict]:
    """The baseline round's grades and its cost per work (grade + zoom), or empty."""
    d = Path.home() / ".meta-eval" / str(assignment_id) / SYSTEM_ROUND.format(round=name)
    g = json.loads((d / "grades.json").read_text(encoding="utf-8")) if (d / "grades.json").is_file() else {}
    cost: dict[str, float] = {}
    for u in _usage_file(d / "usage.jsonl"):
        cost[u.get("work", "")] = cost.get(u.get("work", ""), 0) + (u.get("cost_usd") or 0)
    return g, cost


def _system_cost(root: Path) -> dict:
    rows = [u for u in _usage(root) if u.get("purpose") in ("grade", "locate") and u.get("seconds")]
    out = {}
    for purpose in ("grade", "locate"):
        c = [u["cost_usd"] for u in rows if u["purpose"] == purpose and u.get("cost_usd") is not None]
        s = [u["seconds"] for u in rows if u["purpose"] == purpose]
        out[purpose] = {"n": len(c), "cost": round(statistics.median(c), 3) if c else None,
                        "seconds": round(statistics.median(s)) if s else None}
    return out


def _points(raw) -> list[float] | None:
    if isinstance(raw, list):
        return [float(x) for x in raw]
    try:
        return [float(x) for x in json.loads(raw)] if raw else None
    except (ValueError, TypeError):
        return None


def summary(assignment_id: str, name: str) -> dict:
    assignment = paths.assignment_dir(assignment_id)
    rnd = round_dir(assignment_id, name)
    rows = {}
    for line in (rnd / "bench.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        rows[r["number"]] = r  # the last run of a number counts
    sysg = grades.read(assignment)
    off, off_cost = _offline(assignment_id, name)
    for num, row in off.items():  # the engine's own run, where the system has no grade
        if not (sysg.get(num) or {}).get("grade"):
            sysg[num] = {"grade": row["grade"], "points": [float(x) for x in str(row["points"]).split(";") if x]}
    out_rows, dg, dq, gold = [], [], [], []
    for num, r in sorted(rows.items()):
        s = sysg.get(num) or {}
        note = {}
        nf = assignment / paths.NOTES / f"{num}.json"
        if nf.is_file():
            note = json.loads(nf.read_text(encoding="utf-8"))
        sp = _points(note.get("points")) or _points(s.get("points"))
        d = None
        if r["ok"] and s.get("grade") not in (None, ""):
            d = float(r["grade"]) - float(s["grade"])
            dg.append(d)
            if grades.is_approved(s):
                gold.append(d)
        per = [round(a - b, 2) for a, b in zip(r["points"] or [], sp or [])] if r["ok"] and sp else []
        dq += [abs(x) for x in per]
        out_rows.append({"number": num, "skill": r["grade"], "system": s.get("grade"), "diff": d,
                         "approved": grades.is_approved(s), "questions_off": sum(1 for x in per if x),
                         "cost": round((r["cost_usd"] or 0) + (r["zoom_cost_usd"] or 0), 3), "seconds": r["seconds"],
                         "review": bool(r["review"])})
    ok = [r for r in rows.values() if r["ok"]]
    absd = [abs(x) for x in dg]
    cost = [(r["cost_usd"] or 0) + (r["zoom_cost_usd"] or 0) for r in ok]
    res = {"round": name, "works": len(rows), "graded": len(ok), "failed": len(rows) - len(ok),
           "grade_mean_abs_diff": round(statistics.mean(absd), 2) if absd else None,
           "grade_mean_diff": round(statistics.mean(dg), 2) if dg else None,
           "within_4": sum(1 for x in absd if x <= 4), "same": sum(1 for x in absd if x == 0),
           "over_10": sum(1 for x in absd if x > 10),
           "question_mean_abs_diff": round(statistics.mean(dq), 2) if dq else None,
           "gold_mean_abs_diff": round(statistics.mean(abs(x) for x in gold), 2) if gold else None, "gold_n": len(gold),
           "manual_review": sum(1 for r in ok if r["review"]),
           "cost_median": round(statistics.median(cost), 3) if any(r["cost_usd"] for r in ok) else None,
           "seconds_median": round(statistics.median(r["seconds"] for r in ok)) if ok and all(r["seconds"] for r in ok) else None,
           "turns_median": statistics.median(r["turns"] or 0 for r in ok) if ok else None,
           "system": _system_cost(paths.data_dir()),
           "system_this_round": {"n": len(off_cost), "cost": round(statistics.median(off_cost.values()), 3)}
           if off_cost else None, "rows": out_rows}
    (rnd / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def compare(assignment_id: str, rounds: list[str]) -> dict:
    """Two or more rounds on the same works (the rubric's skill, exercise-grader, ...) side by side, with the system."""
    sums = {r: summary(assignment_id, r) for r in rounds}
    by = {r: {row["number"]: row for row in s_["rows"]} for r, s_ in sums.items()}
    common = sorted(set.intersection(*(set(b) for b in by.values())))
    table = [{"number": n, "system": by[rounds[0]][n]["system"],
              **{r: by[r][n]["skill"] for r in rounds}, **{f"{r}_cost": by[r][n]["cost"] for r in rounds}} for n in common]
    pairs = {}
    for i, a in enumerate(rounds):
        for b in rounds[i + 1:]:
            d = [abs(float(t[a]) - float(t[b])) for t in table if t[a] is not None and t[b] is not None]
            pairs[f"{a} vs {b}"] = round(statistics.mean(d), 2) if d else None
    out = {"works": len(common), "between": pairs,
           "per_round": {r: {k: s_[k] for k in ("graded", "failed", "grade_mean_abs_diff", "grade_mean_diff", "within_4",
                                                 "over_10", "question_mean_abs_diff", "manual_review", "cost_median",
                                                 "seconds_median", "turns_median")} for r, s_ in sums.items()},
           "table": table}
    (BENCH / str(assignment_id) / ("compare-" + "-".join(rounds) + ".json")).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def prepare(assignment_id: str, name: str, numbers: list[str] | None, n: int | None, seed: int,
            exclude: list[str] | None = None) -> list[dict]:
    """The works of a round in their own folders (runs/NNNN/in, out), for grading by agents of a running session
    instead of headless `claude -p` (no sign-in of Claude Code needed). `collect` reads what they wrote."""
    assignment = paths.assignment_dir(assignment_id)
    rnd = round_dir(assignment_id, name)
    rnd.mkdir(parents=True, exist_ok=True)
    on_disk = paths.files_by_number(assignment / paths.TO_GRADE)
    if not numbers:
        graded = grades.read(assignment)
        pool = sorted(x for x in (graded or on_disk) if on_disk.get(x) and x not in set(exclude or []))
        numbers = sorted(random.Random(seed).sample(pool, min(n or 0, len(pool))))
    out = []
    for num in numbers:
        work = rnd / "runs" / num
        (work / "in").mkdir(parents=True, exist_ok=True)
        (work / "out").mkdir(exist_ok=True)
        for f in on_disk.get(num, []):
            shutil.copyfile(f, work / "in" / f.name)
        out.append({"number": num, "in": str(work / "in"), "out": str(work / "out")})
    (rnd / "plan.json").write_text(json.dumps({"numbers": numbers, "via": "agents"}, indent=1), encoding="utf-8")
    return out


def collect(assignment_id: str, name: str) -> int:
    """bench.jsonl from what `mark` wrote in each work's out folder (agents' rounds: no cost from Claude Code)."""
    rnd = round_dir(assignment_id, name)
    rows = []
    for work in sorted((rnd / "runs").iterdir()):
        marked = sorted((work / "out").glob("*.json"))
        s_ = json.loads(marked[-1].read_text(encoding="utf-8")) if marked else None
        rows.append({"number": work.name, "arm": "agent", "ok": bool(s_), "exit": None, "seconds": None,
                     "cost_usd": None, "turns": None, "zoom_cost_usd": 0,
                     "grade": s_ and s_.get("grade"), "review": s_ and s_.get("review"),
                     "points": s_ and [q["points"] for q in s_["questions"]],
                     "labels": s_ and [q["label"] for q in s_["questions"]]})
    (rnd / "bench.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + chr(10) for r in rows), encoding="utf-8")
    return sum(1 for r in rows if r["ok"])


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="bench.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("id")
    r.add_argument("--skill", required=True)
    r.add_argument("--round", required=True)
    r.add_argument("--numbers", nargs="*")
    r.add_argument("--n", type=int)
    r.add_argument("--parallel", type=int, default=3)
    r.add_argument("--model")
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--arm", choices=sorted(PROMPTS), default="skill")
    bl = sub.add_parser("baseline")
    bl.add_argument("id")
    bl.add_argument("--round", required=True)
    bl.add_argument("--parallel", type=int, default=3)
    pr = sub.add_parser("prepare")
    pr.add_argument("id")
    pr.add_argument("--round", required=True)
    pr.add_argument("--numbers", nargs="*")
    pr.add_argument("--n", type=int)
    pr.add_argument("--seed", type=int, default=7)
    pr.add_argument("--exclude", nargs="*")
    co = sub.add_parser("collect")
    co.add_argument("id")
    co.add_argument("--round", required=True)
    cp = sub.add_parser("compare")
    cp.add_argument("id")
    cp.add_argument("--rounds", nargs="+", required=True)
    s = sub.add_parser("summary")
    s.add_argument("id")
    s.add_argument("--round", required=True)
    a = p.parse_args(argv)
    _root()
    if a.cmd == "run":
        if not a.numbers and not a.n:
            p.error("--numbers or --n (how many is the user's call)")
        run(a.id, a.skill, a.round, a.numbers, a.n, a.parallel, a.model, a.seed, a.arm)
        return 0
    if a.cmd == "baseline":
        return baseline(a.id, a.round, a.parallel)
    if a.cmd == "prepare":
        print(json.dumps(prepare(a.id, a.round, a.numbers, a.n, a.seed, a.exclude), indent=1))
        return 0
    if a.cmd == "collect":
        print(f"{collect(a.id, a.round)} works graded")
        return 0
    if a.cmd == "compare":
        print(json.dumps(compare(a.id, a.rounds), ensure_ascii=False, indent=1))
        return 0
    res = summary(a.id, a.round)
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, ensure_ascii=False, indent=1))
    for row in res["rows"]:
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
