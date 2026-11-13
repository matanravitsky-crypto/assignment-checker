#!/usr/bin/env python3
"""rubric.json -> Rubric.md: the grading bot's rubric, from the same source as the PDF (Ori, 2026-10-29: one source).
Grading sends every top-level .md of the assignment's pedagogy folder to Claude with each submission and takes the
points per question from the first table whose first cell ends the question's label ("קבוצות 11" for
"דף קבוצות 11") and whose second cell is a number (grading.grade.pedagogy_points). So the points table comes first.
Usage: render_md.py rubric.json Rubric.md"""
import sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Hebrew on a Windows console
import json

HEADER = ("> הקובץ הזה נוצר מ-`rubric.json` על ידי הסקיל rubric-builder, יחד עם `Rubric.pdf` (אותו מחוון, לבני אדם). "
          "לשינוי: עורכים את `rubric.json` (ב-`Working notes`) ומריצים `make_pdf.py`; לא עורכים את הקובץ הזה ביד.\n"
          "> הבוט בודק לפי עמודת \"רגיל\". \"מחמיר\" הוא משטר בדיקה קשוח להחלטת המרצה, ולא לשימוש הבוט.\n"
          "> פרטיות: הגשות מצוינות רק לפי מספר בן 4 ספרות. אין שמות, ת\"ז או מיילים.")


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def section_heading(s):
    count = int(s.get("count", 1))
    if count > 1:
        return f"### סעיפים {s['letter']} ({s['points']} נק' כל אחד): {s.get('title', '')}".rstrip(": ")
    return f"### סעיף {s['letter']} ({s['points']} נק'): {s.get('title', '')}".rstrip(": ")


def section(s):
    o = [section_heading(s), "", f"**תשובה:** {s['answer']}", ""]
    if s.get("solution"):
        o += ["$$", s["solution"], "$$", ""]
    if s.get("note"):
        o += [f"_{s['note']}_", ""]
    o += ["**חלוקת הניקוד**", "", table(["שלב", "נק'"], [[x["desc"], x["points"]] for x in s["steps"]]), ""]
    for m in s.get("alt_methods", []):
        o += [f"**דרך חלופית: {m['name']}** (מי שפתר כך מנוקד לפי החלוקה הזאת)", "",
              table(["שלב", "נק'"], [[x["desc"], x["points"]] for x in m["steps"]]), ""]
    if s.get("errors"):
        # "טעות" הוא הנוסח שהבוט כותב כתגית (מילה במילה, כדי שאותה טעות תיספר יחד); הדוגמה בעמודה משלה, לא בתוך התגית
        if any(er.get("example") for er in s["errors"]):
            o += ["**טעויות וניכויים** (הבוט מוריד לפי \"רגיל\"; התגית היא עמודת \"טעות\" בלבד)", "",
                  table(["טעות", "דוגמה", "סוג", "רגיל", "מחמיר"],
                        [[er["desc"], er.get("example", ""), er["type"], er["regular"], er["strict"]] for er in s["errors"]]), ""]
        else:
            o += ["**טעויות וניכויים** (הבוט מוריד לפי \"רגיל\")", "",
                  table(["טעות", "סוג", "רגיל", "מחמיר"],
                        [[er["desc"], er["type"], er["regular"], er["strict"]] for er in s["errors"]]), ""]
    return "\n".join(o)


def points_table(r):
    rows = []
    for q in r.get("questions", []):
        parts = " · ".join(f"{s['letter']} {s['points']}" + (" כל אחד" if int(s.get("count", 1)) > 1 else "")
                           for s in q.get("sections", []))
        rows.append([q["n"], q["points"], parts])
    for a in r.get("american", []):
        rows.append([a["n"], a["points"], "אמריקאית: הכול או כלום"])
    total = sum(q["points"] for q in r.get("questions", [])) + sum(a["points"] for a in r.get("american", []))
    rows.append(["**סה\"כ**", f"**{total}**", ""])
    return table(["שאלה", "נק'", "סעיפים"], rows)


def render(r):
    title = f"# {r.get('course', '')}: {r.get('term', '')} – מחוון".replace(":  –", " –")
    o = [title, "", HEADER, "", "## חלוקת הנקודות", "", points_table(r), ""]
    rules = r.get("general_rules") or default_rules()  # the same fallback as the PDF: the bot must see the same rules
    if rules:
        o += ["## כללי בדיקה", ""] + [f"- **{g['label']}:** {g['text']}" for g in rules] + [""]
    u = universal_rules()
    if u["rules"]:
        o += [f"## {u['heading']}", "", u["intro"], ""] + [f"- **{g['label']}:** {g['text']}" for g in u["rules"]] + [""]
    for q in r.get("questions", []):
        label = f"שאלה {q['n']}" if str(q["n"]).isdigit() else str(q["n"])
        o += [f"## {label} ({q['points']} נק')", ""]
        o += [section(s) for s in q.get("sections", [])]
    if r.get("american"):
        o += ["## שאלות אמריקאיות", "", "הניקוד הוא הכול או כלום, לפי ההקפה בטבלה בלבד. יותר מתשובה אחת או אף תשובה: 0.", "",
              table(["שאלה", "תשובה", "נק'", "נימוק"],
                    [[a["n"], a["answer"], a["points"], a.get("reason", "")] for a in r["american"]]), ""]
    return "\n".join(o).rstrip() + "\n"


def universal_rules():
    """assets/universal-rules.json: the rules every rubric gets on top of its own (the same file grading adds to a rubric
    that was not rendered here, grading/grade.py universal_rules_text)."""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "universal-rules.json")
    try:
        return json.load(open(path, encoding="utf-8-sig"))
    except FileNotFoundError:
        return {"heading": "", "intro": "", "rules": []}


def default_rules():
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "default-rules.json")
    return json.load(open(path, encoding="utf-8-sig"))


def main(src, dst):
    r = json.load(open(src, encoding="utf-8-sig"))
    open(dst, "w", encoding="utf-8").write(render(r))
    print("wrote", dst)


if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit("שימוש: render_md.py <rubric.json> <Rubric.md>")
    main(sys.argv[1], sys.argv[2])
