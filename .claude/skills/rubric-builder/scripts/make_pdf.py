#!/usr/bin/env python3
"""One command: validate -> Rubric.md (the bot's rubric) -> TeX -> PDF (the people's rubric), all from rubric.json.
Usage: make_pdf.py <work>/rubric.json   writes <work>/Rubric.md, <work>/rubric.tex, <work>/rubric.pdf"""
import sys, os, subprocess
here = os.path.dirname(os.path.abspath(__file__))
src = os.path.abspath(sys.argv[1]); tex = src[:-5] + ".tex"; md = os.path.join(os.path.dirname(src), "Rubric.md")
for step in (["validate_rubric.py", src], ["render_md.py", src, md], ["render_tex.py", src, tex], ["build_pdf.py", tex]):
    if subprocess.run([sys.executable, os.path.join(here, step[0]), *step[1:]]).returncode:
        sys.exit(1)
