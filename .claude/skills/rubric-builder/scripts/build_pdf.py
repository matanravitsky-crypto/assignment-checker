#!/usr/bin/env python3
"""rubric.tex -> rubric.pdf. Uses latexmk -xelatex if present, else xelatex twice (for page numbers).
Fails loudly: the old PDF is removed first, a PDF that is open in a viewer is reported as such, a compile error
is printed with the line of rubric.tex it points at, and a build whose log says "Missing character" (a symbol
the font doesn't have, which XeLaTeX silently drops) is a failure too."""
import sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Hebrew on a Windows console
import re, subprocess, sys, os, shutil

MISSING = re.compile(r"Missing character: There is no (.+?) in font")


def explain(log_lines, tex_lines):
    """The '!' lines of a LaTeX log, each with the two lines after it and the rubric.tex line it points at."""
    out = []
    for i, l in enumerate(log_lines):
        if not l.startswith("!"): continue
        out.append(l)
        for nxt in log_lines[i + 1:i + 3]:
            if nxt.strip(): out.append("   " + nxt)
        for nxt in log_lines[i:i + 12]:
            m = re.match(r"l\.(\d+)", nxt)
            if m:
                n = int(m.group(1))
                if 0 < n <= len(tex_lines): out.append(f"   rubric.tex שורה {n}: {tex_lines[n - 1].strip()[:160]}")
                break
        if len(out) > 24: break
    return out


def missing_chars(log_text):
    return sorted(set(MISSING.findall(log_text)))


def main(tex):
    tex = os.path.abspath(tex); d, base = os.path.split(tex); name = os.path.splitext(base)[0]
    pdf = os.path.join(d, name + ".pdf"); logp = os.path.join(d, name + ".log")
    if not os.path.exists(tex): sys.exit(f"הקובץ לא נמצא: {tex}")
    if not shutil.which("xelatex"):
        sys.exit("xelatex not found: run setup/check.ps1 (Windows) or setup/check.sh (macOS) from this skill's folder, "
                 "install what it reports, then open a new terminal.")
    if os.path.exists(pdf):
        try:
            with open(pdf, "ab"): pass
            os.remove(pdf)
        except PermissionError:
            sys.exit(f"{pdf} פתוח בתוכנה אחרת (קורא PDF?). לסגור אותו ולהריץ שוב.")
    if shutil.which("latexmk") and shutil.which("perl"):
        cmds = [["latexmk", "-xelatex", "-interaction=nonstopmode", "-halt-on-error", base]]
    else:
        cmds = [["xelatex", "-interaction=nonstopmode", "-halt-on-error", base]] * 2
    tex_lines = open(tex, encoding="utf-8", errors="replace").read().splitlines()
    for c in cmds:
        r = subprocess.run(c, cwd=d, capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            log = open(logp, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(logp) else []
            print("compile failed:"); [print("  ", l) for l in explain(log, tex_lines) or log[-15:] or r.stdout.splitlines()[-15:]]
            sys.exit(1)
    log_text = open(logp, encoding="utf-8", errors="replace").read() if os.path.exists(logp) else ""
    miss = missing_chars(log_text)
    if miss:
        print("compile failed: הגופן לא מכיר את התווים האלה והם נעלמו מה-PDF:", " ".join(miss))
        print("   לכתוב אותם כפקודות LaTeX (למשל $\\cap$, $\\mathbb{R}$, $\\times$) או להוסיף ל-SYMBOLS ב-render_tex.py")
        try: os.remove(pdf)
        except OSError: pass
        sys.exit(1)
    for ext in (".aux", ".log", ".out", ".fls", ".fdb_latexmk", ".xdv"):
        try: os.remove(os.path.join(d, name + ext))
        except OSError: pass
    print("built", pdf)


if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit("שימוש: build_pdf.py <rubric.tex>")
    main(sys.argv[1])
