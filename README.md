# בודק העבודות

מערכת לבדיקה אוטומטית של תרגילי בית במתמטיקה בדידה ובאלגברה לינארית.

יש לה שלושה שלבים:
1. **משיכה:** ההגשות של המטלה נמשכות ממודל, עם פרטי הסטודנטים והקבצים, ישר לתיקיית OneDrive של הקורס.
2. **בדיקה:** כל עבודה נשלחת ל-Claude עם המחוון, הדגשים והפתרון הרשמי. Claude מסמן טעויות, נותן ניקוד לכל שאלה וכותב משוב. *(עוד לא מחובר)*
3. **החזרה:** הציון, המשוב וה-PDF המסומן עולים חזרה למודל. *(עוד לא מחובר)*

## שתי גרסאות של האתר

| | איפה | מה עושה |
|---|---|---|
| **הדגמה** | https://matanravitsky-crypto.github.io/assignment-checker/ | מציגה את המערכת עם נתונים לדוגמה. אפשר לשלוח לכל אחד. |
| **מחוברת** | `http://localhost:8765`, אחרי הפעלת `start.bat` | עובדת עם תיקיית OneDrive האמיתית. "משוך הגשות" מושך באמת. |

## הפעלה (הגרסה המחוברת)

פעם אחת במחשב:
1. **מחברים את OneDrive של האוניברסיטה:** באפליקציית OneDrive (הענן ליד השעון): הגדרות ← חשבון ← הוסף חשבון. מתחברים עם חשבון האוניברסיטה.
2. **מוסיפים את תיקיית הקורס:** בדפדפן, על התיקייה `YallaLinearit`, לוחצים **Add shortcut to My files**. אחרי דקה היא מופיעה במחשב.
3. **מתקינים Python** 3.10 ומעלה, מ-https://www.python.org/downloads/ (אם עוד לא מותקן).

בכל פעם: לוחצים פעמיים על **`start.bat`**. האתר נפתח מחובר לתיקייה. בהפעלה הראשונה ההתקנה לוקחת כדקה.

## איך מכניסים הגשות

- **עם טוקן של מודל (אוטומטי לגמרי):** לוחצים "משוך הגשות". המערכת מביאה ממודל את רשימת המטלות, יוצרת תיקייה לכל אחת ומושכת את ההגשות. בשביל זה צריך טוקן (ראו בהמשך).
- **בלי טוקן:** במודל, במטלה: "הצגת כל ההגשות" ← "הורדת כל ההגשות". שמים את קובץ ה-ZIP בתיקייה `YallaLinearit/0-קליטה` ולוחצים "משוך הגשות". המערכת מזהה לפי שם הקובץ לאיזו מטלה הוא שייך.

הגשה שלא השתנתה לא נכתבת שוב. סטודנט שהגיש מחדש אחרי שכבר נבדק חוזר ל"ממתינה לבדיקה", עם הערה.

## איך התיקייה מאורגנת

המערכת יוצרת את המבנה לבד. אם בתוך `YallaLinearit` יש תיקייה בשם `מערכת בדיקת תרגילים`, המערכת עובדת רק בתוכה ולא נוגעת בשאר הקבצים של המרצה:

```
YallaLinearit/
  איך זה עובד.txt        הסבר לכל מי שנכנס לתיקייה
  הגדרות.json            קורסים, מטלות ומזהים במודל (בלי סיסמאות)
  0-קליטה/               קובצי ZIP ממודל, לכל מטלה
  <קורס>/
    <מטלה>/
      0-קליטה/           ZIP של המטלה הזו. אחרי הקליטה עוברים ל-"נקלטו"
      1-הגשות/           תיקייה לכל סטודנט: "<שם> (<מזהה במודל>)"
      2-נבדקו/           PDF מסומן אחרי הבדיקה
      3-הוחזרו/          מה שכבר עלה חזרה למודל
      ציונים.xlsx        שורה לכל סטודנט
      יומן.txt           כל פעולה, עם תאריך ושעה
```

**`ציונים.xlsx`** הוא המקום שבו הצוות עובד. פותחים אותו ב-Excel Online (כמה אנשים יכולים לערוך יחד) ומעדכנים את העמודות ש1, ש2..., ציון, משוב ומאושר. המערכת לא דורסת את העמודות האלה. עדיף לא לערוך את הקובץ בזמן שמושכים הגשות.

## הגדרות

**`הגדרות.json`** נמצא בתיקיית OneDrive ומשותף לצוות. כדי שהמשיכה ממודל תהיה אוטומטית, מוסיפים לקורס את `moodle_course_id`, המספר שמופיע בכתובת של הקורס במודל (`course/view.php?id=12345`):

```json
{
  "moodle_url": "https://moodle.bgu.ac.il",
  "courses": [
    { "name": "אלגברה לינארית 1", "moodle_course_id": 12345, "assignments": [] }
  ]
}
```

**`.env`** נמצא בתיקיית הריפו במחשב בלבד. הוא לא עולה ל-GitHub ולא ל-OneDrive:

```
MOODLE_TOKEN=...
ANTHROPIC_API_KEY=...
```

את הטוקן של מודל מבקשים מהמרצה, או ממחלקת המחשוב, עבור משתמש עם הרשאת בודק בקורס. סטודנט רגיל לא יכול לקבל גישה להגשות של אחרים.

## מבנה הקוד

| קובץ | מה הוא עושה |
|---|---|
| `start.bat` | הפעלה בלחיצה כפולה |
| `pipeline/config.py` | איפה תיקיית OneDrive ואיך קוראים לתיקיות |
| `pipeline/settings.py` | `הגדרות.json` ו-`.env` |
| `pipeline/moodle_api.py` | משיכה ממודל עם טוקן |
| `pipeline/moodle_zip.py` | קריאת ZIP של "הורדת כל ההגשות" |
| `pipeline/pull.py` | קליטת הגשות, בדיקת תקינות ועדכון טבלת הציונים |
| `pipeline/gradebook.py` | `ציונים.xlsx` |
| `pipeline/service.py` | הפעולות של המערכת, לאתר ולשורת הפקודה |
| `pipeline/server.py` | השרת המקומי שמחבר את האתר לתיקייה |
| `pipeline/demo.py` | הגשות לדוגמה בפורמט של מודל |
| `docs/` | האתר: `app.js` (המסכים), `data.js` (נתוני ההדגמה), `api.js` (הדמיית השלבים בגרסת ההדגמה) |
| `tests/` | בדיקות אוטומטיות |

## פקודות שימושיות

```bash
python -m pipeline where
```
מראה איפה נמצאת תיקיית הקורס במחשב.

```bash
python -m pipeline pull "אלגברה לינארית 1" "תרגיל בית 1"
```
מושך הגשות בלי האתר.

```bash
python -m pipeline demo
```
יוצר קורס "הדגמה" עם הגשות לדוגמה. כדאי להריץ את זה כדי לראות איך הכל עובד.

```bash
python -m pytest
```
מריץ את הבדיקות.

## Browser download and numbered submissions (`moodle/`)

Without a Moodle token, Claude in Chrome does the clicking and these scripts do the rest. Student files never enter this repo (it is public). They live in `Exercise Checking System`, a folder per course and per assignment with plain English names, shared through the lecturer's OneDrive; see `moodle/paths.py` and `CLAUDE.md`.

Needs Python 3.10+ and 7-Zip (`winget install 7zip.7zip`).

**In** — after the due date, in the assignment's Submissions page: Actions → *Download all submissions*, then:

```bash
python -m moodle ingest <assignment id> --course "Linear Algebra" --name "Assignment 0 - Sets and Complex Numbers"
```

(`--course` and `--name` only the first time.) It takes the newest `…-<assignment id>.zip` from Downloads into `<course>/<assignment name>/`, keeps the ZIP there, and writes `1 - Submissions to grade/0001.pdf …` for grading plus the key table `Key - number to student.csv` (number → Moodle participant id). On a later download every student keeps their number, and students who submitted since then get the next numbers.

**Out** — grading writes `Grades.csv` (`number,grade,feedback`) and `2 - Graded with comments/0001.pdf …`; download the grading worksheet from Moodle, then:

```bash
python -m moodle upload <assignment id>
```

It fills `3 - Ready to upload to Moodle/` with `Grades for Moodle worksheet.csv` (Actions → *Upload grading worksheet*), `Graded - part 01.zip …` (Actions → *Upload multiple feedback files in a zip*; each under Moodle's 31 MB limit) and `Upload steps.txt`, the steps for whoever uploads. Grades are matched by number, never by row order.

**Check** — `python -m moodle status <assignment id>` shows what's done and flags file names OneDrive would refuse. `python -m moodle guide` rewrites the `README.txt` files (in Hebrew).

One person downloads and uploads, so there is one key table per assignment; the team works from the shared folder.

`CLAUDE.md` has the full picture for working on this with Claude.

Tests for this part:

```bash
python test_main.py
python test_anonymize.py
python test_ingest.py
python test_upload.py
python test_status.py
python test_guide.py
```
