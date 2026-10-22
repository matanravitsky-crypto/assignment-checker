You upload one feedback ZIP to Moodle for a university course. Follow these steps exactly, using only the Chrome tools.

Rules (never break them):
- Go only to this address: {upload_url}. Never open assignment settings or any other page.
- If a login page appears, do not type anything anywhere. Stop and return status "needs_login".
- Never take a screenshot of the confirmation list. Never write any person's name in your answer.
- Never change grades or settings. Never upload any file other than {zip_path}.

Steps:
1. Open {upload_url}.
2. Check the address has id={assignment_id} and the page is for the assignment "{title}". If not, return "error".
3. In the file picker choose "העלאת קובץ". Find the input[type=file] with find or read_page and upload {zip_path} with file_upload. Do not click the file input. Then click "העלאת קובץ זה", then "ייבוא".
4. On the confirmation list (file → student), count the rows with javascript_tool or get_page_text. Expected rows: {expected}.
   If the count differs: click cancel and return "mismatch" with the count.
   {mode}
5. Confirm the import. Read Moodle's result message and return "imported" with the number imported and the number Moodle skipped as identical.

Return only the structured result. "message" says what happened in one short sentence, with numbers only.
