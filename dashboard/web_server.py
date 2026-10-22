"""שרת מקומי: מגיש את האתר ומחבר את הכפתורים שלו לתיקיית OneDrive.

מפעילים אותו במחשב שמסנכרן את התיקייה (start.bat, או python -m dashboard serve),
ונכנסים ל-http://localhost:8765. שם הכפתור "משוך הגשות" מושך באמת לתוך OneDrive,
והכפתור "בדוק" שולח את ההגשות הממוספרות ל-Claude (צריך ANTHROPIC_API_KEY ב-.env).
האתר הציבורי ב-GitHub Pages ממשיך לעבוד במצב הדגמה.

השרת מאזין רק למחשב עצמו (127.0.0.1), ואתרים אחרים לא יכולים להפעיל אותו:
כל בקשה שמשנה משהו חייבת כותרת מיוחדת ומקור (Origin) של השרת עצמו.
"""
from __future__ import annotations

import json
import mimetypes
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from grading import grade as grading

from . import actions, folder_view, settings as cfg

WEBSITE = cfg.REPO_DIR / "website"
HEADER = "X-Assignment-Checker"
_lock = threading.Lock()  # משיכה אחת בכל פעם
STALE_UPLOAD = "הקבצים השתנו מאז ההכנה. צריך ללחוץ שוב על 'העלה למודל'."
# כתובת → (הפעולה ב-actions, איך קוראים לה בהודעת שגיאה). אלה רצות תחת _lock
_LOCKED_STEPS = {
    "/api/pull": ("pull", "המשיכה"),
    "/api/return": ("prepare_return", "הכנת ההחזרה"),
    "/api/upload/prepare": ("prepare_send", "הכנת ההעלאה"),
}


class Handler(SimpleHTTPRequestHandler):
    server_version = "AssignmentChecker"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEBSITE), **kwargs)

    def log_request(self, code="-", size="-"):  # שקט בקונסול, חוץ משגיאות
        try:
            if int(code) >= 400:
                super().log_request(code, size)
        except (TypeError, ValueError):
            pass

    # ---------- אבטחה ----------
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _write_ok(self) -> bool:
        if self.headers.get(HEADER) != "1":
            return False
        origin = self.headers.get("Origin")
        return origin is None or urlparse(origin).hostname in ("127.0.0.1", "localhost")

    # ---------- תשובות ----------
    def _json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _root(self):
        root, err = actions.root_info()
        if not root:
            self._json({"error": err}, HTTPStatus.SERVICE_UNAVAILABLE)
        return root

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _discard_body(self) -> None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if 0 < n <= 1_000_000:
            self.rfile.read(n)
        elif n:
            self.close_connection = True

    # ---------- GET ----------
    def do_GET(self):
        if not self._host_ok():
            return self.send_error(HTTPStatus.FORBIDDEN)
        url = urlparse(self.path)
        if url.path == "/api/health":
            root, err = actions.root_info()
            return self._json({"ok": True, "root": str(root) if root else None, "error": err,
                               "moodle": actions.moodle_status()["logged_in"], "claude": bool(cfg.claude_key())})
        if url.path == "/api/upload":
            return self._json(actions.send_status())
        if url.path == "/api/moodle":
            return self._json(actions.moodle_status())
        if url.path == "/api/ready":
            # מהירה: לא מפעילה בדיקת כרום. מי שרוצה בדיקה קורא ל-POST /api/ready/check
            root = self._root()
            if not root:
                return
            query = parse_qs(url.query)
            course, assignment = query.get("course", [""])[0], query.get("assignment", [""])[0]
            if not course or not assignment:
                return self._json({"error": "חסרים קורס ומטלה"}, HTTPStatus.BAD_REQUEST)
            try:
                return self._json(actions.readiness(root, course, assignment))
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
        if url.path == "/api/state":
            root = self._root()
            return root and self._json(actions.state(root))
        if url.path == "/api/grade":
            return self._json(actions.grade_status())
        if url.path == "/api/file":
            root = self._root()
            if not root:
                return
            rel = parse_qs(url.query).get("path", [""])[0]
            target = (root / rel).resolve()
            # רק קובצי PDF של הגשות (תיקיות 1-2-3). טבלת המפתח, עם השמות, לא יוצאת מהתיקייה
            allowed = (folder_view.SUBMISSIONS, folder_view.GRADED, folder_view.READY)
            if (not target.is_file() or not target.is_relative_to(root.resolve())
                    or target.suffix.lower() != ".pdf" or target.parent.name not in allowed):
                return self.send_error(HTTPStatus.NOT_FOUND)
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if url.path.startswith("/api/"):
            return self.send_error(HTTPStatus.NOT_FOUND)
        return super().do_GET()

    # ---------- POST ----------
    def do_POST(self):
        if not self._host_ok() or not self._write_ok():
            self._discard_body()  # else Windows may reset the connection before the client reads the 403
            return self.send_error(HTTPStatus.FORBIDDEN)
        url = urlparse(self.path)
        body = self._body()
        if url.path == "/api/claude/login":  # these two work on this computer, not on the shared folder: no root needed
            return self._json(actions.start_claude_login(restart=body.get("restart") is True))
        if url.path == "/api/claude/install":
            return self._json(actions.start_claude_install())
        root = self._root()
        if not root:
            return
        if url.path in _LOCKED_STEPS:
            # משיכה: moodle ingest. החזרה: moodle upload. הכנת העלאה: moodle send. אחת בכל פעם
            course, assignment = body.get("course"), body.get("assignment")
            if not course or not assignment:
                return self._json({"error": "חסרים קורס ומטלה"}, HTTPStatus.BAD_REQUEST)
            if not _lock.acquire(blocking=False):
                return self._json({"error": "פעולה אחרת כבר רצה. כדאי לנסות שוב בעוד רגע."}, HTTPStatus.CONFLICT)
            run, what = _LOCKED_STEPS[url.path]
            try:
                return self._json(getattr(actions, run)(root, course, assignment))
            except actions.UserError as e:
                return self._json({"error": str(e)}, HTTPStatus.UNPROCESSABLE_ENTITY)
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            except Exception as e:  # השגיאה מוצגת באתר במקום שהשרת ייפול
                return self._json({"error": f"{what} נכשלה: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            finally:
                _lock.release()
        if url.path == "/api/upload/start":
            # אחרי "כן" של אדם על האצווה שהוכנה. ההעלאה רצה ברקע, והאתר שואל על המצב ב-GET /api/upload
            course, assignment, batch_id = body.get("course"), body.get("assignment"), body.get("batchId")
            if not course or not assignment or not isinstance(batch_id, str) or not batch_id:
                return self._json({"error": "חסרים קורס, מטלה ומזהה אצווה"}, HTTPStatus.BAD_REQUEST)
            try:
                return self._json(actions.start_send(root, course, assignment, batch_id), HTTPStatus.ACCEPTED)
            except ValueError as e:
                if str(e) == "stale":
                    return self._json({"error": STALE_UPLOAD}, HTTPStatus.CONFLICT)
                return self._json({"error": f"ההעלאה לא התחילה: {e}"}, HTTPStatus.UNPROCESSABLE_ENTITY)
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            except RuntimeError as e:
                return self._json({"error": str(e)}, HTTPStatus.CONFLICT)
        if url.path == "/api/upload/stop":
            return self._json(actions.stop_send())
        if url.path in ("/api/moodle/check", "/api/ready/check"):
            course, assignment = body.get("course"), body.get("assignment")
            if not course or not assignment:
                return self._json({"error": "חסרים קורס ומטלה"}, HTTPStatus.BAD_REQUEST)
            check = actions.check_moodle if url.path == "/api/moodle/check" else actions.check_ready
            try:
                return self._json(check(root, course, assignment))
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            except RuntimeError as e:  # העלאה רצה עכשיו: הבדיקה וההעלאה היו מפעילות את אותו כרום
                return self._json({"error": str(e)}, HTTPStatus.CONFLICT)
            except Exception as e:
                return self._json({"error": f"הבדיקה נכשלה: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
        if url.path == "/api/grade":
            course, assignment = body.get("course"), body.get("assignment")
            if not course or not assignment:
                return self._json({"error": "חסרים קורס ומטלה"}, HTTPStatus.BAD_REQUEST)
            ids = body.get("ids")
            if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, str) and i.isdigit() for i in ids)):
                return self._json({"error": "רשימת ההגשות לא תקינה"}, HTTPStatus.BAD_REQUEST)
            model = body.get("model") or grading.DEFAULT_MODEL
            if not (isinstance(model, str) and model.startswith("claude-")):
                return self._json({"error": "מודל לא מוכר"}, HTTPStatus.BAD_REQUEST)
            try:
                parallel = max(1, min(int(body.get("parallel") or grading.DEFAULT_PARALLEL), 20))
            except (TypeError, ValueError):
                parallel = grading.DEFAULT_PARALLEL
            try:
                job = actions.start_grading(root, course, assignment, ids, model=model, parallel=parallel,
                                            instructions=str(body.get("instructions") or "")[:5000],
                                            send_solution=body.get("sendSolution", True) is not False)
            except grading.NoApiKey as e:
                return self._json({"error": str(e), "noKey": True}, HTTPStatus.BAD_REQUEST)
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            except RuntimeError as e:
                return self._json({"error": str(e)}, HTTPStatus.CONFLICT)
            return self._json(job, HTTPStatus.ACCEPTED)
        if url.path == "/api/open":
            # פותח בסייר הקבצים: תיקיית ההורדות (לשם מודל מוריד את ה-ZIP), תיקיית המטלה, או תיקיית ההעלאה
            try:
                asg = actions.find_assignment(root, body.get("course", ""), body.get("assignment", ""))
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            which = body.get("which")
            target = (Path.home() / "Downloads" if which == "inbox"
                      else asg.dir / folder_view.READY if which == "upload" else asg.dir)
            target.mkdir(exist_ok=True)
            if hasattr(os, "startfile"):
                os.startfile(target)  # noqa: S606 - תיקייה קבועה, לא מהמשתמש
            return self._json({"opened": str(target)})
        return self.send_error(HTTPStatus.NOT_FOUND)


def serve(port: int = 8765, open_browser: bool = True) -> None:
    cfg.load_env()
    root, err = actions.root_info()
    if root:
        print(f"תיקיית המערכת: {root}")
    else:
        print(err)
        print("\nהאתר יעלה בכל זאת, ויציג את ההסבר הזה עד שהתיקייה תסתנכרן.")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    print(f"\nבודק חכם פועל: {url}\nכדי לעצור: Ctrl+C או לסגור את החלון.")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
