# datastore/: בדיקת השלמות של הנתונים, ויומן האירועים של הציונים

הנתונים של המערכת הם קובצי CSV ו-JSON בתיקיית OneDrive, בלי מסד נתונים. החלק הזה בודק שהם שלמים, מתקן את מה שבטוח
לתקן לבד, ושומר יומן של כל שינוי ציון כדי שאפשר יהיה לשחזר ציון שאבד (הצעות A ו-B ב-[`DB_UPGRADE_PLAN.md`](../DB_UPGRADE_PLAN.md)).
מספרים בלבד: שום הודעה כאן לא מכילה שם או מזהה של סטודנט.

## ממשק

| | |
|---|---|
| **נכנס** | תיקיית מטלה (כל הקבצים שבה), ואירועי הציון ב-`Activity log/` |
| **יוצא** | רשימת בעיות (`Report`, עם `Problem` לכל אחת: קוד, הודעה, רמה, איפה, איזה מספר), תיקונים (`fix`), ושחזור של שורת ציון שאבדה לקובץ של מי שכתב אותה (`replay`) |
| **פקודות** | `python -m datastore check <id>` / `check --all`, `fix <id> [--yes]`, `replay <id> [--yes]`, `history <id> <מספר>` |
| **באתר** | `GET /api/integrity`, `POST /api/integrity/fix` (הפס "שלמות הנתונים"), `GET /api/grade-log` (ההיסטוריה בעמוד הבדיקה הידנית) |
| **מפייתון** | `INTERFACE` ב-`datastore/__init__.py`: `doctor.check`, `doctor.check_all`, `doctor.fix`, `ledger.LedgerStore`, `ledger.history` |
| **תלוי ב** | הליבה (`moodle/paths.py`, `grades`, `claims`, `lock`, `atomic`, `schema`), `grading` (המחוון, לבדוק ניקוד מעל המחוון), `activity_log` |

`LedgerStore` הוא מה שהדשבורד מחבר לעריכת ציון (`grade_edit.connect_database`, ב-`web_server.connect_stores`), כך ש"עריכה
התחילה" נרשמת לפני שאר היעדים. grading לא מייבא את datastore.

## הקבצים

| קובץ | מה הוא עושה |
|---|---|
| `doctor.py` | בדיקת השלמות של מטלה: כפילויות, PDF מסומן בלי שורת ציון, עותקים מתנגשים של OneDrive מכל סוג, נעילות תקועות, קבצים לא חוקיים, יומן שלא מסכים עם הקבצים. `fix` מתקן רק מה שבטוח (ממזג עותקים מתנגשים של קובצי בודקים ומעביר אותם ל-`Earlier versions/Conflict copies`, מסיר נעילות תקועות, מוחק עותק מתנגש של סטטיסטיקה, שהיא נגזרת) |
| `ledger.py` | יומן האירועים של הציונים, מעל `activity_log`: `grade_set`, `grade_failed`, `grade_edit_intent`, `grade_edit`, `grade_edit_failed`, `grade_replayed`. `projection` אומר מה הציון צריך להיות (אישור גובר, אחר כך הזמן, אחר כך המזהה), `compare` ו-`replay` מוצאים ומחזירים שורה שאבדה, `history` מראה את כל האירועים של עבודה |
| `__main__.py` | שורת הפקודה |
| `atomic.py`, `schema.py` | **כינויים בלבד.** הכתיבה האטומית והסכמה עברו ב-2026-11-12 לליבה ב-`moodle/` (`moodle/atomic.py`, `moodle/schema.py`), כי `moodle` עצמו כותב דרכן ו-`datastore` משתמש ב-`moodle`: כשהן היו כאן, שני החלקים היו תלויים זה בזה. `from datastore import atomic` עדיין עובד ונותן את אותו מודול |

## הבדיקות

`tests/datastore/`: כתיבה אטומית ונעילות (גם תהליכים אמיתיים במקביל), הסכמה מול קלט עוין, ה-doctor, ה-fix והיומן.
החיבור לשאר המערכת: `tests/integration/test_datastore_wiring.py` ו-`tests/integration/test_grading_transaction.py`.
