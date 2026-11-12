"""שלב 2: בדיקת העבודות עם Claude. ראו grading/README.md."""

# הממשק: מה שחלקים אחרים מותר להם לקחת מכאן. כל השאר פנימי, ואפשר לשנות אותו בלי לשאול אף חלק אחר.
# tests/test_modularity.py נופל כשקוד מחוץ לחלק לוקח משהו שלא ברשימה. "*" = כל מה שלא מתחיל ב-_ (הליבה).
INTERFACE = {
    "grade": [
        # הבדיקה
        "grade_assignment", "pending", "claude_ask", "default_model", "Ask", "DEFAULT_PARALLEL",
        "GradingError", "NoApiKey", "NoRubric", "ClaudeLimit", "is_limit",
        # המחוון, המכוון וחומר הבדיקה
        "load_context", "require_rubric", "official_key", "read_details", "docx_text", "to_points", "parse_points",
        "KEY_MEDIA", "SOLUTION",
        # מה שהבדיקה כתבה
        "read_grades", "read_notes", "notes_path", "marked_files", "is_approved", "number_key",
        "submission_files", "submission_numbers", "submission_pdf",
        # הבדיקה הידנית
        "save_review",
    ],
    "grade_edit": ["connect_database", "connect_stats", "connect_moodle_table", "history", "history_all",
                   "EditIncomplete", "ReasonRequired", "ACTION_FAILED"],
}
