"""The Hebrew PDF report of a factory cycle, rendered by Google Chrome only (never Edge or another engine).

    python report.py <report.json> <out.pdf>      HTML from templates/report.html, then Chrome headless to PDF

report.json is written by the orchestrator at the end of each cycle (SKILL.md, "the report"); its fields are the six
sections the report must have: summary, history, tests, rigor, cost (from ledger.py summary), open. Every text is
Hebrew. The script refuses to run without Chrome, and says where it looked.
"""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "templates" / "report.html"
CHROME = [
    os.environ.get("CHROME_PATH", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
]


def chrome() -> str:
    for c in CHROME:
        if c and Path(c).is_file() and "edge" not in c.lower():
            return c
    raise SystemExit("Google Chrome לא נמצא (חיפשתי: " + ", ".join(c for c in CHROME if c) + "). "
                     "הדוח מופק רק ב-Chrome; אפשר להגדיר CHROME_PATH.")


def _e(x) -> str:
    return html.escape(str(x))


def _table(head: list[str], rows: list[list]) -> str:
    h = "".join(f"<th>{_e(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{h}</tr>{b}</table>"


def _paras(items) -> str:
    return "".join(f"<p>{_e(p)}</p>" for p in items or [])


def _list(items) -> str:
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items or []) + "</ul>"


def render(data: dict) -> str:
    s = data["summary"]
    kpis = "".join(f'<div class="kpi"><b>{_e(k["value"])}</b><span>{_e(k["label"])}</span></div>' for k in s["kpis"])
    sections = {
        "TITLE": _e(data["title"]), "DATE": _e(data["date"]), "SKILL": _e(data["skill"]),
        "KPIS": kpis, "SUMMARY": _paras(s["text"]),
        "HISTORY": _paras(data["history"]["text"]) + _table(data["history"]["head"], data["history"]["rows"]),
        "TESTS": _paras(data["tests"]["text"]) + _table(data["tests"]["head"], data["tests"]["rows"]),
        "RIGOR": _paras(data["rigor"]["text"]) + _list(data["rigor"].get("items")),
        "COST": _paras(data["cost"]["text"]) + _table(data["cost"]["head"], data["cost"]["rows"]),
        "OPEN": _list(data["open"]),
    }
    out = TEMPLATE.read_text(encoding="utf-8")
    for k, v in sections.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def to_pdf(page: str, out: Path) -> Path:
    exe = chrome()
    tmp = Path(tempfile.mkdtemp(prefix="factory-report-"))
    try:
        src = tmp / "report.html"
        src.write_text(page, encoding="utf-8")
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={tmp / 'profile'}", f"--print-to-pdf={Path(out).resolve()}",
                        src.resolve().as_uri()], check=True, capture_output=True, timeout=120)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not Path(out).is_file():
        raise SystemExit("Chrome לא כתב את ה-PDF")
    return Path(out)


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = to_pdf(render(json.loads(Path(argv[0]).read_text(encoding="utf-8"))), Path(argv[1]))
    print(f"נכתב: {out} ({out.stat().st_size // 1024} KB), ב-{chrome()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
