"""המכוון הרשמי של המרצה: מועלה מהאתר, נשלח ל-Claude עם כל עבודה, וקובע את הניקוד לפני כל מחוון אחר."""
from __future__ import annotations

import base64
import io
import json
import zipfile

import pytest

from dashboard import actions
from grading import grade as grading
from grading.claude_cli import write_request
from moodle import paths
from tests.dashboard.helpers import call, hw
from tests.grading.test_grade import (COURSE, HW, LABELS, FakeClaude, answer, asg, no_real_claude, root,  # noqa: F401
                                      save_details, server)
from tests.sample_files import homework_pdf

BODY = {"course": COURSE, "assignment": HW}
HDR = {"X-Assignment-Checker": "1"}


def docx(*paragraphs: str) -> bytes:
    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{p}</w:t></w:r></w:p>' for p in paragraphs)
    xml = (f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
           f'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body>{body}'
           f'<w:p><m:oMath><m:r><m:t>A^-1</m:t></m:r></m:oMath></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_without_a_key_nothing_changes(root):
    ctx = grading.load_context(asg(root).dir)
    assert ctx.official_key is None and "המכוון הרשמי" not in grading.context_text(ctx)
    assert hw(actions.state(root))["officialKey"] is None


def test_a_pdf_key_is_sent_first_and_wins_over_the_rubric(root):
    a = asg(root)
    actions.save_official_key(root, COURSE, HW, file_name="מכוון הגשה 0.pdf", data=homework_pdf("מכוון", HW, pages=1),
                              text="על חוסר נימוק מורידים 3", points={LABELS[0]: 30, LABELS[1]: 10})
    ctx = grading.load_context(a.dir)
    assert [q.points for q in ctx.questions] == [30, 10, 20, 20, 20] and not ctx.no_rubric
    content = grading.build_request(ctx, [])["messages"][0]["content"]
    assert content[0]["type"] == "document" and "המכוון הרשמי" in content[0]["title"]
    text = next(b["text"] for b in content if b["type"] == "text" and b["text"].startswith("מטלה:"))
    assert "המכוון הרשמי של המרצה:" in text and grading.KEY_RULE in text
    assert "על חוסר נימוק מורידים 3" in text and "1. דף קבוצות 11 (30 נקודות)" in text
    assert "המכוון הרשמי" in grading.SYSTEM
    # Claude Code מקבל את המכוון כקובץ בתיקייה הזמנית, עם השם שלו
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        prompt = write_request(grading.build_request(ctx, []), Path(tmp))
        assert "המכוון הרשמי של המרצה" in prompt and len(list(Path(tmp).glob("*.pdf"))) == 1


def test_the_grading_run_sends_the_key_with_every_submission(root):
    a = asg(root)
    actions.save_official_key(root, COURSE, HW, file_name="key.png", data=b"\x89PNG fake", text="")
    fake = FakeClaude()
    grading.grade_assignment(a.dir, ["0001", "0002"], ask=fake)
    assert len(fake.requests) == 2
    for req in fake.requests:
        blocks = req["messages"][0]["content"]
        assert blocks[0]["type"] == "text" and "המכוון הרשמי" in blocks[0]["text"] and blocks[1]["type"] == "image"


def test_word_key_is_kept_and_its_text_is_sent(root):
    a = asg(root)
    actions.save_official_key(root, COURSE, HW, file_name="מכוון.docx", data=docx("שאלה 11: 20 נקודות", "חסר נימוק: 5-"))
    assert (a.dir / paths.OFFICIAL_KEY / "מכוון.docx").is_file()
    key = grading.official_key(a.dir)
    assert key.files == [] and "שאלה 11: 20 נקודות" in key.text and "A^-1" in key.text
    assert "חסר נימוק: 5-" in grading.context_text(grading.load_context(a.dir))
    with pytest.raises(actions.UserError):
        actions.save_official_key(root, COURSE, HW, file_name="x.docx", data=b"not a zip")
    with pytest.raises(actions.UserError):
        actions.save_official_key(root, COURSE, HW, file_name="x.exe", data=b"MZ")


def test_without_points_for_every_question_there_are_no_grades(root):
    a = asg(root)
    save_details(a, {**a.details(), "rubric": None})
    actions.save_official_key(root, COURSE, HW, text="המכוון", points={LABELS[0]: 20})
    ctx = grading.load_context(a.dir)
    assert "במכוון אין ניקוד" in ctx.no_rubric and LABELS[4] in ctx.no_rubric
    with pytest.raises(grading.NoRubric):
        grading.grade_assignment(a.dir, ["0001"], ask=FakeClaude())
    actions.save_official_key(root, COURSE, HW, points={l: 20 for l in LABELS})
    assert not grading.load_context(a.dir).no_rubric
    with pytest.raises(actions.UserError):
        actions.save_official_key(root, COURSE, HW, points={"שאלה שלא קיימת": 5})
    with pytest.raises(actions.UserError):
        actions.save_official_key(root, COURSE, HW, points={LABELS[0]: -3})


def test_replacing_or_removing_a_key_keeps_the_old_one(root):
    a = asg(root)
    actions.save_official_key(root, COURSE, HW, file_name="v1.pdf", data=homework_pdf("1", HW, pages=1))
    actions.save_official_key(root, COURSE, HW, file_name="v2.pdf", data=homework_pdf("2", HW, pages=1))
    assert [f.name for f in grading.official_key(a.dir).files] == ["v2.pdf"]
    out = actions.save_official_key(root, COURSE, HW, remove=True)
    assert out["officialKey"] is None and grading.official_key(a.dir) is None
    kept = sorted(p.name for p in (a.dir / paths.OFFICIAL_KEY_OLD).rglob("*.pdf"))
    assert kept == ["v1.pdf", "v2.pdf"]
    assert "official_key_points" not in a.details()


def test_server_saves_the_key_and_the_site_sees_it(root, server):
    a = asg(root)
    data = base64.b64encode(homework_pdf("מכוון", HW, pages=1)).decode()
    st, out = call(server, "POST", "/api/official-key",
                   {**BODY, "fileName": "key.pdf", "data": data, "text": "הערה", "points": {LABELS[0]: 25}}, HDR)
    assert st == 200, out
    k = out["officialKey"]
    assert k["points"] == {LABELS[0]: 25} and k["text"] == "הערה" and k["by"] == "בודק א" and k["files"][0]["sent"]
    st, raw = call(server, "GET", "/api/file?path=" + __import__("urllib.parse").parse.quote(k["files"][0]["path"]))
    assert st == 200 and raw.startswith(b"%PDF")
    A = hw(actions.state(root))
    assert A["officialKey"]["files"][0]["name"] == "key.pdf" and A["rubric"][0]["points"] == 25
    st, out = call(server, "POST", "/api/official-key", {**BODY, "fileName": "k.pdf", "data": "%%%"}, HDR)
    assert st == 400
    st, out = call(server, "POST", "/api/official-key", {**BODY, "text": "x"})  # בלי הכותרת של האתר
    assert st == 403
    assert json.loads((a.dir / paths.INFO).read_text(encoding="utf-8"))["official_key_points"] == {LABELS[0]: 25}
