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
1. **מסנכרנים את תיקיית הקורס:** בדפדפן, בתוך התיקייה `YallaLinearit`, לוחצים **Sync** ומתחברים עם חשבון האוניברסיטה. התיקייה מופיעה במחשב, למשל `C:\Users\<שם>\BGU\נדב מאיר - YallaLinearit`.
2. **מתקינים Python** 3.10 ומעלה, מ-https://www.python.org/downloads/ (אם עוד לא מותקן).

בכל פעם: לוחצים פעמיים על **`start.bat`**. האתר נפתח מחובר לתיקייה. בהפעלה הראשונה ההתקנה לוקחת כדקה.

## איך התיקייה מאורגנת

המערכת עובדת רק בתוך `YallaLinearit/Exercise Checking System`, במבנה שאורי הגדיר. בשאר התיקייה של המרצה היא לא נוגעת.

```
Exercise Checking System/
  README.txt                          הכללים של הצוות
  Linear Algebra/                     תיקייה לכל קורס
    README.txt                        רשימת המטלות (המערכת מעדכנת את מספר ההגשות)
    Assignment 0 - .../               תיקייה לכל מטלה
      Assignment details.json         מזהה במודל, מזהה קורס, מועד הגשה, שאלות, שם בעברית
      Key - number to student.csv     טבלת המפתח: מספר ↔ סטודנט. השמות נמצאים רק כאן
      0 - Moodle download/            לכאן שמים ZIP של "הורדת כל ההגשות" ממודל
      1 - Submissions to grade/       0001.pdf, 0002.pdf... ממוספרות, בלי שמות
      2 - Graded with comments/       אותו מספר, עם ההערות (שלב הבדיקה)
      3 - Ready to upload to Moodle/  מה שמוכן להעלאה (שלב ההחזרה)
      System log.txt                  מה המערכת עשתה ומתי, בלי שמות
```

## איך מכניסים הגשות

לפי הכללים של הצוות, רק אחד מוריד ממודל ומעלה למודל, כדי שתהיה טבלת מפתח אחת לכל מטלה.

- **בלי טוקן:** במודל, במטלה: "הצגת כל ההגשות" ← "הורדת כל ההגשות". שמים את ה-ZIP בתיקייה `0 - Moodle download` של המטלה, ולוחצים באתר "משוך הגשות".
- **עם טוקן של מודל:** "משוך הגשות" מושך ישר ממודל, ומטלה חדשה במודל מקבלת תיקייה לבד.

מה קורה בכל משיכה:
- כל הקבצים של סטודנט מאוחדים ל-PDF אחד.
- סטודנט שכבר יש לו מספר שומר עליו, וסטודנט חדש מקבל את המספר הבא.
- הגשה שלא השתנתה לא נכתבת שוב. הגשה מחדש של עבודה שכבר נבדקה מסומנת.
- קובץ ריק או פגום לא מקבל מספר, ומדווח לפי מזהה המשתתף, בלי שם.

המערכת קוראת ZIP רק מתיקיית `0 - Moodle download`. ZIP שנמצא במקום אחר, למשל ההורדה המקורית בתיקיית המטלה, לא נקרא ולא זז. אחרי הקליטה ה-ZIP עובר ל-`0 - Moodle download/Imported`.

לטבלת המפתח נוספת עמודה אחת בסוף, `content_hash`, מזהה של תוכן הקובץ. בזכותה, במשיכה הבאה לא צריך להוריד מהענן את כל הקבצים רק כדי להשוות.

**פרטיות:** האתר מציג רק מספרי הגשות. השרת המקומי שולח לדפדפן רק קובצי PDF מתיקיות 1-2-3, ואת טבלת המפתח אי אפשר לפתוח דרכו. ושוב, כמו בכללים של הצוות: לא מעתיקים קבצים מהתיקייה ל-GitHub, כי הריפו ציבורי.

## הגדרות

הפרטים של כל מטלה (המזהה במודל, מזהה הקורס, מועד ההגשה והשאלות) נמצאים ב-`Assignment details.json` שלה.

**`.env`** נמצא בתיקיית הריפו במחשב בלבד. הוא לא עולה ל-GitHub ולא ל-OneDrive:

```
MOODLE_TOKEN=...
ANTHROPIC_API_KEY=...
```

את הטוקן של מודל מבקשים מהמרצה, או ממחלקת המחשוב, עבור משתמש עם הרשאת בודק בקורס.

## מבנה הקוד

| קובץ | מה הוא עושה |
|---|---|
| `start.bat` | הפעלה בלחיצה כפולה |
| `pipeline/config.py` | איפה נמצאת התיקייה `Exercise Checking System` |
| `pipeline/team.py` | המבנה של הצוות: מטלות, טבלת מפתח, תיקיות 1-2-3 |
| `pipeline/settings.py` | `.env`: טוקן מודל ומפתח Claude |
| `pipeline/moodle_api.py` | משיכה ממודל עם טוקן |
| `pipeline/moodle_zip.py` | קריאת ZIP של "הורדת כל ההגשות", סטודנט אחד בכל פעם |
| `pipeline/pull.py` | מספור, איחוד ל-PDF אחד ועדכון טבלת המפתח |
| `pipeline/service.py` | הפעולות של המערכת, לאתר ולשורת הפקודה |
| `pipeline/server.py` | השרת המקומי שמחבר את האתר לתיקייה |
| `pipeline/demo.py` | הגשות לדוגמה בפורמט של מודל, לבדיקות |
| `docs/` | האתר: `app.js` (המסכים), `data.js` (נתוני ההדגמה), `api.js` (הדמיית השלבים בגרסת ההדגמה) |
| `tests/` | בדיקות אוטומטיות |

## פקודות שימושיות

```bash
python -m pipeline where
```
מראה איפה נמצאת תיקיית המערכת במחשב.

```bash
python -m pipeline list
```
מציג את הקורסים, המטלות ומספר ההגשות.

```bash
python -m pipeline pull "Linear Algebra" "Assignment 0 - Sets and Complex Numbers"
```
מושך הגשות בלי האתר. מקבל את שמות התיקיות.

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
