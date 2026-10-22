# website/: האתר

האתר עצמו: HTML, CSS ו-JavaScript, בלי בנייה ובלי ספריות חוץ מ-KaTeX (לנוסחאות). הוא עובד בשתי צורות:

- **הדגמה (ציבורית):** https://matanravitsky-crypto.github.io/assignment-checker/. מתפרסם לבד מ-`main` בכל שינוי בתיקייה הזו, דרך `.github/workflows/website.yml`.
- **מחוברת:** אותם קבצים, דרך השרת המקומי ([`dashboard/`](../dashboard/)). האתר מזהה שהוא רץ ב-`localhost` ואז עובד עם התיקייה האמיתית.

| קובץ | מה הוא |
|---|---|
| `index.html` | המעטפת: ניווט, סרגל עליון, טעינת הסקריפטים |
| `app.js` | כל המסכים: לוח בקרה, משיכה, בדיקה, החזרה, הגדרות. וגם החיבור לשרת המקומי (`runLocalPull`, `runLocalReturn`) |
| `demo-data.js` | נתוני ההדגמה: קורסים, מטלות והגשות לדוגמה |
| `demo-pipeline.js` | הדמיה של שלושת השלבים, לגרסת ההדגמה בלבד |
| `styles.css` | העיצוב, בהיר וכהה, מימין לשמאל |

לבדיקה מקומית בלי השרת המקומי:

```bash
npx http-server website
```
