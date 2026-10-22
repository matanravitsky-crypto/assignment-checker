# dashboard/: השרת המקומי של האתר

מחבר את האתר ([`website/`](../website/)) לתיקייה המשותפת ולקוד של [`moodle/`](../moodle/). מפעילים אותו במחשב שמסנכרן את התיקייה:

```bash
python -m dashboard serve
```

או בלחיצה כפולה על `start.bat`. האתר נפתח בכתובת `http://localhost:8765`.

| קובץ | מה הוא עושה |
|---|---|
| `shared_folder.py` | מוצא במחשב את `YallaLinearit/Exercise Checking System` |
| `folder_view.py` | קורא את המבנה לתצוגה: קורסים, מטלות ומספרי הגשות. בלי שמות |
| `actions.py` | הפעולות: משיכה (`moodle ingest`) עם נעילה ובדיקת עותקים כפולים, בדיקה ברקע (`grading/`), הכנת החזרה (`moodle upload`), העלאה למודל ברקע (`moodle send`), והמצב לאתר |
| `web_server.py` | השרת: מגיש את האתר ואת `/api/...` |
| `settings.py` | קורא את `.env` (מפתח Claude) |

## ה-API של השרת

| כתובת | מה עושה |
|---|---|
| `GET /api/health` | האם התיקייה נמצאה |
| `GET /api/state` | כל הקורסים, המטלות וההגשות, לפי מספר בלבד |
| `GET /api/file?path=` | קובץ PDF של הגשה, רק מתיקיות 1-2-3. טבלת המפתח לא נשלחת לעולם |
| `POST /api/pull` | משיכה: `moodle ingest` |
| `POST /api/grade` | מתחיל בדיקה עם Claude ברקע: `{course, assignment, ids?, model?, parallel?, instructions?, sendSolution?}`. בלי מפתח: 400 עם הסבר |
| `GET /api/grade` | מצב הבדיקה שרצה: כמה נבדקו, מה נכשל, וסיכום בסוף |
| `POST /api/return` | הכנת החזרה: `moodle upload` |
| `POST /api/upload/prepare` | הכנת העלאה למודל: `{course, assignment}`. בונה אצווה של העבודות המסומנות שחדשות או השתנו ומחזירה סיכום וגם `id`. 422 עם הסבר אם אי אפשר (או אם מישהו מעלה עכשיו) |
| `POST /api/upload/start` | מתחיל להעלות ברקע את האצווה: `{course, assignment, batchId}`. 202 עם המצב. 409 אם כבר רצה העלאה או אם האצווה כבר לא העדכנית |
| `GET /api/upload` | מצב ההעלאה שרצה: `running`, `done` מתוך `total`, `current`, `stopped`, `message` |
| `POST /api/upload/stop` | מבקש לעצור אחרי ה-ZIP שמועלה עכשיו |
| `GET /api/moodle` | האם Claude Code מותקן ומחובר במחשב (נשמר דקה) |
| `POST /api/moodle/check` | האם Chrome ומודל מוכנים: `{course, assignment}` (ריצה קצרה של Claude) |
| `GET /api/ready?course=&assignment=` | רשימת המוכנות להעלאה, מהירה: Claude Code מותקן, מחובר, ותוצאת הבדיקה האחרונה של Chrome ומודל (נשמרת 30 דקות) |
| `POST /api/ready/check` | מריץ את בדיקת Chrome ומודל מחדש: `{course, assignment}` |
| `POST /api/claude/login` | מתחיל את ההתחברות של Claude Code (`claude auth login`). ההתחברות מסתיימת בכניסה בדפדפן |
| `POST /api/claude/install` | מתקין את Claude Code במחשב |
| `POST /api/open` | פותח תיקייה בסייר הקבצים |

**אבטחה:** השרת מאזין רק למחשב עצמו. כל בקשה שמשנה משהו חייבת את הכותרת `X-Assignment-Checker`, ו-Host ו-Origin של המחשב, כדי שאתרים אחרים לא יוכלו להפעיל אותו.

## הדגמה בלי מודל

`MOODLE_DRIVER=simulate` מחליף את Claude במדמה שלא נוגע במודל, ו-`MOODLE_READY=simulate` (רק יחד איתו) מדמה גם את רשימת המוכנות וההתחברות. שניהם להדגמה בלבד. להפעלה:

```bash
python -m tests.make_demo_root data/demo-root
python -m tests.serve_demo
```

## העלאה למודל מהאתר

בשלב 3, כשהאתר רץ דרך השרת, לחיצה על "העלה N למודל" מציגה קודם רשימת מוכנות: האם Claude Code מותקן (עם כפתור התקנה), האם הוא מחובר (ההתחברות מתחילה לבד והכניסה בדפדפן משלימה אותה), והאם Chrome ומודל מחוברים. אחר כך חלון אישור, התקדמות, עצירה והמשך.

## פקודות נוספות

```bash
python -m dashboard where
```
מראה איפה נמצאת התיקייה המשותפת במחשב.

```bash
python -m dashboard list
```
מציג את הקורסים, המטלות ומספר ההגשות.

הבדיקות נמצאות ב-[`tests/dashboard/`](../tests/dashboard/).
