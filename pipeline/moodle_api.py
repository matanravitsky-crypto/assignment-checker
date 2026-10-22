"""משיכה אוטומטית ממודל דרך שירותי הרשת שלו (Web services).

דורש טוקן של משתמש עם הרשאת בודק/מרצה בקורס, במשתנה MOODLE_TOKEN (בקובץ .env).
בלי טוקן המערכת עובדת עם קובצי ZIP שהורדו ממודל (ראו moodle_zip.py).

הפונקציות של מודל שבשימוש (חלק מהשירות הרגיל של מודל):
  mod_assign_get_assignments    רשימת המטלות בקורס, עם תאריך הגשה
  mod_assign_get_submissions    ההגשות של מטלה, כולל קישורים לקבצים
  core_user_get_users_by_field  שם, מייל ומספר זהות של הסטודנטים
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime

from .workspace import Submission, SubmittedFile


class MoodleError(Exception):
    pass


class Moodle:
    def __init__(self, url: str, token: str, timeout: float = 60):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def call(self, function: str, **params) -> dict | list:
        data = {"wstoken": self.token, "wsfunction": function, "moodlewsrestformat": "json"}
        for key, value in params.items():
            if isinstance(value, (list, tuple)):
                for i, v in enumerate(value):
                    data[f"{key}[{i}]"] = v
            else:
                data[key] = value
        req = urllib.request.Request(f"{self.url}/webservice/rest/server.php", data=urllib.parse.urlencode(data).encode())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
        except OSError as e:
            raise MoodleError(f"אין חיבור למודל ({self.url}): {e}") from e
        if isinstance(out, dict) and out.get("exception"):
            raise MoodleError(f"מודל החזיר שגיאה: {out.get('message') or out.get('errorcode')}")
        return out

    def download(self, file_url: str) -> bytes:
        sep = "&" if "?" in file_url else "?"
        try:
            with urllib.request.urlopen(f"{file_url}{sep}token={urllib.parse.quote(self.token)}", timeout=self.timeout) as resp:
                return resp.read()
        except OSError as e:
            raise MoodleError(f"הורדת קובץ נכשלה: {e}") from e

    # ---------- מטלות ----------
    def assignments(self, course_id: int) -> list[dict]:
        out = self.call("mod_assign_get_assignments", courseids=[course_id])
        courses = out.get("courses", [])
        return courses[0].get("assignments", []) if courses else []

    # ---------- הגשות ----------
    def submissions(self, assign_id: int) -> list[Submission]:
        out = self.call("mod_assign_get_submissions", assignmentids=[assign_id])
        rows = (out.get("assignments") or [{}])[0].get("submissions", [])
        rows = [r for r in rows if r.get("status") == "submitted"]
        users = self._users([r["userid"] for r in rows])

        subs = []
        for r in rows:
            files = []
            for plugin in r.get("plugins", []):
                for area in plugin.get("fileareas", []):
                    for f in area.get("files", []):
                        files.append(SubmittedFile(name=f["filename"], data=self.download(f["fileurl"])))
                for editor in plugin.get("editorfields", []):
                    if editor.get("text"):
                        files.append(SubmittedFile(name="onlinetext.html", data=editor["text"].encode("utf-8")))
            u = users.get(r["userid"], {})
            subs.append(Submission(
                moodle_id=str(r["userid"]),
                name=u.get("fullname") or f"משתמש {r['userid']}",
                files=files,
                submitted_at=datetime.fromtimestamp(r["timemodified"]) if r.get("timemodified") else None,
                student_id=u.get("idnumber") or "",
                email=u.get("email") or "",
            ))
        return sorted(subs, key=lambda s: s.name)

    def _users(self, ids: list[int]) -> dict[int, dict]:
        if not ids:
            return {}
        out = self.call("core_user_get_users_by_field", field="id", values=ids)
        return {u["id"]: u for u in out}
