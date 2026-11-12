"""היומן: מי עשה מה ומתי. ראו activity_log/README.md.

    from activity_log import record, read
    record(assignment_dir, "grade_edit", by="dana (PC)", number="0001", reason="...")
    read(assignment_dir, "grade_edit", number="0001")
"""
from .log import FOLDER, event_id, file_for, read, record

__all__ = ["FOLDER", "event_id", "file_for", "read", "record"]

# הממשק: מה שחלקים אחרים מותר להם לקחת מכאן. כל השאר פנימי, ואפשר לשנות אותו בלי לשאול אף חלק אחר.
# tests/test_modularity.py נופל כשקוד מחוץ לחלק לוקח משהו שלא ברשימה. "*" = כל מה שלא מתחיל ב-_ (הליבה).
INTERFACE = {"": ["record", "read", "file_for", "event_id", "FOLDER"]}
