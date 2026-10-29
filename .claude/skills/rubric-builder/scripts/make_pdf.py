#!/usr/bin/env python3
"""One command: validate -> render -> compile. Usage: make_pdf.py rubric-work/rubric.json"""
import sys, os, subprocess
here = os.path.dirname(os.path.abspath(__file__))
src = os.path.abspath(sys.argv[1]); tex = src[:-5] + ".tex"
for step in (["validate_rubric.py", src], ["render_tex.py", src, tex], ["build_pdf.py", tex]):
    if subprocess.run([sys.executable, os.path.join(here, step[0]), *step[1:]]).returncode:
        sys.exit(1)
