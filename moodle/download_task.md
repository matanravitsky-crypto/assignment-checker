# Scheduled download task

The prompt for the Claude desktop scheduled task that downloads submissions
automatically. Set it up per computer (see "Setting up a computer" in CLAUDE.md):
replace `<REPO>` with this repo's absolute path and schedule it twice a day
(`0 8,20 * * *`). A run missed while the computer was off happens when the
Claude app next opens, so whoever opens their computer gets what was submitted.

---

You download student submissions from BGU Moodle for the assignment-checker project at `<REPO>`.

1. In `<REPO>`, run `git pull` (so assignments.json is current), then `python -m moodle pending`.
   It prints one line per assignment to download: `<assignment id>` then a tab and its name.
   If it prints nothing, stop: there is nothing to do. Do not notify.
2. For each assignment id, using Claude in Chrome:
   a. Open `https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id=<assignment id>`.
      If Moodle shows a login page, stop and notify: "Log in to Moodle in Chrome so the download can run." Never type a password.
      If the page shows an error or 404, notify with the assignment name and go on to the next one.
   b. Read the grading summary. If time remaining is still positive (the assignment is open), skip it: it is not due yet.
      Note the "submitted" (הוגש) count.
   c. Open `...view.php?id=<assignment id>&action=grading`. Make sure "organize submissions in folders per student" is checked.
      Actions (פעולות) → "הורדת כל ההגשות (השתמש ב 7ZIP לפתיחה)".
   d. Wait until a `*-<assignment id>.zip` is in the Downloads folder and no `*.crdownload` remains (large ZIPs take minutes).
      If after 15 minutes there is still only a `.crdownload`, Chrome is waiting on a Save As window: stop and notify
      "Turn off 'Ask where to save each file' in Chrome settings".
   e. In `<REPO>` run `python -m moodle ingest <assignment id>`. It prints "<N> submissions".
      Check N equals the submitted count from step b.
3. Notify once with a short summary per assignment: name, submissions downloaded, and any mismatch or problem.

Rules: do not upload anything to Moodle, do not change any Moodle setting, do not open files in `original/`,
and do not put names, ID numbers or emails in the notification.
