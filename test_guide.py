import json
import os
import tempfile
from pathlib import Path

from moodle import paths
from moodle.guide import write_guides


def test_guides_at_every_level_name_the_course_and_assignment():
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        os.environ["ASSIGNMENT_DATA"] = tmp
        try:
            assignment = data / "אלגברה לינארית" / "הגשה 0 - קבוצות ומרוכבים"
            (assignment / paths.TO_GRADE).mkdir(parents=True)
            (assignment / paths.TO_GRADE / "0001.pdf").write_bytes(b"")
            (assignment / paths.INFO).write_text(json.dumps({
                "id": "3438636", "course": "אלגברה לינארית", "name": "הגשה 0 - קבוצות ומרוכבים",
                "due": "2026-10-26T23:59:00+02:00",
                "questions": [{"sheet": "דף קבוצות", "numbers": [11, 12]}],
            }, ensure_ascii=False), encoding="utf-8")

            written = write_guides(data)
        finally:
            del os.environ["ASSIGNMENT_DATA"]

        assert written == [assignment / paths.README, assignment.parent / paths.README, data / paths.README]
        top = (data / paths.README).read_text(encoding="utf-8-sig")
        assert "אלגברה לינארית:\n  - הגשה 0 - קבוצות ומרוכבים" in top
        course = (assignment.parent / paths.README).read_text(encoding="utf-8-sig")
        assert "הגשה 0 - קבוצות ומרוכבים: 1 הגשות" in course
        inner = (assignment / paths.README).read_text(encoding="utf-8-sig")
        assert "מועד הגשה: 2026-10-26 23:59" in inner
        assert "שאלות: דף קבוצות, 11, 12" in inner
        assert paths.TO_GRADE in inner


if __name__ == "__main__":
    test_guides_at_every_level_name_the_course_and_assignment()
    print("All tests passed.")
