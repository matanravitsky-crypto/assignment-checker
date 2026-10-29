#!/usr/bin/env python3
"""rubric.tex -> rubric.pdf. Uses latexmk -xelatex if present, else xelatex twice (for page numbers)."""
import sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Hebrew on a Windows console
import subprocess, sys, os, shutil

tex = os.path.abspath(sys.argv[1]); d, base = os.path.split(tex); name = base[:-4]
if not shutil.which("xelatex"):
    sys.exit("xelatex not found: run setup/check.ps1 (Windows) or setup/check.sh (macOS) from this skill's folder, "
             "install what it reports, then open a new terminal.")
if shutil.which("latexmk") and shutil.which("perl"):
    cmds = [["latexmk", "-xelatex", "-interaction=nonstopmode", "-halt-on-error", base]]
else:
    cmds = [["xelatex", "-interaction=nonstopmode", "-halt-on-error", base]] * 2
for c in cmds:
    r = subprocess.run(c, cwd=d, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        log = open(os.path.join(d, name + ".log"), encoding="utf-8", errors="replace").read().splitlines()
        bad = [l for i, l in enumerate(log) if l.startswith("!")][:5]
        print("compile failed:"); [print("  ", l) for l in bad or log[-15:]]; sys.exit(1)
for ext in (".aux", ".log", ".out", ".fls", ".fdb_latexmk", ".xdv"):
    try: os.remove(os.path.join(d, name + ext))
    except OSError: pass
print("built", os.path.join(d, name + ".pdf"))
