#!/usr/bin/env python3
"""Turn every input (PDF / image / docx) into cheap, cached text or small page images.
Usage: prep_inputs.py <file-or-folder>... [--images] --out <work>/inputs
Per file: typed PDF -> name.txt. Scan/photo -> name/page-NN.jpg at 1100 px wide, greyscale, JPEG q70
(~1.2K tokens per page) + name.txt via tesseract if it is installed. Runs once; reruns skip done files.
--images: always pages as images, never text. Use it for Hebrew PDFs (XeLaTeX, Word): their extracted
text comes out reversed and interleaved, and an agent reads the page image correctly.
Student submissions don't go through here: `python -m grading.sample` makes their page images."""
import sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Hebrew on a Windows console
import sys, os, subprocess, shutil, glob

WIDTH = 1100
def ensure(mod, pkg):
    try: return __import__(mod)
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", pkg]) or subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", pkg]); return __import__(mod)

def save_page(pix_bytes_png, dst):
    from PIL import Image; import io
    im = Image.open(io.BytesIO(pix_bytes_png)).convert("L")
    if im.width > WIDTH: im = im.resize((WIDTH, int(im.height * WIDTH / im.width)))
    im.save(dst, "JPEG", quality=70, optimize=True)

def ocr(img):
    if not shutil.which("tesseract"): return ""
    r = subprocess.run(["tesseract", img, "-", "-l", "heb+eng"], capture_output=True, text=True, errors="replace")
    return r.stdout

def handle(path, out, images_only=False):
    fitz = ensure("pymupdf", "pymupdf"); ensure("PIL", "pillow")
    name = os.path.splitext(os.path.basename(path))[0]
    txt_path = os.path.join(out, name + ".txt"); img_dir = os.path.join(out, name)
    if os.path.exists(txt_path) or os.path.isdir(img_dir): return "skip"
    ext = path.lower().rsplit(".", 1)[-1]
    if ext == "docx":
        m = ensure("mammoth", "mammoth")
        open(txt_path, "w", encoding="utf-8").write(m.convert_to_markdown(open(path, "rb")).value); return "text"
    try:
        doc = fitz.open(path)  # pdf or image
    except Exception as ex:  # 0-byte file, not a PDF, damaged
        print(f"  לא נפתח: {os.path.basename(path)} ({type(ex).__name__})"); return "error"
    if doc.needs_pass:
        print(f"  מוגן בסיסמה, דולג: {os.path.basename(path)}"); return "error"
    if len(doc) == 0:
        print(f"  אין עמודים, דולג: {os.path.basename(path)}"); return "error"
    text = "" if images_only else "\n".join(p.get_text() for p in doc)
    if len(text.strip()) > 80 * len(doc):  # typed
        open(txt_path, "w", encoding="utf-8").write(text); return "text"
    os.makedirs(img_dir, exist_ok=True); ocr_text = []
    for i, p in enumerate(doc, 1):
        dst = os.path.join(img_dir, f"page-{i:02d}.jpg")
        save_page(p.get_pixmap(dpi=110).tobytes("png"), dst)
        if not images_only: ocr_text.append(ocr(dst))
    joined = "\n".join(ocr_text)
    if len(joined.strip()) > 80 * len(doc):
        open(txt_path, "w", encoding="utf-8").write(joined); return "ocr"
    return "images"

def main():
    args = sys.argv[1:]; out = "rubric-work/inputs"; images_only = False
    if "--images" in args: args.remove("--images"); images_only = True
    if "--out" in args: i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]
    os.makedirs(out, exist_ok=True); files = []
    for a in args:
        if os.path.isdir(a): files += sorted(glob.glob(os.path.join(a, "*")))
        elif any(ch in a for ch in "*?["): files += sorted(glob.glob(a)) or [a]  # a quoted glob: the shell didn't expand it
        else: files.append(a)
    missing = [f for f in files if not os.path.exists(f)]
    if missing: sys.exit("לא נמצא: " + ", ".join(missing))
    for f in files:
        if f.lower().rsplit(".", 1)[-1] in ("pdf", "png", "jpg", "jpeg", "docx"):
            print(f"{handle(f, out, images_only):7s} {os.path.basename(f)}")
    print(f"\nin {out}: *.txt = read as text; <name>/page-*.jpg = read as images ({WIDTH} px, cheap)")

if __name__ == "__main__": main()
