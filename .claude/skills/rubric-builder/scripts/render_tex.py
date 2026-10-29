#!/usr/bin/env python3
"""rubric.json -> rubric.tex from assets/template.tex. Strings in the JSON are LaTeX and are inserted as-is,
except for a few symbols David CLM lacks (⇒ · • ✓ ≠ …) which are turned into math outside $...$,
and \\notin, which becomes \\not\\in (the kernel's \\notin uses \\ooalign, and that paints a colored
table row black)."""
import sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Hebrew on a Windows console
import json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = ["David CLM", "Noto Serif Hebrew", "Noto Sans Hebrew", "DejaVu Sans"]
SYMBOLS = {"⇒": r"$\Rightarrow$", "·": r"$\cdot$", "•": r"$\bullet$", "✓": r"$\checkmark$", "≠": r"$\neq$",
           "…": r"\ldots{}", "∅": r"$\varnothing$", "∈": r"$\in$", "∉": r"$\not\in$", "≤": r"$\le$", "≥": r"$\ge$"}


def fix(s):
    """Symbols outside math become math; \\notin becomes \\not\\in everywhere."""
    parts = str(s).split("$")
    for i in range(0, len(parts), 2):  # even parts are outside $...$
        for k, v in SYMBOLS.items():
            parts[i] = parts[i].replace(k, v)
    return "$".join(parts).replace(r"\notin", r"\not\in")


def pick_font():
    try: have = subprocess.run(["fc-list", ":", "family"], capture_output=True).stdout.decode("utf-8", "replace").lower()
    except (FileNotFoundError, OSError): return FONTS[0]
    return next((f for f in FONTS if f.lower() in have), FONTS[0])


def people(r):
    parts = [t % v for t, v in (("מרצה: %s", r.get("lecturer", "")), ("מתרגל: %s", r.get("ta", ""))) if v]
    return r"{\small %s}\\[2pt]" % r" \qquad ".join(parts) if parts else ""


def table(head, rows, spec):
    out = [r"\begin{tabularx}{\textwidth}{%s}" % spec,
           r"\rowcolor{paleblue} " + " & ".join(r"\textbf{%s}" % h for h in head) + r" \\"]
    for i, row in enumerate(rows):
        out.append((r"\rowcolor{rowgrey} " if i % 2 else "") + " & ".join(fix(c) for c in row) + r" \\")
    out.append(r"\end{tabularx}")
    return "\n".join(out)


STEPS_SPEC = r"X >{\centering\arraybackslash}p{1.6cm}"
ERR_SPEC = r"X >{\centering\arraybackslash}p{1.9cm} >{\centering\arraybackslash}p{1.2cm} >{\centering\arraybackslash}p{1.2cm}"


def section(s):
    count = int(s.get("count", 1))
    if count > 1:
        head = "סעיפים %s (%d נק' כל אחד)" % (s["letter"], s["points"])
    else:
        head = "סעיף %s (%d נק')" % (s["letter"], s["points"])
    o = [r"\sechead{%s}{%s}" % (head, fix(s.get("title", "")))]
    o.append(r"\answerbox{%s}" % fix(s["answer"]))
    if s.get("solution"): o.append("\\[\n%s\n\\]" % s["solution"])
    if s.get("note"): o.append(r"{\small\textit{%s}}\par" % fix(s["note"]))
    o.append(r"\tblhead{חלוקת הניקוד}")
    o.append(table(["שלב", "נקודות"], [[x["desc"], str(x["points"])] for x in s["steps"]], STEPS_SPEC))
    for m in s.get("alt_methods", []):
        o.append(r"\tblhead{דרך חלופית: %s}" % fix(m["name"]))
        o.append(table(["שלב", "נקודות"], [[x["desc"], str(x["points"])] for x in m["steps"]], STEPS_SPEC))
    if s.get("errors"):
        o.append(r"\tblhead{טעויות וניכויים}")
        rows = [[er["desc"], er["type"],
                 r"\textbf{%s}" % er["regular"], r"\textcolor{ded}{\textbf{%s}}" % er["strict"]] for er in s["errors"]]
        o.append(table(["טעות", "סוג", "רגיל", "מחמיר"], rows, ERR_SPEC))
    return "\n".join(o)


def main(src, dst):
    r = json.load(open(src, encoding="utf-8"))
    rules = r.get("general_rules") or json.load(open(os.path.join(HERE, "..", "assets", "default-rules.json"), encoding="utf-8"))
    body = []
    for q in r.get("questions", []):
        n = q["n"]
        label = "שאלה %s" % n if str(n).isdigit() else str(n)  # "קבוצות 11" stays as it is
        body.append(r"\qbar{%s}{%d}" % (fix(label), q["points"]))
        body += [section(s) for s in q.get("sections", [])]
    if r.get("american"):
        body.append(r"\partbar{חלק ב' -- שאלות אמריקאיות}{%d}" % sum(a["points"] for a in r["american"]))
        body.append(r"הניקוד הוא הכול או כלום, לפי ההקפה בטבלה שבעמוד הראשון בלבד. יותר מתשובה אחת או אף תשובה -- 0.\par\vspace{4pt}")
        body.append(table(["שאלה", "תשובה", "נק'", "נימוק"],
                          [[str(a["n"]), a["answer"], str(a["points"]), a.get("reason", "")] for a in r["american"]],
                          r">{\centering\arraybackslash}p{1.2cm} >{\centering\arraybackslash}p{1.4cm} >{\centering\arraybackslash}p{1cm} X"))
    tpl = open(os.path.join(HERE, "..", "assets", "template.tex"), encoding="utf-8").read()
    tex = tpl
    for k, v in {"FONT": pick_font(), "COURSE": fix(r.get("course", "")), "CODE": fix(r.get("code", "")), "TERM": fix(r.get("term", "")),
                 "DATE": fix(r.get("date", "")), "PEOPLE": people(r),
                 "RULES": "\n".join(r"\item \textbf{%s:} %s" % (fix(x["label"]), fix(x["text"])) for x in rules),
                 "BODY": "\n\n".join(body)}.items():
        tex = tex.replace("<<%s>>" % k, v)
    open(dst, "w", encoding="utf-8").write(tex)
    print("wrote", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
