import json
import tempfile
from pathlib import Path

from moodle.guide import GUIDE_NAME, write_guides


def test_guides_name_each_assignment_and_its_folders():
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        assignment = data / "submissions" / "3438636"
        (assignment / "anon").mkdir(parents=True)
        (assignment / "anon" / "0001.pdf").write_bytes(b"")
        (assignment / "assignment.json").write_text(json.dumps({
            "id": "3438636", "course": "אלגברה לינארית", "name": "הגשה 0",
            "due": "2026-10-26T23:59:00+02:00",
            "questions": [{"sheet": "דף קבוצות", "numbers": [11, 12]}],
        }, ensure_ascii=False), encoding="utf-8")

        written = write_guides(data)

        assert written == [assignment / GUIDE_NAME, data / GUIDE_NAME]
        top = (data / GUIDE_NAME).read_text(encoding="utf-8-sig")
        assert "3438636  =  אלגברה לינארית - הגשה 0" in top
        inner = (assignment / GUIDE_NAME).read_text(encoding="utf-8-sig")
        assert "מועד הגשה: 2026-10-26 23:59" in inner
        assert "שאלות: דף קבוצות, 11, 12" in inner
        assert "1 הגשות ממוספרות" in inner


if __name__ == "__main__":
    test_guides_name_each_assignment_and_its_folders()
    print("All tests passed.")
