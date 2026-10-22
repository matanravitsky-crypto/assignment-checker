"""האתר המחובר של בודק העבודות: מחבר את הדשבורד (docs/) לתיקייה המשותפת ולשלבים של moodle/.

  config.py    איפה נמצאת התיקייה "Exercise Checking System"
  team.py      קריאה של המבנה, לתצוגה (השמות מוגדרים ב-moodle/paths.py)
  service.py   משיכה (moodle ingest), בדיקה (grade.py), החזרה (moodle upload), והמצב לאתר
  render.py    הפיכת עמודי ההגשה לתמונות, לשליחה ל-Claude
  grade.py     שלב 2: בדיקה עם Claude, סימון ההערות על ה-PDF ו-Grades.csv
  server.py    שרת מקומי: האתר + הכפתורים
  settings.py  .env במחשב (מפתח Claude)
  types.py     מבנה של הגשה (בשימוש בשלב הבדיקה)
  demo.py      קובצי PDF לדוגמה, לבדיקות
"""
