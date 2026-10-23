"""בדיקות למדגם ההגשות לבניית מחוון. מריצים: python -m pytest"""
from __future__ import annotations

import json

import pymupdf

from grading import sample
from moodle import paths
from tests.sample_files import homework_pdf


def blank_pdf(pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def make_assignment(tmp_path, count: int = 12):
    folder = tmp_path / "Linear Algebra" / "Assignment 0"
    (folder / paths.TO_GRADE).mkdir(parents=True)
    (folder / paths.INFO).write_text(json.dumps({"id": "3438636"}), encoding="utf-8")
    for i in range(1, count + 1):
        (folder / paths.TO_GRADE / f"{i:04d}.pdf").write_bytes(homework_pdf("נועה כהן", "תרגיל בית 1", pages=2))
    return folder


def test_sample_and_fresh_do_not_overlap_and_repeat(tmp_path):
    folder = make_assignment(tmp_path)

    first = sample.build(folder, tmp_path / "a", n=5, fresh=3)
    again = sample.build(folder, tmp_path / "b", n=5, fresh=3)

    assert len(first["sample"]) == 5 and len(first["fresh"]) == 3
    assert not set(first["sample"]) & set(first["fresh"])
    # אותה מטלה, אותו מדגם: אפשר לחזור עליו
    assert (first["sample"], first["fresh"]) == (again["sample"], again["fresh"])


def test_pages_become_small_jpegs(tmp_path):
    folder = make_assignment(tmp_path, count=3)

    m = sample.build(folder, tmp_path / "out", n=2, fresh=1)

    for number in m["sample"] + m["fresh"]:
        assert m["pages"][number] == [f"{number}_p01.jpg", f"{number}_p02.jpg"]
        pix = pymupdf.Pixmap(str(tmp_path / "out" / "pages" / m["pages"][number][0]))
        assert max(pix.width, pix.height) <= sample.MAX_SIDE + 1
    assert json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8")) == m


def test_blank_pages_are_skipped_and_empty_files_flagged(tmp_path):
    folder = make_assignment(tmp_path, count=2)
    # 0001: עמוד שער ריק ואחריו העבודה. 0002: רק עמודים ריקים
    doc = pymupdf.open(stream=blank_pdf(1), filetype="pdf")
    doc.insert_pdf(pymupdf.open(stream=homework_pdf("איתי לוי", "תרגיל בית 1", pages=1), filetype="pdf"))
    (folder / paths.TO_GRADE / "0001.pdf").write_bytes(doc.tobytes())
    (folder / paths.TO_GRADE / "0002.pdf").write_bytes(blank_pdf(2))

    m = sample.build(folder, tmp_path / "out", n=2, fresh=0)

    assert m["pages"]["0001"] == ["0001_p01.jpg"]
    assert m["blank_skipped"] == {"0001": 1, "0002": 2}
    assert m["flags"]["0002"] == ["no readable page"]


def test_long_files_are_cut_and_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(sample, "MAX_PAGES", 3)
    folder = make_assignment(tmp_path, count=1)
    (folder / paths.TO_GRADE / "0001.pdf").write_bytes(homework_pdf("מאיה מזרחי", "תרגיל בית 1", pages=5))

    m = sample.build(folder, tmp_path / "out", n=1, fresh=0)

    assert len(m["pages"]["0001"]) == 3
    assert m["flags"]["0001"] == ["only the first 3 pages"]
