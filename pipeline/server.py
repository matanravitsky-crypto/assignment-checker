"""שרת מקומי: מגיש את האתר ומחבר את הכפתורים שלו לתיקיית OneDrive.

מפעילים אותו במחשב שמסנכרן את התיקייה (start.bat, או python -m pipeline serve),
ונכנסים ל-http://localhost:8765. שם הכפתור "משוך הגשות" מושך באמת לתוך OneDrive.
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

from . import service, settings as cfg, team

DOCS = cfg.REPO_DIR / "docs"
HEADER = "X-Assignment-Checker"
_lock = threading.Lock()  # משיכה אחת בכל פעם


class Handler(SimpleHTTPRequestHandler):
    server_version = "AssignmentChecker"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS), **kwargs)

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
        root, err = service.root_info()
        if not root:
            self._json({"error": err}, HTTPStatus.SERVICE_UNAVAILABLE)
        return root

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    # ---------- GET ----------
    def do_GET(self):
        if not self._host_ok():
            return self.send_error(HTTPStatus.FORBIDDEN)
        url = urlparse(self.path)
        if url.path == "/api/health":
            root, err = service.root_info()
            return self._json({"ok": True, "root": str(root) if root else None, "error": err,
                               "moodle": False, "claude": bool(cfg.claude_key())})
        if url.path == "/api/state":
            root = self._root()
            return root and self._json(service.state(root))
        if url.path == "/api/file":
            root = self._root()
            if not root:
                return
            rel = parse_qs(url.query).get("path", [""])[0]
            target = (root / rel).resolve()
            # רק קובצי PDF של הגשות (תיקיות 1-2-3). טבלת המפתח, עם השמות, לא יוצאת מהתיקייה
            allowed = (team.SUBMISSIONS, team.GRADED, team.READY)
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
            return self.send_error(HTTPStatus.FORBIDDEN)
        url = urlparse(self.path)
        root = self._root()
        if not root:
            return
        body = self._body()
        if url.path in ("/api/pull", "/api/return"):
            # משיכה: moodle ingest. החזרה: moodle upload. אחת בכל פעם
            course, assignment = body.get("course"), body.get("assignment")
            if not course or not assignment:
                return self._json({"error": "חסרים קורס ומטלה"}, HTTPStatus.BAD_REQUEST)
            if not _lock.acquire(blocking=False):
                return self._json({"error": "פעולה אחרת כבר רצה. כדאי לנסות שוב בעוד רגע."}, HTTPStatus.CONFLICT)
            try:
                run = service.pull if url.path == "/api/pull" else service.prepare_return
                return self._json(run(root, course, assignment))
            except service.UserError as e:
                return self._json({"error": str(e)}, HTTPStatus.UNPROCESSABLE_ENTITY)
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            except Exception as e:  # השגיאה מוצגת באתר במקום שהשרת ייפול
                what = "המשיכה" if url.path == "/api/pull" else "הכנת ההחזרה"
                return self._json({"error": f"{what} נכשלה: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            finally:
                _lock.release()
        if url.path == "/api/open":
            # פותח בסייר הקבצים: תיקיית ההורדות (לשם מודל מוריד את ה-ZIP), תיקיית המטלה, או תיקיית ההעלאה
            try:
                asg = service.find_assignment(root, body.get("course", ""), body.get("assignment", ""))
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            which = body.get("which")
            target = (Path.home() / "Downloads" if which == "inbox"
                      else asg.dir / team.READY if which == "upload" else asg.dir)
            target.mkdir(exist_ok=True)
            if hasattr(os, "startfile"):
                os.startfile(target)  # noqa: S606 - תיקייה קבועה, לא מהמשתמש
            return self._json({"opened": str(target)})
        return self.send_error(HTTPStatus.NOT_FOUND)


def serve(port: int = 8765, open_browser: bool = True) -> None:
    cfg.load_env()
    root, err = service.root_info()
    if root:
        print(f"תיקיית המערכת: {root}")
    else:
        print(err)
        print("\nהאתר יעלה בכל זאת, ויציג את ההסבר הזה עד שהתיקייה תסתנכרן.")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    print(f"\nבודק העבודות פועל: {url}\nכדי לעצור: Ctrl+C או לסגור את החלון.")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
