"""השרת המקומי של האתר: מחבר את הדשבורד (website/) לתיקייה המשותפת ולשלבים של moodle/.

  folder_view.py    קריאה של המבנה, לתצוגה באתר (השמות מוגדרים ב-moodle/paths.py)
  actions.py        משיכה (moodle ingest), הכנת החזרה (moodle upload), והמצב לאתר
  web_server.py     שרת מקומי: מגיש את האתר ואת הכפתורים

הפעלה: start.bat, או python -m dashboard serve
"""

# הדשבורד הוא למעלה: אף חלק לא מייבא אותו. הממשק שלו הוא ה-API ב-HTTP (dashboard/README.md), שהאתר (website/)
# והסנכרון (onedrive/sync.js) משתמשים בו. shared_folder.py ו-settings.py שכאן הם כינויים לליבה ב-moodle/.
INTERFACE: dict = {}
