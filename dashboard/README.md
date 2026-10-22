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
| `actions.py` | הפעולות: משיכה (`moodle ingest`) עם נעילה ובדיקת עותקים כפולים, הכנת החזרה (`moodle upload`), והמצב לאתר |
| `web_server.py` | השרת: מגיש את האתר ואת `/api/...` |
| `settings.py` | קורא את `.env` (מפתח Claude) |

## ה-API של השרת

| כתובת | מה עושה |
|---|---|
| `GET /api/health` | האם התיקייה נמצאה |
| `GET /api/state` | כל הקורסים, המטלות וההגשות, לפי מספר בלבד |
| `GET /api/file?path=` | קובץ PDF של הגשה, רק מתיקיות 1-2-3. טבלת המפתח לא נשלחת לעולם |
| `POST /api/pull` | משיכה: `moodle ingest` |
| `POST /api/return` | הכנת החזרה: `moodle upload` |
| `POST /api/open` | פותח תיקייה בסייר הקבצים |

**אבטחה:** השרת מאזין רק למחשב עצמו. כל בקשה שמשנה משהו חייבת את הכותרת `X-Assignment-Checker`, ו-Host ו-Origin של המחשב, כדי שאתרים אחרים לא יוכלו להפעיל אותו.

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
