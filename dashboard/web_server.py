"""שרת מקומי: מגיש את האתר ומחבר את הכפתורים שלו לתיקיית OneDrive.

מפעילים אותו במחשב שמסנכרן את התיקייה (start.bat, או python -m dashboard serve),
ונכנסים ל-http://localhost:8765. שם הכפתור "משוך הגשות" מושך באמת לתוך OneDrive,
והכפתור "בדוק" שולח את ההגשות הממוספרות ל-Claude (צריך ANTHROPIC_API_KEY ב-.env).
האתר הציבורי (https://bodek-hacham.vercel.app) מתחבר לשרת הזה כשהוא פועל במחשב,
ובלעדיו לא מציג נתונים.

השרת מאזין רק למחשב עצמו (127.0.0.1), ואתרים אחרים לא יכולים להפעיל אותו:
כל בקשה שמשנה משהו חייבת כותרת מיוחדת ומקור (Origin) של השרת עצמו או של האתר הציבורי,
ורק האתר הציבורי מקבל הרשאת CORS לקרוא את התשובות.
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
# האתר הציבורי ב-Vercel: רק הכתובת הזו בדיוק (לא כתובות תצוגה מקדימה של Vercel)
SITE_ORIGINS = ("https://bodek-hacham.vercel.app",)
_lock = threading.Lock()  # משיכה אחת בכל פעם
FILE_TYPES = (".pdf", ".jpg", ".jpeg", ".png")  # מה אפשר להוריד מ-"1 - Submissions to grade"
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
        return origin is None or origin in SITE_ORIGINS or urlparse(origin).hostname in ("127.0.0.1", "localhost")

    def end_headers(self):
        # האתר הציבורי קורא את התשובות (CORS). אתרים אחרים לא
        headers = getattr(self, "headers", None)
        origin = headers.get("Origin") if headers else None
        if origin in SITE_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        if not urlparse(getattr(self, "path", "") or "").path.startswith("/api/"):
            # קובצי האתר: הדפדפן בודק בכל טעינה אם יש גרסה חדשה (אחרי עדכון מ-GitHub), אחרת נשארת גרסה ישנה
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_OPTIONS(self):
        """בקשת ה-preflight של הדפדפן לפני שהאתר הציבורי פונה לשרת (כולל Private Network Access של Chrome)."""
        if not self._host_ok() or self.headers.get("Origin") not in SITE_ORIGINS:
            return self.send_error(HTTPStatus.FORBIDDEN)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", f"Content-Type, {HEADER}")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

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
            # עונה מיד: מצב Claude Code נבדק ברקע (quick_status). checking=true עד שיש תשובה, והאתר שואל שוב
            root, err = actions.root_info()
            st, via = actions.quick_status(), actions.quick_via()
            return self._json({"ok": True, "root": str(root) if root else None, "error": err,
                               "moodle": bool(st and st.get("logged_in")), "claude": via is not None, "claudeVia": via,
                               "checking": st is None and via is None})
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
        if url.path in ("/api/pages", "/api/page"):
            # עמודי הגשה כתמונות, לבדיקה הידנית: /api/pages אומר כמה עמודים, /api/page מחזיר עמוד אחד
            root = self._root()
            if not root:
                return
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            course, assignment, number = q.get("course", ""), q.get("assignment", ""), q.get("number", "")
            if not course or not assignment or not number.isdigit():
                return self._json({"error": "חסרים קורס, מטלה ומספר הגשה"}, HTTPStatus.BAD_REQUEST)
            try:
                if url.path == "/api/pages":
                    return self._json({"pages": actions.page_count(root, course, assignment, number)})
                data = actions.page_image(root, course, assignment, number, int(q.get("page") or 0))
            except (FileNotFoundError, ValueError):
                return self.send_error(HTTPStatus.NOT_FOUND)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if url.path == "/api/file":
            root = self._root()
            if not root:
                return
            query = parse_qs(url.query)
            rel = query.get("path", [""])[0]
            target = (root / rel).resolve()
            # רק קבצים של הגשות (תיקיות 1-2-3): PDF, ובהגשות גם תמונות. טבלת המפתח, עם השמות, לא יוצאת מהתיקייה
            allowed = (folder_view.SUBMISSIONS, folder_view.GRADED, folder_view.READY)
            kinds = FILE_TYPES if target.parent.name == folder_view.SUBMISSIONS else (".pdf",)
            if (not target.is_file() or not target.is_relative_to(root.resolve())
                    or target.suffix.lower() not in kinds or target.parent.name not in allowed):
                return self.send_error(HTTPStatus.NOT_FOUND)
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            if query.get("download", [""])[0] == "1":
                # הורדה: "0023 - submission.pdf" או "0023 - graded.pdf", כדי שההגשה והבדוקה לא יידרסו זו את זו
                which = "graded" if target.parent.name == folder_view.GRADED else "submission"
                self.send_header("Content-Disposition", f'attachment; filename="{target.stem} - {which}{target.suffix.lower()}"')
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
                # הגשה שעוד לא נמשכה: המשיכה הראשונה שולחת גם את מזהה המטלה במודל
                extra = {"moodle_id": str(body["moodleId"])} if url.path == "/api/pull" and body.get("moodleId") else {}
                return self._json(getattr(actions, run)(root, course, assignment, **extra))
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
            except grading.NoRubric as e:
                return self._json({"error": str(e), "noRubric": True}, HTTPStatus.UNPROCESSABLE_ENTITY)
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            except RuntimeError as e:
                return self._json({"error": str(e)}, HTTPStatus.CONFLICT)
            return self._json(job, HTTPStatus.ACCEPTED)
        if url.path == "/api/review":
            # בדיקה ידנית: אדם קבע ניקוד, הערות ומשוב לעבודה אחת. נשמר ב-Grades.csv כמאושר
            course, assignment, number = body.get("course"), body.get("assignment"), body.get("number")
            points = body.get("points")
            if not course or not assignment or not isinstance(number, str) or not number.isdigit():
                return self._json({"error": "חסרים קורס, מטלה ומספר הגשה"}, HTTPStatus.BAD_REQUEST)
            if not isinstance(points, list) or not all(isinstance(p, (int, float)) and not isinstance(p, bool) for p in points):
                return self._json({"error": "הניקוד לא תקין"}, HTTPStatus.BAD_REQUEST)
            try:
                return self._json(actions.save_review(root, course, assignment, number, points, body.get("comments") or [],
                                                      str(body.get("feedback") or ""), body.get("mistakes")))
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
            except grading.GradingError as e:
                return self._json({"error": str(e)}, HTTPStatus.UNPROCESSABLE_ENTITY)
            except Exception as e:
                return self._json({"error": f"השמירה נכשלה: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
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
    actions.refresh_status_soon()  # כבר עכשיו, כדי שהתשובה תהיה מוכנה כשהאתר נפתח
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
