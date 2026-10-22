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
            assignment = data / "Linear Algebra" / "Assignment 0 - Sets and Complex Numbers"
            (assignment / paths.TO_GRADE).mkdir(parents=True)
            (assignment / paths.TO_GRADE / "0001.pdf").write_bytes(b"")
            (assignment / paths.INFO).write_text(json.dumps({
                "id": "3438636", "course": "Linear Algebra", "name": "Assignment 0 - Sets and Complex Numbers",
                "title": "הגשה 0 - קבוצות ומרוכבים", "due": "2026-10-26T23:59:00+02:00",
                "questions": [{"sheet": "דף קבוצות", "numbers": [11, 12]}],
            }, ensure_ascii=False), encoding="utf-8")

            (data / "Discrete Mathematics").mkdir()
            written = write_guides(data)
        finally:
            del os.environ["ASSIGNMENT_DATA"]

        assert written == [data / "Discrete Mathematics" / paths.README, assignment / paths.README,
                           assignment.parent / paths.README, data / paths.README]
        empty_course = (data / "Discrete Mathematics" / paths.README).read_text(encoding="utf-8-sig")
        assert "עוד אין" in empty_course
        assert (assignment / paths.MARKED / paths.README).exists()
        upload_note = (assignment / paths.UPLOAD / paths.README).read_text(encoding="utf-8-sig")
        assert "Upload steps.txt" in upload_note and "Upload log.csv" in upload_note
        assert "הוראות העלאה.txt" not in upload_note
        top = (data / paths.README).read_text(encoding="utf-8-sig")
        assert "Linear Algebra:\n  - Assignment 0 - Sets and Complex Numbers  (הגשה 0 - קבוצות ומרוכבים)" in top
        course = (assignment.parent / paths.README).read_text(encoding="utf-8-sig")
        assert "(הגשה 0 - קבוצות ומרוכבים): 1 הגשות" in course
        inner = (assignment / paths.README).read_text(encoding="utf-8-sig")
        assert inner.startswith("הגשה 0 - קבוצות ומרוכבים\n")
        assert "מועד הגשה: 2026-10-26 23:59" in inner
        assert "שאלות: דף קבוצות, 11, 12" in inner
        assert paths.TO_GRADE in inner


if __name__ == "__main__":
    test_guides_at_every_level_name_the_course_and_assignment()
    print("All tests passed.")
