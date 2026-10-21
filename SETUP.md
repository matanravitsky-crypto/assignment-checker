# הקמת המסד המשותף (Supabase)

הקוד כבר מוכן: הסכמה של המסד, ההרשאות, ההתחברות עם GitHub והסנכרון החי.
נשארו כמה צעדים שרק בעל החשבון יכול לעשות. בסך הכל בערך 10 דקות.

עד שהצעדים האלה יושלמו, האתר ממשיך לעבוד במצב הדגמה, כמו היום.

## 1. פתיחת פרויקט ב-Supabase

1. נכנסים ל-https://supabase.com ולוחצים **Start your project**, ואז **Continue with GitHub**.
2. **New project**:
   - Name: `assignment-checker`
   - Database password: ממציאים סיסמה ושומרים אותה אצלכם. לא צריך לשלוח אותה לאף אחד.
   - Region: **Central EU (Frankfurt)**, הכי קרוב לישראל.
   - Plan: **Free**.
3. מחכים דקה-שתיים עד שהפרויקט מוכן.

## 2. יצירת הטבלאות וההרשאות

1. בתפריט של Supabase: **SQL Editor**, ואז **New query**.
2. מעתיקים את כל התוכן של הקובץ [`supabase/schema.sql`](supabase/schema.sql), מדביקים ולוחצים **Run**.
3. אמור להופיע `Success. No rows returned`.

הקובץ יוצר את הטבלאות, מגדיר שרק חברי הצוות יכולים לקרוא ולכתוב, ומכניס את חברי הצוות שכבר אישרו את ההזמנה בריפו.
אפשר להריץ אותו שוב בלי חשש, הוא לא מוחק נתונים.

## 3. התחברות עם GitHub

1. ב-Supabase: **Authentication**, ואז **Sign In / Providers**, ואז **GitHub**. מעתיקים משם את ה-**Callback URL**.
   הוא נראה בערך כך: `https://abcd1234.supabase.co/auth/v1/callback`
2. בלשונית חדשה: https://github.com/settings/developers, ואז **OAuth Apps** ו-**New OAuth App**:
   - Application name: `בודק העבודות`
   - Homepage URL: `https://matanravitsky-crypto.github.io/assignment-checker/`
   - Authorization callback URL: ה-Callback URL שהעתקתם מ-Supabase
3. לוחצים **Register application**, מעתיקים את ה-**Client ID**, לוחצים **Generate a new client secret** ומעתיקים גם אותו.
4. חוזרים ל-Supabase, למסך של GitHub: מפעילים את **Enable**, מדביקים את ה-Client ID וה-Client Secret ולוחצים **Save**.

## 4. כתובות מורשות

ב-Supabase: **Authentication**, ואז **URL Configuration**:

- Site URL: `https://matanravitsky-crypto.github.io/assignment-checker/`
- Redirect URLs, מוסיפים את שתי הכתובות:
  - `https://matanravitsky-crypto.github.io/assignment-checker/**`
  - `http://localhost:5173/**`

## 5. חיבור האתר למסד

ב-Supabase: **Project Settings**, ואז **API Keys** (או **Data API**). צריך שני ערכים:

- **Project URL**, למשל `https://abcd1234.supabase.co`
- **Publishable key** (מתחיל ב-`sb_publishable_`), או במקומו ה-**anon public key** הישן

שולחים את שניהם, ואני אכניס אותם ל-[`docs/config.js`](docs/config.js) ואדחוף. אפשר גם לעשות את זה לבד: למלא בקובץ ולדחוף ל-`main`.

שני הערכים האלה ציבוריים בכוונה, ומותר שיופיעו בקוד. מה שמגן על הנתונים הן ההרשאות שבמסד.
**לא לשלוח ולא לשים בריפו**: את ה-`service_role` / `secret` key ואת סיסמת המסד.

## 6. כניסה ראשונה

1. נכנסים לאתר ולוחצים **התחברות עם GitHub**.
2. המסד ריק בהתחלה. לוחצים **טען נתוני דוגמה למסד**.
3. מעכשיו כל חברי הצוות שמתחברים רואים את אותם נתונים, וכל שינוי מגיע לכולם מיד.

## מי מקבל גישה

- רק משתמשי GitHub שברשימת הצוות. הרשימה מופיעה בדף **חיבורים והגדרות** באתר.
- מנהל מוסיף ומסיר חברי צוות מאותו דף, לפי שם המשתמש שלהם ב-GitHub.
- מי שמתחבר ולא ברשימה רואה הודעה שהוא עוד לא נוסף, ורק נתוני הדגמה.
- מי שנכנס בלי להתחבר רואה את נתוני ההדגמה, כמו היום.
