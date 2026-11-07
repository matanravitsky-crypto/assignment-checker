"""היומן: מי עשה מה ומתי. ראו activity_log/README.md.

    from activity_log import record, read
    record(assignment_dir, "grade_edit", by="dana (PC)", number="0001", reason="...")
    read(assignment_dir, "grade_edit", number="0001")
"""
from .log import FOLDER, file_for, read, record

__all__ = ["FOLDER", "file_for", "read", "record"]
