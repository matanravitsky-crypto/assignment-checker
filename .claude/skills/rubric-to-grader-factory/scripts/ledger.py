"""The token and cost ledger of a factory run: one line per stage and agent, with the cost in USD.

    python ledger.py add <run dir> --stage <שלב> --agent <מי> --model opus|sonnet|haiku --tokens N [--seconds S]
                     [--input N --output N --cache-read N --cache-write N] [--usd X]
    python ledger.py summary <run dir>        per stage: agents, tokens, seconds, USD (exact or a range)

Exact when it is known: a headless `claude -p` run reports its own `total_cost_usd` (`--usd`), or the usage split
(`--input/--output/--cache-*`). A subagent of a session reports only its total tokens: then the cost is a range,
from all of them read from the cache (the floor) to all of them fresh input plus 5% output (the ceiling), and it is
labelled as an estimate. Prices: Anthropic's first-party list (claude-api skill, cached 2026-11-03), per 1M tokens.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PRICES = {  # $ per 1M tokens: input, output, cache read, cache write (5 min = 1.25 x input)
    "opus": {"id": "claude-opus-5-5", "in": 4.00, "out": 20.00, "read": 0.20, "write": 5.00},
    "sonnet": {"id": "claude-sonnet-5-5", "in": 2.00, "out": 10.00, "read": 0.10, "write": 2.50},
    "haiku": {"id": "claude-haiku-5-5", "in": 0.10, "out": 0.50, "read": 0.01, "write": 0.125},
}
LEDGER = "ledger.jsonl"


def cost(row: dict) -> tuple[float, float, bool]:
    """(low, high, exact) in USD."""
    if row.get("usd") is not None:
        return row["usd"], row["usd"], True
    p = PRICES[row["model"]]
    if any(row.get(k) is not None for k in ("input", "output", "cache_read", "cache_write")):
        usd = ((row.get("input") or 0) * p["in"] + (row.get("output") or 0) * p["out"]
               + (row.get("cache_read") or 0) * p["read"] + (row.get("cache_write") or 0) * p["write"]) / 1e6
        return usd, usd, True
    t = row.get("tokens") or 0
    return t * p["read"] / 1e6, (t * 0.95 * p["in"] + t * 0.05 * p["out"]) / 1e6, False


def add(run: Path, **row) -> dict:
    run.mkdir(parents=True, exist_ok=True)
    with (run / LEDGER).open("a", encoding="utf-8") as f:
        f.write(json.dumps({k: v for k, v in row.items() if v is not None}, ensure_ascii=False) + "\n")
    return row


def read(run: Path) -> list[dict]:
    f = Path(run) / LEDGER
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.is_file() else []


def summary(run: Path) -> dict:
    stages: dict[str, dict] = {}
    for r in read(run):
        s = stages.setdefault(r["stage"], {"agents": 0, "tokens": 0, "seconds": 0, "low": 0.0, "high": 0.0,
                                           "exact": True, "models": set()})
        lo, hi, exact = cost(r)
        s["agents"] += 1
        s["tokens"] += r.get("tokens") or 0
        s["seconds"] += r.get("seconds") or 0
        s["low"] += lo
        s["high"] += hi
        s["exact"] = s["exact"] and exact
        s["models"].add(r["model"])
    out = {k: {**v, "models": sorted(v["models"]), "low": round(v["low"], 2), "high": round(v["high"], 2)}
           for k, v in stages.items()}
    out["סה\"כ"] = {"agents": sum(v["agents"] for v in stages.values()),
                    "tokens": sum(v["tokens"] for v in stages.values()),
                    "seconds": sum(v["seconds"] for v in stages.values()),
                    "low": round(sum(v["low"] for v in stages.values()), 2),
                    "high": round(sum(v["high"] for v in stages.values()), 2),
                    "exact": all(v["exact"] for v in stages.values()), "models": []}
    return out


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="ledger.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("run", type=Path)
    a.add_argument("--stage", required=True)
    a.add_argument("--agent", required=True)
    a.add_argument("--model", required=True, choices=sorted(PRICES))
    a.add_argument("--tokens", type=int)
    a.add_argument("--seconds", type=float)
    for k in ("input", "output", "cache-read", "cache-write"):
        a.add_argument(f"--{k}", type=int)
    a.add_argument("--usd", type=float)
    s = sub.add_parser("summary")
    s.add_argument("run", type=Path)
    x = p.parse_args(argv)
    if x.cmd == "add":
        add(x.run, stage=x.stage, agent=x.agent, model=x.model, tokens=x.tokens, seconds=x.seconds, input=x.input,
            output=x.output, cache_read=x.cache_read, cache_write=x.cache_write, usd=x.usd)
        return 0
    print(json.dumps(summary(x.run), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
