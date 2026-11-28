"""The user's remarks as permanent regression tests (the loop with the person: every remark is checked every round).

    python regress.py add <skill> --work 0586 --section 14א --points 5 --why "<the remark, in the user's words>"
    python regress.py check <skill> <round dir>      every case the round graded: pass or fail, and why

Cases live in ~/.grading-skill-drafts/<skill>-regressions.jsonl (numbers and points only, never a name). `check`
reads `<round>\\runs\\NNNN\\out\\*.json` (what `mark` wrote) and compares the section's points with the case.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

DRAFTS = Path.home() / ".grading-skill-drafts"


def cases_file(skill: str) -> Path:
    return DRAFTS / f"{skill}-regressions.jsonl"


def cases(skill: str) -> list[dict]:
    f = cases_file(skill)
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.is_file() else []


def add(skill: str, work: str, section: str, points: float, why: str) -> dict:
    DRAFTS.mkdir(parents=True, exist_ok=True)
    case = {"work": work, "section": section, "points": points, "why": why,
            "added": datetime.now().isoformat(timespec="seconds")}
    with cases_file(skill).open("a", encoding="utf-8") as f:
        f.write(json.dumps(case, ensure_ascii=False) + "\n")
    return case


def check(skill: str, rnd: Path) -> list[dict]:
    out = []
    for c in cases(skill):
        marked = sorted((Path(rnd) / "runs" / c["work"] / "out").glob("*.json"))
        if not marked:
            continue
        got = json.loads(marked[-1].read_text(encoding="utf-8"))
        q = next((q for q in got["questions"] if " ".join(q["label"].split()).endswith(c["section"])), None)
        pts = q["points"] if q else None
        out.append({**c, "got": pts, "pass": pts is not None and abs(pts - c["points"]) < 0.01})
    return out


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="regress.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("skill")
    a.add_argument("--work", required=True)
    a.add_argument("--section", required=True)
    a.add_argument("--points", type=float, required=True)
    a.add_argument("--why", required=True)
    c = sub.add_parser("check")
    c.add_argument("skill")
    c.add_argument("round", type=Path)
    x = p.parse_args(argv)
    if x.cmd == "add":
        print(json.dumps(add(x.skill, x.work, x.section, x.points, x.why), ensure_ascii=False))
        return 0
    res = check(x.skill, x.round)
    for r in res:
        print(f"{'עבר' if r['pass'] else 'נכשל'}: {r['work']} {r['section']} צפוי {r['points']:g}, התקבל {r['got']}  ({r['why']})")
    print(f"{sum(r['pass'] for r in res)} מתוך {len(res)} מקרים עברו")
    return 0 if all(r["pass"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
