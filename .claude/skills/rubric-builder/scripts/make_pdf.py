#!/usr/bin/env python3
"""One command: validate -> Rubric.md (the bot's rubric) -> TeX -> PDF (the people's rubric), all from rubric.json.
Usage: make_pdf.py <work>/rubric.json   writes <work>/Rubric.md, <work>/rubric.tex, <work>/rubric.pdf
Rubric.md is written only after the PDF built, so the two never disagree after a failed build."""
import sys, os, subprocess, shutil
here = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) < 2: sys.exit("שימוש: make_pdf.py <תיקייה>/rubric.json")
src = os.path.abspath(sys.argv[1])
if not os.path.isfile(src): sys.exit(f"הקובץ לא נמצא: {src}")
stem = os.path.splitext(src)[0]; tex = stem + ".tex"; md = os.path.join(os.path.dirname(src), "Rubric.md"); md_tmp = md + ".tmp"
for step in (["validate_rubric.py", src], ["render_md.py", src, md_tmp], ["render_tex.py", src, tex], ["build_pdf.py", tex]):
    if subprocess.run([sys.executable, os.path.join(here, step[0]), *step[1:]]).returncode:
        try: os.remove(md_tmp)
        except OSError: pass
        sys.exit(1)
shutil.move(md_tmp, md)
print("wrote", md)
