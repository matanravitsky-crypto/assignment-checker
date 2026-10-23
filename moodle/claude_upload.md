You upload one feedback ZIP to Moodle for a university course. Follow these steps exactly, using only the Chrome tools.

Rules (never break them):
- Go only to this address: {upload_url} (and {home_url}, as the next rule says). Never open assignment settings or any other page.
- If a page shows "404 Not Found" or a login page, Moodle's session has expired. Open {home_url} once, wait a few seconds (Moodle signs in again by itself), and open the address you wanted again. {give_up}
- In a dry run never click יבוא קבצי משוב: it imports immediately and cannot be undone.
- Click יבוא קבצי משוב at most once. Never click it twice and never retry an import.
- Never take a screenshot of the grading page that Moodle shows after the import. Never write any person's name in your answer.
- Never change grades or settings. Never upload any file other than {zip_path}.

Steps:
1. Open {upload_url}.
2. Check the address has id={assignment_id} and the page is for the assignment "{title}". If not, return "error".
3. In the file picker choose "העלאת קובץ". Find the input[type=file] with find or read_page and upload {zip_path} with file_upload. Do not click the file input. Then click "העלאת קובץ זה".
4. Check that the ZIP's file name appears in the form's file area. If it does not, return "error".
   {mode}
5. Real run only (a dry run stops at step 4): click יבוא קבצי משוב exactly once. Moodle imports at once and lands on the grading page, where the result message may be a notification. Read that message.
   Return "imported" with imported = the number Moodle says it imported, skipped = the number it says it skipped as unchanged (0 if none), and rows = imported + skipped.
   If that total differs from the expected {expected}, return "mismatch" with the numbers, and say in the message that the import already happened and cannot be cancelled.
   If you cannot find a result message, return "error" with the message "לא נמצאה הודעת תוצאה ממודל".

Return only the structured result. "message" says what happened in one short sentence, with numbers only.
