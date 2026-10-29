#!/usr/bin/env python3
"""Check rubric.json: points add up, deductions are sane, types are allowed. Exit 1 on any problem."""
import sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Hebrew on a Windows console
import json, re, sys

TYPES = {"הבנה", "חוסר", "חישוב", "סימון", "נימוק חסר"}
DED = re.compile(r"^(\d+|\d+[–-]\d+|עד \d+)$")

def ded_max(s):
    return max(int(x) for x in re.findall(r"\d+", s))

def main(path):
    r = json.load(open(path, encoding="utf-8"))
    e = []
    for q in r.get("questions", []):
        qn = q.get("n", "?")
        secs = q.get("sections", [])
        total = sum(s["points"] * int(s.get("count", 1)) for s in secs)  # count: one block for several identical sections
        if secs and total != q["points"]:
            e.append(f"שאלה {qn}: סעיפים מסתכמים ל-{total} ולא ל-{q['points']}")
        for s in secs:
            sid = f"שאלה {qn} סעיף {s.get('letter','?')}"
            if not s.get("answer", "").strip(): e.append(f"{sid}: אין תשובה")
            st = s.get("steps", [])
            if sum(x["points"] for x in st) != s["points"]:
                e.append(f"{sid}: שלבים מסתכמים ל-{sum(x['points'] for x in st)} ולא ל-{s['points']}")
            for m in s.get("alt_methods", []):
                ms = sum(x["points"] for x in m.get("steps", []))
                if ms != s["points"]: e.append(f"{sid}: דרך '{m.get('name')}' מסתכמת ל-{ms} ולא ל-{s['points']}")
            for er in s.get("errors", []):
                if er.get("type") not in TYPES: e.append(f"{sid}: סוג טעות לא מוכר '{er.get('type')}'")
                for k in ("regular", "strict"):
                    v = str(er.get(k, ""))
                    if not DED.match(v): e.append(f"{sid}: ניכוי לא תקין '{v}' ({er['desc'][:30]})")
                    elif ded_max(v) > s["points"]: e.append(f"{sid}: ניכוי {v} גדול מהסעיף ({s['points']})")
                if DED.match(str(er.get("regular",""))) and DED.match(str(er.get("strict",""))) \
                   and ded_max(str(er["strict"])) < ded_max(str(er["regular"])):
                    e.append(f"{sid}: מחמיר קטן מרגיל ({er['desc'][:30]})")
    for a in r.get("american", []):
        if not a.get("answer"): e.append(f"שאלה {a.get('n')}: אין תשובה")
    if e:
        print("rubric.json לא תקין:"); [print("  -", x) for x in e]; sys.exit(1)
    tot = sum(q["points"] for q in r.get("questions", [])) + sum(a["points"] for a in r.get("american", []))
    print(f"OK — {len(r.get('questions', []))} שאלות, {tot} נק' סה\"כ")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rubric-work/rubric.json")
