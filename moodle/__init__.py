"""Moving submissions between Moodle and the grader, without student names.

Two things live here (see moodle/README.md):
- the core: the shared folder's names and rules, which every part uses and which uses nothing outside itself:
  paths, settings, shared_folder, atomic, schema, grades, claims, lock, claude_code (tools/modules.py, CORE);
- the Moodle steps: pull (ingest, anonymize, pull_check), return (upload, upload_log, send, send_grades,
  moodle_table) and the Claude-in-Chrome driver (claude_driver).
"""

# הממשק: מה שחלקים אחרים מותר להם לקחת מכאן. כל השאר פנימי, ואפשר לשנות אותו בלי לשאול אף חלק אחר.
# tests/test_modularity.py נופל כשקוד מחוץ לחלק לוקח משהו שלא ברשימה. "*" = כל מה שלא מתחיל ב-_ (הליבה).
INTERFACE = {
    # the core
    "paths": "*", "settings": "*", "shared_folder": "*", "atomic": "*", "schema": "*",
    "grades": "*", "claims": "*", "lock": "*", "claude_code": "*",
    # the pull
    "ingest": ["ingest", "wait_for_download", "name_from_zip", "parts_progress", "pulls", "INCOMPLETE", "LIST",
               "NO_FOLDERS"],
    "anonymize": ["check_key", "key_conflicts", "submission_conflicts", "KeyBroken", "KEY_EMPTY"],
    "pull_check": ["read", "PullCheckFailed"],
    # the return
    "upload": ["prepare_upload", "find_worksheet", "INSTRUCTIONS_FILE"],
    "upload_log": ["read_log", "read_batch", "last_hashes", "file_hash", "log_conflicts"],
    "send": ["prepare_batch", "run_batch", "current_batch", "MoodleDriver", "UploadResult", "UPLOAD_LOCK"],
    "send_grades": ["send_grades", "pending", "wait_for_worksheet", "WORKSHEET_WAIT_S"],
    "moodle_table": ["build", "save_worksheet"],
    # Claude Code and Chrome on this computer
    "claude_driver": ["ClaudeChromeDriver", "open_chrome", "find_claude", "auth_status", "NOT_INSTALLED",
                      "NOT_LOGGED_IN"],
}
