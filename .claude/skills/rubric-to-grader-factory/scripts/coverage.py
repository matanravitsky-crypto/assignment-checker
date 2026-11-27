"""Zero-skip proof for a rubric PDF: every page of the file is accounted for in the package made from it.

    python coverage.py pages <rubric.pdf>                       one line per page: number, sha256 of its content, chars
    python coverage.py check <rubric.pdf> <coverage.json>       refuses (exit 1) unless every page is mapped

coverage.json is what the transcribing agent writes next to the package (brief-rubric-from-pdf.md):
    {"pdf_sha256": "...", "pages": [{"page": 1, "sha256": "...", "sections": ["כללי", "8א"], "error_rows": 0}, ...]}
`check` recomputes the PDF's page checksums and refuses a map that misses a page, maps a page that is not in the file,
has a checksum that differs (another version of the PDF), or gives a page no section without saying why
("sections": [] needs "empty": "<why>", e.g. a cover page).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def page_sums(pdf: Path) -> tuple[str, list[dict]]:
    import pymupdf
    data = Path(pdf).read_bytes()
    doc = pymupdf.open(stream=data, filetype="pdf")
    pages = []
    for i, page in enumerate(doc, start=1):
        content = page.read_contents() or b""
        images = b"".join(doc.extract_image(x[0]).get("image", b"")[:4096] for x in page.get_images(full=True))
        pages.append({"page": i, "sha256": hashlib.sha256(content + images).hexdigest()[:16],
                      "chars": len(page.get_text())})
    return hashlib.sha256(data).hexdigest()[:16], pages


def check(pdf: Path, coverage: Path) -> list[str]:
    whole, pages = page_sums(pdf)
    got = json.loads(Path(coverage).read_text(encoding="utf-8"))
    problems = []
    if got.get("pdf_sha256") not in (None, whole):
        problems.append(f"the map is of another file (pdf_sha256 {got.get('pdf_sha256')} != {whole})")
    mapped = {int(p["page"]): p for p in got.get("pages", [])}
    for p in pages:
        m = mapped.get(p["page"])
        if m is None:
            problems.append(f"page {p['page']} is not in the map")
            continue
        if m.get("sha256") not in (None, p["sha256"]):
            problems.append(f"page {p['page']}: checksum {m.get('sha256')} != {p['sha256']}")
        if not m.get("sections") and not m.get("empty"):
            problems.append(f"page {p['page']}: no section and no reason it is empty")
    extra = sorted(set(mapped) - {p["page"] for p in pages})
    if extra:
        problems.append(f"pages {extra} are mapped but the file has {len(pages)} pages")
    return problems


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if len(argv) == 2 and argv[0] == "pages":
        whole, pages = page_sums(Path(argv[1]))
        print(json.dumps({"pdf_sha256": whole, "pages": pages}, ensure_ascii=False, indent=1))
        return 0
    if len(argv) == 3 and argv[0] == "check":
        problems = check(Path(argv[1]), Path(argv[2]))
        if problems:
            print("כיסוי חסר:\n" + "\n".join(f"- {p}" for p in problems))
            return 1
        print("כל העמודים מכוסים.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
