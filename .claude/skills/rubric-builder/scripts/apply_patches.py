#!/usr/bin/env python3
"""Apply a committee's patch list to rubric.json (Step 7, the calibration round; also usable for remark rounds).
Usage: apply_patches.py <rubric.json> <patches.json or the committee's .md with a ```json block> [--dry-run]
Patch shapes (a JSON list):
  {"q": "<question n>", "letter": "<section letter>", "action": "add", "desc": "...", "type": "...", "regular": "2", "strict": "3"}
  {"q": ..., "letter": ..., "action": "reword", "old_desc": "<exact current desc>", "desc": "<new desc>"}
  {"q": ..., "letter": ..., "action": "note", "note": "<sentence appended to the section's note>"}
Points never change here. The file is written only if every patch applied and the validator passes; the previous
rubric.json is kept as rubric.json.bak. Prints one line per patch, in Hebrew."""
import sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
import json, os, re, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def load_patches(path):
    text = open(path, encoding="utf-8-sig").read()
    if path.lower().endswith(".json"):
        return json.loads(text)
    m = re.search(r"```json\s*(.*?)```", text, re.S)
    if not m: sys.exit("לא נמצא בלוק ```json בקובץ הוועדה")
    return json.loads(m.group(1))


def find_section(r, q, letter):
    for qq in r.get("questions", []):
        if str(qq.get("n")).strip() == str(q).strip():
            for s in qq.get("sections", []):
                if str(s.get("letter")).strip() == str(letter).strip():
                    return s
            sys.exit(f"שאלה {q}: אין סעיף '{letter}' (יש: {[s.get('letter') for s in qq.get('sections', [])]})")
    sys.exit(f"אין שאלה '{q}' (יש: {[qq.get('n') for qq in r.get('questions', [])]})")


def apply(r, patches):
    lines = []
    for p in patches:
        s = find_section(r, p["q"], p["letter"])
        where = f"{p['q']} {p['letter']}"
        a = p.get("action")
        if a == "add":
            row = {"desc": p["desc"].strip(), "type": p["type"], "regular": str(p["regular"]), "strict": str(p["strict"])}
            if any(e["desc"].strip() == row["desc"] for e in s.setdefault("errors", [])):
                lines.append(f"= {where}: השורה כבר קיימת: {row['desc'][:50]}"); continue
            s["errors"].append(row); lines.append(f"+ {where}: {row['desc'][:60]} ({row['type']}, {row['regular']}/{row['strict']})")
        elif a == "reword":
            hit = [e for e in s.get("errors", []) if e["desc"].strip() == p["old_desc"].strip()]
            if not hit:
                near = [e["desc"][:50] for e in s.get("errors", []) if p["old_desc"].strip()[:15] in e["desc"]]
                sys.exit(f"{where}: לא נמצאה שורה עם הניסוח המדויק '{p['old_desc'][:50]}' (דומות: {near})")
            hit[0]["desc"] = p["desc"].strip(); lines.append(f"~ {where}: {p['old_desc'][:35]} → {p['desc'][:45]}")
        elif a == "note":
            note = (s.get("note") or "").strip()
            s["note"] = (note + " " if note else "") + p["note"].strip(); lines.append(f"* {where}: הערה: {p['note'][:60]}")
        else:
            sys.exit(f"{where}: action לא מוכר '{a}'")
    return lines


def main(argv):
    if len(argv) < 2: sys.exit("שימוש: apply_patches.py <rubric.json> <patches.json|committee.md> [--dry-run]")
    src, pfile = argv[0], argv[1]; dry = "--dry-run" in argv
    r = json.load(open(src, encoding="utf-8-sig"))
    patches = load_patches(pfile)
    lines = apply(r, patches)
    print("\n".join(lines))
    tmp = src + ".tmp"
    json.dump(r, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if subprocess.run([sys.executable, os.path.join(HERE, "validate_rubric.py"), tmp]).returncode:
        os.remove(tmp); sys.exit("לא נכתב: המחוון אחרי התיקונים לא עובר את הבדיקה")
    if dry:
        os.remove(tmp); print("(dry run: לא נכתב)"); return
    shutil.copy2(src, src + ".bak"); os.replace(tmp, src)
    print(f"נכתב {src} ({len(patches)} תיקונים); הגרסה הקודמת ב-{src}.bak")


if __name__ == "__main__":
    main(sys.argv[1:])
