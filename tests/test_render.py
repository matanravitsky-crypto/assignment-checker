"""בדיקות להפיכת הגשה לתמונות. מריצים: python -m pytest"""
from __future__ import annotations

import pymupdf

from pipeline.demo import homework_pdf
from pipeline.render import MAX_SIDE, render_pdf, render_submission
from pipeline.workspace import SubmittedFile, Submission

PNG_START = b"\x89PNG"  # כל קובץ PNG מתחיל בבייטים האלה


def test_every_page_becomes_an_image():
    pdf = homework_pdf("נועה כהן", "תרגיל בית 1")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pages = doc.page_count

    images = render_pdf(pdf)

    # תמונה אחת לכל עמוד, לפי הסדר
    assert [img.page for img in images] == list(range(1, pages + 1))
    for img in images:
        assert img.data.startswith(PNG_START)
        assert img.media_type == "image/png"
        # הצד הארוך הוא MAX_SIDE (אפשר הפרש של פיקסל בגלל עיגול)
        assert abs(max(img.width, img.height) - MAX_SIDE) <= 1


def test_submission_uses_only_the_pdf():
    pdf = homework_pdf("איתי לוי", "תרגיל בית 1")
    sub = Submission("222", "איתי לוי", [
        SubmittedFile("onlinetext.html", b"<p>hi</p>"),
        SubmittedFile("hw.pdf", pdf),
    ])

    assert len(render_submission(sub)) == len(render_pdf(pdf))
