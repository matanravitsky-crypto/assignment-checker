"""השרת המקומי של האתר: מחבר את הדשבורד (website/) לתיקייה המשותפת ולשלבים של moodle/.

  shared_folder.py  איפה נמצאת התיקייה "Exercise Checking System" במחשב
  folder_view.py    קריאה של המבנה, לתצוגה באתר (השמות מוגדרים ב-moodle/paths.py)
  actions.py        משיכה (moodle ingest), הכנת החזרה (moodle upload), והמצב לאתר
  web_server.py     שרת מקומי: מגיש את האתר ואת הכפתורים
  settings.py       .env במחשב (מפתח Claude)

הפעלה: start.bat, או python -m dashboard serve
"""
