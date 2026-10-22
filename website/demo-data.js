// נתוני ההדגמה של האתר הציבורי (GitHub Pages). בגרסה המחוברת (start.bat) הנתונים מגיעים מהתיקייה המשותפת.
window.DEMO = (() => {
  // מחולל מספרים קבוע לכל מטלה, כדי שהדמו ייראה אותו דבר בכל טעינה
  const hash = (s) => { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };
  const rng = (seed) => { let x = seed || 1; return () => { x ^= x << 13; x >>>= 0; x ^= x >> 17; x ^= x << 5; x >>>= 0; return x / 4294967296; }; };
  const shuffle = (arr, r) => { const a = [...arr]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const H = 3600e3;

  const courses = [
    { id: "la", name: "אלגברה לינארית 1" },
    { id: "dm", name: "מתמטיקה בדידה" },
  ];

  const NAMES = [
    "נועה כהן", "איתי לוי", "מאיה מזרחי", "יונתן פרץ", "שירה ביטון", "עומר אברהם", "תמר פרידמן", "אלון דהן",
    "רוני אזולאי", "דניאל שפירא", "הילה גבאי", "אורי קליין", "ליאור חדד", "יעל רוזנברג", "אביב סויסה", "גל אוחיון",
    "עדי ברק", "נדב טל", "מיכל אשכנזי", "רועי וקנין", "שקד יוסף", "אסף נחום", "טליה בן דוד", "עידו שמעוני",
    "רותם שגיא", "אלה כספי", "בן ממן", "ספיר נגר", "יואב רז", "מור לנדאו", "עמית גולן", "הדר אלמוג", "נוי פלד", "אריאל סלע",
  ];

  // מבנה הניקוד של כל תרגיל בית: ארבע שאלות, 100 נקודות
  const rubrics = {
    la: {
      questions: [
        { n: 1, pts: 25, req: "דירוג המטריצה עם כל שלבי פעולות השורה, וחישוב הדרגה." },
        { n: 2, pts: 25, req: "הוכחה מלאה, כולל נימוק לכך שהדטרמיננטה שונה מאפס." },
        { n: 3, pts: 30, req: "קביעה אם הקבוצה בלתי תלויה לינארית, עם פתרון המערכת ונימוק." },
        { n: 4, pts: 20, req: "חישוב הפולינום האופייני ומציאת כל הערכים העצמיים." },
      ],
      emphases: [
        "טענה בלי נימוק לא מקבלת ניקוד.",
        "טעות חישוב שלא משנה את הרעיון: עד 2 נקודות הורדה.",
        "פתרון נכון בדרך אחרת מהפתרון הרשמי מקבל ניקוד מלא.",
        "הגשה באיחור: 5 נקודות הורדה לכל יום.",
      ],
      mistakes: [
        { text: "חילקו בדטרמיננטה בלי לנמק שהיא שונה מאפס", pct: 0.34 },
        { text: "קבעו אי-תלות לינארית בלי לפתור את המערכת עד הסוף", pct: 0.27 },
        { text: "טעויות חשבון בדירוג המטריצה", pct: 0.19 },
        { text: "מצאו רק חלק מהערכים העצמיים", pct: 0.12 },
      ],
    },
    dm: {
      questions: [
        { n: 1, pts: 25, req: "הוכחה באינדוקציה: בסיס, הנחת האינדוקציה וצעד." },
        { n: 2, pts: 25, req: "ספירה נכונה עם הסבר של שיטת הספירה." },
        { n: 3, pts: 25, req: "הגדרת השובכים והיונים, ושימוש נכון בעקרון שובך היונים." },
        { n: 4, pts: 25, req: "בדיקה של שלוש התכונות: רפלקסיביות, סימטריות וטרנזיטיביות." },
      ],
      emphases: [
        "הוכחה באינדוקציה בלי בסיס: 4 נקודות הורדה.",
        "תשובה מספרית בלי הסבר מקבלת חצי מהניקוד.",
        "פתרון נכון בדרך אחרת מהפתרון הרשמי מקבל ניקוד מלא.",
        "הגשה באיחור: 5 נקודות הורדה לכל יום.",
      ],
      mistakes: [
        { text: "הוכחה באינדוקציה בלי בסיס", pct: 0.31 },
        { text: "לא בדקו טרנזיטיביות של היחס", pct: 0.26 },
        { text: "ספרו סידורים במקום צירופים", pct: 0.2 },
        { text: "מסקנה הפוכה מעקרון שובך היונים", pct: 0.1 },
      ],
    },
  };

  // עבודה לדוגמה לכל קורס. לכל שאלה: שורות משותפות, סיום נכון (ok) וסיום עם טעות (bad) + הערת הבודק.
  const samples = {
    la: [
      {
        prompt: "מצאו את הדרגה של המטריצה $A$.",
        lines: [
          "$$A=\\begin{pmatrix}1&2&3\\\\2&4&6\\\\1&0&1\\end{pmatrix}$$",
          "נבצע את פעולות השורה $R_2 \\to R_2-2R_1$ וגם $R_3 \\to R_3-R_1$:",
          "$$\\begin{pmatrix}1&2&3\\\\0&0&0\\\\0&-2&-2\\end{pmatrix}$$",
        ],
        ok: ["נשארו שתי שורות שאינן אפס, ולכן $\\operatorname{rank}(A)=2$."],
        bad: ["יש שורת אפסים, ולכן $\\operatorname{rank}(A)=1$."],
        note: "נשארו שתי שורות שאינן אפס, ולכן הדרגה היא 2.",
        fb: "בשאלה 1 הדרגה היא 2: אחרי הדירוג נשארות שתי שורות שאינן אפס.",
      },
      {
        prompt: "הוכיחו: אם $A$ הפיכה אז $\\det(A^{-1})=\\frac{1}{\\det A}$.",
        lines: [
          "מתקיים $AA^{-1}=I$, ולכן לפי כפליות הדטרמיננטה:",
          "$$\\det(A)\\cdot\\det(A^{-1})=\\det(I)=1$$",
        ],
        ok: ["$A$ הפיכה ולכן $\\det A\\neq 0$, ומותר לחלק: $\\det(A^{-1})=\\frac{1}{\\det A}$. $\\blacksquare$"],
        bad: ["נחלק את שני האגפים בדטרמיננטה ונקבל $\\det(A^{-1})=\\frac{1}{\\det A}$. $\\blacksquare$"],
        note: "לפני החלוקה צריך לנמק למה $\\det A \\neq 0$.",
        fb: "בשאלה 2 חסר נימוק לכך ש-det A שונה מאפס לפני החלוקה.",
      },
      {
        prompt: "האם $v_1=(1,1,0)$, $v_2=(0,1,1)$, $v_3=(1,2,1)$ בלתי תלויים לינארית?",
        lines: [
          "נבדוק מתי $\\alpha v_1+\\beta v_2+\\gamma v_3=0$:",
          "$$\\begin{cases}\\alpha+\\gamma=0\\\\ \\alpha+\\beta+2\\gamma=0\\\\ \\beta+\\gamma=0\\end{cases}$$",
        ],
        ok: ["יש פתרון לא טריוויאלי $\\alpha=\\beta=1,\\ \\gamma=-1$, כלומר $v_3=v_1+v_2$. הקבוצה תלויה לינארית."],
        bad: ["מהמשוואה הראשונה $\\alpha=-\\gamma$, ולכן הפתרון היחיד הוא $\\alpha=\\beta=\\gamma=0$. הקבוצה בלתי תלויה."],
        note: "המערכת לא מחייבת $\\gamma=0$. למשל $v_3=v_1+v_2$, ולכן הקבוצה תלויה.",
        fb: "בשאלה 3 הקבוצה תלויה לינארית, כי v3 = v1 + v2. כדאי לפתור את המערכת עד הסוף לפני המסקנה.",
      },
      {
        prompt: "מצאו את הערכים העצמיים של $B=\\begin{pmatrix}2&1\\\\1&2\\end{pmatrix}$.",
        lines: ["$$\\det(B-\\lambda I)=(2-\\lambda)^2-1=0$$"],
        ok: ["$$2-\\lambda=\\pm1 \\;\\Rightarrow\\; \\lambda_1=1,\\ \\lambda_2=3$$"],
        bad: ["$$2-\\lambda=1 \\;\\Rightarrow\\; \\lambda=1$$"],
        note: "חסר הפתרון $2-\\lambda=-1$, כלומר $\\lambda=3$.",
        fb: "בשאלה 4 חסר הערך העצמי 3, מהמקרה 2 − λ = −1.",
      },
    ],
    dm: [
      {
        prompt: "הוכיחו באינדוקציה: $\\sum_{i=1}^{n} i=\\frac{n(n+1)}{2}$ לכל $n\\ge1$.",
        lines: [
          "הנחת האינדוקציה: נניח שהטענה נכונה עבור $n$.",
          "$$\\sum_{i=1}^{n+1} i=\\frac{n(n+1)}{2}+(n+1)=\\frac{(n+1)(n+2)}{2}$$",
        ],
        ok: ["בסיס: עבור $n=1$ מתקיים $1=\\frac{1\\cdot 2}{2}$. לכן הטענה נכונה לכל $n$. $\\blacksquare$"],
        bad: ["לכן הטענה נכונה לכל $n$. $\\blacksquare$"],
        note: "חסר בסיס האינדוקציה: צריך לבדוק את $n=1$.",
        fb: "בשאלה 1 חסר בסיס האינדוקציה. בלי בדיקה של n = 1 ההוכחה לא שלמה.",
      },
      {
        prompt: "כמה מחרוזות בינאריות באורך 8 יש בהן בדיוק שלוש פעמים 1?",
        lines: ["צריך לבחור 3 מקומות מתוך 8 שבהם יופיע 1. בשאר יופיע 0."],
        ok: ["$$\\binom{8}{3}=\\frac{8!}{3!\\,5!}=56$$"],
        bad: ["$$8\\cdot 7\\cdot 6=336$$"],
        note: "הסדר בין המקומות לא משנה, ולכן צריך לחלק במספר הסידורים $3!$. התשובה $\\binom{8}{3}=56$.",
        fb: "בשאלה 2 ספרתם סידורים במקום צירופים. התשובה הנכונה היא C(8,3) = 56.",
      },
      {
        prompt: "הוכיחו שבכל קבוצה של 13 אנשים יש שניים שנולדו באותו חודש.",
        lines: ["השובכים הם 12 החודשים, והיונים הם 13 האנשים."],
        ok: ["$13>12$, ולכן לפי עקרון שובך היונים יש חודש שבו נולדו לפחות שניים. $\\blacksquare$"],
        bad: ["יש 13 אנשים ו-12 חודשים, ולכן בכל חודש נולד לפחות אדם אחד. $\\blacksquare$"],
        note: "זו לא המסקנה של עקרון שובך היונים. צריך להראות שיש חודש עם לפחות שני אנשים.",
        fb: "בשאלה 3 המסקנה הפוכה: עקרון שובך היונים מבטיח חודש עם לפחות שני אנשים.",
      },
      {
        prompt: "האם היחס $a\\,R\\,b \\iff 2 \\mid (a-b)$ על $\\mathbb{Z}$ הוא יחס שקילות?",
        lines: [
          "רפלקסיביות: $a-a=0$ זוגי.",
          "סימטריות: אם $a-b$ זוגי אז גם $b-a=-(a-b)$ זוגי.",
        ],
        ok: ["טרנזיטיביות: $a-c=(a-b)+(b-c)$ הוא סכום של זוגיים ולכן זוגי. זהו יחס שקילות."],
        bad: ["לכן זהו יחס שקילות."],
        note: "חסרה בדיקת טרנזיטיביות: $a-c=(a-b)+(b-c)$.",
        fb: "בשאלה 4 חסרה בדיקת טרנזיטיביות, שהיא חלק מההגדרה של יחס שקילות.",
      },
    ],
  };

  // הנחיות ברירת מחדל לכל שלב. המשתמש עורך אותן במסך, והן יישלחו לצד השרת.
  const instructions = {
    pull: [
      "1. להתחבר למודל עם חשבון הבודק של הקורס.",
      "2. לבחור את הקורס ואת המטלה שנבחרו למעלה במסך.",
      "3. למשוך רק הגשות במצב \"הוגש לציון\". טיוטות לא נמשכות.",
      "4. לכל הגשה לשמור: שם מלא, תעודת זהות, מייל, זמן הגשה וכל הקבצים.",
      "5. לבדוק שכל קובץ נפתח, שהוא PDF או תמונה, ושיש בו לפחות עמוד אחד.",
      "6. תמונות של דפים סרוקים לאחד לקובץ PDF אחד, לפי סדר העמודים.",
      "7. הגשה באיחור לסמן, אבל לא לדלג עליה.",
    ].join("\n"),
    grade: [
      "לבדוק כל שאלה בנפרד, לפי המחוון ולפי הפתרון הרשמי.",
      "פתרון נכון בדרך אחרת מקבל ניקוד מלא.",
      "טענה בלי הוכחה או נימוק לא מקבלת ניקוד.",
      "לסמן על גבי העבודה את המקום המדויק של כל טעות, ולכתוב לידו הערה קצרה.",
      "אם כתב היד לא קריא או שהביטחון בציון נמוך, לסמן את העבודה לבדיקה ידנית.",
      "משוב בעברית, בגוף שני רבים, ענייני ומעודד. לפתוח במה שנעשה טוב.",
    ].join("\n"),
    ret: [
      "1. לכל סטודנט ליצור PDF של העבודה המקורית, עם הסימונים וההערות בעט אדום.",
      "2. בראש העמוד הראשון להוסיף טבלת ניקוד לפי שאלות ואת הציון הסופי.",
      "3. להעלות למודל את הציון הסופי (0–100) בשדה הציון של המטלה.",
      "4. להעלות את המשוב הכתוב בשדה \"הערות משוב\".",
      "5. לצרף את ה-PDF המסומן כקובץ משוב.",
      "6. לא לשנות שום דבר בהגשה המקורית של הסטודנט.",
      "7. בסוף לוודא מול מודל שכל הציונים נשמרו, ולדווח על כל הגשה שנכשלה.",
    ].join("\n"),
  };

  const returnFormat = {
    method: "api",
    include: { grade: true, feedback: true, pdf: true, breakdown: true },
    pattern: "{studentId}_hw{n}_checked.pdf",
  };

  // ---------- מחולל הגשות ----------
  function scoreQuestions(r, qs) {
    const ability = 0.5 + r() * 0.5;
    return qs.map((Q) => {
      if (r() < ability * 0.78) return Q.pts;
      const f = Math.max(0.2, Math.min(0.92, ability - 0.15 + (r() - 0.5) * 0.3));
      return Math.round(Q.pts * f);
    });
  }

  function makeSubmission(A, r, name, i, at) {
    const due = new Date(A.due).getTime();
    const time = at ?? (r() < 0.07 ? due + (1 + r() * 20) * H : due - (0.5 + r() * 96) * H);
    const scanned = r() < 0.12;
    const img = () => ({ name: `IMG_${2000 + Math.floor(r() * 7999)}.jpg`, pages: 1 });
    return {
      id: `${A.id}-${i}`,
      name,
      studentId: String(200000000 + Math.floor(r() * 99999999)),
      email: `student${100 + Math.floor(r() * 899)}@post.bgu.ac.il`,
      submittedAt: new Date(time).toISOString(),
      late: time > due,
      scanned,
      files: scanned ? [img(), img(), img()] : [{ name: `hw${A.n}.pdf`, pages: 3 + Math.floor(r() * 5) }],
      status: "pulled",
      q: null,
      score: null,
      issue: null,
      feedback: null,
    };
  }

  function gradeSubmission(s, r = Math.random) {
    const A = assignments.find((a) => s.id.startsWith(a.id + "-"));
    s.q = scoreQuestions(r, rubrics[A.courseId].questions);
    s.score = s.q.reduce((a, b) => a + b, 0);
    s.status = "graded";
    s.feedback = null;
    return s;
  }

  // הגשות חדשות שמופיעות כשלוחצים "משוך הגשות"
  function newSubmissions(A, k) {
    const used = new Set(A.subs.map((s) => s.name));
    const free = shuffle(NAMES.filter((n) => !used.has(n)), Math.random).slice(0, k);
    const now = Date.now(), due = new Date(A.due).getTime();
    return free.map((name, j) => {
      const at = now > due ? due + Math.random() * (now - due) : now - Math.random() * 72 * H;
      // מזהה ייחודי, כדי ששני חברי צוות שמושכים באותו זמן לא ידרסו זה את זה
      return makeSubmission(A, Math.random, name, `${Date.now().toString(36)}${j}${Math.floor(Math.random() * 1e4)}`, at);
    });
  }

  // ---------- מטלות ----------
  const now = Date.now();
  const dueDates = { la: ["2026-09-30", "2026-10-07", "2026-10-19", "2026-10-28"], dm: ["2026-10-01", "2026-10-08", "2026-10-20", "2026-10-29"] };
  const assignments = [];
  courses.forEach((c) => [1, 2, 3, 4].forEach((n) => {
    assignments.push({
      id: `${c.id}-hw${n}`, courseId: c.id, n, title: `תרגיל בית ${n}`,
      due: `${dueDates[c.id][n - 1]}T23:59`, phase: n < 3 ? "done" : n === 3 ? "current" : "new",
      subs: [], pulledAt: null, gradedAt: null, returnedAt: null, lastFresh: null,
    });
  }));

  const runs = [];
  const where = (A) => `${courses.find((c) => c.id === A.courseId).name}, ${A.title}`;

  assignments.forEach((A) => {
    if (A.phase === "new") return;
    const r = rng(hash(A.id));
    const qs = rubrics[A.courseId].questions;
    const count = 24 + Math.floor(r() * 5);
    A.subs = shuffle(NAMES, r).slice(0, count).map((name, i) => makeSubmission(A, r, name, i + 1));
    const due = new Date(A.due).getTime();

    if (A.phase === "done") {
      A.subs.forEach((s) => { s.q = scoreQuestions(r, qs); s.score = s.q.reduce((a, b) => a + b, 0); s.status = "returned"; });
      A.pulledAt = new Date(due + 7 * H).toISOString();
      A.gradedAt = new Date(due + 7.4 * H).toISOString();
      A.returnedAt = new Date(due + 31 * H).toISOString();
      const avg = Math.round(A.subs.reduce((a, s) => a + s.score, 0) / A.subs.length);
      runs.push({ at: A.pulledAt, kind: "pull", text: `נמשכו ${count} הגשות ממודל`, where: where(A) });
      runs.push({ at: A.gradedAt, kind: "grade", text: `Claude בדק ${count} עבודות. ממוצע ${avg}`, where: where(A) });
      runs.push({ at: A.returnedAt, kind: "return", text: `הוחזרו ${count} ציונים וקבצים מסומנים למודל`, where: where(A) });
    } else {
      // המטלה הנוכחית: נמשכה הבוקר, חלק נבדק, הגשה אחת עם קובץ ריק
      const graded = Math.round(count * 0.66);
      A.subs.forEach((s, i) => {
        if (i < graded) { s.q = scoreQuestions(r, qs); s.score = s.q.reduce((a, b) => a + b, 0); s.status = "graded"; }
      });
      const bad = A.subs[count - 1];
      bad.status = "error"; bad.scanned = false; bad.files = [{ name: `hw${A.n}.pdf`, pages: 0 }];
      bad.issue = "הקובץ ריק (0 עמודים)";
      A.pulledAt = new Date(now - (A.courseId === "la" ? 2.3 : 5.1) * H).toISOString();
      runs.push({ at: A.pulledAt, kind: "pull", text: `נמשכו ${count} הגשות ממודל`, where: where(A) });
      runs.push({ at: A.pulledAt, kind: "error", text: `${bad.name}: הקובץ ריק. נדרשת פנייה לסטודנט`, where: where(A) });
      runs.push({ at: new Date(new Date(A.pulledAt).getTime() + 0.4 * H).toISOString(), kind: "grade", text: `Claude בדק ${graded} עבודות. הבדיקה נעצרה ידנית`, where: where(A) });
    }
  });
  runs.sort((a, b) => b.at.localeCompare(a.at));

  return { courses, assignments, rubrics, samples, instructions, returnFormat, runs, where, gradeSubmission, newSubmissions };
})();
