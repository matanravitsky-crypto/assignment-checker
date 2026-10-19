// נתוני דמו לשלד. בהמשך יוחלפו בקריאות ל-API של מערכת האוניברסיטה ושל השרת שלנו.
window.DEMO = (() => {
  const courses = [
    { id: "cs101-hw3", course: "מבוא למדעי המחשב", code: "202-1-1011", assignment: "תרגיל בית 3: רקורסיה", due: "2026-10-16T23:59" },
    { id: "ds-hw2", course: "מבני נתונים", code: "202-1-1031", assignment: "תרגיל בית 2: עצי חיפוש", due: "2026-10-21T23:59" },
    { id: "algo-hw1", course: "אלגוריתמים", code: "202-1-2041", assignment: "תרגיל בית 1: תכנון דינמי", due: "2026-10-26T23:59" },
  ];

  const names = [
    "נועה כהן", "איתי לוי", "מאיה מזרחי", "יונתן פרץ", "שירה ביטון", "עומר אברהם",
    "תמר פרידמן", "אלון דהן", "רוני אזולאי", "דניאל שפירא", "הילה גבאי", "אורי קליין",
    "ליאור חדד", "יעל רוזנברג", "אביב סויסה", "גל אוחיון", "עדי ברק", "נדב טל",
    "מיכל אשכנזי", "רועי וקנין", "שקד יוסף", "אסף נחום", "טליה בן דוד", "עידו שמעוני",
  ];

  // מצבים: received, grading, review, returned, error
  const plan = [
    "review", "returned", "review", "grading", "returned", "review", "received", "returned",
    "review", "error", "returned", "grading", "review", "returned", "received", "review",
    "returned", "review", "received", "returned", "review", "returned", "received", "review",
  ];
  const scores = [86, 92, 71, null, 98, 64, null, 88, 79, null, 95, null, 58, 83, null, 90, 77, 81, null, 94, 69, 87, null, 74];
  const flagsFor = { 5: ["חשד להעתקה"], 12: ["ציון נמוך"], 9: ["קובץ לא נפתח"], 20: ["הגשה באיחור"] };

  const pad = (n) => String(n).padStart(2, "0");
  const submissions = names.map((name, i) => {
    const day = 14 + (i % 3);
    const hour = 9 + ((i * 7) % 14);
    return {
      id: `S-${1040 + i}`,
      name,
      studentId: String(203000000 + ((i * 7919) % 900000)).padStart(9, "0"),
      email: `student${i + 1}@post.bgu.ac.il`,
      courseId: "cs101-hw3",
      submittedAt: `2026-10-${pad(day)}T${pad(hour)}:${pad((i * 13) % 60)}`,
      file: i % 4 === 0 ? "hw3.zip" : "hw3.py",
      status: plan[i],
      score: scores[i],
      flags: flagsFor[i] || [],
      late: i === 20,
    };
  });

  const rubric = {
    courseId: "cs101-hw3",
    criteria: [
      { key: "correct", name: "נכונות", weight: 40, desc: "הפונקציות מחזירות תוצאה נכונה לכל הקלטים, כולל מקרי קצה." },
      { key: "recursion", name: "שימוש ברקורסיה", weight: 25, desc: "הפתרון רקורסיבי, עם תנאי עצירה ברור. אין לולאות." },
      { key: "style", name: "קריאות ותיעוד", weight: 20, desc: "שמות משתנים משמעותיים, docstring לכל פונקציה." },
      { key: "tests", name: "בדיקות", weight: 15, desc: "לפחות שלוש בדיקות לכל פונקציה." },
    ],
    emphases: [
      "אין להשתמש בלולאות for או while בשאלות 1–3.",
      "להוריד 5 נקודות על פונקציה בלי docstring, עד 10 נקודות לכל היותר.",
      "הגשה באיחור: מינוס 2 נקודות לכל יום.",
      "הערות בעברית, בגוף שני, בטון מעודד.",
    ],
  };

  // עבודה לדוגמה עם הערות בעט אדום (מוצגת בכל פתיחה של עבודה)
  const sampleCode = [
    { n: 1, code: 'def factorial(n):' },
    { n: 2, code: '    if n == 0:', },
    { n: 3, code: '        return 1' },
    { n: 4, code: '    return n * factorial(n - 1)', },
    { n: 5, code: '' },
    { n: 6, code: 'def sum_digits(x):', mark: "חסר docstring. מינוס 5 לפי הדגשים." },
    { n: 7, code: '    total = 0' },
    { n: 8, code: '    while x > 0:', mark: "לולאה במקום רקורסיה. השאלה דורשת פתרון רקורסיבי." },
    { n: 9, code: '        total += x % 10' },
    { n: 10, code: '        x //= 10' },
    { n: 11, code: '    return total' },
    { n: 12, code: '' },
    { n: 13, code: 'def power(base, exp):' },
    { n: 14, code: '    """Return base raised to the power of exp."""' },
    { n: 15, code: '    if exp == 0:' },
    { n: 16, code: '        return 1' },
    { n: 17, code: '    return base * power(base, exp - 1)', mark: "עובד, אבל לא מטפל במעריך שלילי. מה יקרה עבור `power(2, -1)`?" },
  ];

  const breakdown = { correct: 34, recursion: 17, style: 15, tests: 13 };

  const feedback =
    "עבודה טובה ומסודרת. factorial ו-power כתובות נכון ובצורה רקורסיבית נקייה. " +
    "ב-sum_digits השתמשת בלולאת while, ולכן לא עמדת בדרישת הרקורסיה בשאלה 2. שווה לחשוב: מה הספרה האחרונה, ומה נשאר אחריה? " +
    "כדאי גם להוסיף docstring לכל פונקציה ולבדוק את power עם מעריך שלילי.";

  const runs = [
    { at: "2026-10-19T08:42", kind: "pull", text: "נמשכו 6 הגשות חדשות ממערכת האוניברסיטה", course: "מבוא למדעי המחשב" },
    { at: "2026-10-19T08:44", kind: "grade", text: "Claude סיים לבדוק 9 עבודות. ציון ממוצע 82", course: "מבוא למדעי המחשב" },
    { at: "2026-10-19T08:45", kind: "error", text: "S-1049: הקובץ hw3.zip לא נפתח. נדרשת בדיקה ידנית", course: "מבוא למדעי המחשב" },
    { at: "2026-10-19T09:10", kind: "return", text: "הוחזרו 8 ציונים והערות לאתר האוניברסיטה", course: "מבוא למדעי המחשב" },
    { at: "2026-10-18T21:03", kind: "pull", text: "נמשכו 14 הגשות חדשות ממערכת האוניברסיטה", course: "מבוא למדעי המחשב" },
    { at: "2026-10-18T21:09", kind: "grade", text: "Claude סיים לבדוק 14 עבודות. ציון ממוצע 79", course: "מבוא למדעי המחשב" },
  ];

  return { courses, submissions, rubric, sampleCode, breakdown, feedback, runs };
})();
