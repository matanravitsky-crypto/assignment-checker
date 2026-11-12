# מודולריות: כל חלק עצמאי, וכל חלק יכול לצאת לסקיל

המטרה: שכל חלק במערכת יהיה עצמאי, כך שמי שרוצה להוציא חלק לסקיל (כמו `rubric-builder`) יוכל לעשות את זה בלי לשבור
את שאר המערכת. הבדיקה נעשתה ב-2026-11-12. הכללים נבדקים בכל הרצה של `python -m pytest`
(`tests/test_modularity.py`), כך שהם לא נשחקים עם הזמן.

## הכללים

1. **אין תלות מעגלית.** החלקים מסודרים בשכבות, מלמטה למעלה (`LAYERS` ב-`tools/modules.py`):
   `moodle` ← `activity_log` ← `copying` ← `grading` ← `stats` ← `datastore` ← `dashboard`.
   חלק משתמש רק בחלקים שמתחתיו, אף פעם לא באחד שמעליו. `website/` ו-`onedrive/` מדברים עם הדשבורד רק דרך HTTP.
2. **הליבה לא תלויה בכלום.** הליבה היא השמות והכללים של התיקייה המשותפת, שכל חלק צריך:
   `moodle/paths.py` (כל שמות התיקיות והקבצים), `settings.py` (מה שבקובץ `.env` של כל מחשב, כולל המודלים),
   `shared_folder.py` (איפה התיקייה), `atomic.py` (כתיבה בטוחה), `schema.py` (מה חוקי), `grades.py`, `claims.py`,
   `lock.py`, `claude_code.py` (Claude Code במחשב). היא משתמשת רק בעצמה, ולכן חלק שיוצא לסקיל לוקח איתו את מה שהוא
   צריך ממנה.
3. **ממשק קטן ומוצהר.** בכל `__init__.py` יש `INTERFACE`: מה שחלקים אחרים מותר להם לקחת. כל השאר פנימי, ואף חלק לא
   לוקח שם פרטי (`_x`) של חלק אחר.
4. **README לכל חלק** עם סעיף `## ממשק`: מה נכנס, מה יוצא, ובמה הוא תלוי.
5. **בדיקות לכל חלק בלי שאר המערכת.** `tests/<חלק>/` לא מייבא חלק שמעליו. בדיקות של איך חלקים מתחברים נמצאות
   ב-`tests/integration/`.

## מה היה, ומה תוקן

| בעיה | איפה | התיקון |
|---|---|---|
| ארבעה מעגלים בין החלקים | `moodle`, `grading`, `copying` ו-`stats` מצאו את התיקייה המשותפת דרך `dashboard/shared_folder.py`, והדשבורד משתמש בכולם | `shared_folder.py` ו-`settings.py` עברו לליבה ב-`moodle/` |
| | `moodle` כתב דרך `datastore/atomic.py` ו-`schema.py`, ו-`datastore` משתמש ב-`moodle` | `atomic.py` ו-`schema.py` עברו לליבה ב-`moodle/` |
| | `grading` קרא ל-`stats.build`, ו-`stats` קורא את המחוון דרך `grading` | `grading` לא מייבא את `stats`. הדשבורד מחבר אותו בהפעלה (`grade_edit.connect_stats`, כמו `connect_database`) |
| | `grading` היה צריך את `moodle/claude_driver.py` (כרום, מודל, ההעלאה) רק כדי להריץ את Claude Code | `moodle/claude_code.py` בליבה: למצוא את Claude Code, לבדוק שהוא מחובר, לקרוא תשובה |
| `grading` מושך את ההחזרה למודל | `grade._update_moodle_table` ו-`grade_edit.MoodleTableTarget` ייבאו את `moodle.moodle_table`, וממנו `upload`, `anonymize` ו-`pull_check` (23 קבצים בסקיל) | מחובר כמו `stats`: `grade_edit.connect_moodle_table(moodle_table.build)` ב-`web_server.connect_stores` (2026-11-12). כשהוא מחובר הוא לא optional. `python -m grading` לא מחבר אותו: ההעלאה בונה את הטבלה מחדש, והעלאת הציונים קוראת את הציונים עצמם (`tests/integration/test_moodle_table_after_grading.py`) |
| גישה לפנימיות | `datastore` ו-`stats` השתמשו ב-`grades._rank`, והדשבורד ב-`grading._num` | `grades.rank`, `grading.to_points` (השמות הישנים נשארו בפנים) |
| שמות שנכתבו ביד | `"Upload batch.json"` ב-`datastore/doctor.py`, `"Assignment details.json"` ו-`"Key - number to student.csv"` ב-`schema.py`, `"YallaLinearit"` ו-`"Exercise Checking System"` ב-`shared_folder.py`, `Path.home() / "Downloads"` בשלושה מקומות, קובצי ההעלאה, `Grading usage.jsonl`, קובצי המחוון שהאתר קורא | כולם ב-`moodle/paths.py` (`UPLOAD_BATCH`, `PULL_CHECK`, `USAGE_LOG`, `RUBRIC_*`, `DATA_FOLDER`, `downloads_dir()`...) |
| מודל שנכתב ביד | `claude-opus-5-5` (הבדיקה) ו-`claude-sonnet-5-5` (כרום) | נשארו ברירת מחדל, ו-`GRADING_MODEL` / `MOODLE_MODEL` ב-`.env` דורסים (`settings.get`) |
| בלי README | `datastore/` | `datastore/README.md` |
| בלי "מה נכנס ומה יוצא" | כל ה-README | סעיף `## ממשק` בכל אחד |
| בדיקות שתלויות בחלק שמעליהן | `tests/grading` (הדשבורד, `stats`, `datastore`), `tests/moodle` (שורות הפקודה של `grading` ו-`copying`), `tests/datastore` ו-`tests/stats` (הדשבורד) | הבדיקות של החיבורים עברו ל-`tests/integration/`. לבדיקות של `grading` יש עזר משלהן במקום `dashboard/folder_view` |

בכתובות הישנות (`dashboard/shared_folder.py`, `dashboard/settings.py`, `datastore/atomic.py`, `datastore/schema.py`)
נשארו כינויים, כך שכל ייבוא ישן ממשיך לעבוד ונותן בדיוק את אותו מודול (גם monkeypatch בבדיקות).

## האם כל חלק יכול לצאת לסקיל

"קבצים" = כמה קבצים מהריפו הסקיל ייקח (`python tools/extract_skill.py <חלק> --list`).

| חלק | אחראי על | תלוי ב | קבצים | מוכן לסקיל? | מה עוד נדרש |
|---|---|---|---|---|---|
| `copying/` | חשד להעתקה בין הגשות | הליבה בלבד | 10 | **כן, והוצא בפועל**: הסקיל `copying-check` | כלום |
| `activity_log/` | יומן "מי עשה מה" | הליבה בלבד | 5 | כן, כספרייה | אין לו פעולה משלו (אין CLI): הוא חלק של סקיל אחר, לא סקיל לבד |
| `grading/` | בדיקה עם Claude, בדיקה ידנית, עריכת ציון | הליבה, `activity_log` | 20 | **כן, והוצא בפועל**: הסקיל `exercise-grader` (הגשה אחת, `grading/one_submission.py`), במקום ההעתקה הידנית מ-43b48dc | כלום. `tests/integration/test_grading_skill.py` משווה אותו למערכת: אותן תמונות ל-Claude, ואותו ציון, ניקוד, סימונים ו-PDF מסומן מאותה תשובה |
| `moodle/` (משיכה והחזרה) | משיכה ממודל והחזרה למודל | הליבה (שבתוכו) | 22 | **טכנית כן** (יש CLI, ואין תלות בחלק אחר) | צריך כרום עם Claude in Chrome ומשתמש מחובר למודל. הממשק רחב (כ-50 שמות), כי הדשבורד מנהל בעצמו את זרימת המשיכה וההעלאה. כדי לצמצם: להעביר את הזרימה מ-`dashboard/actions.py` לפונקציות של `moodle` |
| `stats/` | מסד הנתונים הסטטיסטי | הליבה, `grading` | 25 | **כמעט** | הוא צריך את המחוון ואת ההערות דרך `grading.load_context`, שמושך את כל `grading` (ו-PyMuPDF). אפשר להפריד את קריאת המחוון למודול קטן בלי PyMuPDF. הסקיל `stats-db` שבריפו היום קורא דרך `python -m stats`, לא מחוצה לו |
| `datastore/` | בדיקת שלמות ויומן הציונים | הליבה, `grading`, `activity_log` | 25 | **כמעט** | כמו `stats`: המחוון דרך `grading` |
| `dashboard/` | השרת שמרכיב את הכול | כל החלקים | הכול | **לא מועמד** | הוא נקודת ההרכבה: מחבר ל-`grading` את היומן ואת הסטטיסטיקה, ומגיש את ה-API |
| `website/` | האתר | ה-API של הדשבורד (HTTP) | 0 פייתון | עצמאי, אבל אתר ולא סקיל | כלום |
| `onedrive/` | העלאה לוואן דרייב של המרצה | ה-API של הדשבורד, או תיקייה שבוחרים ביד | 0 פייתון | **קרוב**: Claude כבר מריץ אותו ב-Claude in Chrome | `SKILL.md` שאומר איך להריץ את `sync.js`. בלי שרת מקומי: רק דרך בחירת תיקייה ביד |

**אחריות אחת לכל חלק:** כל החלקים עושים דבר אחד, חוץ משניים. `moodle/` מחזיק גם את הליבה וגם את השלבים מול מודל
(הליבה נשארה שם כי `moodle/paths.py` הוא המקום הקבוע לשמות). `dashboard/actions.py` (כ-1,900 שורות) עושה גם חלק
מהלוגיקה של החלקים, למשל שמירת המכוון הרשמי, מצב קובצי המחוון וזרימת המשיכה. אלה המועמדים הבאים לפיצול, אבל הם לא
מונעים הוצאה לסקיל.

## איך מוציאים חלק לסקיל

1. החלק צריך `SKILL.md` משלו ב-`<חלק>/skill/` (ראו `copying/skill/SKILL.md`).
2. `python tools/extract_skill.py <חלק>` בונה את הסקיל ב-`~/.claude/skills/<שם>/`: את `SKILL.md`, ו-`scripts/` עם
   החלק, הקבצים של הליבה שהוא צריך, `run.py` (שמריץ `python -m <חלק>` מהעותק), ו-`MANIFEST.json` (מאיזה commit,
   וה-sha256 של כל קובץ).
3. `python tools/extract_skill.py --stale <תיקיית הסקיל>` אומר אם הסקיל פיגר אחרי הריפו. אם כן, בונים שוב.

הקוד לא מועתק ביד ולא משוכתב. הכלי מסרב לבנות חלק שצריך חלק שמעליו, ו-`tests/integration/test_copying_skill.py`
בונה את `copying-check`, מריץ אותו בלי הריפו (`python -I`, מתיקייה אחרת), ומשווה את התוצאה שלו לתוצאה של המערכת על
אותן הגשות. `tests/integration/test_grading_skill.py` עושה אותו דבר ל-`exercise-grader`.

**`exercise-grader` אצל כל הצוות, לבד.** כל מחשב שמריץ את המערכת בונה אותו מהקוד שלו בכל הפעלה של השרת
(`dashboard/skills.py` → `python tools/extract_skill.py grading --install`), והשרת עולה מחדש אחרי כל עדכון מ-`main`, כך
שכל אחד מקבל את הגרסה שב-`main` בתוך שעה ממיזוג. נבנה רק כשהסקיל חסר או נשאר מאחור (הקוד, `SKILL.md` או
`run.py`). הגרסה הקודמת הייתה העתקה ידנית (`grade_tool.py`) שהופצה כ-ZIP: תיקייה שהכלי לא בנה מועתקת קודם כולה
ל-`%USERPROFILE%\.claude\skill-backups\exercise-grader-<תאריך>` (מחוץ לתיקיית הסקילים, כדי שלא יהיו שני סקילים באותו
שם), ורק אז מוחלפת. `INSTALL_SKILLS=off` ב-`.env` מכבה. למי שאין מערכת במחשב: מכווצים את תיקיית הסקיל שנבנתה
(`exercise-grader\SKILL.md` בתוכו), והוא מתקין אותה עם `scripts/install.ps1` שבתוכה.
