(() => {
  // כל מה שהאתר מציג אמיתי: הנתונים מגיעים מהמערכת שרצה במחשב (start.bat, dashboard/web_server.py),
  // שקוראת את תיקיית OneDrive של הקורס. בלי המערכת אין מספרים במסך
  // stats: מסד הנתונים הסטטיסטי (stats/, api/stats): רשומה לכל מטלה, מספרים בלבד
  const D = { courses: [], assignments: [], rubrics: {}, runs: [], usage: null, stats: [], integrity: [] };
  // באתר הציבורי (Vercel) פונים למערכת שבמחשב. כשהאתר נפתח מהמערכת עצמה, לאותה כתובת
  const ON_LOCAL_HOST = ["localhost", "127.0.0.1"].includes(location.hostname);
  const BASE = ON_LOCAL_HOST ? "" : "http://127.0.0.1:8765/";
  // אותו אתר, ישירות מהמערכת: עובד בלי הרשאת "גישה למכשיר" של כרום
  const LOCAL_SITE = "http://localhost:8765/";
  const REPO_URL = "https://github.com/matanravitsky-crypto/assignment-checker";
  // מחבר מחשב של מישהו מהצוות בפקודה אחת (website/connect.ps1, מתפרסם עם האתר)
  const CONNECT_COMMAND = "irm https://bodek-hacham.vercel.app/connect.ps1 | iex";
  const DEFAULT_GRADE_INSTR = [
    "לבדוק כל שאלה בנפרד, לפי המחוון ולפי הפתרון הרשמי.",
    "פתרון נכון בדרך אחרת מקבל ניקוד מלא.",
    "טענה בלי הוכחה או נימוק לא מקבלת ניקוד.",
    "לסמן על גבי העבודה את המקום המדויק של כל טעות, ולכתוב לידו הערה קצרה.",
    "אם כתב היד לא קריא או שהביטחון בציון נמוך, לסמן את העבודה לבדיקה ידנית.",
    "משוב בעברית, ענייני ומעודד. לפתוח במה שנעשה טוב.",
  ].join("\n");
  // הכלל, כמו RUBRIC_RULE ב-grading/grade.py: ניקוד רק לפי המחוון. האתר אף פעם לא מחלק ניקוד בעצמו
  const RUBRIC_RULE = "הניקוד ניתן אך ורק לפי המחוון של המטלה: לכל שאלה הניקוד שלה במחוון, ולא יותר. המערכת לא מחלקת ניקוד בעצמה, ובלי מחוון אין ציונים.";
  // המערכת במחשב: האם היא עונה, ומה היא יודעת
  const LOCAL = {
    on: false, health: null, report: null,
    batch: null,       // ההעלאה שהוכנה וממתינה ל"כן" של אדם: {...תשובת api/upload/prepare, assignmentId}
    sending: null,     // מצב ההעלאה למודל כפי שהשרת מדווח (GET api/upload)
    polling: false, starting: false, stopping: false,
    rd: null,          // מוכנות המחשב להעלאה (Claude Code, התחברות, כרום ומודל), למטלה הנוכחית
    probing: false,    // מנסים עכשיו להתחבר למערכת במחשב
    me: null,          // השם שלי בצוות: {name, set}. set=false עד שבחרו שם באתר (אז זה שם המשתמש של Windows)
    syncing: false, syncedAt: null,  // הכפתור "סנכרון": רץ עכשיו, ומתי סונכרן לאחרונה
    access: null,      // באתר הציבורי: מה כרום אומר על הגישה למערכת שבמחשב ("granted" / "prompt" / "denied")
  };
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem("ac:" + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("ac:" + k, JSON.stringify(v)); } catch {} },
  };

  // האתר הציבורי (Vercel) עובד ישירות מול המערכת שבמחשב (BASE), והכתובת למעלה נשארת bodek-hacham.vercel.app
  // (מתן, 2026-11-03). כרום שואל פעם אחת בכל מחשב אם לאפשר לאתר לגשת לאפליקציות ולשירותים במכשיר: לוחצים "אפשר".
  // עד אז מי שלחץ פעם "פתח את המערכת" הועבר בכל כניסה ל-localhost:8765 (openLocal), ומי שהמערכת שלו לא רצה באותו רגע
  // קיבל שגיאה של כרום בלי שום הסבר. אין יותר מעבר, ו-openLocal הישן לא נקרא. localhost:8765 עדיין עובד גם ישירות

  // ---------- State ----------
  const state = {
    courseId: null,
    assignmentId: null,
    tab: { pull: "list", grade: "list", ret: "list" },
    filter: "all",
    query: { pull: "", grade: "", ret: "" },
    keyDraft: {},     // assignmentId -> המכוון שעוד לא נשמר: { file, text, points: {שאלה: ניקוד} }
    moodleDraft: {},  // assignmentId -> מה שהוקלד בשדה "מזהה המטלה במודל" של הגשה שעוד לא נמשכה
    run: {},          // assignmentId -> { stage, steps[] }
    seenDone: {},     // assignmentId:stage -> true, כדי להנפיש את ה-V רק ברגע ההשלמה
    openId: null,
    instr: { grade: store.get("instr.grade", DEFAULT_GRADE_INSTR) },  // נשלחות ל-Claude עם כל בדיקה
    claude: store.get("claude", { model: "claude-opus-5-5", parallel: 5, sendSolution: true }),
    loading: false,
    pullPick: null,  // מזהה המטלה שחלונית "כמה הגשות למשוך" פתוחה בה
    pullLimit: 0,  // כמה הגשות למשוך (0 = את כולן). לא נשמר בין ביקורים: הגבלה ששכחו הייתה מפתיעה את המשיכה הבאה
    teamCount: store.get("teamCount", 20),  // כמה עבודות פנויות לוקחים בלחיצה אחת
    gradePick: null,  // assignmentId שהחלונית "כמה לבדוק" של כפתור הבדיקה פתוחה בו
    gradeCount: store.get("gradeCount", 100),  // כמה עבודות בודקים בלחיצה אחת
    nameDraft: null,  // מה שהוקלד בשדה "השם שלך"
    renaming: false,
    // לוח הבקרה: טעות נפוצה שנפתחה
    mistakeOpen: null,
    // הבדיקה הידנית: העבודה שפתוחה, סינון לפי סוג הבעיה, מה מוצג (מסומנת/מקורית) והטיוטה של כל עבודה עד השמירה
    review: { id: null, edits: {}, saving: false, pages: {}, marks: true, open: {}, fbOpen: false, log: {} },
    // חלונות מתקפלים: מה פתוח (מפתח → true/false). בלי מפתח: ברירת המחדל של החלון
    fold: store.get("fold", {}),
  };

  // מה כל שלב עושה באמת (moodle/ingest.py, grading/grade.py, moodle/send.py)
  const STAGES = {
    pull: {
      no: 1, route: "/pull", name: "משיכת הגשות",
      desc: "Claude בכרום מוריד ממודל את קובץ ה-ZIP עם כל ההגשות של המטלה, והמערכת קולטת אותו: שומרת אותו רק במחשב שמשך, נותנת לכל סטודנט מספר קבוע ומעתיקה את ההגשות הממוספרות לתיקיית OneDrive, בלי שמות.",
      steps: ["הורדת ה-ZIP ממודל (Claude בכרום)", "בדיקה שה-ZIP שלם", "חילוץ ה-ZIP (במחשב הזה בלבד)", "מספור ההגשות ועדכון טבלת המפתח"],
      tabs: [["list", "ההגשות שנמשכו"], ["instr", "מה קורה במשיכה"], ["conn", "חיבור למודל"]],
    },
    grade: {
      no: 2, route: "/grade", name: "בדיקה וציון",
      desc: "כל הגשה ממוספרת נשלחת ל-Claude כתמונות של העמודים, עם השאלות, המחוון, ההנחיות והפתרון הרשמי. Claude נותן ניקוד ומשפט לכל שאלה, כותב משוב ומסמן כל טעות במקום שלה. המערכת מחשבת את הציון, מציירת את ההערות על ה-PDF ושומרת אותו ב-\"2 - Graded with comments\", ואת הציון בקובץ הציונים של הבודק. אפשר לחלק את העבודות בין חברי הצוות: כל אחד לוקח עבודות, וכולם רואים מי בודק מה. עבודה ש-Claude לא בטוח בה מסומנת לבדיקה ידנית.",
      steps: ["קריאת השאלות, המחוון וההנחיות", "שליחת ההגשות ל-Claude", "סימון ההערות על ה-PDF", "שמירת הציונים"],
      tabs: [["list", "העבודות"], ["instr", "מחוון והנחיות לבדיקה"], ["conn", "חיבור ל-Claude"]],
    },
    ret: {
      no: 3, route: "/return", name: "החזרה לאוניברסיטה",
      desc: "העבודות המסומנות עולות למודל כקובצי משוב. המערכת אורזת רק מה שחדש או השתנה מאז ההעלאה הקודמת, בודקת שהמחשב מוכן, ואחרי אישור שלך Claude בכרום מעלה כל קובץ ZIP לעמוד \"העלאת מספר קובצי משוב\" במודל. אחרי כל קובץ המערכת בודקת שמודל קלט בדיוק את מספר העבודות שבו, ורושמת אותן ביומן ההעלאה.",
      steps: ["הכנת קובצי ZIP", "העלאה למודל דרך Claude בכרום", "אימות מול מודל"],
      tabs: [["list", "העבודות להעלאה"], ["instr", "מה עולה למודל"], ["conn", "חיבור למודל"]],
    },
  };
  const ROUTE_STAGE = { "/pull": "pull", "/grade": "grade", "/return": "ret" };
  const RET_LOCAL_STEPS = STAGES.ret.steps;
  const stepsOf = (stage) => STAGES[stage].steps;
  const moodleGradingUrl = (A) => `https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id=${encodeURIComponent(A.moodleId || "")}&action=grading`;
  // הגשה שעוד לא נמשכה אין לה מזהה מודל, אז אין לאן לקשר
  const moodleLink = (A, cls = "") => A.moodleId ? `<a class="btn secondary ${cls}" href="${moodleGradingUrl(A)}" target="_blank" rel="noopener">פתח את ההגשות במודל</a>` : "";
  // "https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id=3438636&action=grading" או "3438636" → "3438636"
  const parseMoodleId = (text) => ((text || "").match(/[?&]id=(\d+)/) || (text || "").trim().match(/^(\d+)$/) || [])[1] || null;

  const NO_KEY = "אין חיבור ל-Claude, ולכן אי אפשר לבדוק. הדרך הפשוטה: מחברים את Claude Code במחשב (כמו להעלאה למודל, ברשימת המוכנות של שלב 3, או claude auth login). אפשר גם מפתח API: שורה ANTHROPIC_API_KEY=... בקובץ .env שבתיקיית הריפו, ומפעילים מחדש את start.bat.";
  const STATUS = { pulled: "ממתינה לבדיקה", grading: "בבדיקה", graded: "נבדקה", returned: "הוחזרה", error: "דורשת טיפול" };

  const ICON = {
    pull: '<svg viewBox="0 0 24 24"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>',
    grade: '<svg viewBox="0 0 24 24"><path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4z"/><path d="M18 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/></svg>',
    ret: '<svg viewBox="0 0 24 24"><path d="M12 20V9M7 14l5-5 5 5M5 4h14"/></svg>',
    spin: '<svg class="spin" viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 9 9"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    chev: '<svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg>',
    chart: '<svg viewBox="0 0 24 24"><path d="M4 19h16M7 16V9M12 16V5M17 16v-6"/></svg>',
    file: '<svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5"/></svg>',
    img: '<svg viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M5 17l5-4 3 2.5 2.5-2 3.5 3"/></svg>',
    redo: '<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4"/></svg>',
    pen: '<svg viewBox="0 0 24 24"><path d="M4 20l4-1 11-11-3-3L5 16z"/></svg>',
    warn: '<svg viewBox="0 0 24 24"><path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.5"/></svg>',
    clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3 2"/></svg>',
    stop: '<svg viewBox="0 0 24 24"><rect x="6.5" y="6.5" width="11" height="11" rx="2"/></svg>',
    download: '<svg viewBox="0 0 24 24"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>',
    eye: '<svg viewBox="0 0 24 24"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/></svg>',
    hand: '<svg viewBox="0 0 24 24"><path d="M5 19c2-1 3-3 3-5V7a1.5 1.5 0 0 1 3 0v4m0-6a1.5 1.5 0 0 1 3 0v6m0-5a1.5 1.5 0 0 1 3 0v6m0-3a1.5 1.5 0 0 1 3 0v4c0 4-3 7-7 7h-2"/></svg>',
    expand: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>',
    lock: '<svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
    upload: '<svg viewBox="0 0 24 24"><path d="M12 16V5M7 10l5-5 5 5M5 19h14"/></svg>',
    search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>',
    folder: '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
  };
  // סימן V שמצויר (stroke-dashoffset) כששלב מסתיים
  const CHECK_DRAW = '<svg class="check-draw" viewBox="0 0 24 24"><path pathLength="1" d="M5 12.5l4.5 4.5L19 7.5"/></svg>';

  // ---------- Helpers ----------
  const course = () => D.courses.find((c) => c.id === state.courseId);
  const cur = () => D.assignments.find((a) => a.id === state.assignmentId);
  const rubric = () => (LOCAL.on && cur()?.rubricQ) || D.rubrics[state.courseId];
  // למה אין ציונים במטלה (אין מחוון עם ניקוד לכל שאלה). ריק = יש מחוון
  const noRubric = () => rubric().missing || "";
  // שאלות שהניקוד בהן עובר את המחוון: נבדקו לפי חלוקה אחרת, ואסור לאשר אותן ככה
  const overRubric = (points) => rubric().questions.map((q, i) => ({ q, i, p: points?.[i] })).filter((x) => x.p > x.q.pts);
  const rubricNoticeHTML = () => `<div class="notice rule-notice">${ICON.warn}<div><b>אין ציונים בלי מחוון.</b> ${esc(noRubric())}
    <span class="muted" style="display:block">כדי לתת ציונים, שמים בתיקייה "פדגוגי" שבתיקיית המטלה את המחוון (Rubric.md) עם טבלת ניקוד לכל שאלה.</span></div></div>`;
  const pad = (n) => String(n).padStart(2, "0");
  const hhmm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  function when(iso) {
    if (!iso) return "";
    const d = new Date(iso), t = new Date();
    const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = (day(t) - day(d)) / 864e5;
    if (diff === 0) return `היום ב-${hhmm(d)}`;
    if (diff === 1) return `אתמול ב-${hhmm(d)}`;
    return `${d.toLocaleDateString("he-IL", { day: "numeric", month: "short" })}, ${hhmm(d)}`;
  }
  const dueText = (A) => (A.due ? new Date(A.due).toLocaleString("he-IL", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" }) : "לא נקבע");
  const avg = (arr) => (arr.length ? Math.round(arr.reduce((a, b) => a + b, 0) / arr.length) : null);
  const plural = (n, one, many) => (n === 1 ? one : `${n} ${many}`);
  const median = (arr) => { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const half = (x) => Math.round(x * 2) / 2;
  const fmt = (x) => (x == null ? "—" : String(Math.round(x * 10) / 10));

  // ---------- קבצים, בדיקה ידנית וטעויות ----------
  const fileUrl = (f, download = false) => `${BASE}api/file?path=${encodeURIComponent(f.path)}${download ? "&download=1" : ""}`;
  const origFiles = (s) => s.files.filter((f) => !f.marked);
  const markedFiles = (s) => s.files.filter((f) => f.marked);
  // עבודה בתור הבדיקה הידנית: Claude ביקש שאדם יבדוק, או שהבדיקה האוטומטית נכשלה. יוצאת מהתור כשמישהו מאשר
  // בדיקה שנכשלה (למשל נגמרו הטוקנים) היא לא מקרה לאדם: היא עדיין "ממתינה לבדיקה", ו"בדוק" ינסה אותה שוב
  const needsReview = (s) => !s.approved && !!s.review;
  const gradingFailed = (s) => !!s.failed && s.score == null;
  const wasReviewed = (s) => s.approved && (!!s.review || !!s.reviewedBy);
  // מקרים מיוחדים: רק הם מגיעים לאדם (grading.SPECIAL_CASES, הסקיל "קשיחות והחלטות"), ועוד סוגים מבדיקות ישנות
  const REVIEW_KIND = {
    missing_question: ["חסר תרגיל או סעיף", "שאלה שלמה או סעיף שלם לא נמצאו בהגשה"],
    missing_page: ["חסר עמוד", "המספור קופץ, תשובה נקטעת, או עמוד חתוך"],
    other_assignment: ["הגשה של מטלה אחרת", "ההגשה עונה על שאלות של מטלה אחרת"],
    unreadable_file: ["עמוד שאי אפשר לקרוא", "עמוד ריק, שחור או מטושטש, או קובץ שאי אפשר לבדוק"],
    unreadable: ["כתב יד לא קריא", "Claude לא הצליח לקרוא חלק מהעבודה"],
    missing: ["חסרים עמודים או שאלות", "שאלה או עמוד לא נמצאו בהגשה"],
    uncertain: ["ניקוד לא ודאי", "Claude לא בטוח בניקוד של שאלה"],
    format: ["לא לפי כללי ההגשה", "ההגשה לא בפורמט שנדרש"],
    failed: ["הבדיקה האוטומטית נכשלה", "צריך לבדוק ידנית או לנסות שוב"],
    other: ["מקרה מיוחד אחר", "משהו שלא קשור לבדיקה עצמה"],
  };
  const kindOf = (s) => s.reviewKind || (s.failed ? "failed" : "other");

  // טעויות נפוצות במטלה: כל טעות ש-Claude (או מתרגל) רשם לשאלה, כמה עבודות עשו אותה, ובכמה בדרך כלל מורידים עליה
  function mistakeStats(A = cur()) {
    const qs = rubric().questions;
    const withNotes = A.subs.filter((s) => s.score != null && Array.isArray(s.mistakes) && s.mistakes.length);
    const map = new Map();
    withNotes.forEach((s) => s.mistakes.forEach((ms, qi) => ms.forEach((text) => {
      const k = `${qi}|${text}`;
      const e = map.get(k) || { q: qi, text, ids: [], losses: [] };
      e.ids.push(s.id);
      if (ms.length === 1 && s.q && qs[qi]) e.losses.push(qs[qi].pts - s.q[qi]);  // הטעות היחידה בשאלה: כל מה שירד הוא בגללה
      map.set(k, e);
    })));
    return [...map.values()].map((e) => {
      const known = (qs[e.q]?.deductions || []).find((d) => d.text === e.text);
      const typical = e.losses.length ? half(median(e.losses)) : null;
      return { ...e, count: e.ids.length, pct: withNotes.length ? Math.round((100 * e.ids.length) / withNotes.length) : 0, ded: known ? known.points : typical };
    }).sort((a, b) => b.count - a.count || a.q - b.q);
  }

  // חלוקה בצוות (moodle/claims.py): s.claim = {who, at} של מי שלקח את העבודה, או null
  const myName = () => LOCAL.me?.name || "";
  const isMine = (s) => !!s.claim && s.claim.who === myName();

  function info(A = cur()) {
    const subs = A.subs;
    const ok = subs.filter((s) => s.status !== "error");
    const graded = ok.filter((s) => s.status === "graded" || s.status === "returned");
    const returned = ok.filter((s) => s.status === "returned");
    const toGrade = ok.filter((s) => s.status === "pulled");
    // ברגע שמישהו לקח עבודה, "בדוק" בודק רק את מה שלי. בלי חלוקה: את כל מה שמחכה, כמו קודם
    const teamMode = subs.some((s) => s.claim);
    const myLeft = toGrade.filter(isMine).map((s) => s.id), free = toGrade.filter((s) => !s.claim).length;
    return {
      subs, ok, graded, returned, teamMode, myLeft, free,
      gradeIds: (teamMode ? toGrade.filter(isMine) : toGrade).map((s) => s.id),
      canTake: myLeft.length + free,  // מה שאני יכול לבדוק: מה שכבר שלי ועוד לא נבדק, ועוד הפנויות
      issues: subs.length - ok.length,
      files: subs.reduce((a, s) => a + s.files.length, 0),
      late: subs.filter((s) => s.late).length,
      toGrade,
      toReturn: ok.filter((s) => s.status === "graded"),
      gradesToSend: A.gradesToSend || 0,  // ציונים של עבודות שהקבצים שלהן כבר במודל (moodle/send_grades.py)
      done: {
        pull: !!A.pulledAt,
        grade: ok.length > 0 && graded.length === ok.length,
        ret: ok.length > 0 && returned.length === ok.length && !A.gradesToSend,
      },
    };
  }

  function toast(msg, icon = ICON.check) {
    const el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = icon + `<span>${esc(msg)}</span>`;
    $("#toasts").append(el);
    setTimeout(() => el.remove(), 3400);
  }

  // LaTeX בתוך טקסט: $...$ בשורה, $$...$$ כתצוגה
  function tex(str) {
    return String(str).split(/(\$\$[\s\S]+?\$\$|\$[^$]+?\$)/g).map((part) => {
      const display = part.startsWith("$$");
      if (!(display || (part.startsWith("$") && part.length > 1))) return esc(part);
      const src = part.slice(display ? 2 : 1, display ? -2 : -1);
      if (!window.katex) return `<code dir="ltr">${esc(src)}</code>`;
      return window.katex.renderToString(src, { displayMode: display, throwOnError: false });
    }).join("");
  }

  // ---------- Pipeline runs ----------
  // כל כפתור מפעיל את הקוד האמיתי במחשב. המספרים מתעדכנים רק ממה שנכתב בתיקייה
  function runStage(stage) {
    if (!LOCAL.on || !cur()) return;
    if (stage === "pull") {
      // הגשה שעוד לא נמשכה ועוד אין לה קישור: ההודעה "קודם מדביקים את הקישור" באה מיד, בלי חלונית
      if (cur().empty && !parseMoodleId(state.moodleDraft[cur().id])) { runLocalPull(); return; }
      state.pullPick = state.pullPick === cur().id ? null : cur().id;
      state.pullLimit = 0;
      render();
      return;
    }
    if (stage === "grade") { state.gradePick = state.gradePick === cur().id ? null : cur().id; render(); $("#grade-count")?.select(); }
    if (stage === "ret") startSendFlow();
  }

  // החלונית שנפתחת מתחת ל"בדוק": כמה עבודות לבדוק עכשיו. קודם משלימים מהפנויות (באקראי, בשרת) ומסמנים אותן עליי,
  // ורק אז בודקים, ורק את מה שעליי. כך אף אחד לא צריך לבדוק הכל, ושני בודקים לא בודקים את אותה עבודה
  function gradePickHTML() {
    const A = cur(), I = info(A);
    if (state.gradePick !== A.id || state.run[A.id] || !I.canTake) return "";
    const max = I.canTake, n = Math.max(1, Math.min(state.gradeCount || 1, max)), mine = I.myLeft.length;
    const more = Math.max(0, n - mine), others = I.toGrade.length - max;
    const chips = [...new Set([25, 50, 100, max].filter((c) => c <= max))];
    const plan = more
      ? `${mine ? `${plural(mine, "עבודה אחת כבר שלך", "עבודות כבר שלך")}, ו-` : ""}${plural(more, "עבודה פנויה אחת תסומן", "עבודות פנויות ייבחרו באקראי ויסומנו")} עליך לפני שהבדיקה מתחילה.`
      : `ייבדקו ${n === 1 ? "עבודה אחת" : `${n} עבודות`} מתוך ${mine} שכבר שלך. לא נלקחות עבודות חדשות.`;
    return `<div class="grade-pick" role="dialog" aria-label="כמה עבודות לבדוק">
      <label class="team-count">כמה לבדוק עכשיו? <input type="number" id="grade-count" data-grade-count min="1" max="${max}" value="${n}"></label>
      <div class="chips">${chips.map((c) => `<button class="chip" data-grade-chip="${c}" aria-pressed="${c === n}">${c === max ? `הכל (${c})` : c}</button>`).join("")}</div>
      <p class="hint">${plan} ${others > 0 ? `${others} עבודות שמישהו אחר לקח לא ייבדקו כאן.` : ""} מי שבודק במחשב אחר רואה את הסימון תוך כמה שניות, ולא יבדוק אותן.</p>
      <div class="gp-act">
        <button class="btn primary small" data-act="grade-pick-go">${ICON.grade}בדוק ${n}</button>
        <button class="btn ghost small" data-act="grade-pick-close">ביטול</button>
      </div>
    </div>`;
  }

  async function gradePicked() {
    const A = cur(), I = info(A);
    const n = Math.max(1, Math.min(state.gradeCount || 1, I.canTake));
    state.gradePick = null;
    try {
      let ids = I.myLeft;
      if (n > ids.length) {
        // השרת קורא את הסימונים מהתיקייה עכשיו, ולוקח רק פנויות. מה שמישהו לקח בינתיים לא נלקח
        const rep = await api("api/claims", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder, next: n - ids.length }) });
        applyClaims(A, rep);
        ids = info(A).myLeft;
      }
      ids = ids.slice(0, n);
      if (ids.length < n) toast(`רק ${ids.length} עבודות היו פנויות. בודק אותן.`, ICON.warn);
      await runLocalGrade(ids);
    } catch (e) {
      render();
      toast(e.message, ICON.warn);
    }
  }

  // ---------- Stage pieces ----------
  // "העלה ציונים": רק בלחיצה. מעלה את הציונים של עבודות שהקבצים שלהן כבר במודל (moodle/send_grades.py)
  function gradesButton({ big = false } = {}) {
    const A = cur();
    if (!LOCAL.on || !A || A.empty) return "";
    const I = info(A), n = I.gradesToSend, S = LOCAL.sending;
    const here = S?.running && sendingHere() && S.phase === "grades";
    const checking = LOCAL.rd?.flow && LOCAL.rd.then === "grades" && LOCAL.rd.assignmentId === A.id;
    const owner = ownerOf(A, "ret");
    const theirs = owner && owner.who !== myName();
    const disabled = !n || S?.running || LOCAL.starting || checking || theirs || !!state.run[A.id];
    const text = here ? "מעלה ציונים…" : checking ? "בודק שהמחשב מוכן…" : theirs ? `אצל ${owner.who}`
      : n ? `העלה ${n} ציונים` : "אין ציונים להעלאה";
    return `<button class="btn ${n && !I.toReturn.length ? "primary" : "secondary"} ${big ? "lg" : ""}" data-act="grades-flow" ${disabled ? "disabled" : ""}
      title="הציונים עולים רק בלחיצה הזו, של עבודות שהקבצים הבדוקים שלהן כבר במודל">${here || checking ? ICON.spin : ICON.upload}${text}</button>`;
  }

  function stageButton(stage, { big = false } = {}) {
    const A = cur(), I = info(A), run = state.run[A.id];
    const busy = !!run, mine = run?.stage === stage;
    let label, n = 0, primary = false;
    if (stage === "pull") { label = "משוך הגשות"; primary = !I.subs.length; }
    if (stage === "grade") {
      n = I.canTake;
      label = n ? `בדוק עבודות (${n} זמינות) ▾` : I.toGrade.length ? "כל העבודות שנשארו נלקחו" : "הכל נבדק";
      primary = n > 0;
    }
    if (stage === "ret") { n = I.toReturn.length; label = n ? `החזר ${n} עבודות` : I.done.ret ? "הכל הוחזר" : "אין מה להחזיר"; primary = n > 0 && !I.toGrade.length; }
    let disabled = busy || (stage !== "pull" && !n);
    if (LOCAL.on && stage === "grade" && !LOCAL.health?.claude) {
      // בלי מפתח אי אפשר לבדוק. ההסבר מופיע בלשונית "חיבור ל-Claude"
      label = "צריך מפתח Claude";
      disabled = true;
      primary = false;
    }
    let text = mine ? (run.progress || "רץ עכשיו…") : label, spinning = mine;
    if (LOCAL.on && stage === "ret") {
      if (!mine) text = n ? `העלה ${n} למודל` : I.done.ret ? "הכל הועלה" : I.gradesToSend ? "כל העבודות הועלו" : "אין עבודות להעלאה";
      if (LOCAL.sending?.running || LOCAL.starting) disabled = true;  // העלאה אחת בכל פעם, גם אם היא של מטלה אחרת
      if (LOCAL.sending?.running && sendingHere()) { text = sendProgressText(); spinning = true; }
      if (LOCAL.rd?.flow && LOCAL.rd.then === "send" && LOCAL.rd.assignmentId === A.id && !mine) { text = "בודק שהמחשב מוכן…"; spinning = true; disabled = true; }
    }
    if (LOCAL.on && stage === "pull" && LOCAL.rd?.flow && LOCAL.rd.then === "pull" && LOCAL.rd.assignmentId === A.id && !mine) {
      text = "מחבר את המחשב ל-Claude…"; spinning = true; disabled = true;
    }
    // החזרה שמישהו אחר בצוות לקח: הכפתור אצלו. אפשר להעביר אליך מלוח המשימות. משיכה: כל אחד יכול למשוך, גם כשהיא
    // רשומה על מישהו אחר (רק המשיכה הלילית נשארת שלו); הבדיקה שבסוף כל משיכה (moodle/pull_check.py) מוודאת ששום דבר לא אבד
    const owner = ownerOf(A, stage);
    if (stage !== "pull" && owner && owner.who !== myName() && !spinning) { text = `אצל ${owner.who}`; disabled = true; primary = false; }
    const icon = spinning ? ICON.spin : ICON[stage === "ret" ? "ret" : stage];
    const why = LOCAL.on && stage === "grade" && !LOCAL.health?.claude ? ` title="${esc(NO_KEY)}"` : "";
    // בזמן בדיקה: כפתור עצירה. מה שכבר נשלח ל-Claude מסתיים ונשמר, והשאר נשאר "ממתינה לבדיקה"
    const stopBtn = mine && stage === "grade" ? `<button class="btn danger ${big ? "lg" : ""}" data-act="grade-stop" ${run.stopping ? "disabled" : ""}
      title="העבודות שכבר נשלחו ל-Claude יסתיימו ויישמרו. השאר יחכו ללחיצה הבאה על 'בדוק'">${run.stopping ? ICON.spin : ICON.stop}${run.stopping ? "עוצר…" : "עצור בדיקה"}</button>` : "";
    const btn = `<button class="btn ${primary ? "primary" : "secondary"} ${big ? "lg" : ""}" data-run="${stage}" ${disabled ? "disabled" : ""}${why}
      ${stage === "grade" ? `aria-expanded="${state.gradePick === A.id}"` : ""}${stage === "pull" && LOCAL.on ? `aria-expanded="${state.pullPick === A.id}" aria-haspopup="dialog"` : ""}>${icon}${text}${stage === "pull" && LOCAL.on && !spinning ? `<span class="caret" aria-hidden="true">▾</span>` : ""}</button>${stopBtn}`;
    if (stage === "pull" && LOCAL.on) return `<span class="pick-wrap">${btn}${disabled ? "" : pullPickHTML()}</span>`;
    return stage === "grade" ? `<span class="pick-wrap">${btn}${disabled ? "" : gradePickHTML()}</span>` : btn;
  }

  // "כמה הגשות למשוך": חלונית שנפתחת מתחת לכפתור המשיכה, כמו "כמה לבדוק". המשיכה לוקחת את ההגשות הראשונות בטבלת
  // ההגשות במודל שיש להן הגשה; משיכה בלי מספר מביאה אחר כך את כל השאר, והמספרים של מי שכבר נמשך נשמרים
  const PULL_CHIPS = [10, 25, 50, 100];
  const pullGoLabel = () => (state.pullLimit > 0 ? `משוך ${state.pullLimit}` : "משוך הכול");
  function pullPickHTML() {
    const A = cur(), n = state.pullLimit > 0 ? state.pullLimit : 0;
    if (state.pullPick !== A.id || state.run[A.id]) return "";
    const known = n && !PULL_CHIPS.includes(n);
    const chip = (v, label) => `<button type="button" class="chip" data-pull-chip="${v}" aria-pressed="${n === v}">${label}</button>`;
    const again = A.pulledAt
      ? "המשיכה הזו כבר נעשתה פעם: נמשכים רק מי שההגשה שלו השתנתה מאז, ובתוכם לא יותר מהמספר שבחרת."
      : "נמשכות ההגשות הראשונות בטבלת ההגשות במודל. משיכה בלי מספר מביאה אחר כך את כל השאר, והמספרים של מי שכבר נמשך נשמרים.";
    return `<div class="grade-pick pull-pick" role="dialog" aria-label="כמה הגשות למשוך">
      <div class="pp-title">כמה הגשות למשוך?</div>
      <div class="chips pp-chips">${PULL_CHIPS.map((c) => chip(c, c)).join("")}${chip(0, "הכול")}</div>
      <label class="team-count pp-custom">או מספר אחר
        <input type="number" id="pull-limit" data-pull-limit min="1" step="1" inputmode="numeric" placeholder="למשל 30" value="${known ? n : ""}"></label>
      <p class="hint">${again}</p>
      <div class="gp-act">
        <button class="btn primary small" data-act="pull-pick-go">${ICON.pull}<span data-pull-go>${pullGoLabel()}</span></button>
        <button class="btn ghost small" data-act="pull-pick-close">ביטול</button>
      </div>
    </div>`;
  }

  function stageState(stage) {
    const A = cur(), I = info(A), run = state.run[A.id];
    if (run?.stage === stage) {
      const i = run.steps.findIndex((s) => s === "running");
      return { kind: "running", text: `${stepsOf(stage)[Math.max(i, 0)]}…` };
    }
    if (LOCAL.on && stage === "ret" && sendingHere()) return { kind: "running", text: sendProgressText() };
    if (I.done[stage]) {
      const at = { pull: A.pulledAt, grade: A.gradedAt, ret: A.returnedAt }[stage];
      return { kind: "done", text: at ? `הושלם ${when(at)}` : "הושלם" };
    }
    if (stage === "pull") return { kind: "todo", text: "עוד לא נמשכו הגשות" };
    if (stage === "grade") return I.ok.length ? { kind: "todo", text: `${I.toGrade.length} ממתינות לבדיקה` } : { kind: "idle", text: "מחכה למשיכה" };
    return I.toReturn.length ? { kind: "todo", text: `${I.toReturn.length} מוכנות להחזרה` } : { kind: "idle", text: I.ok.length ? "מחכה לבדיקה" : "מחכה למשיכה" };
  }

  function stageMark(stage, cls = "") {
    const A = cur(), done = info(A).done[stage];
    if (state.run[A.id]?.stage === stage || (LOCAL.on && stage === "ret" && sendingHere())) return `<span class="stage-mark ${cls} running">${ICON.spin}</span>`;
    const key = `${A.id}:${stage}`;
    const fresh = done && state.seenDone[key] === false;
    return `<span class="stage-mark ${cls} ${done ? "done" : ""} ${fresh ? "just-done" : ""}">${done ? CHECK_DRAW : STAGES[stage].no}</span>`;
  }

  function dotsFor(stage, I) {
    let list;
    if (stage === "pull") list = I.subs.map((s) => (s.status === "error" ? "warn" : "on"));
    if (stage === "grade") list = I.ok.map((s) => (s.status === "grading" ? "busy" : s.status === "pulled" ? "off" : "on"));
    if (stage === "ret") list = I.ok.map((s) => (s.status === "returned" ? "on" : "off"));
    const subs = stage === "pull" ? I.subs : I.ok;
    return list.map((k, i) => {
      const s = subs[i], f = dotFile(stage, s);
      const what = f?.marked ? "העבודה הבדוקה" : "ההגשה";
      return `<i class="d ${k} ${s.fresh ? "pop" : ""}" ${f ? `data-dl="${s.id}" data-stage="${stage}"` : ""}
        title="עבודה ${esc(s.id)}${s.score != null ? ` · ${s.score}` : ""}${f ? `\nלחיצה כפולה מורידה את ${what}` : ""}"></i>`;
    }).join("");
  }

  // מה ריבוע מוריד: במשיכה את ההגשה, בבדיקה ובהחזרה את העבודה הבדוקה (ואם עוד אין, את ההגשה)
  function dotFile(stage, s) {
    const marked = markedFiles(s)[0], orig = origFiles(s)[0];
    return stage === "pull" ? orig : marked || orig;
  }
  function downloadDot(el) {
    const s = cur()?.subs.find((x) => x.id === el.dataset.dl), f = s && dotFile(el.dataset.stage, s);
    if (!f) return;
    const a = document.createElement("a");
    a.href = fileUrl(f, true);
    a.download = "";
    document.body.append(a);
    a.click();
    a.remove();
    toast(`מוריד את עבודה ${s.id}${f.marked ? " (בדוקה)" : ""}`, ICON.download);
  }

  function pipelineHTML() {
    const A = cur(), I = info(A);
    const nums = {
      pull: [I.subs.length, "הגשות נמשכו", I.issues ? `${I.issues} דורשות טיפול` : ""],
      grade: [I.graded.length, `מתוך ${I.ok.length} נבדקו`, (() => {
        const n = I.subs.filter(gradingFailed).length;
        return n ? `${plural(n, "בדיקה אחת נכשלה", "בדיקות נכשלו")}. "בדוק" ינסה שוב` : "";
      })()],
      ret: [I.returned.length, `מתוך ${I.ok.length} הוחזרו`, ""],
    };
    return `
      <section class="pipeline" aria-label="מסלול הבדיקה">
        ${["pull", "grade", "ret"].map((st, idx) => {
          const S = STAGES[st], ss = stageState(st);
          return `
          <article class="stage" data-state="${ss.kind}">
            ${idx ? `<span class="stage-arrow" aria-hidden="true">${ICON.chev}</span>` : ""}
            <header class="stage-top">
              ${stageMark(st)}
              <div>
                <h2>${S.name}</h2>
                <p class="stage-status ${ss.kind}">${ss.kind === "running" ? ICON.spin : ""}${esc(ss.text)}</p>
              </div>
            </header>
            <div class="stage-count num">${nums[st][0]}<small>${nums[st][1]}</small></div>
            <div class="dots" aria-label="כל ריבוע הוא עבודה. לחיצה כפולה מורידה אותה">${dotsFor(st, I)}</div>
            ${st === "pull" ? pullBarHTML(true) : ""}
            ${nums[st][2] ? `<p class="stage-warn">${ICON.warn}${nums[st][2]}</p>` : ""}
            <footer class="stage-foot">
              ${stageButton(st)}${st === "ret" ? gradesButton() : ""}
              <a class="link" href="#${S.route}">הנחיות והגדרות</a>
            </footer>
          </article>`;
        }).join("")}
      </section>`;
  }

  // ההורדות של עבודה אחת: הקבצים המקוריים שהסטודנט הגיש והעבודה אחרי הבדיקה, עם ההערות
  function downloadsHTML(s) {
    const orig = origFiles(s), marked = markedFiles(s);
    const link = (f, label) => `<a class="btn secondary small" href="${fileUrl(f, true)}" download>${ICON.download}${esc(label)}</a>`;
    return `<div class="dl-group">
        <span class="dl-label">ההגשה</span>
        ${orig.map((f) => link(f, orig.length > 1 ? `הגשה (${f.name})` : "הורד את ההגשה")).join("") || `<span class="muted">אין קובץ</span>`}
      </div>
      <div class="dl-group">
        <span class="dl-label">אחרי בדיקה</span>
        ${marked.map((f) => link(f, marked.length > 1 ? `בדוקה (${f.name})` : "הורד את העבודה הבדוקה")).join("")
          || `<span class="btn secondary small" aria-disabled="true">${ICON.clock}${s.score != null ? "אין עבודה מסומנת" : "עוד לא נבדקה"}</span>`}
      </div>`;
  }

  function runStepsHTML(stage) {
    const A = cur(), I = info(A), run = state.run[A.id];
    const S = { ...STAGES[stage], steps: stepsOf(stage) };
    const live = run?.stage === stage ? run.steps : LOCAL.on && stage === "ret" && sendingHere() ? ["done", "running", "pending"] : null;
    const done = I.done[stage] || (stage === "pull" && A.pulledAt);
    const gradedNow = I.graded.length;
    const marks = I.graded.reduce((a, s) => a + (s.q || []).filter((v, i) => v < rubric().questions[i]?.pts).length, 0);
    const results = {
      pull: [`ZIP מ-${when(A.pulledAt)}`, "ה-ZIP שלם ונשמר במחשב שמשך", `${I.files} קבצים`, `${I.subs.length} הגשות, לכל הגשה מספר קבוע`],
      grade: [`${rubric().questions.length} שאלות, ${A.maxGrade || 100} נקודות`, `${gradedNow} עבודות`, `${marks} הורדות ניקוד`, `ממוצע ${avg(I.graded.map((s) => s.score)) ?? "—"}`],
      ret: [`${I.returned.length} עבודות מסומנות`, `${I.returned.length} עבודות עלו`, "מודל קלט את אותו מספר קבצים"],
    }[stage];
    return `
      <ol class="run-steps" aria-label="שלבי הריצה">
        ${S.steps.map((name, i) => {
          const st = live ? live[i] : done ? "done" : "pending";
          return `<li class="${st}">
            <span class="rs-icon">${st === "done" ? ICON.check : st === "running" ? ICON.spin : `<span>${i + 1}</span>`}</span>
            <span class="rs-text"><b>${name}</b><small>${st === "done" ? esc(live && stage === "pull" ? run.notes?.[i] || "הושלם" : results[i])
              : st === "running" ? esc(stage === "pull" && run?.stage === "pull" ? pullView(run.pull).text : "רץ עכשיו…") : "ממתין"}</small></span>
          </li>`;
        }).join("")}
      </ol>`;
  }

  function stageHeroHTML(stage) {
    const S = STAGES[stage], ss = stageState(stage);
    return `
      <section class="stage-hero" data-state="${ss.kind}">
        ${stageMark(stage, "lg")}
        <div class="sh-text">
          <p class="sh-kicker">שלב ${S.no} מתוך 3</p>
          <h1>${S.name}</h1>
          <p>${S.desc}</p>
        </div>
        <div class="sh-side">
          <span class="stage-status ${ss.kind}">${ss.kind === "running" ? ICON.spin : ss.kind === "done" ? ICON.check : ""}${esc(ss.text)}</span>
          ${stageButton(stage, { big: true })}${stage === "ret" ? gradesButton({ big: true }) : ""}
        </div>
      </section>
      ${stage === "pull" ? `${readyPanelHTML("pull")}${pullBarHTML()}` : ""}
      ${runStepsHTML(stage)}`;
  }

  // ---------- מד ההתקדמות של המשיכה ----------
  // השרת אומר באיזה שלב המשיכה (GET /api/pull, dashboard/actions.py PullProgress), וכאן הופכים את זה לאחוזים:
  // הורדה 0-60 (לפי גודל ההורדה הקודמת, אם יש), בדיקת ה-ZIP 60-70, חילוץ 70-90, מספור 90-100
  // בין שני סימני כיוון (LRI…PDI), כדי ש-"600 MB" לא יתהפך בתוך משפט בעברית
  const size = (b) => `⁦${b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`}⁩`;
  const LONG_WAIT = "לא סוגרים את כרום ולא מכבים את המחשב. ZIP גדול ממודל יכול לקחת כמה דקות.";
  const HERE = "מכאן הכול קורה במחשב הזה, בלי מודל. אפשר לעבור לחלון אחר.";
  // כמה זמן נשאר, מ-eta_s שהשרת מחשב לפי הקצב של השלב עד עכשיו. אחרי ההורדה יש עוד חילוץ ומספור, בערך דקה
  const left = (sec) => (sec == null ? "" : sec < 50 ? "נשארה פחות מדקה" : `נשארו בערך ${Math.round(sec / 60)} דקות`);
  function pullView(p = {}) {
    const v = pullPhase(p), eta = left(p.eta_s);
    if (!eta) return v;
    const tail = v.step === 0 ? ` להורדה, ואחריה עוד כדקה במחשב` : "";
    return { ...v, text: `${v.text} · ${eta}${tail}`, soon: p.eta_s < 50 ? "פחות מדקה" : `עוד ${Math.round(p.eta_s / 60)} דק'` };
  }
  function pullPhase(p) {
    // האחוז מבודד גם הוא: אחרי "ZIP" הדפדפן היה מצמיד אותו למילה האנגלית ומזיז אותו
    const f = p.total ? Math.min(p.done / p.total, 1) : 0, pct = `⁦${Math.round(100 * f)}%⁩`;
    switch (p.phase) {
      case "connect": return { step: 0, pct: null, short: "בודק חיבור למודל…", text: "בודק שהתוסף של Claude בכרום מחובר ושכרום מחובר למודל (בדרך כלל עד דקה)…", hint: LONG_WAIT };
      case "claude": return { step: 0, pct: null, short: "Claude פותח את מודל…", text: "Claude פותח את מודל בכרום ומכין את ההורדה (בדרך כלל עד דקה)…", hint: LONG_WAIT };
      case "download": return {
        step: 0, pct: p.total ? Math.round(Math.min(58, 60 * f)) : null, short: "מוריד ממודל…",
        text: p.total ? `מוריד ממודל: ${size(p.done)} מתוך כ-${size(p.total)}` : `מוריד ממודל: ${size(p.done)} עד עכשיו`,
        hint: p.total ? LONG_WAIT : `${LONG_WAIT} זו ההורדה הראשונה של המטלה, אז עוד לא ידוע כמה גדול ה-ZIP.`,
      };
      // הורדה בחלקים (moodle/download_parts.js): כל חלק נשמר בהורדות כשהוא מגיע, והשרת סופר כמה כבר הגיעו
      case "parts": return {
        step: 0, pct: p.total ? Math.round(Math.min(58, 60 * f)) : null, short: "מוריד ממודל…",
        text: p.total ? `מוריד ממודל בחלקים: ${p.done} מתוך ${p.total} חלקים הגיעו` : `מוריד ממודל בחלקים: ${p.done} חלקים הגיעו עד עכשיו`,
        hint: LONG_WAIT,
      };
      case "check": return { step: 1, pct: Math.round(60 + 10 * f), short: "בודק את ה-ZIP…", text: `בודק שה-ZIP שלם: ${pct}%`, hint: HERE };
      case "extract": return { step: 2, pct: Math.round(70 + 20 * f), short: "מחלץ…", text: `מחלץ את ה-ZIP: ${pct}%`, hint: HERE };
      case "number": return { step: 3, pct: Math.round(90 + 10 * f), short: "ממספר הגשות…", text: `ממספר הגשות: ${p.done} מתוך ${p.total}`, hint: HERE };
      default: return { step: 0, pct: 1, short: "מתחיל…", text: "מתחיל משיכה ממודל…", hint: LONG_WAIT };
    }
  }
  function elapsed(since) {
    const sec = Math.max(0, Math.round((Date.now() - since) / 1000));
    return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
  }
  // מה שהשרת אמר עכשיו → השלבים, הטקסט על הכפתור והמד
  function showPull(run, p) {
    run.pull = p;
    const v = pullView(p);
    run.steps = STAGES.pull.steps.map((_, i) => (i < v.step ? "done" : i === v.step ? "running" : "pending"));
    run.notes = ["הורד ממודל"];
    run.progress = [v.short, v.pct == null ? "" : `${v.pct}%`, v.soon ? `· ${v.soon}` : ""].filter(Boolean).join(" ");
  }
  function pullBarHTML(compact = false) {
    const A = cur(), run = A && state.run[A.id];
    if (run?.stage !== "pull") return "";
    const v = pullView(run.pull), known = v.pct != null;
    const bar = `<div class="send-bar ${known ? "" : "indet"}" role="progressbar" aria-label="התקדמות המשיכה" aria-valuemin="0" aria-valuemax="100"
      ${known ? `aria-valuenow="${v.pct}"` : ""}><i style="width:${known ? v.pct : 30}%"></i></div>`;
    if (compact) return `<div class="pull-progress compact">${bar}<p>${known ? `<b class="num">${v.pct}%</b>` : ""}${esc(v.text)}</p></div>`;
    return `<section class="panel report send-panel pull-progress" aria-live="polite">
      <div class="panel-head"><h3>המשיכה רצה${known ? ` · <span class="num">${v.pct}%</span>` : ""}</h3><span class="meta num">עברו ${elapsed(run.startedAt)} דקות</span></div>
      <div class="panel-body">
        <p class="send-line">${ICON.spin}<b>${esc(v.text)}</b></p>
        ${bar}
        <p class="hint">${esc(v.hint)}</p>
      </div>
    </section>`;
  }

  function tabsHTML(stage) {
    return `<div class="tabs" role="tablist">
      ${STAGES[stage].tabs.map(([k, label]) => `<button role="tab" class="tab" id="tab-${stage}-${k}" aria-selected="${state.tab[stage] === k}" data-tab="${stage}:${k}">${label}</button>`).join("")}
    </div>`;
  }

  // ---------- לוח המשימות: השלב הזה בכל המטלות של הקורס, כמו שהוא בתיקיית OneDrive ----------
  // משיכה והחזרה הולכות לפי מטלה: לכל אחת אחראי/ת (A.owners, moodle/claims.py). בדיקה הולכת לפי עבודה (s.claim)
  const TASK_STAGE = { pull: "pull", ret: "return" };
  const ownerOf = (A, stage) => (TASK_STAGE[stage] && A.owners?.[TASK_STAGE[stage]]) || null;

  function ownerCell(A, stage) {
    const o = ownerOf(A, stage), mine = !!o && o.who === myName(), can = LOCAL.me?.set;
    const btn = (act, label, kind) => `<button class="btn ${kind} small" data-act="${act}" data-id="${A.id}" data-stage="${stage}">${label}</button>`;
    if (o) {
      return `<span class="claim ${mine ? "mine" : ""}" title="${esc(`לקח/ה ${when(o.at)}`)}">${mine ? "שלך" : esc(o.who)}</span>`
        + (can ? (mine ? btn("task-release", "שחרר", "ghost") : btn("task-take", "העבר אליי", "ghost")) : "");
    }
    return can ? btn("task-take", "קח", "secondary") : `<span class="muted">—</span>`;
  }

  // מי בודק כמה במטלה: "מתן 12 · אורי 8"
  function peopleHTML(A) {
    const by = {};
    A.subs.forEach((s) => { if (s.claim) by[s.claim.who] = (by[s.claim.who] || 0) + 1; });
    const list = Object.entries(by).sort((x, y) => y[1] - x[1]);
    if (!list.length) return `<span class="muted">אף אחד עוד לא לקח</span>`;
    return list.map(([who, c]) => `<span class="claim ${who === myName() ? "mine" : ""}">${who === myName() ? "שלך" : esc(who)} <b class="num">${c}</b></span>`).join(" ");
  }

  function progressHTML(done, total) {
    const pct = total ? Math.round((100 * done) / total) : 0;
    return `<span class="prog"><span class="track"><i style="width:${pct}%"></i></span><b class="num">${done}<small>/${total}</small></b></span>`;
  }

  function boardHTML(stage) {
    if (!LOCAL.on) return "";
    const all = D.assignments.filter((a) => a.courseId === state.courseId);
    const list = stage === "pull" ? all : all.filter((A) => A.subs.length);
    const rows = list.map((A) => {
      const I = info(A), sel = A.id === state.assignmentId;
      const busy = (A.warnings || []).find((w) => w.startsWith(stage === "ret" ? "העלאה בתהליך" : "משיכה בתהליך"));
      let cells;
      if (stage === "pull") {
        cells = `<td>${A.empty ? `<span class="muted">עוד לא נמשכה</span>` : `<b class="num">${I.subs.length}</b> הגשות<small class="sub">נמשכה ${esc(when(A.pulledAt))}</small>`}
            ${busy ? `<span class="flag">${esc(busy)}</span>` : ""}</td>
          <td class="claim-cell">${ownerCell(A, stage)}</td>`;
      } else if (stage === "grade") {
        const free = I.toGrade.filter((s) => !s.claim).length;
        const St = statOfAssignment(A);
        cells = `<td>${progressHTML(I.graded.length, I.ok.length)}</td>
          <td class="num">${St?.counts?.graded ? fmt(St.grade.mean) : `<span class="muted">—</span>`}</td>
          <td class="col-hide-sm">${peopleHTML(A)}</td>
          <td>${free ? `<b class="num">${free}</b> פנויות` : `<span class="muted">${I.toGrade.length ? "הכל נלקח" : "הכל נבדק"}</span>`}</td>`;
      } else {
        cells = `<td>${I.toReturn.length ? `<b class="num">${I.toReturn.length}</b> מוכנות` : `<span class="muted">${I.graded.length ? "אין חדשות" : "עוד לא נבדקו"}</span>`}
            ${busy ? `<span class="flag">${esc(busy)}</span>` : ""}</td>
          <td class="col-hide-sm">${progressHTML(I.returned.length, I.ok.length)}</td>
          <td class="claim-cell">${ownerCell(A, stage)}</td>`;
      }
      return `<tr class="clickable ${sel ? "sel" : ""}" data-assign="${A.id}" tabindex="0" ${sel ? 'aria-current="true"' : ""}><td><b>${esc(A.title)}</b></td>${cells}</tr>`;
    }).join("");
    const head = {
      pull: "<th>בתיקייה</th><th>אחראי/ת</th>",
      grade: `<th>נבדקו</th><th>ממוצע</th><th class="col-hide-sm">מי בודק</th><th>מה נשאר לקחת</th>`,
      ret: `<th>להעלאה</th><th class="col-hide-sm">הוחזרו</th><th>אחראי/ת</th>`,
    }[stage];
    // מה עוד יש לעשות בשלב הזה, בכל הקורס
    const todo = {
      pull: () => {
        const notYet = all.filter((A) => A.empty).length, noOwner = all.filter((A) => !ownerOf(A, "pull")).length;
        return [`${notYet} עוד לא נמשכו`, `${noOwner} בלי אחראי/ת`];
      },
      grade: () => {
        const free = list.reduce((n, A) => n + info(A).toGrade.filter((s) => !s.claim).length, 0);
        const mine = list.reduce((n, A) => n + info(A).toGrade.filter(isMine).length, 0);
        return [`${free} עבודות פנויות לקחת`, `${mine} שלך מחכות לבדיקה`];
      },
      ret: () => {
        const ready = list.reduce((n, A) => n + info(A).toReturn.length, 0);
        return [`${ready} עבודות מוכנות להעלאה`, `${list.filter((A) => info(A).toReturn.length && !ownerOf(A, "ret")).length} מטלות בלי אחראי/ת`];
      },
    }[stage]();
    const empty = `<tr><td colspan="4"><div class="empty slim">${stage === "pull" ? "אין מטלות בקורס." : "עוד אין מטלות שנמשכו בקורס הזה."}</div></td></tr>`;
    return `<section class="panel board" aria-label="${esc(STAGES[stage].name)} בכל המטלות">
      <div class="panel-head">
        <h2>${esc(STAGES[stage].name)} בכל המטלות</h2>
        <div class="stats">${todo.map((t) => `<span>${esc(t)}</span>`).join("")}</div>
        <span class="meta end">מתעדכן לבד מתיקיית OneDrive · לחיצה על שורה בוחרת מטלה</span>
      </div>
      ${LOCAL.me && !LOCAL.me.set && stage !== "grade" ? `<p class="board-note">כדי לקחת משימות צריך שם: בוחרים אותו בשלב "בדיקה וציון".</p>` : ""}
      <div class="table-wrap"><table class="board-table">
        <thead><tr><th>מטלה</th>${head}</tr></thead>
        <tbody>${rows || empty}</tbody>
      </table></div>
    </section>`;
  }

  // ---------- Tables ----------
  function statusPill(s) { return `<span class="status ${s.status}">${STATUS[s.status]}</span>`; }
  function who(s) {
    // אין שמות: רק מספר ההגשה, כמו בתיקייה
    return `<div class="who"><span class="ini num">${esc(String(s.id).slice(-2))}</span><div><b>${esc(s.name)}</b></div></div>`;
  }
  function scoreHTML(s) {
    if (s.score == null) return `<span class="score none">—</span>`;
    return `<span class="score ${s.score < 60 ? "low" : ""}">${s.score}</span>`;
  }
  function searchBox(stage) {
    return `<label class="search">${ICON.search}<span class="sr">חיפוש הגשה</span><input type="search" id="q-${stage}" data-query="${stage}" value="${esc(state.query[stage])}" placeholder="חיפוש לפי מספר הגשה"></label>`;
  }
  const matches = (s, q) => !q.trim() || s.name.includes(q.trim()) || s.studentId.includes(q.trim());

  function emptyPulled() {
    const A = cur();
    const idField = A.empty ? `
      <div class="field moodle-id"><label for="moodle-id">הקישור למטלה במודל, או רק המספר שאחרי <span dir="ltr">id=</span></label>
        <input id="moodle-id" dir="ltr" inputmode="url" autocomplete="off" data-moodle-id="${A.id}" value="${esc(state.moodleDraft[A.id] || "")}" placeholder="https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id=…"></div>` : "";
    const lead = A.empty
      ? `${esc(A.title)} עוד לא נמשכה. בפעם הראשונה המערכת צריכה לדעת איזו מטלה במודל זו: מדביקים כאן את הקישור לעמוד המטלה. מהפעם הבאה הוא כבר שמור.`
      : "";
    // מה עושים, בשלוש שורות: מי שנכנס בפעם הראשונה צריך לדעת רק את זה
    const how = `<ol class="how-to">
        <li>כרום פתוח, עם התוסף Claude in Chrome. ההתחברות למודל קורית לבד</li>
        <li>לוחצים "משוך הגשות" פעם אחת${A.empty ? ", אחרי שהדבקתם את הקישור" : ""}</li>
        <li>מחכים לבר: הוא מראה כמה נשאר. ההגשות נכנסות לתיקייה המשותפת ומופיעות כאן לכל הצוות</li>
      </ol>`;
    return `<div class="empty"><strong>עוד אין הגשות במטלה הזו</strong>${lead}${how}${idField}
      <div class="empty-act">${stageButton("pull")}${moodleLink(A)}<button class="btn secondary" data-act="open-inbox">${ICON.folder}פתח את תיקיית ההורדות</button></div></div>`;
  }

  // מה קרה במשיכה האחרונה (בגרסה המחוברת)
  function pullReportHTML() {
    // אזהרות מהתיקייה: משיכה שרצה עכשיו אצל מישהו אחר, או עותק כפול של טבלת המפתח
    const warnings = (LOCAL.on && cur()?.warnings) || [];
    const rule = warnings.length ? `<div class="banner warn">${ICON.warn}<div>${warnings.map((w) => `<div>${esc(w)}</div>`).join("")}</div></div>` : "";
    const r = LOCAL.report;
    if (!LOCAL.on || !r || r.assignmentId !== state.assignmentId) return rule;
    const lines = [...(r.notes || []), ...(r.result?.problems || []).map((p) => `דורשת טיפול: ${p}`)];
    return `<section class="panel report">
      <div class="panel-head"><h3>המשיכה האחרונה</h3><span class="meta">${when(r.pulled_at)}</span><span class="end tag ${r.result?.total ? "ok" : ""}">${esc(r.summary)}</span></div>
      ${lines.length ? `<ul class="report-lines">${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}
    </section>${rule}`;
  }

  // ---------- שלב 3 בגרסה המחוברת: העלאה למודל ----------
  // ההעלאה עצמה (Claude in Chrome) רצה בשרת, ברקע. כאן: חלון אישור, התקדמות, עצירה והמשך
  const sendHere = () => {
    const A = cur(), S = LOCAL.sending;
    return !!(A && S && S.course === A.courseFolder && S.assignment === A.folder);
  };
  const sendingHere = () => sendHere() && !!LOCAL.sending.running;
  function sendProgressText() {
    const S = LOCAL.sending;
    if (S.phase === "grades") return "מעלה את הציונים למודל…";
    return `מעלה קובץ ${Math.min((S.done || 0) + 1, S.total || 1)} מתוך ${S.total}…`;
  }
  const numList = (items, max = 20) => (items.length > max ? `${items.slice(0, max).join(", ")} ועוד ${items.length - max}` : items.join(", "));
  // "mismatch" (Moodle imported, the numbers are off) and "stale" are not here on purpose: a person checks Moodle
  // and prepares again, so nothing is imported twice by one click (tests/moodle/test_send_run.py checks this list)
  const RESUMABLE = ["needs_login", "user", "error"];

  function sendPanelHTML() {
    if (!LOCAL.on) return "";
    const A = cur(), S = LOCAL.sending, b = LOCAL.batch;
    if (S?.running) {
      if (!sendHere()) return `<div class="banner">${ICON.spin}<div>העלאה למודל רצה עכשיו במטלה אחרת. אפשר להכין העלאה חדשה כשהיא תסתיים.</div></div>`;
      const pct = S.total ? Math.round((100 * (S.done || 0)) / S.total) : 0;
      return `<section class="panel report send-panel" aria-live="polite">
        <div class="panel-head"><h3>${S.phase === "grades" ? "העלאת ציונים למודל" : "העלאה למודל"}</h3>${S.phase === "grades" ? "" : `<span class="end tag">${S.done || 0} מתוך ${S.total} הועלו</span>`}</div>
        <div class="panel-body">
          <p class="send-line">${ICON.spin}<b>${sendProgressText()}</b></p>
          <div class="send-bar" role="progressbar" aria-label="התקדמות ההעלאה" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div>
          ${LOCAL.stopping ? `<p class="hint">ביקשת לעצור: ההעלאה תיעצר אחרי הקובץ הנוכחי.</p>` : ""}
          ${S.phase === "grades" ? "" : `<div class="send-actions"><button class="btn secondary" data-act="send-stop" ${LOCAL.stopping ? "disabled" : ""}>עצור אחרי הקובץ הנוכחי</button></div>`}
        </div>
      </section>`;
    }
    if (b && b.assignmentId === A.id) {
      const notes = [];
      if (b.not_approved?.length) notes.push(`לידיעה: ${b.not_approved.length} מהן עוד לא סומנו כמאושרות בקובצי הציונים.`);
      if (b.too_big?.length) notes.push(`גדולות מדי ולא ייכללו: ${numList(b.too_big)}`);
      if (b.resubmitted?.length) notes.push(`הוגשו מחדש אחרי הבדיקה ולא ייכללו: ${numList(b.resubmitted)}`);
      const noteList = notes.length ? `<ul class="report-lines send-notes">${notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : "";
      if (!b.zips?.length) {
        return `<section class="panel report send-panel">
          <div class="panel-head"><h3>העלאה למודל</h3></div>
          <div class="panel-body"><p class="send-line"><b>אין עבודות חדשות להעלאה</b></p>${noteList}
            <div class="send-actions"><button class="btn secondary" data-act="send-cancel">סגור</button></div></div>
        </section>`;
      }
      return `<section class="panel report send-panel">
        <div class="panel-head"><h3>אישור העלאה למודל</h3><span class="end tag warn">ממתין לאישור</span></div>
        <div class="panel-body">
          <p class="send-line"><b>${esc(b.summary)}</b></p>
          <ul class="send-zips" dir="ltr">${b.zips.map((z) => `<li><code>${esc(z.name)}</code><span>${z.count} files, ${z.mb} MB</span></li>`).join("")}</ul>
          ${noteList}
          <p class="send-warn">${ICON.warn}<span>אחרי הלחיצה הקבצים נכנסים למודל מיד, בלי מסך אישור נוסף.</span></p>
          <div class="send-actions">
            <button class="btn primary" data-act="send-confirm" ${LOCAL.starting ? "disabled" : ""}>${LOCAL.starting ? ICON.spin : ICON.upload}העלה למודל</button>
            <button class="btn secondary" data-act="send-cancel" ${LOCAL.starting ? "disabled" : ""}>ביטול</button>
          </div>
        </div>
      </section>`;
    }
    const g = LOCAL.gradesAsk;
    if (g && g.assignmentId === A.id) {
      return `<section class="panel report send-panel">
        <div class="panel-head"><h3>אישור העלאת ציונים</h3><span class="end tag warn">ממתין לאישור</span></div>
        <div class="panel-body">
          <p class="send-line"><b>${esc(g.summary)}</b></p>
          <p class="hint">Claude מוריד ממודל את גיליון הציונים, המערכת ממלאת את הציונים לפי המספרים, ו-Claude מעלה אותו. לפני השמירה מודל מראה רשימה של כל השינויים, והם נשמרים רק אם הרשימה מראה בדיוק את מה שציפינו. אחרת שום ציון לא משתנה.</p>
          <div class="send-actions">
            <button class="btn primary" data-act="grades-confirm" ${LOCAL.starting ? "disabled" : ""}>${LOCAL.starting ? ICON.spin : ICON.upload}העלה ציונים</button>
            <button class="btn secondary" data-act="grades-cancel" ${LOCAL.starting ? "disabled" : ""}>ביטול</button>
          </div>
        </div>
      </section>`;
    }
    if (sendHere() && S.stopped && S.phase === "grades") {
      const message = S.stopped === "needs_login" ? "צריך להתחבר שוב למודל בכרום, ואז ללחוץ שוב על 'העלה ציונים'." : S.message;
      return `<section class="panel report send-panel">
        <div class="panel-head"><h3>העלאת הציונים נעצרה</h3></div>
        <div class="panel-body"><p class="send-line">${ICON.warn}<span>${esc(message)}</span></p></div>
      </section>`;
    }
    if (sendHere() && S.stopped) {
      const message = S.stopped === "needs_login" ? "צריך להתחבר שוב למודל בכרום. אחרי ההתחברות לוחצים 'המשך'." : S.message;
      return `<section class="panel report send-panel">
        <div class="panel-head"><h3>ההעלאה נעצרה</h3><span class="end tag warn">${S.done || 0} מתוך ${S.total} הועלו</span></div>
        <div class="panel-body">
          <p class="send-line">${ICON.warn}<span>${esc(message)}</span></p>
          ${RESUMABLE.includes(S.stopped) ? `<div class="send-actions"><button class="btn primary" data-act="send-resume" ${LOCAL.starting ? "disabled" : ""}>${ICON.redo}המשך</button></div>` : ""}
        </div>
      </section>`;
    }
    return "";
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // "העלה N למודל": רק מכינים אצווה ומראים חלון אישור. שום דבר לא עולה לפני ה"כן"
  async function prepareLocalSend() {
    const A = cur();
    if (!A || state.run[A.id] || LOCAL.sending?.running) return;
    const run = (state.run[A.id] = { stage: "ret", steps: RET_LOCAL_STEPS.map(() => "pending"), progress: "מכין את הקבצים…" });
    run.steps[0] = "running";
    LOCAL.batch = null;
    render();
    try {
      const rep = await api("api/upload/prepare", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder }) });
      LOCAL.batch = { ...rep, assignmentId: A.id };
      delete state.run[A.id];
      render();
    } catch (e) {
      delete state.run[A.id];
      render();
      toast(e.message, ICON.warn);
    }
  }

  // "העלה ציונים": שואלים את השרת כמה ציונים יעלו ומראים חלון אישור. שום ציון לא עולה לפני ה"כן"
  async function prepareLocalGrades() {
    const A = cur();
    if (!A) return;
    try {
      const g = await api(`api/grades?course=${encodeURIComponent(A.courseFolder)}&assignment=${encodeURIComponent(A.folder)}`);
      if (g.uploading) toast(`${g.uploading} מעלה את המטלה הזו עכשיו.`, ICON.warn);
      else if (!g.count) toast("אין ציונים חדשים להעלאה.", ICON.check);
      else LOCAL.gradesAsk = { ...g, assignmentId: A.id };
    } catch (e) {
      toast(e.message, ICON.warn);
    }
    render();
  }

  async function startLocalGrades() {
    const A = cur();
    if (!A || LOCAL.starting || LOCAL.sending?.running) return;
    LOCAL.starting = true;
    render();
    try {
      LOCAL.sending = await api("api/grades/start", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder }) });
      LOCAL.gradesAsk = null;
      render();
      followSend();
    } catch (e) {
      toast(e.message, ICON.warn);
    } finally {
      LOCAL.starting = false;
      render();
    }
  }

  // אחרי ה"כן" (או "המשך"): מתחילים, ושואלים את השרת על המצב כל 2 שניות, כמו בבדיקה
  async function startLocalSend(batchId) {
    const A = cur();
    if (!A || !batchId || LOCAL.starting || LOCAL.sending?.running) return;
    LOCAL.starting = true;
    render();
    try {
      LOCAL.sending = await api("api/upload/start", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder, batchId }) });
      LOCAL.batch = null;
      LOCAL.stopping = false;
      render();
      followSend();
    } catch (e) {
      toast(e.message, ICON.warn);
    } finally {
      LOCAL.starting = false;
      render();
    }
  }

  async function followSend() {
    if (LOCAL.polling) return;
    LOCAL.polling = true;
    let S = LOCAL.sending, shown = S?.done, failures = 0;
    try {
      while (S?.running) {
        await sleep(2000);
        try { S = await api("api/upload"); failures = 0; } catch (e) { if (++failures >= 3) throw e; continue; }
        LOCAL.sending = S;
        render();
        if (S.done !== shown) { shown = S.done; await loadLocal(); }  // כל ZIP שעלה מסמן את העבודות שלו "הוחזרה"
      }
    } catch (e) {
      toast(`אי אפשר לקבל את מצב ההעלאה: ${e.message}`, ICON.warn);
    } finally {
      LOCAL.polling = false;
      LOCAL.stopping = false;
    }
    await loadLocal();
    if (S && !S.running) toast(S.message || (S.stopped ? "ההעלאה נעצרה" : "ההעלאה הסתיימה"), S.stopped ? ICON.warn : ICON.check);
  }

  async function stopLocalSend() {
    if (!LOCAL.sending?.running || LOCAL.stopping) return;
    LOCAL.stopping = true;
    render();
    try {
      const S = await api("api/upload/stop", { method: "POST" });
      if (!LOCAL.polling) LOCAL.sending = S;
    } catch (e) {
      LOCAL.stopping = false;
      render();
      toast(e.message, ICON.warn);
    }
  }

  // ---------- מוכנות המחשב להעלאה ----------
  // כל אחד בצוות מעלה מהמחשב שלו. "העלה N למודל" בודק קודם שהמחשב הזה מוכן (Claude Code מותקן, מחובר לחשבון שלך,
  // והכרום והמודל מחוברים), מחבר אוטומטית מה שאפשר, ורק אז עובר לחלון האישור. אותה רשימה מופיעה גם בלשונית "חיבור למודל".
  const READY_POLL_MS = 3000;
  const MOODLE_LOGIN_URL = "https://moodle.bgu.ac.il/moodle/login/index.php";
  const CHROME_EXT_URL = "https://claude.ai/chrome";
  const readyUrl = (A) => `api/ready?course=${encodeURIComponent(A.courseFolder)}&assignment=${encodeURIComponent(A.folder)}`;
  const readyAssignment = (rd) => D.assignments.find((a) => a.id === rd.assignmentId);
  const allReady = (d) => !!d && d.installed && d.logged_in && d.chrome === true && d.moodle === true;
  const newReady = (A, flow, then = "send") => ({
    assignmentId: A.id, flow, then, data: null, looping: false, fetchedAt: 0, checking: false, checkTried: false, checkError: "",
    loginTried: false, loginError: "", installAsk: false, installTried: false, installError: "",
  });

  // הלחיצה על "העלה N למודל". אם הכול כבר מוכן (גם לפי הזיכרון של 30 הדקות), ממשיכים ישר להכנה
  async function startSendFlow(then = "send") {
    const A = cur();
    if (!A || state.run[A.id] || LOCAL.sending?.running || LOCAL.starting || (LOCAL.rd?.flow && LOCAL.rd.assignmentId === A.id)) return;
    LOCAL.batch = null;
    LOCAL.gradesAsk = null;
    const rd = (LOCAL.rd = newReady(A, true, then));
    // הציונים: כפתור משלהם מראה "בודק שהמחשב מוכן…", וכפתור הקבצים לא מסתובב
    if (then === "send") state.run[A.id] = { stage: "ret", steps: RET_LOCAL_STEPS.map(() => "pending"), progress: "בודק שהמחשב מוכן…" };
    render();
    try {
      rd.data = await api(readyUrl(A));
    } catch (e) {
      delete state.run[A.id];
      LOCAL.rd = null;
      render();
      toast(e.message, ICON.warn);
      return;
    }
    delete state.run[A.id];
    if (allReady(rd.data)) { readyDone(rd); return; }
    render();
    readyLoop(rd);
  }

  // שואל את השרת על המוכנות כל 3 שניות כל עוד משהו קורה (התקנה, התחברות, בדיקה). בזרימה, גם מחבר את מה שחסר
  async function readyLoop(rd) {
    if (rd.looping) return;
    rd.looping = true;
    try {
      while (LOCAL.rd === rd && rd.assignmentId === state.assignmentId) {
        rd.fetchedAt = Date.now();
        const d = (rd.data = await api(readyUrl(readyAssignment(rd))));
        let acted = false;
        if (rd.flow) {
          if (allReady(d)) { readyDone(rd); break; }
          if (d.installed && !d.logged_in && !d.login_running && !rd.loginTried) { acted = true; await startReadyLogin(rd, false); }
          if (d.installed && d.logged_in && d.chrome == null && !rd.checking && !rd.checkTried) { acted = true; rd.checkTried = true; checkReady(rd); }
        }
        render();
        // עוד סיבוב אחרי שהתחברות או התקנה נגמרו: ככה רואים את התוצאה שלהן גם אם הסטטוס התעדכן באיחור
        const running = !!(d.installing || d.login_running);
        const justEnded = rd.wasRunning && !running;
        rd.wasRunning = running;
        if (!(acted || running || rd.checking || justEnded)) break;
        await sleep(READY_POLL_MS);
      }
    } catch (e) {
      rd.flow = false;
      toast(e.message, ICON.warn);
    } finally {
      rd.looping = false;
      if (rd.assignmentId !== state.assignmentId) rd.flow = false;  // עברו למטלה אחרת באמצע: לא משאירים זרימה תקועה
      render();
    }
  }

  // פותח התחברות ל-Claude בדפדפן (השרת מריץ `claude auth login`). restart: "נסה שוב"
  async function startReadyLogin(rd, restart) {
    rd.loginTried = true;
    rd.loginError = "";
    try {
      const r = await api("api/claude/login", { method: "POST", body: JSON.stringify({ restart }) });
      if (!r.started && !r.running) rd.loginError = r.message;
      if (r.running && rd.data) rd.data = { ...rd.data, login_running: true };  // עד התשובה הבאה של השרת
    } catch (e) {
      rd.loginError = e.message;
    }
    render();
    readyLoop(rd);
  }

  // רק אחרי שהאדם אישר בלחיצה
  async function startReadyInstall(rd) {
    rd.installAsk = false;
    rd.installTried = true;
    rd.installError = "";
    try {
      const r = await api("api/claude/install", { method: "POST", body: "{}" });
      if (!r.started && !r.running) rd.installError = r.message;
      if (r.running && rd.data) rd.data = { ...rd.data, installing: true };
    } catch (e) {
      rd.installError = e.message;
    }
    render();
    readyLoop(rd);
  }

  // בדיקת כרום ומודל: ריצה קצרה של Claude (כחצי דקה), בלי להעלות כלום
  async function checkReady(rd) {
    if (rd.checking) return;
    rd.checking = true;
    rd.checkError = "";
    render();
    readyLoop(rd);
    try {
      const A = readyAssignment(rd);
      rd.data = await api("api/ready/check", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder }) });
      if (rd.data.check_error) rd.checkError = rd.data.check_error;  // הבדיקה לא נענתה (זמן קצוב, שגיאה): מציגים את ההודעה שלה
    } catch (e) {
      rd.checkError = e.message;
    } finally {
      rd.checking = false;
      render();
    }
    readyLoop(rd);
  }

  // בלשונית "חיבור למודל": מצב המוכנות של המטלה הנוכחית, בלי לחבר שום דבר לבד
  function ensureReady() {
    const A = cur();
    let rd = LOCAL.rd;
    if (!rd || rd.assignmentId !== A.id) rd = LOCAL.rd = newReady(A, false);
    if (!rd.looping && Date.now() - rd.fetchedAt > 20000) readyLoop(rd);
    return rd;
  }

  // ---------- משיכה דרך ה-Claude של מי שלוחץ ----------
  // "משוך" עובר באותה רשימת מוכנות כמו ההעלאה: כל אחד בצוות שלוחץ מושך דרך Claude Code שמותקן ומחובר במחשב שלו,
  // והתוסף Claude in Chrome בכרום שלו. מה שחסר מותקן או מתחבר כאן (התחברות נפתחת לבד; התקנה רק אחרי "כן"),
  // וכשהכול ✓ המשיכה מתחילה בלי לחיצה נוספת. בדיקה מ-30 הדקות האחרונות מספיקה, אז במחשב מחובר זה מיידי.
  // הגשה שעוד אין לה תיקייה (הגשה ריקה, משיכה ראשונה) הולכת ישר לשרת, וגם שם require_moodle בודק את כרום ומודל
  async function startPullFlow({ full = false, limit = 0 } = {}) {
    const A = cur();
    if (!A || state.run[A.id] || !LOCAL.health?.root || (LOCAL.rd?.flow && LOCAL.rd.assignmentId === A.id)) return;
    if (A.empty) { runLocalPull(full, limit); return; }
    const rd = (LOCAL.rd = newReady(A, true, "pull"));
    rd.full = full;
    rd.limit = limit;
    render();
    try {
      rd.data = await api(readyUrl(A));
    } catch (e) {
      LOCAL.rd = null;
      render();
      toast(e.message, ICON.warn);
      return;
    }
    if (allReady(rd.data)) { readyDone(rd); return; }
    render();
    readyLoop(rd);
  }

  // הכול ✓: ממשיכים למה שביקשו, משיכה או הכנת ההעלאה
  function readyDone(rd) {
    rd.flow = false;
    render();
    if (rd.then === "pull") runLocalPull(rd.full, rd.limit);
    else if (rd.then === "grades") prepareLocalGrades();
    else prepareLocalSend();
  }

  // הרשימה עצמה: ✓ מוכן, ✗ חסר (עם כפתור), ⏳ בעבודה. משמשת גם את חלון ההכנה וגם את הלשונית
  function readyChecklistHTML(rd) {
    const d = rd.data;
    if (!d) return `<p class="send-line">${ICON.spin}<span>בודק את המחשב…</span></p>`;
    const uploading = !!LOCAL.sending?.running;
    const row = (kind, title, body = "", actions = "") => `<li class="ready-row ${kind}">
      <span class="ready-mark">${kind === "ok" ? ICON.check : kind === "bad" ? ICON.warn : kind === "busy" ? ICON.spin : "<i></i>"}</span>
      <div class="ready-text"><b>${title}</b>${body ? `<div class="ready-body">${body}</div>` : ""}</div>
      ${actions ? `<div class="ready-actions">${actions}</div>` : ""}</li>`;
    const btn = (act, label, primary = false) => `<button class="btn ${primary ? "primary" : "secondary"} small" data-act="${act}" ${uploading ? "disabled" : ""}>${label}</button>`;
    const link = (href, label) => `<a class="btn secondary small" href="${href}" target="_blank" rel="noopener">${label}</a>`;

    let install;
    if (d.installed) install = row("ok", "Claude Code מותקן");
    else if (d.installing) install = row("busy", "Claude Code מותקן", "מתקין ברקע. זה לוקח בערך דקה.");
    else if (rd.installAsk) {
      install = row("bad", "Claude Code מותקן", "להתקין את Claude Code מהאתר הרשמי של Anthropic?",
        `${btn("ready-install-yes", "כן, התקן", true)}${btn("ready-install-no", "לא")}`);
    } else {
      install = row("bad", "Claude Code מותקן",
        esc(rd.installError || (rd.installTried ? "ההתקנה הסתיימה, אבל Claude Code עדיין לא נמצא. אפשר לנסות שוב." : "Claude Code לא נמצא במחשב הזה.")),
        btn("ready-install-ask", "התקן את Claude Code", true));
    }

    let login;
    if (!d.installed) login = row("wait", "מחובר ל-Claude", "אחרי ההתקנה.");
    else if (d.logged_in) login = row("ok", "מחובר ל-Claude");
    else if (d.login_running) {
      login = row("busy", "מחובר ל-Claude",
        `נפתח דף התחברות בדפדפן. התחבר עם החשבון שלך ב-Claude (של האוניברסיטה) ולחץ Authorize. המערכת תזהה לבד כשזה הסתיים.
         <div class="ready-tip">אם הדף אומר שצריך מנוי Max או Pro, הדפדפן מחובר לחשבון Claude אחר: היכנס ל-claude.ai, התנתק, ולחץ 'נסה שוב'.</div>`,
        btn("ready-login-retry", "נסה שוב"));
    } else {
      login = row("bad", "מחובר ל-Claude",
        esc(rd.loginError || (rd.loginTried ? "ההתחברות לא הסתיימה. אפשר לנסות שוב." : "עוד לא מחוברים לחשבון Claude.")),
        btn("ready-login-retry", rd.loginTried ? "נסה שוב" : "התחבר ל-Claude", true));
    }

    let chrome;
    if (!d.installed || !d.logged_in) chrome = row("wait", "הכרום והמודל מחוברים", "אחרי ההתחברות ל-Claude.");
    else if (rd.checking) chrome = row("busy", "הכרום והמודל מחוברים", "בודק את הכרום ואת המודל (כחצי דקה)…");
    else if (d.chrome === true && d.moodle === true) chrome = row("ok", "הכרום והמודל מחוברים", d.checked_at ? `נבדק ${when(d.checked_at)}` : "");
    else if (rd.checkError) chrome = row("bad", "הכרום והמודל מחוברים", esc(rd.checkError), btn("ready-check", "בדוק שוב", true));
    else if (d.chrome === false) {
      chrome = row("bad", "הכרום והמודל מחוברים", `צריך את התוסף Claude in Chrome בכרום. אחרי ההתקנה והחיבור שלו לוחצים 'בדוק שוב'.${d.message ? `<div>${esc(d.message)}</div>` : ""}`,
        `${link(CHROME_EXT_URL, "פתח את claude.ai/chrome")}${btn("ready-check", "בדוק שוב", true)}`);
    } else if (d.moodle === false) {
      chrome = row("bad", "הכרום והמודל מחוברים", `צריך להתחבר למודל בכרום. אחרי ההתחברות לוחצים 'בדוק שוב'.${d.message ? `<div>${esc(d.message)}</div>` : ""}`,
        `${link(MOODLE_LOGIN_URL, "פתח את מודל")}${btn("ready-check", "בדוק שוב", true)}`);
    } else chrome = row("wait", "הכרום והמודל מחוברים", "עוד לא נבדק. הבדיקה לא מעלה כלום למודל.", btn("ready-check", "בדוק חיבור"));

    return `<ul class="ready-list">${install}${login}${chrome}</ul>`;
  }

  // חלון ההכנה: מופיע אחרי הלחיצה על "העלה N למודל" (then: "send") או על "משוך" (then: "pull"), ונעלם כשהכול ✓
  // (ואז עוברים להכנת האצווה, או שהמשיכה מתחילה)
  function readyPanelHTML(then = "send") {
    const rd = LOCAL.rd;
    const same = rd?.then === then || (then === "send" && rd?.then === "grades");  // הציונים: אותו חלון בדף ההחזרה
    if (!LOCAL.on || !rd?.flow || !same || rd.assignmentId !== cur()?.id || !rd.data) return "";
    const title = then === "pull" ? "לפני המשיכה: מחברים את המחשב הזה ל-Claude שלך" : "לפני ההעלאה: בודקים שהמחשב הזה מוכן";
    return `<section class="panel report send-panel ready-panel" aria-live="polite">
      <div class="panel-head"><h3>${title}</h3><button class="btn ghost small end" data-act="ready-close">ביטול</button></div>
      ${then === "pull" ? `<p class="hint" style="margin:0 16px">המשיכה רצה דרך Claude Code שבמחשב הזה ודרך התוסף Claude in Chrome בכרום שלך, עם ההתחברות שלך למודל. כשהכול כאן ✓ היא מתחילה לבד.</p>` : ""}
      <div class="panel-body">${readyChecklistHTML(rd)}</div>
    </section>`;
  }

  function pullList() {
    const A = cur(), I = info(A);
    if (!I.subs.length) return `${pullReportHTML()}<section class="panel">${emptyPulled()}</section>`;
    const rows = I.subs.filter((s) => matches(s, state.query.pull)).sort((a, b) => (b.submittedAt || "").localeCompare(a.submittedAt || ""));
    return `${pullReportHTML()}
      <section class="panel">
        <div class="panel-head">
          <div class="stats">
            <span><b class="num">${I.subs.length}</b> הגשות</span>
            <span><b class="num">${I.files}</b> קבצים</span>
          </div>
          <div class="end">${searchBox("pull")}</div>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>הגשה</th><th>זמן הקובץ</th><th class="col-hide">קבצים</th><th>מצב</th></tr></thead>
          <tbody>${rows.map((s) => `
            <tr class="${s.fresh ? "flash" : ""}">
              <td>${who(s)}</td>
              <td class="muted num">${when(s.submittedAt)}</td>
              <td class="col-hide"><div class="files">${s.files.filter((f) => !f.marked).map((f) => `<span class="file">${/\.(jpe?g|png)$/i.test(f.name) ? ICON.img : ICON.file}<span dir="ltr">${esc(f.name)}</span></span>`).join("")}</div></td>
              <td>${statusPill(s)}</td>
            </tr>`).join("") || `<tr><td colspan="4"><div class="empty slim">אין תוצאות לחיפוש הזה.</div></td></tr>`}
          </tbody>
        </table></div>
      </section>`;
  }

  // ---------- חלוקת העבודה בצוות ----------
  function nameFormHTML() {
    const value = state.nameDraft ?? (state.renaming ? myName() : "");
    return `<section class="panel team">
      <div class="panel-head"><h3>חלוקת העבודה בצוות</h3>${state.renaming ? `<button class="btn ghost small end" data-act="rename-cancel">ביטול</button>` : ""}</div>
      <div class="panel-body">
        <p class="team-lead">כדי לחלק את העבודות בין חברי הצוות, המערכת צריכה לדעת מי בודק במחשב הזה. השם יופיע אצל כולם ליד העבודות שלוקחים.</p>
        <div class="team-act">
          <div class="field"><label for="my-name">השם שלך</label><input id="my-name" data-name-draft maxlength="40" autocomplete="name" value="${esc(value)}" placeholder="למשל: מתן"></div>
          <button class="btn primary small" data-act="save-name">שמור</button>
        </div>
      </div>
    </section>`;
  }

  function teamHTML() {
    const A = cur(), I = info(A);
    if (!LOCAL.on || !LOCAL.me) return "";
    if (!LOCAL.me.set || state.renaming) return nameFormHTML();
    const people = {};
    I.subs.forEach((s) => {
      if (!s.claim) return;
      const p = (people[s.claim.who] ||= { all: 0, left: 0 });
      p.all++;
      if (s.status === "pulled") p.left++;
    });
    const mine = people[myName()] || { all: 0, left: 0 };
    const others = Object.entries(people).filter(([who]) => who !== myName()).sort((x, y) => y[1].all - x[1].all);
    const free = I.toGrade.filter((s) => !s.claim).length;
    const count = Math.max(1, Math.min(state.teamCount || 1, free || 1));
    return `<section class="panel team" aria-live="polite">
      <div class="panel-head">
        <h3>חלוקת העבודה בצוות</h3>
        <span class="meta">בודק/ת במחשב הזה: <b>${esc(myName())}</b></span>
        <button class="btn ghost small end" data-act="rename">שינוי שם</button>
      </div>
      <div class="panel-body">
        <div class="team-people">
          <span class="person mine"><b class="num">${mine.all}</b> שלך${mine.left ? ` · ${mine.left} עוד לא נבדקו` : ""}</span>
          <span class="person free"><b class="num">${free}</b> פנויות</span>
          ${others.map(([who, p]) => `<span class="person"><b class="num">${p.all}</b> ${esc(who)}${p.left ? ` · ${p.left} עוד לא נבדקו` : ""}</span>`).join("")}
        </div>
        <div class="team-act">
          <label class="team-count">קח <input type="number" id="team-count" data-team-count min="1" max="${free || 1}" value="${count}" ${free ? "" : "disabled"}> עבודות פנויות</label>
          <button class="btn primary small" data-act="claim-next" ${free ? "" : "disabled"}>סמן אותן עליי</button>
          ${mine.left ? `<button class="btn secondary small" data-act="release-mine">שחרר ${plural(mine.left, "עבודה אחת שלי", "עבודות שלי")} שלא נבדקו</button>` : ""}
        </div>
        <p class="team-note">אפשר גם ללחוץ "קח" ליד עבודה בטבלה. הסימון נשמר בתיקיית OneDrive ומגיע לשאר הצוות תוך כמה שניות עד דקה. "בדוק" שואל כמה עבודות לבדוק, משלים מהפנויות ומסמן אותן עליך, ובודק רק את מה שעליך.</p>
      </div>
    </section>`;
  }

  function claimCell(s) {
    if (s.claim) {
      const mine = isMine(s);
      const release = mine ? `<button class="btn ghost small" data-act="release" data-id="${esc(s.id)}" title="להחזיר את העבודה לפנויות">שחרר</button>` : "";
      return `<span class="claim ${mine ? "mine" : ""}" title="${esc(`לקח/ה ${when(s.claim.at)}`)}">${mine ? "שלך" : esc(s.claim.who)}</span>${release}`;
    }
    if (s.status === "pulled" && LOCAL.me?.set) return `<button class="btn secondary small" data-act="claim" data-id="${esc(s.id)}">קח</button>`;
    return `<span class="muted">—</span>`;
  }

  const GRADE_PAGE = 50;
  function gradeList() {
    const A = cur(), I = info(A);
    if (!I.subs.length) return `<section class="panel">${emptyPulled()}</section>`;
    const qs = rubric().questions;
    const team = [["mine", "שלי", I.subs.filter(isMine).length], ["free", "פנויות", I.toGrade.filter((s) => !s.claim).length]];
    const opts = [["all", "הכל", I.subs.length], ...(LOCAL.me?.set ? team : []), ...Object.keys(STATUS).map((k) => [k, STATUS[k], I.subs.filter((s) => s.status === k).length])]
      .filter(([k, , c]) => k === "all" || c);
    if (!opts.some(([k]) => k === state.filter)) state.filter = "all";
    const shown = (s) => state.filter === "all" || (state.filter === "mine" ? isMine(s) : state.filter === "free" ? !s.claim && s.status === "pulled" : s.status === state.filter);
    const found = I.subs.filter((s) => shown(s) && matches(s, state.query.grade));
    // עד 1,000 שורות בטבלה מכבידות על הדף: מציגים חמישים, ו"עוד" מוסיף. משנים סינון, חיפוש או מטלה: חוזרים לחמישים
    const key = `${A.id}|${state.filter}|${state.query.grade}`;
    if (state.gradeKey !== key) { state.gradeKey = key; state.gradeShown = GRADE_PAGE; }
    const rows = found.slice(0, state.gradeShown);
    const more = found.length - rows.length;
    const K = A.officialKey;
    const keyLine = `<div class="notice ${K ? "ok" : ""}">${K ? ICON.check : ICON.warn}<div>${K
      ? `<b>הבדיקה הולכת לפי המכוון הרשמי</b>${K.at ? ` (הועלה ${esc(when(K.at))})` : ""}. כדאי להתחיל ב"בדוק" על כמה עבודות ולעבור עליהן לפני שבודקים את כולן.`
      : `<b>עוד אין מכוון רשמי.</b> כשהוא מגיע מהמרצה מעלים אותו`} <button class="btn ghost small" data-tab="grade:instr">${K ? "לצפייה במכוון" : "בלשונית \"מחוון והנחיות\""}</button></div></div>`;
    return `${teamHTML()}
      ${keyLine}
      <section class="panel">
        <div class="panel-head">
          <div class="chips" role="group" aria-label="סינון לפי מצב">
            ${opts.map(([k, label, c]) => `<button class="chip" data-filter="${k}" aria-pressed="${state.filter === k}">${label}<span class="c num">${c}</span></button>`).join("")}
          </div>
          <div class="end">${searchBox("grade")}</div>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>הגשה</th><th>מצב</th><th>בודק/ת</th><th>ציון</th>${qs.map((q) => `<th class="col-hide qcol">ש${q.n}</th>`).join("")}<th class="col-hide-sm">הערות</th></tr></thead>
          <tbody>${rows.map((s) => {
            const lost = s.q ? s.q.filter((v, i) => v < qs[i].pts).length : 0;
            return `<tr data-open="${s.id}" tabindex="0" class="clickable ${s.fresh ? "flash" : ""} ${isMine(s) ? "mine" : ""}" aria-label="פתח את העבודה של ${esc(s.name)}">
              <td>${who(s)}</td>
              <td>${statusPill(s)}</td>
              <td class="claim-cell">${claimCell(s)}</td>
              <td><span class="score-cell">${scoreHTML(s)}${editLinkHTML(s)}</span></td>
              ${qs.map((q, i) => `<td class="col-hide qcol num">${s.q ? `<span class="qv ${s.q[i] < q.pts ? "lost" : ""}">${s.q[i]}</span>` : `<span class="muted">·</span>`}</td>`).join("")}
              <td class="col-hide-sm">${s.issue ? `<span class="flag">${esc(s.issue)}</span>` : needsReview(s) ? `<span class="flag" title="${esc(s.failed || s.review)}">לבדיקה ידנית: ${esc(REVIEW_KIND[kindOf(s)][0])}</span>` : s.q ? (lost ? `<span class="pen-count">${ICON.pen}${plural(lost, "הערה אחת", "הערות")}</span>` : `<span class="muted">ללא הערות</span>`) : `<span class="muted">—</span>`}</td>
            </tr>`;
          }).join("") || `<tr><td colspan="${5 + qs.length}"><div class="empty slim">אין עבודות שמתאימות לסינון.</div></td></tr>`}
          </tbody>
        </table></div>
        ${more > 0 ? `<div class="panel-body more-row"><span class="muted">מוצגות <b class="num">${rows.length}</b> מתוך <b class="num">${found.length}</b></span>
          <button class="btn secondary small" data-act="grade-more">הצג עוד ${Math.min(more, GRADE_PAGE)}</button></div>` : ""}
      </section>`;
  }

  function returnList() {
    const I = info();
    if (!I.subs.length) return `<section class="panel">${emptyPulled()}</section>`;
    const list = [...I.toReturn, ...I.returned].filter((s) => matches(s, state.query.ret));
    if (!I.graded.length) {
      return `${readyPanelHTML()}${sendPanelHTML()}<section class="panel"><div class="empty"><strong>עוד אין עבודות בדוקות</strong>אחרי שלב הבדיקה, העבודות המסומנות יופיעו כאן מוכנות להעלאה למודל.<div class="empty-act">${stageButton("ret")}</div></div></section>`;
    }
    return `${readyPanelHTML()}${sendPanelHTML()}
      <section class="panel">
        <div class="panel-head">
          <div class="stats">
            <span><b class="num">${I.toReturn.length}</b> מוכנות להעלאה</span>
            <span><b class="num">${I.returned.length}</b> הוחזרו</span>
            <span><b class="num">${I.toGrade.length}</b> עוד לא נבדקו</span>
          </div>
          <div class="end">${searchBox("ret")}</div>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>הגשה</th><th>ציון</th><th>מצב</th></tr></thead>
          <tbody>${list.map((s) => `
            <tr data-open="${s.id}" tabindex="0" class="clickable ${s.fresh ? "flash" : ""}">
              <td>${who(s)}</td>
              <td>${scoreHTML(s)}</td>
              <td>${s.status === "returned" ? `<span class="check ok">${ICON.check}הוחזרה</span>` : `<span class="status graded">מוכנה להעלאה</span>`}</td>
            </tr>`).join("") || `<tr><td colspan="3"><div class="empty slim">אין תוצאות לחיפוש הזה.</div></td></tr>`}
          </tbody>
        </table></div>
        <div class="panel-body"><button class="btn secondary small" data-act="open-upload">${ICON.folder}פתח את התיקייה "3 - Ready to upload to Moodle"</button></div>
      </section>`;
  }

  // ---------- Instruction + connection tabs ----------
  function instrBox(stage, title, help) {
    return `
      <section class="panel instr">
        <div class="panel-head"><h2>${title}</h2><span class="saved" id="saved-${stage}">נשמר במכשיר הזה</span></div>
        <div class="panel-body">
          <p class="lead">${help}</p>
          <label class="sr" for="instr-${stage}">${title}</label>
          <textarea id="instr-${stage}" data-instr="${stage}" rows="9" class="instr-text">${esc(state.instr[stage])}</textarea>
          <div class="row-end">
            <button class="btn ghost small" data-reset="${stage}">${ICON.redo}החזר לברירת המחדל</button>
          </div>
        </div>
      </section>`;
  }

  function sw(id, label, desc, on, key) {
    return `<div class="switch-row"><div><b id="${id}-l">${label}</b><small>${desc}</small></div><span class="switch"><input type="checkbox" id="${id}" ${on ? "checked" : ""} aria-labelledby="${id}-l" ${key ? `data-set="${key}"` : ""}><i></i></span></div>`;
  }

  function secretField(name, where, isSet = false) {
    return `<div class="secret">${ICON.lock}<div><b dir="ltr">${name}</b><small>${where}</small></div><span class="tag ${isSet ? "ok" : "warn"}">${isSet ? "מוגדר" : "לא הוגדר"}</span></div>`;
  }

  // שלב 1: מה קורה בלחיצה על "משוך הגשות" (moodle/ingest.py, moodle/anonymize.py)
  function pullInstr() {
    const A = cur();
    return `<div class="split wide-first">
      <section class="panel">
        <div class="panel-head"><h2>מה קורה כשמושכים הגשות</h2></div>
        <div class="panel-body">
          <ol class="todo">
            <li><b>Claude בכרום מוריד ממודל.</b> בכרום שלך, עם ההתחברות שלך: עמוד ההגשות של המטלה ← "הורדת כל ההגשות", כש"הורדת הגשות בתיקיות" מסומן. הוא לא מקליד כלום ולא משנה שום הגדרה של המטלה. ה-ZIP נשמר בתיקיית ההורדות, והמערכת מחכה עד שההורדה מסתיימת.</li>
            <li><b>משיכה חוזרת מורידה רק מה שהשתנה.</b> אחרי המשיכה הראשונה, Claude מבקש ממודל רק את מי שהגיש או החליף קובץ מאז המשיכה הקודמת: כמה דקות במקום כמה GB. כל השאר נשארים כמו שהם. "משוך הכול מחדש" מוריד את כולם.</li>
            <li><b>בלילה זה קורה לבד.</b> מועד ההגשה נקרא ממודל בכל משיכה. בלילה שאחריו (00:05), ובכל לילה בשבוע שאחריו (הגשות מאוחרות והארכות), המחשב של מי שלקח את "משיכה" מושך בעצמו: פותח את כרום אם הוא סגור, ומנסה שוב אחרי חצי שעה אם מודל לא ענה. רק המחשב שלו, כדי ששני מחשבים לא ימשכו יחד.</li>
            <li><b>רק ממודל האמיתי.</b> לפני כל משיכה המערכת בודקת שהתוסף של Claude בכרום מחובר ושכרום מחובר למודל. אם משהו לא מחובר, לא מושכים כלום ומקבלים הודעה מה לתקן. ZIP שכבר נמצא בתיקיית ההורדות לא נקלט: כל משיכה מורידה ממודל מחדש.</li>
            <li><b>שומרת אותו רק במחשב הזה</b>, בתיקייה <code dir="ltr">Moodle originals/Backup - Moodle downloads</code>, ולא ב-OneDrive (יש בו שמות, וכמה GB בכל משיכה). כל הורדה נשמרת, כך שהורדה מאוחרת לא מוחקת את הקודמת. בתיקיית המטלה נרשמת שורה ב-<code dir="ltr">Pull log.csv</code>: מתי, מי וכמה.</li>
            <li><b>אפשר למשוך רק חלק.</b> בשדה "כמה הגשות?" ליד הכפתור כותבים מספר (למשל 30, לניסוי): נמשכות ההגשות הראשונות בטבלת ההגשות במודל. משיכה בלי מספר מביאה אחר כך את כל השאר, ומי שכבר נמשך שומר על המספר שלו.</li>
            <li><b>מחלצת אותו עם 7-Zip במחשב שלך בלבד.</b> התיקיות עם שמות הסטודנטים לא עולות ל-OneDrive.</li>
            <li><b>נותנת לכל סטודנט מספר קבוע</b> (0001, 0002…) ומעתיקה את הקבצים ל-"1 - Submissions to grade". מי שכבר נמשך שומר על המספר שלו, ומי שהגיש מאז מקבל את המספר הפנוי הבא.</li>
            <li><b>מעדכנת את טבלת המפתח</b> (מספר ← מזהה המשתתף במודל). זה המקום היחיד שמקשר מספר לסטודנט, והוא נשאר בתיקיית המטלה.</li>
          </ol>
          <div class="row-start">
            ${moodleLink(A, "small")}
            <button class="btn secondary small" data-act="open-inbox">${ICON.folder}פתח את תיקיית ההורדות</button>
            ${LOCAL.on && !A.empty && A.pulledAt ? `<button class="btn secondary small" data-act="pull-full">משוך הכול מחדש</button>` : ""}
          </div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-head"><h3>מה נשמר ב-OneDrive</h3></div>
        <div class="panel-body">
          <dl class="fields">
            <div><dt>הגשות</dt><dd>הקבצים של כל סטודנט תחת המספר שלו: 0001.pdf, ואם יש עוד קובץ 0001-2.pdf. בלי שמות</dd></div>
            <div><dt>ה-ZIP</dt><dd>בדיוק כמו שמודל נתן אותו, לכל הורדה</dd></div>
            <div><dt>טבלת המפתח</dt><dd>מספר ← מזהה משתתף במודל. Claude לא רואה אותה</dd></div>
            <div><dt>נעילה</dt><dd>בזמן משיכה נוצר "Pull in progress.txt", ומשיכה נוספת של אותה מטלה מחכה</dd></div>
          </dl>
        </div>
      </section>
    </div>`;
  }

  // מודל: בלי API ובלי סיסמאות. Claude in Chrome עובד בכרום של האדם, עם החשבון שלו
  function pullConn() {
    const A = cur(), rd = ensureReady();
    return `<section class="panel">
      <div class="panel-head"><h2>חיבור למודל</h2>${allReady(rd.data) ? `<span class="end tag ok">מחובר</span>` : ""}</div>
      <div class="panel-body">
        <p class="lead">למודל של האוניברסיטה אין API, ולכן המערכת לא מתחברת אליו עם מפתח. מודל נפתח בכרום שלך, עם החשבון שלך, ו-Claude in Chrome עובד בו. אף סיסמה לא נכנסת למערכת.</p>
        <p class="lead">במשיכה Claude בכרום מוריד את ה-ZIP של כל ההגשות, והמערכת קולטת אותו מתיקיית ההורדות. בהחזרה Claude בכרום מעלה את העבודות המסומנות. בשני המקרים צריך את אותה רשימת מוכנות שלמטה.</p>
        <div class="row-start" style="margin:0 0 16px">
          ${moodleLink(A, "small")}
        </div>
        ${readyChecklistHTML(rd)}
      </div>
    </section>`;
  }

  function promptPreview() {
    const A = cur(), R = rubric();
    return [
      `בדיקה של ${A.title}, ${course().name}.`,
      "",
      "הנחיות:",
      state.instr.grade,
      "",
      `השאלות והניקוד (מתוך ${A.maxGrade || 100}):`,
      ...R.questions.map((q) => `${q.req || `שאלה ${q.n}`}: ${q.pts} נק'${q.criteria ? `. ${q.criteria}` : ""}`),
      "",
      ...(A.officialKey ? ["המכוון הרשמי של המרצה מצורף, והבדיקה הולכת לפיו (הוא גובר על המחוון)."] : []),
      state.claude.sendSolution && A.solution ? "מצורפים: הפתרון הרשמי ועמודי ההגשה כתמונות." : "מצורפים: עמודי ההגשה כתמונות.",
      "Claude מחזיר JSON לפי הסכמה.",
    ].join("\n");
  }

  const SCHEMA = `{
  "questions": [
    { "label": "דף קבוצות 11", "points": 16, "comment": "חסר נימוק" }
  ],
  "feedback": "משוב כללי לסטודנט",
  "annotations": [
    { "page": 2, "x0": 120, "y0": 340, "x1": 480, "y1": 372,
      "text": "חסר נימוק לכך ש-det A ≠ 0" }
  ],
  "needs_review": false,
  "review_reason": ""
}`;

  // המחוון שבנה הסקיל rubric-builder: Rubric.pdf לאנשים ו-Rubric.md לבוט, שניהם מ-rubric.json. המצב לפי היומן ב-Working notes
  function rubricFilePanel(A) {
    const r = A.rubricFile || {};
    if (!r.pdf) return `<section class="panel">
      <div class="panel-head"><h3>המחוון (PDF)</h3><span class="end tag warn">אין מחוון</span></div>
      <div class="panel-body"><p class="lead" style="margin:0">עוד אין מחוון למטלה הזאת.${r.md === "council" ? " יש בתיקייה \"פדגוגי\" Rubric.md ישן, והבוט עובד לפיו בינתיים." : ""}
        <span class="muted" style="display:block">בונים אותו ב-Claude Code בתיקיית הריפו: "מחוון לדף תרגילים X, תמשוך Y עבודות". כשייבנה, ה-PDF יופיע כאן.</span></p></div>
    </section>`;
    const url = `${BASE}api/file?path=${encodeURIComponent(r.path)}`;
    const bot = r.md === "rendered" ? "הבוט בודק לפי אותו מחוון (Rubric.md מיוצר מאותו מקור)."
      : r.md === "council" ? "שימו לב: Rubric.md של הבוט ישן ולא מאותו מקור." : "אין Rubric.md לבוט.";
    return `<section class="panel">
      <div class="panel-head"><h3>המחוון (PDF)</h3><span class="end tag ${r.approved ? "ok" : "warn"}">${r.approved ? "מאושר" : "ממתין לאישור"}</span></div>
      <div class="panel-body">
        <p class="lead" style="margin:0 0 8px">נבנה ${esc(when(r.pdfAt))}${r.rounds ? `, ${r.rounds} סבבי ועדה` : ""}. ${bot}
          ${r.approved ? "" : " הוועדה ממתינה להערות המתרגל; \"מאושר\" סוגר את הלופ."}</p>
        <div class="row-start" style="margin-bottom:8px"><a class="btn secondary small" href="${url}" target="_blank" rel="noopener">${ICON.folder}פתח את ה-PDF</a></div>
        <object data="${url}" type="application/pdf" style="width:100%;height:520px;border:1px solid var(--line,#ddd);border-radius:8px"><p class="muted">הדפדפן לא מציג PDF בתוך הדף. <a href="${url}" target="_blank" rel="noopener">פתחו אותו בלשונית חדשה</a>.</p></object>
      </div>
    </section>`;
  }

  // המכוון הרשמי של המרצה (grading.official_key): קובץ (PDF, תמונה, Word, טקסט) או טקסט מודבק, וניקוד לכל שאלה.
  // כשיש מכוון, כל "בדוק" שולח אותו ל-Claude עם כל עבודה, והוא גובר על המחוון. נשמר בתיקיית המטלה, אז כל הצוות רואה אותו
  const KEY_ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx,.txt,.md";
  function keyDraft(A) {
    const k = A.officialKey;
    return (state.keyDraft[A.id] ||= { file: null, text: k?.text || "", points: { ...(k?.points || {}) } });
  }
  function officialKeyPanel(A) {
    const k = A.officialKey, d = keyDraft(A), qs = A.rubric?.length ? A.rubric : (A.questionLabels || []).map((l) => ({ label: l, points: 0 }));
    const missing = qs.filter((q) => !(Number(d.points[q.label]) > 0) && !(q.points > 0));
    const files = (k?.files || []).map((f) => f.path
      ? `<a class="btn secondary small" href="${BASE}api/file?path=${encodeURIComponent(f.path)}" target="_blank" rel="noopener">${ICON.folder}${esc(f.name)}</a>`
      : `<span class="tag">${esc(f.name)}</span>`).join(" ");
    return `<section class="panel" id="official-key">
      <div class="panel-head"><h2>המכוון הרשמי</h2><span class="end tag ${k ? "ok" : "warn"}">${k ? "פעיל: הבדיקה לפיו" : "עוד לא הועלה"}</span></div>
      <div class="panel-body">
        <p class="lead" style="margin:0 0 10px">${k
          ? `הועלה${k.by ? ` על ידי ${esc(k.by)}` : ""}${k.at ? ` ב-${esc(when(k.at))}` : ""}. כל לחיצה על "בדוק" שולחת אותו ל-Claude עם כל עבודה, והוא גובר על המחוון ועל הפתרון.`
          : "כשהמכוון מגיע מהמרצה, מעלים אותו כאן (PDF, תמונה, Word או טקסט) או מדביקים את הטקסט שלו. מאותו רגע כל בדיקה הולכת לפיו."}</p>
        ${files ? `<div class="row-start" style="margin-bottom:10px;flex-wrap:wrap;gap:6px">${files}</div>` : ""}
        <div class="field"><label for="ok-file">${k ? "להחליף בקובץ אחר" : "קובץ המכוון"}</label>
          <input id="ok-file" type="file" accept="${KEY_ACCEPT}" data-key-file>
          ${d.file ? `<p class="hint">נבחר: <b>${esc(d.file.name)}</b> (${Math.ceil(d.file.size / 1024)} KB). יישמר בלחיצה על "שמור".</p>` : ""}
          <p class="hint">PDF ותמונות נשלחים ל-Claude כמו שהם. מ-Word נשלח הטקסט (נוסחאות מורכבות עדיף לשמור כ-PDF).</p></div>
        <div class="field"><label for="ok-text">טקסט המכוון${k?.files?.length ? " (לא חובה, נוסף לקובץ)" : ""}</label>
          <textarea id="ok-text" rows="6" data-key-text placeholder="אפשר להדביק כאן את המכוון, או הערות נוספות של המרצה לבדיקה">${esc(d.text)}</textarea></div>
        <div class="field"><label>ניקוד לכל שאלה לפי המכוון</label>
          ${qs.length ? qs.map((q) => `<div class="rubric-row">
              <span>${esc(q.label)}${q.points ? `<small class="muted" style="display:block">עכשיו: ${q.points} נק׳</small>` : ""}</span>
              <span class="rpts"><input type="number" min="0" step="0.5" style="width:80px" data-key-pt="${esc(q.label)}" value="${d.points[q.label] ?? ""}" placeholder="${q.points || ""}"><span>נק׳</span></span>
            </div>`).join("") : `<p class="muted">למטלה עוד אין רשימת שאלות.</p>`}
          <p class="hint">${missing.length ? `אין ציונים בלי ניקוד לכל שאלה: חסר ל${esc(missing.map((q) => q.label).join(", "))}.` : "ריק = הניקוד מהמחוון."}</p></div>
        <div class="row-start" style="gap:8px">
          <button class="btn primary small" data-act="key-save">${ICON.check}${k ? "שמור שינויים" : "שמור מכוון"}</button>
          ${k ? `<button class="btn ghost small" data-act="key-remove">הוצא את המכוון מהבדיקה</button>` : ""}
        </div>
      </div>
    </section>`;
  }

  async function saveOfficialKey(remove) {
    const A = cur(), d = keyDraft(A);
    if (remove && !confirm("להוציא את המכוון מהבדיקה? הקבצים לא נמחקים: הם עוברים לתיקייה Earlier official keys.")) return;
    const body = { course: A.courseFolder, assignment: A.folder };
    if (remove) body.remove = true;
    else {
      if (d.file) {
        const buf = new Uint8Array(await d.file.arrayBuffer());
        let bin = "";
        for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
        Object.assign(body, { fileName: d.file.name, data: btoa(bin) });
      }
      body.text = d.text;
      body.points = Object.fromEntries(Object.entries(d.points).filter(([, v]) => v !== "" && v != null).map(([k, v]) => [k, Number(v)]));
    }
    try {
      await api("api/official-key", { method: "POST", body: JSON.stringify(body) });
      delete state.keyDraft[A.id];
      await loadLocal();
      toast(remove ? "המכוון הוצא מהבדיקה." : "המכוון נשמר. מעכשיו כל בדיקה הולכת לפיו.");
    } catch (e) {
      toast(e.message, ICON.warn);
    }
  }

  // שלב 2: ההנחיות נשלחות ל-Claude. המחוון והפתרון נקראים מתיקיית המטלה (grading/grade.py)
  function gradeInstr() {
    const R = rubric(), A = cur();
    const total = R.questions.reduce((a, q) => a + q.pts, 0);
    return `<div class="split wide-first">
      <div class="stack">
        ${officialKeyPanel(A)}
        ${instrBox("grade", "הנחיות לבדיקה", "ההנחיות הכלליות שנשלחות ל-Claude עם כל עבודה, יחד עם המחוון. כדאי לכתוב כאן כל מה שהייתם אומרים למתרגל חדש לפני שהוא מתחיל לבדוק. הן נשמרות בדפדפן הזה ונשלחות בכל לחיצה על \"בדוק\".")}
        <section class="panel">
          <div class="panel-head"><h2>מחוון</h2><span class="meta">${esc(course().name)}, ${esc(A.title)}</span></div>
          <div class="panel-body">
            ${R.missing ? rubricNoticeHTML() : ""}
            ${R.questions.map((q) => `
              <div class="rubric-row">
                <span class="rq">שאלה ${q.n}</span>
                <span class="rpts"><b class="num">${q.pts}</b><span>נק׳</span></span>
                <span>${esc(q.req)}${q.criteria ? `<small class="muted" style="display:block">${esc(q.criteria)}</small>` : ""}</span>
              </div>`).join("")}
            <div class="total-line"><span>סך הכל</span><span class="num">${total} נק׳</span></div>
            <p class="hint">כך הבדיקה קוראת את המחוון מהקובץ Assignment details.json שבתיקיית המטלה. ${esc(RUBRIC_RULE)} כדי לשנות, עורכים את הקובץ.</p>
            <div class="row-start"><button class="btn secondary small" data-act="open-folder">${ICON.folder}פתח את תיקיית המטלה</button></div>
          </div>
        </section>
      </div>
      <div class="stack">
        ${rubricFilePanel(A)}
        <section class="panel">
          <div class="panel-head"><h3>פתרון רשמי</h3><span class="end tag ${A.solution ? "ok" : "warn"}">${A.solution ? "נמצא" : "אין"}</span></div>
          <div class="panel-body"><p class="lead" style="margin:0">${A.solution
            ? "הקובץ Official solution.pdf שבתיקיית המטלה נשלח ל-Claude עם כל הגשה (אפשר לכבות בלשונית \"חיבור ל-Claude\")."
            : "עוד אין פתרון רשמי. כדי שהבדיקה תשווה אליו, שמים את הפתרון בשם Official solution.pdf בתיקיית המטלה."}</p></div>
        </section>
        <section class="panel">
          <div class="panel-head"><h3>מה נשלח ל-Claude</h3><span class="meta">בקיצור</span></div>
          <div class="panel-body"><pre class="prompt" id="prompt-preview">${esc(promptPreview())}</pre></div>
        </section>
      </div>
    </div>`;
  }

  function gradeConn() {
    const c = state.claude;
    return `<div class="split">
      <section class="panel">
        <div class="panel-head"><h2>חיבור ל-Claude</h2>${LOCAL.health?.claude ? `<span class="end tag ok">מחובר</span>` : `<span class="end tag warn">עוד לא מחובר</span>`}</div>
        <div class="panel-body">
          ${LOCAL.health?.claude ? `<div class="notice">${ICON.lock}<div><b>הבדיקה עובדת</b> (${LOCAL.health?.claudeVia === "api" ? "דרך מפתח ה-API" : "דרך Claude Code במחשב, במנוי של הצוות"}). ל-Claude נשלחים רק העמודים של ההגשה הממוספרת, בלי שמות. העבודה המסומנת נשמרת ב-"2 - Graded with comments" והציון בקובץ הציונים של הבודק ("Grades by <שם>.csv").</div></div>`
            : `<div class="notice">${ICON.lock}<div><b>הבדיקה עם Claude עוד לא מחוברת.</b> ${esc(NO_KEY)}</div></div>`}
          <div class="form-grid">
            <div class="field"><label for="c-model">מודל</label>
              <select id="c-model" dir="ltr" data-set="claude.model">
                ${["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"].map((m) => `<option ${c.model === m ? "selected" : ""}>${m}</option>`).join("")}
              </select>
              <p class="hint">Opus לבדיקה מעמיקה של הוכחות. Haiku לבדיקות מהירות וזולות.</p></div>
            <div class="field"><label for="c-par">עבודות במקביל</label><input id="c-par" type="number" min="1" max="20" value="${c.parallel}" data-set="claude.parallel"></div>
          </div>
          ${sw("c-sol", "לצרף את הפתרון הרשמי", "Claude משווה כל עבודה ל-Official solution.pdf של המטלה, אם יש", c.sendSolution, "claude.sendSolution")}
        </div>
      </section>
      <div class="stack">
        <section class="panel">
          <div class="panel-head"><h3>מפתח</h3></div>
          <div class="panel-body">${secretField("ANTHROPIC_API_KEY", "לא חובה: בלי מפתח הבדיקה רצה דרך Claude Code שמחובר במחשב. אם יש מפתח, הוא נשמר בקובץ .env במחשב שמריץ את המערכת, לא בדפדפן ולא ב-GitHub.", LOCAL.health?.claudeVia === "api")}</div>
        </section>
        <section class="panel">
          <div class="panel-head"><h3>מה Claude מחזיר על כל עבודה</h3></div>
          <div class="panel-body"><pre class="code-block" dir="ltr">${esc(SCHEMA)}</pre>
          <p class="hint">המיקום של כל הערה (עמוד ומלבן, באלפיות של העמוד) מאפשר לצייר את הסימון האדום על גבי ה-PDF המקורי. את הציון מחשבת המערכת מהניקוד של השאלות, לא Claude.</p></div>
        </section>
      </div>
    </div>`;
  }

  // שלב 3: מה בדיוק עולה למודל ואיך (moodle/send.py, moodle/claude_upload.md)
  function retInstr() {
    return `<div class="split wide-first">
      <section class="panel">
        <div class="panel-head"><h2>מה קורה כשלוחצים "העלה למודל"</h2></div>
        <div class="panel-body">
          <ol class="todo">
            <li><b>בוחרים מה עולה.</b> רק עבודות מסומנות מ-"2 - Graded with comments" שעוד לא עלו, או שהשתנו מאז ההעלאה האחרונה שלהן (לפי Upload log.csv).</li>
            <li><b>אורזים לפי מה שמודל מצפה לו.</b> לכל סטודנט תיקייה עם השם ומזהה המשתתף שלו מטבלת המפתח, ובתוכה feedback.pdf. ה-ZIP-ים (עד 9MB כל אחד) נשמרים ב-"3 - Ready to upload to Moodle". עבודה שהוגשה מחדש אחרי הבדיקה, או קובץ גדול מדי, נשארים בחוץ ומדווחים.</li>
            <li><b>בודקים שהמחשב מוכן:</b> Claude Code מותקן ומחובר, והכרום והמודל מחוברים (לשונית "חיבור למודל").</li>
            <li><b>אדם מאשר.</b> חלון אישור מראה כמה קבצים וכמה סטודנטים. בלי "כן" שום דבר לא עולה.</li>
            <li><b>Claude בכרום מעלה כל ZIP</b> בעמוד "העלאת מספר קובצי משוב כקובץ 7Zip אחד" של המטלה. מודל של האוניברסיטה קולט את הקבצים מיד, בלי מסך אישור נוסף.</li>
            <li><b>המערכת מאמתת.</b> אחרי כל ZIP היא (לא Claude) בודקת שמודל קלט בדיוק את מספר הקבצים שבו, ורושמת אותם ב-Upload log.csv. מספר שלא מתאים עוצר הכל עד שמישהו בודק במודל.</li>
          </ol>
        </div>
      </section>
      <div class="stack">
        <section class="panel">
          <div class="panel-head"><h3>מה הסטודנט מקבל</h3></div>
          <div class="panel-body">
            <dl class="fields">
              <div><dt>קובץ משוב</dt><dd>העבודה שלו עם ההערות במקום של כל טעות, ובהתחלה עמוד עם הציון, הניקוד לכל שאלה והמשוב</dd></div>
              <div><dt>הציון</dt><dd>עולה רק בלחיצה על "העלה ציונים", אחרי שהקבצים הבדוקים כבר במודל: Claude מוריד ממודל את גיליון הציונים, המערכת ממלאת אותו לפי המספרים, ו-Claude מעלה אותו ומאשר רק אם רשימת השינויים של מודל תואמת</dd></div>
            </dl>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h3>יומן ההעלאה</h3></div>
          <div class="panel-body"><p class="lead" style="margin:0">עבודה נחשבת "הוחזרה" רק כשהקובץ המסומן שלה זהה למה שנרשם ב-Upload log.csv אחרי העלאה שאומתה. אם מישהו מתקן את העבודה אחר כך, היא חוזרת להיות "מוכנה להעלאה".</p></div>
        </section>
      </div>
    </div>`;
  }

  function retConn() {
    const rd = ensureReady();
    return `<section class="panel">
      <div class="panel-head"><h2>חיבור למודל</h2>${allReady(rd.data) ? `<span class="end tag ok">מוכן להעלאה</span>` : ""}</div>
      <div class="panel-body">
        <p class="lead">ההעלאה למודל נעשית דרך Claude Code ו-Claude in Chrome, בכרום שלך ועם החשבון שלך. אף סיסמה לא נכנסת למערכת: מתחברים למודל בעצמך. כשלוחצים "העלה למודל", הבדיקה הזו רצה לבד ומחברת מה שחסר.</p>
        ${readyChecklistHTML(rd)}
      </div>
    </section>`;
  }

  // ---------- Views ----------
  function stageView(stage) {
    const t = state.tab[stage];
    const body = {
      pull: { list: pullList, instr: pullInstr, conn: pullConn },
      grade: { list: gradeList, instr: gradeInstr, conn: gradeConn },
      ret: { list: returnList, instr: retInstr, conn: retConn },
    }[stage][t]();
    return `${stageHeroHTML(stage)}${boardHTML(stage)}
      <h2 class="picked">${esc(cur().title)}<small>המטלה שנבחרה</small></h2>
      ${stage === "grade" ? assignmentStatsHTML(cur()) : ""}
      ${tabsHTML(stage)}<div class="tab-body" role="tabpanel" aria-labelledby="tab-${stage}-${t}">${body}</div>`;
  }

  // ---------- חלון מתקפל ----------
  // שורה קטנה עם כותרת וסיכום קצר; לחיצה מגדילה אותו לפרטים המלאים. מה שנפתח או נסגר נזכר בין ביקורים (state.fold)
  const foldOpen = (k, def = false) => (k in state.fold ? state.fold[k] : def);
  function foldHTML(k, { title, sum = "", body, link = "", def = false, cls = "" }) {
    const open = foldOpen(k, def);
    return `<section class="panel fold ${open ? "open" : ""} ${cls}">
      <div class="fold-head">
        <button type="button" class="fold-btn" data-fold="${esc(k)}" data-fold-def="${def ? 1 : 0}" aria-expanded="${open}">
          <span class="fold-chev" aria-hidden="true">${ICON.chev}</span><span class="fold-title">${title}</span>${sum ? `<span class="fold-sum">${sum}</span>` : ""}
        </button>${link}
      </div>
      ${open ? `<div class="fold-body">${typeof body === "function" ? body() : body}</div>` : ""}
    </section>`;
  }

  // לוח הבקרה: כרטיס קטן עם המספרים העיקריים של המטלה. לחיצה עליו פותחת את לשונית הסטטיסטיקה, שם כל הפירוט
  function statsMiniHTML(A, I) {
    const max = A.maxGrade || 100;
    const g = I.graded.map((s) => s.score).filter((x) => typeof x === "number");
    const mean = g.length ? g.reduce((a, b) => a + b, 0) / g.length : null;
    const pass = g.length ? Math.round((100 * g.filter((x) => x >= 0.6 * max).length) / g.length) : null;
    const approved = I.graded.filter((s) => s.approved).length;
    const item = (label, value) => `<span class="sm-item"><b class="num">${value}</b><small>${label}</small></span>`;
    return `<a class="stats-mini" href="#/stats" title="פתח את הסטטיסטיקה המלאה של המטלה">
      <span class="sm-icon" aria-hidden="true">${ICON.chart}</span>
      ${item("נבדקו", `${I.graded.length}<i>/${I.ok.length}</i>`)}
      ${item("ממוצע", fmt(mean))}
      ${item("חציון", fmt(median(g)))}
      ${item("עוברים", pass != null ? `${pass}%` : "—")}
      ${item("אושרו", `${approved}<i>/${I.graded.length}</i>`)}
      <span class="sm-more">לסטטיסטיקה המלאה<span aria-hidden="true">${ICON.chev}</span></span>
    </a>`;
  }

  // מה מחכה לבדיקה ידנית, לפי סוג הבעיה. Claude שולח לשם כל עבודה שהוא לא בטוח בה
  function reviewCalloutHTML(A) {
    const queue = A.subs.filter(needsReview);
    if (!queue.length) return "";
    const kinds = Object.keys(REVIEW_KIND).map((k) => [k, queue.filter((s) => kindOf(s) === k).length]).filter(([, c]) => c);
    return `<section class="review-callout">
      <span class="rc-icon">${ICON.hand}</span>
      <div class="rc-text">
        <b>${plural(queue.length, "מקרה מיוחד אחד מחכה", "מקרים מיוחדים מחכים")} לבדיקה ידנית</b>
        <div class="rc-kinds">${kinds.map(([k, c]) => `<span class="chip">${REVIEW_KIND[k][0]}<span class="c num">${c}</span></span>`).join("")}</div>
      </div>
      <a class="btn primary" href="#/review">${ICON.pen}התחל לבדוק</a>
    </section>`;
  }

  // טעויות נפוצות: מה הכי הרבה סטודנטים טעו בו. לחיצה על טעות מראה את העבודות שעשו אותה
  function mistakesHTML(A) {
    const list = mistakeStats(A);
    if (!list.length) return `<p class="muted empty-line">יופיע אחרי שיהיו עבודות בדוקות. Claude רושם לכל שאלה את סוגי הטעויות, ומכאן הרשימה.</p>`;
    const qs = rubric().questions, top = list.slice(0, 10), most = top[0].count;
    return `<ol class="mk-list">${top.map((m) => {
      const k = `${m.q}|${m.text}`, open = state.mistakeOpen === k;
      return `<li class="${open ? "open" : ""}">
        <button class="mk-row" data-mistake="${esc(k)}" aria-expanded="${open}">
          <span class="mk-text"><b>${esc(m.text)}</b><small>שאלה ${m.q + 1}${qs[m.q]?.req ? ` · ${esc(qs[m.q].req)}` : ""}${m.ded != null ? ` · בדרך כלל −${fmt(m.ded)}` : ""}</small></span>
          <span class="track"><i style="width:${(m.count / most) * 100}%"></i></span>
          <span class="mk-n num">${m.count}<small>${m.pct}%</small></span>
        </button>
        ${open ? `<div class="mk-works">${m.ids.map((id) => `<button class="work-tile mini" data-open="${id}" title="פתח את עבודה ${id}"><b class="num">${id}</b></button>`).join("")}</div>` : ""}
      </li>`;
    }).join("")}</ol>
    ${list.length > top.length ? `<p class="hint">ועוד ${list.length - top.length} סוגי טעויות פחות נפוצים.</p>` : ""}`;
  }

  // עלות הבדיקה עד עכשיו, מתוך יומן השימוש של Claude Code. שווה ערך ל-API: הבדיקה רצה במנוי של הצוות, לא מחויבת
  function usageHTML() {
    const u = D.usage;
    if (!u) return "";
    const share = u.cacheReadShare == null ? "—" : `${Math.round(u.cacheReadShare * 100)}%`;
    const models = Object.entries(u.models || {}).map(([m, v]) => `<bdi>${esc(m)}</bdi> · ${v.runs} ריצות · <bdi>$${v.costUsd}</bdi>`).join("<br>");
    return foldHTML("stats:usage", {
      title: "עלות הבדיקה", sum: `<bdi>$${u.costUsd}</bdi> · ${u.runs} ריצות · שווה ערך ל-API, לא חיוב`,
      body: () => `<div class="stat-row compact" style="grid-template-columns:repeat(3,minmax(0,1fr));margin-top:0">
        <div class="stat"><span class="stat-l">סך הכל</span><b class="stat-v num">$${u.costUsd}</b><span class="stat-s">${u.runs} ריצות</span></div>
        <div class="stat"><span class="stat-l">לעבודה</span><b class="stat-v num">$${u.avgUsd}</b><span class="stat-s">ממוצע לריצה</span></div>
        <div class="stat"><span class="stat-l">מהמטמון</span><b class="stat-v num">${share}</b><span class="stat-s">מהקלט נקרא ולא נכתב מחדש</span></div>
      </div><p class="muted" style="margin:12px 0 0">${models}</p>`,
    });
  }

  function logHTML(limit, onlyHere) {
    const icon = { pull: ICON.pull, grade: ICON.grade, return: ICON.ret, error: ICON.warn };
    const list = D.runs.filter((r) => !onlyHere || (r.where || "").startsWith(course()?.name || "")).slice(0, limit);
    if (!list.length) return `<p class="muted empty-line" style="padding:12px 0">עוד אין פעילות.</p>`;
    return `<ul class="log">${list.map((r) => `
      <li><span class="ic ${r.kind}">${icon[r.kind]}</span><div>${esc(r.text)}<small>${esc(r.where || "")}<time class="num">${when(r.at)}</time>${r.actor ? `<span dir="ltr">${esc(r.actor)}</span>` : ""}</small></div></li>`).join("")}</ul>`;
  }

  // כל המטלות של הקורס. בקטן: רק מטלות שיש בהן הגשות (והנבחרת); "הצג את כולן" מגדיל לכל עשר המשבצות
  function overviewHTML() {
    const list = D.assignments.filter((a) => a.courseId === state.courseId);
    const active = list.filter((A) => A.subs.length || A.id === state.assignmentId);
    const all = foldOpen("overview:all") || active.length === list.length;
    const mark = (done, txt) => `<span class="ov ${done ? "done" : ""}">${done ? ICON.check : ""}${txt}</span>`;
    const more = list.length > active.length || foldOpen("overview:all")
      ? `<button type="button" class="fold-more" data-fold="overview:all" data-fold-def="0" aria-expanded="${all}">${all ? "הצג רק מטלות עם הגשות" : `הצג את כל ${list.length} המטלות`}</button>` : "";
    return `<div class="table-wrap"><table class="overview">
      <thead><tr><th>מטלה</th><th class="col-hide">מועד הגשה</th><th>משיכה</th><th>בדיקה</th><th>החזרה</th><th>ממוצע</th></tr></thead>
      <tbody>${(all ? list : active).map((A) => {
        const I = info(A);
        const sel = A.id === state.assignmentId;
        return `<tr class="clickable ${sel ? "sel" : ""}" data-assign="${A.id}" tabindex="0" ${sel ? 'aria-current="true"' : ""}>
          <td><b>${A.title}</b></td>
          <td class="col-hide muted num">${A.due ? new Date(A.due).toLocaleDateString("he-IL", { day: "numeric", month: "short" }) : "—"}</td>
          <td>${I.subs.length ? mark(I.done.pull, `${I.subs.length}`) : `<span class="muted">—</span>`}</td>
          <td>${I.subs.length ? mark(I.done.grade, `${I.graded.length}/${I.ok.length}`) : `<span class="muted">—</span>`}</td>
          <td>${I.subs.length ? mark(I.done.ret, `${I.returned.length}/${I.ok.length}`) : `<span class="muted">—</span>`}</td>
          <td class="num">${avg(I.graded.map((s) => s.score)) ?? `<span class="muted">—</span>`}</td>
        </tr>`;
      }).join("")}</tbody>
    </table></div>${more}`;
  }

  function rubricSummaryHTML() {
    const R = rubric();
    return `
      <ul class="criteria">${R.questions.map((q) => `<li><span title="${esc(q.req)}">שאלה ${q.n}</span><span class="track"><i style="width:${q.pts}%"></i></span><b class="num">${q.pts}</b></li>`).join("")}</ul>`;
  }

  // ---------- לוח המספרים הציבורי ----------
  // מי שאין במחשב שלו מערכת רואה כאן מה נעשה: מחשב אחד בצוות מפרסם סיכום של מספרים בלבד (dashboard/public_status.py)
  // לקובץ ציבורי, והאתר קורא אותו. בלי שמות, ציונים, הערות או קבצים. מתרענן כל דקה
  const PUBLIC_STATUS_URL = "https://gist.githubusercontent.com/matanravitsky-crypto/f1d11991473c2ece643fc479ed963117/raw/status.json";
  const PUBLIC_STALE_H = 3;  // המחשב שמפרסם שולח לפחות פעם בשעה. יותר מזה: כנראה כבוי
  const PUB = { data: null, error: "", loading: !!PUBLIC_STATUS_URL && !ON_LOCAL_HOST };

  // פעם בדקה מקבלים עותק טרי (ה-CDN של GitHub שומר עותק עד 5 דקות). fresh: הכפתור "סנכרון", כתובת שלא הייתה
  // בשום מטמון, כדי לקבל את מה שפורסם ממש עכשיו
  async function fetchPublic(fresh = false) {
    const q = fresh ? `t=${Date.now()}` : `m=${Math.floor(Date.now() / 60000)}`;
    const r = await fetch(`${PUBLIC_STATUS_URL}?${q}`, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  async function loadPublic() {
    if (!PUBLIC_STATUS_URL || LOCAL.on) return;
    try {
      PUB.data = await fetchPublic();
      PUB.error = "";
    } catch (e) {
      PUB.error = e.message;
    }
    PUB.loading = false;
    if (!LOCAL.on && !cur()) render();
  }

  function publicBoardHTML() {
    const d = PUB.data;
    if (!d?.courses?.length) return PUB.loading ? `<p class="send-line">${ICON.spin}<span>טוען את מצב העבודה…</span></p>` : "";
    const age = (Date.now() - Date.parse(d.publishedAt)) / 3600000;
    const stale = age > PUBLIC_STALE_H;
    const cell = (n, of) => `<td><b class="num">${n}</b>${of && n < of ? `<small class="sub">מתוך ${of}</small>` : ""}</td>`;
    const courses = d.courses.map((c) => {
      const rows = c.assignments.filter((a) => !a.empty);
      const notYet = c.assignments.length - rows.length;
      const body = rows.map((a) => `<tr>
          <td><b>${esc(a.title)}</b>${a.due ? `<small class="sub">הגשה עד ${esc(when(a.due))}</small>` : ""}</td>
          <td><b class="num">${a.pulled}</b>${a.pulledAt ? `<small class="sub">${esc(when(a.pulledAt))}</small>` : ""}</td>
          ${cell(a.graded, a.pulled)}${cell(a.review)}${cell(a.approved, a.graded)}
          <td><b class="num">${a.returned}</b>${a.returnedAt ? `<small class="sub">${esc(when(a.returnedAt))}</small>` : ""}</td>
          <td class="col-hide-sm">${a.pullOwner ? esc(a.pullOwner) : `<span class="muted">—</span>`}</td>
        </tr>`).join("");
      return `<section class="panel" style="margin-bottom:24px">
        <div class="panel-head"><h2>${esc(c.name)}</h2><span class="meta">${rows.length ? plural(rows.length, "מטלה אחת נמשכה", "מטלות נמשכו") : "עוד לא נמשכה אף מטלה"}${notYet ? ` · ${notYet} עוד לא` : ""}</span></div>
        ${rows.length ? `<div class="table-wrap"><table class="board-table">
          <thead><tr><th>מטלה</th><th>נמשכו</th><th>נבדקו</th><th>לבדיקה ידנית</th><th>אושרו</th><th>הוחזרו למודל</th><th class="col-hide-sm">מושך/ת</th></tr></thead>
          <tbody>${body}</tbody></table></div>` : ""}
      </section>`;
    }).join("");
    return `<p class="hint" style="margin:0 0 16px">${stale ? `<span class="tag warn">לא עודכן מאז ${esc(when(d.publishedAt))}</span> המחשב שמפרסם את המספרים כנראה כבוי, אז ייתכן שהם ישנים.`
      : `עודכן ${esc(when(d.publishedAt))}${d.publishedBy ? `, מהמחשב של ${esc(d.publishedBy)}` : ""}. מתעדכן לבד.`}</p>${courses}`;
  }

  // אין חיבור למערכת שבמחשב, או שאין עדיין מטלות: אין מספרים להציג
  function offlineHTML() {
    const how = `
      <section class="pipeline" aria-label="מסלול הבדיקה">
        ${["pull", "grade", "ret"].map((st, idx) => `
          <article class="stage" data-state="idle">
            ${idx ? `<span class="stage-arrow" aria-hidden="true">${ICON.chev}</span>` : ""}
            <header class="stage-top"><span class="stage-mark">${STAGES[st].no}</span><div><h2>${STAGES[st].name}</h2></div></header>
            <p class="lead" style="margin:0">${esc(STAGES[st].desc)}</p>
          </article>`).join("")}
      </section>`;
    if (LOCAL.on && LOCAL.health?.root) {
      return `<div class="page-head"><div><h1>עוד אין מטלות בתיקייה</h1>
          <p>המערכת מחוברת לתיקיית OneDrive, אבל אין בה עדיין מטלה. מטלה חדשה נוספת פעם אחת משורת הפקודה, עם שמות התיקיות באנגלית, ואחר כך מושכים אליה מכאן:</p>
          <pre class="prompt" dir="ltr">python -m moodle ingest &lt;assignment id&gt; --course "Linear Algebra" --name "Assignment 1 - Vectors"</pre></div></div>${how}`;
    }
    if (LOCAL.on) return `<div class="page-head"><div><h1>תיקיית OneDrive לא נמצאה</h1><p>המערכת פועלת, אבל לא מצאה במחשב הזה את התיקייה של הקורס. ההסבר מופיע למעלה.</p></div></div>${how}`;
    const board = publicBoardHTML();
    return `
      ${board ? `<div class="page-head"><div><h1>מצב העבודה</h1>
        <p>כל אחד רואה כאן כמה הגשות נמשכו, נבדקו והוחזרו בכל מטלה. רק מספרים: בלי שמות, בלי ציונים ובלי קבצים. כדי למשוך, לבדוק ולהחזיר מהמחשב שלך, מחברים אותו פעם אחת (למטה).</p></div></div>${board}`
        : `<div class="page-head"><div><h1>המערכת לא מחוברת</h1>
        <p>האתר מציג רק נתונים אמיתיים, מתוך תיקיית OneDrive של הקורס. הם מגיעים מהמערכת שרצה במחשב שלך, ועכשיו היא לא מחוברת.</p></div></div>`}
      <section class="panel" style="margin-bottom:24px">
        <div class="panel-head"><h2>איך מתחברים</h2><span class="end tag warn">${LOCAL.probing ? (LOCAL.access === "prompt" ? "מחכה לאישור בכרום…" : "מנסה להתחבר…") : "לא מחובר"}</span></div>
        <div class="panel-body">
          <ol class="todo">
            <li>המערכת צריכה לרוץ במחשב הזה. <b>פעם ראשונה במחשב הזה?</b> הפקודה שבחלק הבא מתקינה אותה, כך שהיא עולה לבד, בלי חלון, בכל הדלקה. מחשב שכבר מותקן: היא עולה לבד, או בלחיצה כפולה על <code dir="ltr">start.bat</code>.</li>
            <li>${accessStep()}</li>
          </ol>
          <div class="row-start">
            <button class="btn primary lg" data-act="recheck">${ICON.redo}התחבר</button>
            <a class="btn secondary small" href="${LOCAL_SITE}${esc(location.hash)}">פתח בכתובת המקומית (localhost:8765)</a>
          </div>
          <p class="hint">האתר מתחבר לבד ברגע שהמערכת במחשב עונה, ונשאר בכתובת הזו.</p>
        </div>
      </section>
      <section class="panel" style="margin-bottom:24px">
        <div class="panel-head"><h2>פעם ראשונה במחשב הזה? פקודה אחת מחברת אותו</h2><span class="meta">פעם אחת לכל אחד מהצוות</span></div>
        <div class="panel-body">
          <p class="lead">כל אחד בצוות מושך, בודק ומעלה דרך ה-Claude שלו, במחשב שלו. כדי שהכפתורים כאן יפעילו אותו, מחברים את המחשב פעם אחת:</p>
          <ol class="todo">
            <li><b>פותחים PowerShell:</b> לוחצים על מקש Windows, כותבים PowerShell ולוחצים Enter.</li>
            <li><b>מדביקים את השורה הזו ולוחצים Enter:</b>
              <div class="row-start" style="margin-top:8px"><pre class="prompt" dir="ltr" style="flex:1">${esc(CONNECT_COMMAND)}</pre>
              <button class="btn primary small" data-act="copy-connect">${ICON.check}העתק</button></div></li>
            <li><b>זהו.</b> הפקודה מתקינה מה שחסר (Git, Python, 7-Zip ו-Claude Code), מורידה את המערכת, מפעילה אותה כך שתעלה לבד, בלי חלון, בכל הדלקה של המחשב, ופותחת את האתר מחובר. מהפעם הבאה הקישור הזה מעביר לשם לבד.</li>
            <li><b>בלחיצה הראשונה על "משוך הגשות"</b> האתר מחבר את Claude Code לחשבון Claude שלך (נפתח דף התחברות) ובודק שהתוסף Claude in Chrome מחובר בכרום שלך ושכרום מחובר למודל. מאז כל משיכה רצה דרך ה-Claude שלך, וההגשות נשמרות ממוספרות בתיקיית OneDrive של הקורס.</li>
            <li><b>גישה לתיקייה:</b> מבקשים מהמרצה גישה לתיקייה YallaLinearit. בדפדפן, על התיקייה: Add shortcut to My files. באפליקציית OneDrive במחשב מתחברים עם חשבון האוניברסיטה.</li>
          </ol>
          <details style="margin-top:12px"><summary>בלי הפקודה: אותו דבר ביד</summary>
            <ol class="todo" style="margin-top:8px">
              <li><b>התוכנות</b>, בחלון PowerShell: <code dir="ltr">winget install Python.Python.3.12</code>, <code dir="ltr">winget install 7zip.7zip</code>, <code dir="ltr">winget install Git.Git</code></li>
              <li><b>המערכת:</b> בחלון חדש, בתיקייה שבה רוצים לשמור אותה: <code dir="ltr">git clone ${REPO_URL}</code></li>
              <li><b>מפעילים, פעם אחת:</b> לחיצה כפולה על <code dir="ltr">install-autostart.bat</code> בתיקייה assignment-checker. מעכשיו המערכת עולה לבד, בלי חלון, בכל פעם שהמחשב נדלק. בכל הפעלה היא מתעדכנת מ-GitHub, כך שכולם עובדים על אותה גרסה. (בלי הפעלה אוטומטית: לחיצה כפולה על <code dir="ltr">start.bat</code>, והחלון השחור נשאר פתוח.)</li>
            </ol>
          </details>
          <div class="row-start" style="margin-top:12px"><a class="btn secondary small" href="${REPO_URL}#readme" target="_blank" rel="noopener">ההסבר המלא ב-GitHub</a>
            <a class="btn secondary small" href="connect.ps1" target="_blank" rel="noopener">מה הפקודה עושה</a></div>
        </div>
      </section>
      ${how}`;
  }

  // ---------- הגרסה המחוברת: תיקיית OneDrive דרך השרת המקומי ----------
  // שער השלמות: באנר אחד למטלה הנוכחית עם מה ש-datastore doctor מצא (שגיאות, אזהרות), ו"תקן" למה שהוא יודע לתקן לבד
  const INTEGRITY_LEVEL = { reject: "שגיאה", warn: "אזהרה", info: "ידיעה" };
  function integrityOf(A) {
    return A ? D.integrity.find((r) => r.course === A.courseFolder && r.folder === A.folder) : null;
  }
  function integrityBannerHTML() {
    const A = cur(), R = integrityOf(A);
    if (!R || !R.problems?.length) return "";
    const shown = R.problems.filter((p) => p.level !== "info");
    if (!shown.length) return "";
    const s = R.summary || {}, open = state.integrityOpen;
    const fixable = (R.fixable || []).length;
    return `<div class="banner ${s.reject ? "warn" : ""} integrity" role="status">${ICON.warn}<div>
        <b>שלמות הנתונים: ${s.reject ? `${s.reject} שגיאות` : ""}${s.reject && s.warn ? ", " : ""}${s.warn ? `${s.warn} אזהרות` : ""}</b>
        <span class="muted"> · נבדק ${when(R.checked_at)}${fixable ? ` · ${fixable} סוגים אפשר לתקן לבד` : ""}</span>
        ${open ? `<ul class="integrity-list">${shown.slice(0, 40).map((p) => `<li><span class="chip">${INTEGRITY_LEVEL[p.level] || p.level}</span> ${esc(p.message)}</li>`).join("")}
          ${shown.length > 40 ? `<li class="muted">ועוד ${shown.length - 40}…</li>` : ""}</ul>` : ""}
      </div>
      <button type="button" class="btn secondary small" data-integrity-toggle>${open ? "סגור" : "פרטים"}</button>
      ${fixable ? `<button type="button" class="btn primary small" data-integrity-fix ${state.integrityFixing ? "disabled" : ""}>${state.integrityFixing ? ICON.spin : ICON.check}תקן מה שאפשר</button>` : ""}
    </div>`;
  }
  async function runIntegrityFix() {
    const A = cur();
    if (!A || state.integrityFixing) return;
    state.integrityFixing = true; render();
    try {
      const out = await api("api/integrity/fix", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder, dryRun: false }) });
      toast(out.done?.length ? out.done.join(" · ") : "לא היה מה לתקן", ICON.check);
      await loadLocal();
    } catch (e) {
      toast(e.message, ICON.warn);
    } finally {
      state.integrityFixing = false; render();
    }
  }

  function bannerHTML() {
    if (LOCAL.on && !LOCAL.health?.root) {
      return `<div class="banner warn">${ICON.warn}<div><b>המערכת פועלת, אבל תיקיית OneDrive של הקורס עוד לא נמצאה במחשב.</b><pre class="banner-pre">${esc(LOCAL.health?.error || "")}</pre></div><button class="btn secondary small" data-act="recheck">בדוק שוב</button></div>`;
    }
    return integrityBannerHTML();
  }

  function drivePanelHTML() {
    if (LOCAL.on) {
      const h = LOCAL.health || {};
      return `<section class="panel" style="margin-top:24px">
        <div class="panel-head"><h2>תיקיית OneDrive</h2><span class="end tag ${h.root ? "ok" : "warn"}">${h.root ? "מחובר" : "לא נמצאה"}</span></div>
        <div class="panel-body">
          ${h.root ? `<p class="lead">ההגשות, טבלאות הציונים והיומן נשמרים בתיקייה הזו, ו-OneDrive מסנכרן אותה לכל מי שיש לו גישה.</p>
            <div class="path-line" dir="ltr">${esc(h.root)}</div>
            <div class="row-start">
              <button class="btn secondary small" data-act="open-folder">${ICON.folder}פתח את תיקיית המטלה</button>
              <button class="btn secondary small" data-act="open-inbox">${ICON.upload}פתח את תיקיית ההורדות</button>
            </div>` : `<pre class="prompt">${esc(h.error || "")}</pre>`}
        </div>
      </section>`;
    }
    return `<section class="panel" style="margin-top:24px">
      <div class="panel-head"><h2>תיקיית OneDrive</h2><span class="end tag warn">לא מחובר</span></div>
      <div class="panel-body">
        <p class="lead">האתר קורא את תיקיית OneDrive של הקורס דרך המערכת שרצה במחשב שמסנכרן אותה:</p>
        <ol class="todo">
          <li>באפליקציית OneDrive מחברים את חשבון האוניברסיטה. בדפדפן, על התיקייה YallaLinearit, לוחצים Add shortcut to My files.</li>
          <li>מורידים את הריפו מ-GitHub ולוחצים פעם אחת על <code dir="ltr">install-autostart.bat</code> (או בכל פעם על <code dir="ltr">start.bat</code>).</li>
          <li>עובדים בכתובת <code dir="ltr">http://localhost:8765</code>. מי שפתח אותה פעם אחת מהאתר הציבורי מועבר אליה לבד.</li>
        </ol>
      </div>
    </section>`;
  }

  // עבודה אמיתית: מציגים את הקובץ עצמו. אחרי הבדיקה, את העבודה המסומנת
  function localDrawerHTML(s, head) {
    const url = (f) => `${BASE}api/file?path=${encodeURIComponent(f.path)}`;
    const pdf = s.files.find((f) => f.marked) || s.files.find((f) => f.name.toLowerCase().endsWith(".pdf") && f.size);
    const qs = rubric().questions;
    const busy = s.status === "grading";
    const canGrade = LOCAL.health?.claude && !s.approved && s.status !== "returned" && !state.run[cur().id];
    return `${head}
      <div class="drawer-body">
        <div class="doc-col">
          ${pdf ? `<iframe class="pdf-view" src="${url(pdf)}" title="${esc(pdf.name)}"></iframe>`
            : `<div class="panel"><div class="empty"><strong>${esc(s.issue || "אין קובץ PDF לתצוגה")}</strong>אפשר לפתוח את הקבצים מהרשימה.</div></div>`}
        </div>
        <aside class="grade-col">
          <div class="grade-card">
            <h3 class="gc-title">הורדה</h3>
            <div class="dl-stack">${downloadsHTML(s)}</div>
            <ul class="file-list">${s.files.map((f) => `<li>${ICON.file}<a href="${url(f)}" target="_blank" rel="noopener" dir="ltr">${esc(f.name)}</a>${f.marked ? `<span class="muted">מסומן</span>` : ""}</li>`).join("") || `<li class="muted">אין קבצים</li>`}</ul>
          </div>
          <div class="grade-card">
            <h3 class="gc-title">ציון</h3>
            ${busy ? `<p class="muted" style="margin:0">Claude בודק את העבודה עכשיו.</p>`
              : s.score != null ? `<div class="grade-top"><span class="big num">${s.score}</span><span class="lbl"><b>${s.approved ? "מאושר" : "עוד לא אושר"}</b>מתוך ${cur().maxGrade || 100}</span></div>
                ${s.q && s.q.length === qs.length && !noRubric() ? `<ul class="breakdown">${qs.map((q, i) => `<li><label>${esc(q.req || `שאלה ${q.n}`)}</label><span class="num ${s.q[i] > q.pts ? "over" : ""}" ${s.q[i] > q.pts ? `title="יותר מהניקוד של השאלה במחוון: צריך לבדוק מחדש"` : ""}>${s.q[i]} / ${q.pts}</span><span class="track"><i class="${s.q[i] < q.pts ? "short" : ""}" style="width:${Math.min(100, (s.q[i] / q.pts) * 100)}%"></i></span></li>`).join("")}</ul>` : ""}
                ${s.review ? `<p class="hint"><span class="flag" style="white-space: normal">${s.approved ? "נבדקה ידנית" : "לבדיקה ידנית"}: ${esc(s.review)}</span></p>` : ""}`
              : `<p class="muted" style="margin:0">עוד לא נבדקה.</p>`}
            <p class="hint">אחרי הבדיקה, העבודה עם ההערות נשמרת ב-"2 - Graded with comments" באותו מספר, והציון בקובץ הציונים של הבודק.</p>
          </div>
          ${s.feedback ? `<div class="grade-card"><h3 class="gc-title">משוב לסטודנט</h3><p style="margin:0; white-space: pre-line">${esc(s.feedback)}</p></div>` : ""}
        </aside>
      </div>
      <div class="drawer-foot"><span class="grow">${s.issue ? esc(s.issue) : "הקבצים שמורים בתיקיית OneDrive של המטלה."}</span>
        ${s.score != null || s.failed ? `<a class="btn ${needsReview(s) ? "primary" : "secondary"}" href="#/review?n=${s.id}">${ICON.pen}${needsReview(s) ? "לבדיקה ידנית" : "ערוך ציון"}</a>` : ""}
        ${canGrade && !busy ? `<button class="btn ${s.status === "pulled" ? "primary" : "secondary"}" data-act="grade-one" data-id="${s.id}">${s.status === "pulled" ? ICON.grade + "בדוק עכשיו" : ICON.redo + "בדיקה חוזרת"}</button>` : ""}
        <button class="btn secondary" data-act="open-folder">${ICON.folder}פתח את התיקייה</button></div>`;
  }

  // ---------- בדיקה ידנית ----------
  // לכאן Claude שולח כל עבודה שהוא לא בטוח בה (needs_review), וגם עבודות שהבדיקה שלהן נכשלה. לכל עבודה: מה הבעיה ואיפה,
  // הערות מוכנות מהמחוון ומהטעויות הנפוצות עם הניקוד שלהן, והציון מחושב לבד. "אשר" שומר ועובר לעבודה הבאה.
  const hashParam = (k) => new URLSearchParams(location.hash.split("?")[1] || "").get(k);

  function reviewList(A = cur()) {
    const queue = A.subs.filter(needsReview);
    return { queue, done: A.subs.filter(wasReviewed) };
  }

  // ההערות המוכנות לשאלה: הטעויות המוכרות מהמחוון, הטעויות הנפוצות במטלה, ומה ש-Claude מצא בעבודה הזו. לכל אחת: בכמה מורידים
  function readyComments(qi, s) {
    const q = rubric().questions[qi], out = new Map();
    (q.deductions || []).forEach((d) => out.set(d.text, { text: d.text, pts: d.points, src: "rubric", n: 0 }));
    mistakeStats().filter((m) => m.q === qi).slice(0, 8).forEach((m) => {
      if (out.has(m.text)) out.get(m.text).n = m.count;
      else out.set(m.text, { text: m.text, pts: m.ded, src: "common", n: m.count });
    });
    const mine = s.mistakes?.[qi] || [];
    mine.forEach((t) => {
      if (!out.has(t)) out.set(t, { text: t, pts: mine.length === 1 && s.q ? q.pts - s.q[qi] : null, src: "claude", n: 0 });
    });
    return [...out.values()].slice(0, 6);
  }

  function draft(s) {
    let d = state.review.edits[s.id];
    if (d) return d;
    const qs = rubric().questions, fresh = s.score == null;  // נכשלה: מתחילים מניקוד מלא ומורידים לפי ההערות
    d = state.review.edits[s.id] = {
      points: qs.map((q, i) => (fresh ? q.pts : s.q?.[i] ?? 0)),
      comments: qs.map((q, i) => s.comments?.[i] || ""),
      picks: qs.map((q, i) => [...(s.mistakes?.[i] || [])]),
      feedback: s.feedback || "",
      reason: "",
      changed: false,
    };
    return d;
  }
  const draftTotal = (d) => {
    const qs = rubric().questions, full = qs.reduce((a, q) => a + q.pts, 0), max = cur().maxGrade || 100;
    return full ? Math.floor((d.points.reduce((a, b) => a + b, 0) / full) * max + 0.5) : 0;
  };

  // בחירה של הערה מוכנה: מסמנת אותה, מחשבת מחדש את הניקוד של השאלה וכותבת את ההערה
  function togglePick(s, qi, text) {
    const d = draft(s), q = rubric().questions[qi], opts = readyComments(qi, s);
    const picks = d.picks[qi];
    const at = picks.indexOf(text);
    if (at >= 0) picks.splice(at, 1); else picks.push(text);
    const lost = picks.reduce((a, t) => a + (opts.find((o) => o.text === t)?.pts || 0), 0);
    d.points[qi] = Math.max(0, half(q.pts - lost));
    d.comments[qi] = picks.length ? picks.join(". ") + "." : "";
    d.changed = true;
  }

  // עריכה של ציון קיים (לא אישור ראשון מהתור, ולא ציון ראשון לעבודה שנכשלה): חייבים לכתוב סיבה, כמו grade_edit.kind_of
  const isEdit = (s) => s.score != null && !needsReview(s);
  // לכל עבודה שנבדקה יש "ערוך ציון" ישר בשורה שלה בטבלה (וגם בחלונית העבודה), לכל אחד בצוות, לא משנה מי בדק
  const editLinkHTML = (s) => (s.score == null ? "" : `<a class="row-edit" data-row-link href="#/review?n=${s.id}" title="${needsReview(s) ? "לבדיקה ידנית" : "ערוך ציון"} (עבודה ${s.id})">${ICON.pen}${needsReview(s) ? "לבדיקה" : "ערוך ציון"}</a>`);

  // יומן העריכות של הציון (api/grade-log): מי, מתי, מאיזה ציון לאיזה ולמה
  function gradeLog(A, s) {
    const key = `${A.id}:${s.id}`, known = state.review.log[key];
    if (known !== undefined) return known;
    state.review.log[key] = null;
    api(`api/grade-log?course=${encodeURIComponent(A.courseFolder)}&assignment=${encodeURIComponent(A.folder)}&number=${s.id}`)
      .then((r) => { state.review.log[key] = r.history?.length ? r.history : (r.entries || []); }, () => { state.review.log[key] = []; })
      .then(() => { if (route() === "/review") render(); });
    return null;
  }
  const KIND_TEXT = { edit: "עריכה", review: "אישור מהבדיקה הידנית", first: "ציון ראשון" };
  // שורה אחת לכל אירוע ביומן (datastore/ledger.py): בדיקה אוטומטית, כישלון, עריכה, שחזור. "עריכה התחילה" לא מוצגת
  function histLine(e) {
    const who = `${esc(e.by || "")} · ${esc(when(e.at))}`;
    if (e.action === "grade_set") return `<div class="rv-hist-top"><b class="num">${esc(e.grade)}</b><span>בדיקה אוטומטית · ${who}</span></div>`;
    if (e.action === "grade_failed") return `<div class="rv-hist-top"><b class="num">—</b><span>הבדיקה נכשלה · ${who}</span></div>
        <p class="rv-hist-err">${esc(e.error || "")}</p>`;
    if (e.action === "grade_replayed") return `<div class="rv-hist-top"><b class="num">${esc(e.grade)}</b><span>שוחזר מהיומן · ${who}</span></div>`;
    return `<div class="rv-hist-top"><b class="num">${e.from == null ? "—" : esc(e.from)} ← ${esc(e.to)}</b>
          <span>${esc(KIND_TEXT[e.kind] || "")} · ${who}</span></div>
        ${e.reason ? `<p>${esc(e.reason)}</p>` : ""}
        ${e.action === "grade_edit_failed" ? `<p class="rv-hist-err">לא הגיע לכל המקומות: ${esc(e.error || "")}</p>` : ""}`;
  }
  function historyHTML(A, s) {
    const log = (gradeLog(A, s) || []).filter((e) => e.action !== "grade_edit_intent");
    if (!log.length) return "";
    return `<details class="rv-hist"><summary>היסטוריית הציון (${log.length})</summary><ol>${log.slice().reverse().map((e) => `
      <li class="${["grade_edit_failed", "grade_failed"].includes(e.action) ? "failed" : ""}">${histLine(e)}</li>`).join("")}</ol></details>`;
  }

  // העמודים של ההגשה כתמונות (api/page), והסימונים של Claude מצוירים מעליהם במקום שלהם
  const pageUrl = (A, id, p) => `${BASE}api/page?course=${encodeURIComponent(A.courseFolder)}&assignment=${encodeURIComponent(A.folder)}&number=${id}&page=${p}`;
  function pagesOf(A, s) {
    const key = `${A.id}:${s.id}`, known = state.review.pages[key];
    if (known !== undefined) return known;
    state.review.pages[key] = null;
    api(`api/pages?course=${encodeURIComponent(A.courseFolder)}&assignment=${encodeURIComponent(A.folder)}&number=${s.id}`)
      .then((r) => { state.review.pages[key] = r.pages; }, () => { state.review.pages[key] = 0; })
      .then(() => { if (route() === "/review") render(); });
    return null;
  }

  function docHTML(A, s) {
    const n = pagesOf(A, s), orig = origFiles(s)[0], marked = markedFiles(s)[0];
    const show = state.review.marks && s.marks?.length;
    const tools = `<div class="rv-doc-tools">
      ${s.marks?.length ? `<button class="rv-toggle" data-rv-marks aria-pressed="${!!state.review.marks}">${ICON.pen}הסימונים של Claude (${s.marks.length})</button>` : `<span class="muted">אין סימונים של Claude</span>`}
      <span class="rv-dl">
        ${orig ? `<a href="${fileUrl(orig, true)}" download>${ICON.download}ההגשה</a>` : ""}
        ${marked ? `<a href="${fileUrl(marked, true)}" download>${ICON.download}הבדוקה</a>` : ""}
      </span>
    </div>`;
    if (n === null) return `${tools}<div class="rv-pages"><div class="rv-page loading">${ICON.spin}טוען את העבודה…</div></div>`;
    if (!n) return `${tools}<div class="rv-pages"><div class="rv-page empty">אין בהגשה עמודים שאפשר להציג.${orig ? ` אפשר להוריד את הקובץ.` : ""}</div></div>`;
    return `${tools}<div class="rv-pages">${Array.from({ length: n }, (_, i) => i + 1).map((p) => `
      <figure class="rv-page">
        <div class="rv-sheet">
          <img src="${pageUrl(A, s.id, p)}" alt="עבודה ${s.id}, עמוד ${p}" loading="lazy">
          ${show ? s.marks.filter((m) => Number(m.page) === p && m.x1 > m.x0).map((m) => `
            <div class="rv-mark" style="left:${m.x0 / 10}%;top:${m.y0 / 10}%;width:${(m.x1 - m.x0) / 10}%;height:${(m.y1 - m.y0) / 10}%">
              <span>${esc(m.text)}</span></div>`).join("") : ""}
        </div>
        ${n > 1 ? `<figcaption>עמוד ${p} מתוך ${n}</figcaption>` : ""}
      </figure>`).join("")}</div>`;
  }

  // שאלה בטופס: שורה אחת סגורה (תווית וניקוד), ונפתחת לניקוד, הערות מוכנות והערה. פתוחות מראש רק השאלות שצריך לבדוק
  function openQuestions(s, d) {
    if (!state.review.open[s.id]) {
      const qs = rubric().questions;
      const want = qs.map((q, i) => i).filter((i) => s.unsure?.[i] || (s.q && s.q[i] < qs[i].pts));
      state.review.open[s.id] = new Set(want);
    }
    return state.review.open[s.id];
  }

  function questionHTML(s, d, qi, open) {
    const q = rubric().questions[qi], unsure = !!s.unsure?.[qi], pts = d.points[qi];
    const head = `<button type="button" class="rq-head" data-rq-toggle="${qi}" aria-expanded="${open}">
      <span class="rq-n num">${qi + 1}</span>
      <span class="rq-label">${esc(q.req || `שאלה ${qi + 1}`)}${unsure ? `<em class="rq-flag">לבדוק</em>` : ""}</span>
      <span class="rq-pts num ${pts > q.pts ? "over" : pts < q.pts ? "lost" : ""}" ${pts > q.pts ? `title="יותר מהניקוד של השאלה במחוון"` : ""}>${fmt(pts)}<small>/${q.pts}</small></span>
      <span class="rq-chev" aria-hidden="true">${ICON.chev}</span>
    </button>`;
    if (!open) {
      const note = d.comments[qi];
      return `<li class="rq ${unsure ? "unsure" : ""}">${head}${note && pts < q.pts ? `<p class="rq-note">${esc(note)}</p>` : ""}</li>`;
    }
    const opts = readyComments(qi, s);
    return `<li class="rq open ${unsure ? "unsure" : ""}" id="rv-q${qi}">${head}
      <div class="rq-body">
        <div class="rq-score">
          <div class="stepper" dir="ltr">
            <button type="button" data-rv-step="${qi}|-0.5" aria-label="פחות חצי נקודה">−</button>
            <input type="number" id="rv-pts-${qi}" data-rv-pts="${qi}" value="${pts}" min="0" max="${q.pts}" step="0.5" aria-label="ניקוד לשאלה ${qi + 1}">
            <button type="button" data-rv-step="${qi}|0.5" aria-label="עוד חצי נקודה">+</button>
          </div>
          <button type="button" class="link-btn" data-rv-set="${qi}|full">ניקוד מלא</button>
          <button type="button" class="link-btn" data-rv-set="${qi}|zero">אפס</button>
          ${s.q && s.q[qi] !== pts ? `<span class="rq-was">Claude נתן ${fmt(s.q[qi])}</span>` : ""}
        </div>
        ${opts.length ? `<div class="rq-chips" role="group" aria-label="הערות מוכנות">${opts.map((o) => {
          const on = d.picks[qi].includes(o.text);
          return `<button type="button" class="rc" data-rv-pick="${qi}" data-text="${esc(o.text)}" aria-pressed="${on}"
            title="${o.src === "rubric" ? "מהמחוון" : o.src === "common" ? `טעות נפוצה במטלה (${o.n} עבודות)` : "Claude מצא את זה בעבודה"}">
            <span>${esc(o.text)}</span>${o.pts ? `<b class="num">−${fmt(o.pts)}</b>` : ""}</button>`;
        }).join("")}</div>` : ""}
        <input class="rq-comment" id="rv-c-${qi}" data-rv-comment="${qi}" value="${esc(d.comments[qi])}" placeholder="הערה לסטודנט (לא חובה)" aria-label="הערה לשאלה ${qi + 1}">
      </div>
    </li>`;
  }

  function reviewView() {
    const A = cur();
    if (!A) return offlineHTML();
    const I = info(A), { queue, done } = reviewList(A);
    const want = hashParam("n");
    if (want && A.subs.some((s) => s.id === want)) state.review.id = want;
    let s = A.subs.find((x) => x.id === state.review.id);
    if (!s || (!want && !needsReview(s))) s = queue[0] || null;
    state.review.id = s?.id || null;
    const total = queue.length + done.length;
    const top = `<header class="rv-top">
      <div><h1>בדיקה ידנית</h1>
        <p>${queue.length ? `${plural(queue.length, "מקרה מיוחד אחד מחכה", "מקרים מיוחדים מחכים")} לך: חסר תרגיל, חסר עמוד, מטלה אחרת או עמוד שאי אפשר לקרוא` : "אין מקרים מיוחדים שמחכים"}${done.length ? ` · ${done.length} כבר נבדקו` : ""}</p></div>
      ${total ? `<div class="rv-meter" role="progressbar" aria-label="כמה נבדקו" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${done.length}"><i style="width:${(100 * done.length) / total}%"></i></div>` : ""}
    </header>`;
    if (!I.subs.length) return `${top}<section class="panel">${emptyPulled()}</section>`;
    if (!s) {
      return `${top}<section class="rv-empty">${ICON.check}<b>הכל נבדק</b><p>${I.graded.length ? "אין עבודות ש-Claude ביקש שאדם יסתכל עליהן." : "אחרי שלב הבדיקה, עבודות ש-Claude לא בטוח בהן יגיעו לכאן."}</p><a class="btn secondary" href="#/">ללוח הבקרה</a></section>`;
    }
    const d = draft(s), qs = rubric().questions, max = A.maxGrade || 100, open = openQuestions(s, d);
    const list = queue.includes(s) ? queue : [s, ...queue];
    const at = list.indexOf(s), prev = list[at - 1], next = list[at + 1];
    const k = kindOf(s), flagged = needsReview(s) || s.review || s.failed;
    const unsure = (s.unsure || []).map((u, i) => (u ? i : -1)).filter((i) => i >= 0);
    const over = overRubric(d.points), edit = isEdit(s), noReason = edit && !d.reason.trim();
    const blocked = !!noRubric() || over.length > 0 || noReason;
    // הכלל קודם לכל: בלי מחוון אין טופס ניקוד, וניקוד שעובר את המחוון לא מאושר
    const rule = noRubric() ? rubricNoticeHTML()
      : over.length ? `<div class="notice rule-notice">${ICON.warn}<div><b>הניקוד בעבודה הזו לא לפי המחוון.</b>
          ${over.map((x) => `${esc(x.q.req || `שאלה ${x.i + 1}`)} קיבלה ${fmt(x.p)}, ובמחוון יש לה ${fmt(x.q.pts)}.`).join(" ")}
          כנראה היא נבדקה לפי חלוקה אחרת של הניקוד, אז צריך לתת ניקוד מחדש לכל השאלות לפי המחוון, או לבדוק אותה שוב עם Claude.
          ${LOCAL.health?.claude && !s.approved ? `<button type="button" class="btn secondary small" data-act="grade-one" data-id="${s.id}" ${state.run[A.id] ? "disabled" : ""}>${ICON.redo}לבדוק שוב עם Claude</button>` : ""}</div></div>`
      : `<p class="rv-rule">${ICON.lock}הניקוד לפי המחוון בלבד: לכל שאלה עד הניקוד שלה במחוון.</p>`;
    return `${top}
      <nav class="rv-steps" aria-label="העבודות בתור">
        ${prev ? `<a class="rv-arrow" href="#/review?n=${prev.id}" aria-label="העבודה הקודמת">${ICON.chev}</a>` : `<span class="rv-arrow" aria-hidden="true"></span>`}
        <div class="rv-pills">${list.map((x) => `<a class="rv-pill ${x.id === s.id ? "on" : ""}" href="#/review?n=${x.id}" title="${esc(REVIEW_KIND[kindOf(x)][0])}" ${x.id === s.id ? 'aria-current="true"' : ""}><i class="k-${kindOf(x)}"></i>${x.id}</a>`).join("")}</div>
        ${next ? `<a class="rv-arrow next" href="#/review?n=${next.id}" aria-label="העבודה הבאה">${ICON.chev}</a>` : `<span class="rv-arrow" aria-hidden="true"></span>`}
      </nav>
      <div class="rv-main">
        <section class="rv-doc">
          <div class="rv-issue ${flagged ? `k-${k}` : "ok"}">
            <div class="rv-issue-top"><span class="rv-work">עבודה <b class="num">${s.id}</b></span>
              ${flagged ? `<span class="rv-kind">${esc(REVIEW_KIND[k][0])}</span>` : s.approved ? `<span class="rv-kind ok">אושרה${s.reviewedBy ? ` · ${esc(s.reviewedBy)}` : ""}</span>` : ""}</div>
            ${flagged && s.missing ? `<p class="rv-missing">חסר: <b>${esc(s.missing)}</b></p>` : ""}
            ${flagged ? `<p>${esc(s.failed || s.review || "Claude ביקש שאדם יבדוק את העבודה.")}</p>` : ""}
            ${s.failed && LOCAL.health?.claude ? `<button class="btn secondary small" data-act="grade-one" data-id="${s.id}" ${state.run[A.id] ? "disabled" : ""}>${ICON.redo}לבדוק שוב עם Claude</button>` : ""}
          </div>
          ${docHTML(A, s)}
        </section>
        <form class="rv-panel" data-rv-form="${s.id}" autocomplete="off">
          <div class="rv-panel-head"><h2>ציון</h2>${unsure.length ? `<span>Claude לא בטוח ב${unsure.map((i) => `<button type="button" class="link-btn" data-rv-jump="${i}">שאלה ${i + 1}</button>`).join(", ")}</span>` : ""}</div>
          ${rule}
          ${noRubric() ? "" : `<ol class="rq-list">${qs.map((q, qi) => questionHTML(s, d, qi, open.has(qi))).join("")}</ol>
          <details class="rv-fb" ${state.review.fbOpen ? "open" : ""}><summary>משוב לסטודנט</summary>
            <textarea id="rv-fb" data-rv-feedback rows="4" aria-label="משוב לסטודנט">${esc(d.feedback)}</textarea></details>`}
          ${edit && !noRubric() ? `<div class="rv-reason"><label for="rv-reason">סיבה לשינוי <em>חובה</em></label>
            <textarea id="rv-reason" data-rv-reason rows="2" maxlength="1000" placeholder="למשל: ערעור, הנימוק בשאלה 12 נמצא בעמוד 2" aria-required="true">${esc(d.reason)}</textarea>
            <small>נרשם ביומן עם השם שלך, השעה, הציון הקודם והחדש.</small></div>` : ""}
          ${historyHTML(A, s)}
          <div class="rv-bar">
            <div class="rv-total"><b class="num" id="rv-total">${noRubric() ? "—" : draftTotal(d)}</b><span>/ ${max}</span></div>
            <button type="submit" class="btn primary" ${state.review.saving || blocked ? "disabled" : ""} title="${noReason && !noRubric() && !over.length ? "צריך לכתוב סיבה לשינוי" : blocked ? "אפשר לאשר רק ניקוד לפי המחוון" : "Ctrl+Enter"}" data-rv-submit>${state.review.saving ? ICON.spin : ICON.check}${needsReview(s) ? (next ? "אשר ועבור לבאה" : "אשר") : edit ? "שמור שינוי" : "שמור"}</button>
          </div>
        </form>
      </div>`;
  }

  async function saveReview(id) {
    const A = cur(), s = A?.subs.find((x) => x.id === id);
    if (!s || state.review.saving) return;
    const d = draft(s), wasQueued = needsReview(s);
    if (noRubric() || overRubric(d.points).length) { toast(noRubric() || `אפשר לאשר רק ניקוד לפי המחוון. ${RUBRIC_RULE}`, ICON.warn); return; }
    if (isEdit(s) && !d.reason.trim()) { toast("צריך לכתוב סיבה לשינוי הציון", ICON.warn); $("#rv-reason")?.focus(); return; }
    const { queue } = reviewList(A);
    const at = queue.findIndex((x) => x.id === id);
    const next = wasQueued ? (queue[at + 1] || queue.find((x) => x.id !== id)) : null;
    state.review.saving = true;
    render();
    try {
      const r = await api("api/review", { method: "POST", body: JSON.stringify({
        course: A.courseFolder, assignment: A.folder, number: id,
        points: d.points, comments: d.comments, feedback: d.feedback, mistakes: d.picks, reason: d.reason,
      }) });
      delete state.review.edits[id];
      delete state.review.log[`${A.id}:${id}`];
      toast((r.from != null && String(r.from) !== String(r.grade) ? `עבודה ${id}: הציון שונה מ-${r.from} ל-${r.grade}` : `עבודה ${id} נשמרה: ${r.grade}`)
        + (r.not_updated?.length ? `. לא עודכן עכשיו: ${r.not_updated.join(", ")} (יתעדכן בפעם הבאה)` : ""));
      state.review.saving = false;
      await loadLocal();
      const target = next ? `#/review?n=${next.id}` : wasQueued ? "#/review" : location.hash;
      if (location.hash === target) render(); else location.hash = target;
    } catch (e) {
      state.review.saving = false;
      delete state.review.log[`${A.id}:${id}`];  // גם עריכה שנכשלה באמצע נרשמת ביומן
      render();
      toast(e.message, ICON.warn);
    }
  }

  // ---------- סטטיסטיקה: לשונית הדשבורד של מסד הנתונים (stats/, api/stats) ----------
  // כל מה שבמסד, לכל המטלות: טבלה לכל קורס להשוואה בין מטלות, ולמטלה שנבחרה ההתפלגות, השאלות והטעויות הנפוצות.
  // המספרים מגיעים מהמודול stats בלבד (אותם מספרים שהאתר מראה בלוח הבקרה), אף פעם לא מחושבים כאן.
  const KIND_LABEL = (k) => (REVIEW_KIND[k] || [k])[0];
  const statOf = (key) => D.stats.find((s) => s.key === key);
  const pctCell = (v) => (v == null ? `<span class="muted">—</span>` : `${v}%`);
  const numCell = (v) => (v == null ? `<span class="muted">—</span>` : fmt(v));

  // הסטטיסטיקה של מטלה, מאותו מסד נתונים (Statistics/ בדרייב): בשלב "בדיקה וציון" לכל מטלה שיש בה עבודות בדוקות
  const statKeyOf = (A) => (A ? `${A.courseFolder}/Assignment ${A.n - 1}` : null);
  const statOfAssignment = (A) => statOf(statKeyOf(A));
  function assignmentStatsHTML(A) {
    const S = statOfAssignment(A);
    if (!S?.counts?.graded) return "";
    const g = S.grade, k = S.counts;
    const tile = (label, value, sub = "", cls = "") => `<div class="stat ${cls}"><span class="stat-l">${label}</span><b class="stat-v num">${value}</b>${sub ? `<span class="stat-s">${sub}</span>` : ""}</div>`;
    const qs = S.per_question.map((q) => `<li><span class="sq-l">שאלה ${q.index}</span>
        <span class="track"><i style="width:${q.success_pct ?? 0}%"></i></span><b class="num">${pctCell(q.success_pct)}</b>
        <small class="muted">${q.mistakes[0] ? esc(q.mistakes[0].text) : ""}</small></li>`).join("");
    const top = S.per_question.flatMap((q) => q.mistakes.map((m) => ({ ...m, q: q.index }))).sort((a, b) => b.count - a.count).slice(0, 3);
    return `<section class="panel a-stats" aria-label="הסטטיסטיקה של המטלה">
      <div class="panel-head"><h3>הסטטיסטיקה של המטלה</h3>
        <span class="meta">ממסד הנתונים בדרייב · חושב ${when(S.computed_at)}</span>
        <button class="btn ghost small end" data-stats-open="${esc(S.key)}">${ICON.chev}כל הנתונים</button></div>
      <div class="panel-body">
        <div class="stat-row">
          ${tile("נבדקו", `${k.graded}<small>/${k.submitted}</small>`, k.submitted ? `${Math.round((100 * k.graded) / k.submitted)}% מההגשות` : "")}
          ${tile("ממוצע", fmt(g.mean), `מתוך ${S.max_grade}`)}
          ${tile("חציון", fmt(g.median), g.sd != null ? `סטיית תקן ${fmt(g.sd)}` : "")}
          ${tile("עוברים", g.pass_pct != null ? `${g.pass_pct}%` : "—", `ציון ${fmt(0.6 * S.max_grade)} ומעלה`)}
          ${tile("לבדיקה ידנית", k.needs_review, "מקרים לאדם", k.needs_review ? "warn" : "ok")}
          ${tile("אושרו", `${k.approved}<small>/${k.graded}</small>`, "ציונים שאדם אישר")}
        </div>
        ${qs ? `<ol class="sq-list" aria-label="הצלחה לפי שאלה">${qs}</ol>` : ""}
        ${top.length ? `<p class="hint">הטעויות הנפוצות: ${top.map((m) => `${esc(m.text)} <small class="num">(שאלה ${m.q}, ${m.count})</small>`).join(" · ")}</p>` : ""}
      </div>
    </section>`;
  }

  function statsView() {
    if (!LOCAL.on) return offlineHTML();
    const all = D.stats.filter((s) => !s.error), withData = all.filter((s) => s.counts?.graded);
    const errors = D.stats.filter((s) => s.error);
    const curKey = cur() ? `${cur().courseFolder}/Assignment ${cur().n - 1}` : null;
    if (!statOf(state.statsKey)?.counts?.graded) state.statsKey = (withData.find((s) => s.key === curKey) || withData[0])?.key || null;
    const S = statOf(state.statsKey);
    const newest = all.map((s) => s.computed_at).filter(Boolean).sort().pop();
    const head = `<div class="page-head">
      <div><h1>סטטיסטיקה</h1>
        <p>מסד הנתונים של הבדיקה: לכל מטלה ולכל שאלה, ממוצע, התפלגות, טעויות נפוצות וכמה מחכות לאדם. מספרים בלבד, בלי שום פרט מזהה של סטודנט. מתעדכן לבד אחרי כל בדיקה ואישור, בכל המחשבים של הצוות.</p>
        ${newest ? `<p class="muted">עודכן לאחרונה ${when(newest)} · הקבצים: <code dir="ltr">Statistics/</code> בתיקייה המשותפת · <code dir="ltr">python -m stats show</code> מהמסוף</p>` : ""}</div>
    </div>
    ${errors.map((e) => `<div class="notice">${ICON.warn}<div><b>${esc(e.key)}</b>: הסטטיסטיקה לא חושבה. ${esc(e.error)}</div></div>`).join("")}`;
    if (!withData.length) return `${head}<section class="rv-empty">${ICON.check}<b>עוד אין עבודות בדוקות</b><p>אחרי הבדיקה הראשונה המטלה תופיע כאן עם הממוצע, ההתפלגות והטעויות הנפוצות שלה.</p></section>`;
    return `${head}${D.courses.map((c) => statsCourseTable(c, all.filter((s) => s.course === c.folder))).join("")}
      ${S ? statsDetailHTML(S) : ""}
      <div class="st-usage">${usageHTML()}</div>`;
  }

  function statsCourseTable(c, list) {
    if (!list.length) return "";
    const sorted = list.slice().sort((a, b) => (a.slot ?? 99) - (b.slot ?? 99));
    const active = sorted.filter((s) => s.counts?.graded || s.key === state.statsKey), allKey = `stats:all:${c.folder}`;
    const showAll = foldOpen(allKey) || active.length === sorted.length;
    const more = sorted.length > active.length || foldOpen(allKey)
      ? `<button type="button" class="fold-more" data-fold="${esc(allKey)}" data-fold-def="0" aria-expanded="${showAll}">${showAll ? "הצג רק מטלות עם עבודות בדוקות" : `הצג את כל ${sorted.length} המטלות`}</button>` : "";
    const rows = (showAll ? sorted : active).map((s) => {
      const g = s.grade, k = s.counts, sel = s.key === state.statsKey, has = k.graded > 0;
      const review = k.needs_review ? `<span class="st-warn">${k.needs_review}</span>` : "0";
      return `<tr class="${has ? "clickable" : "muted"} ${sel ? "sel" : ""}" ${has ? `data-stats-key="${esc(s.key)}" tabindex="0"` : ""} ${sel ? 'aria-current="true"' : ""}>
        <td><b>${esc(s.title || `הגשה ${s.slot}`)}</b></td>
        <td class="num">${k.submitted || `<span class="muted">—</span>`}</td>
        <td class="num">${has ? `${k.graded}<small class="muted">/${k.submitted}</small>` : `<span class="muted">—</span>`}</td>
        <td class="num">${numCell(g.mean)}</td>
        <td class="num col-hide">${numCell(g.median)}</td>
        <td class="num col-hide">${numCell(g.sd)}</td>
        <td class="num">${pctCell(g.pass_pct)}</td>
        <td class="num">${has ? review : `<span class="muted">—</span>`}</td>
        <td class="num col-hide">${has ? `${k.approved}<small class="muted">/${k.graded}</small>` : `<span class="muted">—</span>`}</td>
        <td class="col-hide">${s.graders.by.map((x) => esc(x.name)).join(", ") || `<span class="muted">—</span>`}</td>
      </tr>`;
    }).join("");
    return `<section class="panel st-course">
      <div class="panel-head"><h2>${esc(c.name)}</h2><span class="meta">לחיצה על מטלה פותחת את הפירוט שלה</span></div>
      <div class="table-wrap"><table class="st-table">
        <thead><tr><th>מטלה</th><th>הוגשו</th><th>נבדקו</th><th>ממוצע</th><th class="col-hide">חציון</th><th class="col-hide">סטיית תקן</th><th>עוברים</th><th>לבדיקה ידנית</th><th class="col-hide">אושרו</th><th class="col-hide">בודקים</th></tr></thead>
        <tbody>${rows}</tbody></table></div>${more}
    </section>`;
  }

  function statsDetailHTML(S) {
    const g = S.grade, k = S.counts, H = g.histogram, most = Math.max(...H.counts, 1);
    const course = D.courses.find((c) => c.folder === S.course)?.name || S.course;
    const tile = (label, value, sub = "", cls = "") => `<div class="stat ${cls}"><span class="stat-l">${label}</span><b class="stat-v num">${value}</b>${sub ? `<span class="stat-s">${sub}</span>` : ""}</div>`;
    const kinds = Object.entries(k.review_kinds || {}).map(([kind, n]) => `<span class="chip">${esc(KIND_LABEL(kind))}<span class="c num">${n}</span></span>`).join("");
    const hist = `<div class="dist-wrap">
      <div class="dist" role="img" aria-label="התפלגות ציונים">
        ${H.bins.map((b, i) => `<div class="bar ${b.to <= 0.6 * S.max_grade ? "low" : ""} ${H.counts[i] ? "" : "zero"}"><span class="v num">${H.counts[i] || ""}</span><i style="height:${(H.counts[i] / most) * 100}%"></i><span class="l num">${fmt(b.from)}–${fmt(i === H.bins.length - 1 ? b.to : b.to - (Number.isInteger(b.to) ? 1 : 0))}</span></div>`).join("")}
      </div>
      <dl class="kv">
        <div><dt>מינימום</dt><dd class="num">${numCell(g.min)}</dd></div>
        <div><dt>מקסימום</dt><dd class="num">${numCell(g.max)}</dd></div>
        <div><dt>ציון מלא</dt><dd class="num">${g.full_marks}</dd></div>
        <div><dt>מתחת ל-${fmt(0.6 * S.max_grade)}</dt><dd class="num">${g.n - Math.round(((g.pass_pct ?? 100) / 100) * g.n)}</dd></div>
        ${g.out_of_range ? `<div><dt title="ציונים מחוץ לטווח 0 עד ${S.max_grade}, לא נספרו">מחוץ לטווח</dt><dd class="num">${g.out_of_range}</dd></div>` : ""}
      </dl></div>`;
    const qRows = S.per_question.map((q) => {
      const top = q.mistakes[0];
      return `<tr>
        <td><b>שאלה ${q.index}</b><br><small class="muted">${esc(q.label)}</small></td>
        <td class="num">${numCell(q.points)}</td>
        <td class="num">${q.graded}</td>
        <td class="num">${numCell(q.mean)}</td>
        <td class="st-bar-cell"><span class="track"><i style="width:${q.success_pct ?? 0}%"></i></span><b class="num">${pctCell(q.success_pct)}</b></td>
        <td class="num col-hide">${pctCell(q.full_marks_pct)}</td>
        <td class="num col-hide">${pctCell(q.zero_pct)}</td>
        <td class="num">${q.unsure ? `<span class="st-warn">${q.unsure}</span>` : "0"}</td>
        <td>${top ? `${esc(top.text)} <small class="muted num">(${top.count}, ${top.pct}%)</small>` : `<span class="muted">—</span>`}</td>
      </tr>`;
    }).join("");
    const mistakes = S.per_question.flatMap((q) => q.mistakes.map((m) => ({ ...m, q: q.index }))).sort((a, b) => b.count - a.count || a.q - b.q);
    const top = mistakes.slice(0, 15), mostM = top[0]?.count || 1;
    const hardest = S.per_question.filter((q) => q.success_pct != null).sort((a, b) => a.success_pct - b.success_pct)[0];
    const live = cur() && `${cur().courseFolder}/Assignment ${cur().n - 1}` === S.key && mistakeStats(cur()).length ? cur() : null;
    const mkList = top.length ? `<ol class="mk-list">${top.map((m) => `<li><div class="mk-row">
        <span class="mk-text"><b>${esc(m.text)}</b><small>שאלה ${m.q}${m.in_rubric ? " · במחוון" : ""}${m.deduction != null ? ` · בדרך כלל −${fmt(m.deduction)}` : ""}</small></span>
        <span class="track"><i style="width:${(m.count / mostM) * 100}%"></i></span>
        <span class="mk-n num">${m.count}<small>${m.pct}%</small></span></div></li>`).join("")}</ol>
      ${mistakes.length > top.length ? `<p class="hint">ועוד ${mistakes.length - top.length} סוגי טעויות פחות נפוצים.</p>` : ""}` : `<p class="muted empty-line">אין טעויות רשומות.</p>`;
    return `<section class="st-detail" aria-live="polite">
      <div class="page-head st-detail-head"><div><h2>${esc(S.title || `הגשה ${S.slot}`)}</h2><p class="muted">${esc(course)}${S.moodle_id ? ` · מזהה מודל ${esc(S.moodle_id)}` : ""} · חושב ${when(S.computed_at)}${S.computed_by ? ` על ידי ${esc(S.computed_by)}` : ""}</p></div></div>
      <div class="stat-row compact">
        ${tile("נבדקו", `${k.graded}<small>/${k.submitted}</small>`, k.submitted ? `${Math.round((100 * k.graded) / k.submitted)}% מההגשות` : "")}
        ${tile("ממוצע", fmt(g.mean), `מתוך ${S.max_grade}`)}
        ${tile("חציון", fmt(g.median), g.sd != null ? `סטיית תקן ${fmt(g.sd)}` : "")}
        ${tile("עוברים", g.pass_pct != null ? `${g.pass_pct}%` : "—", `ציון ${fmt(0.6 * S.max_grade)} ומעלה`)}
        ${tile("לבדיקה ידנית", k.needs_review, k.failed ? `${k.failed} נכשלו` : "מקרים לאדם", k.needs_review ? "warn" : "ok")}
        ${tile("אושרו", `${k.approved}<small>/${k.graded}</small>`, "ציונים שאדם אישר")}
      </div>
      ${kinds ? `<div class="chips st-kinds">${kinds}</div>` : ""}
      <div class="st-folds">
        ${foldHTML("stats:hist", { title: "התפלגות ציונים", def: true,
          sum: g.n ? `${g.n} ציונים · מינימום ${numCell(g.min)} · מקסימום ${numCell(g.max)} · ${g.full_marks} ציון מלא` : "אין ציונים",
          body: () => (g.n ? hist : `<p class="muted empty-line">אין ציונים.</p>`) })}
        ${foldHTML("stats:mistakes", { title: "טעויות נפוצות",
          sum: mistakes.length ? `${mistakes.length} סוגים · הנפוצה: ${esc(mistakes[0].text)} (${mistakes[0].count})` : "אין טעויות רשומות",
          body: () => (live ? mistakesHTML(live) : mkList) })}
        ${foldHTML("stats:questions", { title: "לפי שאלה",
          sum: hardest ? `${S.per_question.length} שאלות · הקשה ביותר: שאלה ${hardest.index} (${pctCell(hardest.success_pct)} הצלחה)` : "אין מחוון, אז אין ניקוד לפי שאלה",
          body: () => `${S.over_rubric ? `<p class="hint">${S.over_rubric} עבודות עם ניקוד מחוץ למחוון לא נספרות כאן.</p>` : ""}<div class="table-wrap"><table class="st-table st-q">
          <thead><tr><th>שאלה</th><th>ניקוד</th><th>נבדקו</th><th>ממוצע</th><th>הצלחה</th><th class="col-hide">ניקוד מלא</th><th class="col-hide">אפס</th><th>לא בטוח</th><th>הטעות הנפוצה ביותר</th></tr></thead>
          <tbody>${qRows || `<tr><td colspan="9" class="muted">אין מחוון, אז אין ניקוד לפי שאלה.</td></tr>`}</tbody></table></div>` })}
      </div>
      <p class="hint">בודקים: ${S.graders.by.map((x) => `${esc(x.name)} (${x.graded})`).join(", ") || "—"}</p>
    </section>`;
  }

  const views = {
    "/review": () => reviewView(),
    "/stats": () => statsView(),
    "/"() {
      const A = cur(), I = info(A);
      return `
        <div class="page-head">
          <div>
            <h1>${A.title}</h1>
            <p>${esc(course().name)}. מועד הגשה ${dueText(A)}. ${rubric().questions.length} שאלות, ${A.maxGrade || 100} נקודות.</p>
            ${A.notes ? `<p class="muted">${esc(A.notes)}</p>` : ""}
          </div>
        </div>
        ${noRubric() ? rubricNoticeHTML() : ""}
        ${pipelineHTML()}
        ${statsMiniHTML(A, I)}
        ${reviewCalloutHTML(A)}
        <div class="home-folds">
          ${foldHTML("home:overview", {
            title: `כל המטלות ב${esc(course().name)}`,
            sum: plural(D.assignments.filter((a) => a.courseId === state.courseId && a.subs.length).length, "מטלה אחת עם הגשות", "מטלות עם הגשות"),
            body: () => overviewHTML(),
          })}
          ${foldHTML("home:rubric", {
            title: "מחוון", sum: noRubric() ? "עוד אין מחוון" : `${rubric().questions.length} שאלות · ${A.maxGrade || 100} נקודות`,
            body: () => rubricSummaryHTML(),
            link: `<a class="end link" href="#/grade" data-goto-tab="grade:instr">פרטים</a>`,
          })}
        </div>`;
    },
    "/pull": () => stageView("pull"),
    "/grade": () => stageView("grade"),
    "/return": () => stageView("ret"),
    "/runs"() {
      return `
        <div class="page-head"><div><h1>יומן פעילות</h1><p>מה שבאמת קרה בתיקיות של כל הקורסים: כל ZIP שנמשך ממודל, כל עדכון של קובץ ציונים וכל העלאה למודל שאומתה.</p></div></div>
        <section class="panel"><div class="panel-body tight">${logHTML(80, false)}</div></section>`;
    },
    "/settings"() {
      const node = (title, tech, tag, cls = "warn") => `<div class="node"><b>${title}</b><small>${tech}</small><span class="tag ${cls}">${tag}</span></div>`;
      return `
        <div class="page-head"><div><h1>חיבורים והגדרות</h1><p>איך המערכת בנויה ומה מחובר עכשיו.</p></div></div>
        <section class="panel">
          <div class="panel-head"><h2>איך המערכת בנויה</h2></div>
          <div class="panel-body">
            <div class="arch">
              <div class="arch-row">
                ${node("מודל", "דרך Claude in Chrome, בכרום ובחשבון שלך", ...(LOCAL.health?.moodle ? ["מחובר", "ok"] : LOCAL.on ? ["צריך להתחבר ל-Claude", "warn"] : ["לא ידוע", "warn"]))}
                <span class="arch-link" aria-hidden="true">⇄</span>
                ${node("המערכת", "פייתון במחשב שמסנכרן את התיקייה (start.bat)", ...(LOCAL.on ? ["פועלת", "ok"] : ["לא מחוברת", "warn"]))}
                <span class="arch-link" aria-hidden="true">⇄</span>
                ${node("Claude", "בדיקה, סימון וציון", ...(LOCAL.health?.claude ? ["מחובר", "ok"] : ["עוד לא מחובר", "warn"]))}
              </div>
              <span class="arch-v" aria-hidden="true">⇅</span>
              <div class="arch-row center">${node("תיקיית OneDrive", "YallaLinearit: הגשות, ציונים ויומן", ...(LOCAL.health?.root ? ["מחוברת", "ok"] : ["לא מחוברת", "warn"]))}</div>
              <span class="arch-v" aria-hidden="true">⇅</span>
              <div class="arch-row center">${node("האתר הזה", ON_LOCAL_HOST ? "דרך המערכת במחשב" : "Vercel, מתחבר למערכת שבמחשב", ...(LOCAL.on ? ["מחובר", "ok"] : ["לא מחובר", "warn"]))}</div>
            </div>
          </div>
        </section>
        ${drivePanelHTML()}
        <div class="grid-2">
          <section class="panel">
            <div class="panel-head"><h2>מפתחות</h2><span class="meta">נשמרים בקובץ .env במחשב שמריץ את המערכת</span></div>
            <div class="panel-body">
              ${secretField("ANTHROPIC_API_KEY", "בדיקת העבודות עם Claude. לא חובה כש-Claude Code מחובר במחשב", LOCAL.health?.claudeVia === "api")}
              <p class="hint">למודל לא צריך מפתח: הוא עובד דרך Claude in Chrome, בחשבון שלך.</p>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><h3>כללים שהמערכת שומרת</h3></div>
            <div class="panel-body">
              <ul class="emph" style="margin:0; padding:0; border:0">
                <li>שום דבר לא עולה למודל בלי "כן" של אדם על אותה העלאה.</li>
                <li>ל-Claude נשלחות רק הגשות ממוספרות. שמות ות"ז לא יוצאים מהמחשב ומטבלת המפתח.</li>
                <li>ציונים מותאמים לסטודנטים לפי מספר, אף פעם לא לפי סדר השורות.</li>
                <li>אף סיסמה לא נכנסת למערכת. למודל ול-Claude מתחברים בעצמך.</li>
              </ul>
            </div>
          </section>
        </div>`;
    },
  };

  // ---------- Drawer: the submission and its marked copy ----------
  function drawerHTML(s) {
    const files = s.files.filter((f) => !f.marked).map((f) => `<span dir="ltr">${esc(f.name)}</span>`).join(", ");
    const head = `
      <div class="drawer-head">
        <div>
          <h2>${esc(s.name)}</h2>
          <div class="sub"><span>${when(s.submittedAt)}</span><span>${files}</span>${statusPill(s)}</div>
        </div>
        <button class="btn ghost close" data-act="close" aria-label="סגור">${ICON.close}</button>
      </div>`;

    return localDrawerHTML(s, head);
  }

  let lastFocus = null;
  function openDrawer(id) {
    const s = cur().subs.find((x) => x.id === id);
    if (!s) return;
    state.openId = id;
    lastFocus = document.activeElement;
    const d = $("#drawer");
    d.innerHTML = drawerHTML(s);
    d.setAttribute("aria-hidden", "false");
    d.classList.add("open");
    const scrim = $("#scrim");
    scrim.hidden = false;
    requestAnimationFrame(() => scrim.classList.add("on"));
    setTimeout(() => $(".close", d)?.focus(), 60);
  }
  function refreshDrawer() {
    if (!state.openId) return;
    const s = cur().subs.find((x) => x.id === state.openId);
    if (s && !$("#drawer").contains(document.activeElement)) $("#drawer").innerHTML = drawerHTML(s);
  }
  function closeDrawer() {
    if (!state.openId) return;
    state.openId = null;
    const d = $("#drawer");
    d.classList.remove("open");
    d.setAttribute("aria-hidden", "true");
    const scrim = $("#scrim");
    scrim.classList.remove("on");
    setTimeout(() => (scrim.hidden = true), 200);
    lastFocus?.focus?.();
  }

  function gradeOne(id) {
    runLocalGrade([id]);
  }

  // ---------- Render ----------
  const route = () => { const r = (location.hash.replace(/^#/, "") || "/").split("?")[0]; return views[r] ? r : "/"; };

  function renderNav() {
    $$(".nav a").forEach((a) => (a.dataset.route === route() ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    const A = cur();
    if (!A) { $$(".nav-badge").forEach((b) => (b.textContent = "")); return; }
    const rb = $("#nav-review-badge"), waiting = A.subs.filter(needsReview).length;
    rb.textContent = waiting || "";
    rb.title = waiting ? `${waiting} עבודות מחכות לבדיקה ידנית` : "";
    const I = info(A), run = state.run[A.id];
    $$(".nav-stage").forEach((a) => {
      const st = a.dataset.stage, done = I.done[st];
      a.classList.toggle("done", done);
      $(".nav-step", a).innerHTML = done ? ICON.check : `<span>${STAGES[st].no}</span>`;
      // רק סימן "רץ עכשיו". את המספרים רואים בלוח הבקרה
      const badge = $(".nav-badge", a), running = run?.stage === st || (st === "ret" && sendingHere());
      if (running) badge.innerHTML = ICON.spin;
      else badge.textContent = "";
      badge.className = `nav-badge ${running ? "running" : ""}`;
    });
  }

  function renderPickers() {
    const cs = $("#course-select"), as = $("#assignment-select");
    const list = D.assignments.filter((a) => a.courseId === state.courseId);
    // כותבים מחדש רק כשמשהו השתנה: טעינה מחדש מ-OneDrive לא סוגרת רשימה שפתוחה עכשיו
    const fill = (el, html) => { if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; } };
    fill(cs, D.courses.map((c) => `<option value="${c.id}" ${c.id === state.courseId ? "selected" : ""}>${esc(c.name)}</option>`).join("") || "<option>אין קורסים</option>");
    fill(as, list.map((a) => `<option value="${a.id}" ${a.id === state.assignmentId ? "selected" : ""}>${esc(a.title)}</option>`).join("") || "<option>אין מטלות</option>");
    cs.disabled = !D.courses.length;
    as.disabled = !list.length;
  }

  function render() {
    // שמירת פוקוס בשדות טקסט בזמן רינדור מחדש
    const ae = document.activeElement;
    const keep = ae && ae.id && $("#main").contains(ae) ? { id: ae.id, s: ae.selectionStart, e: ae.selectionEnd } : null;

    // ה-V מונפש פעם אחת, ברינדור שבו השלב הושלם (false = הושלם הרגע)
    D.assignments.forEach((A) => {
      const I = info(A);
      ["pull", "grade", "ret"].forEach((st) => {
        const k = `${A.id}:${st}`;
        if (!I.done[st] || state.run[A.id]?.stage === st) { delete state.seenDone[k]; return; }
        if (state.seenDone[k] === undefined) state.seenDone[k] = booted && A.id === state.assignmentId ? false : true;
        else if (state.seenDone[k] === false) state.seenDone[k] = true;
      });
    });

    let html;
    if (state.loading && !booted) html = `<div class="loading">${ICON.spin}טוען…</div>`;
    else if (!cur() && !["/settings", "/runs", "/stats"].includes(route())) html = offlineHTML();
    else html = views[route()]();
    $("#main").innerHTML = bannerHTML() + html;
    renderNav();
    renderStatus();

    if (keep) {
      const el = document.getElementById(keep.id);
      if (el) { el.focus(); try { el.setSelectionRange(keep.s, keep.e); } catch {} }
    }

    D.assignments.forEach((A) => A.subs.forEach((s) => (s.fresh = false)));
  }

  // ---------- Events ----------
  document.addEventListener("click", (e) => {
    const t = e.target;
    const runBtn = t.closest("[data-run]");
    if (runBtn) { runStage(runBtn.dataset.run); return; }
    const pChip = t.closest("[data-pull-chip]");
    if (pChip) { state.pullLimit = Number(pChip.dataset.pullChip); render(); return; }
    if (state.pullPick && !t.closest(".pull-pick")) { state.pullPick = null; render(); }  // לחיצה מחוץ לחלונית סוגרת אותה
    const gChip = t.closest("[data-grade-chip]");
    if (gChip) { state.gradeCount = Number(gChip.dataset.gradeChip); store.set("gradeCount", state.gradeCount); render(); return; }
    if (state.gradePick && !t.closest(".grade-pick")) { state.gradePick = null; render(); }  // לחיצה מחוץ לחלונית סוגרת אותה
    // חלון מתקפל (fold): לחיצה על הכותרת מגדילה או מקטינה, ונזכר בין ביקורים
    const fold = t.closest("[data-fold]");
    if (fold) { const k = fold.dataset.fold; state.fold[k] = !foldOpen(k, fold.dataset.foldDef === "1"); store.set("fold", state.fold); render(); return; }

    // לוח הבקרה: טעות נפוצה שנפתחה
    const mk = t.closest("[data-mistake]");
    if (mk) { state.mistakeOpen = state.mistakeOpen === mk.dataset.mistake ? null : mk.dataset.mistake; render(); return; }

    // הבדיקה הידנית
    const rvs = reviewSub();
    const pick = t.closest("[data-rv-pick]");
    if (pick && rvs) { togglePick(rvs, Number(pick.dataset.rvPick), pick.dataset.text); render(); return; }
    const set = t.closest("[data-rv-set], [data-rv-step]");
    if (set && rvs) {
      const [qi, how] = (set.dataset.rvSet || set.dataset.rvStep).split("|"), q = rubric().questions[qi], d = draft(rvs);
      if (how === "full") { d.points[qi] = q.pts; d.picks[qi] = []; d.comments[qi] = ""; }
      else if (how === "zero") { d.points[qi] = 0; d.picks[qi] = []; d.comments[qi] = d.comments[qi] || "השאלה לא נמצאה בהגשה."; }
      else d.points[qi] = Math.min(q.pts, Math.max(0, half(d.points[qi] + Number(how))));
      d.changed = true;
      render(); return;
    }
    const rqt = t.closest("[data-rq-toggle]");
    if (rqt && rvs) {
      const open = openQuestions(rvs, draft(rvs)), qi = Number(rqt.dataset.rqToggle);
      if (open.has(qi)) open.delete(qi); else open.add(qi);
      render(); return;
    }
    if (t.closest("[data-rv-marks]")) { state.review.marks = !state.review.marks; render(); return; }
    const jump = t.closest("[data-rv-jump]");
    if (jump && rvs) {
      openQuestions(rvs, draft(rvs)).add(Number(jump.dataset.rvJump));
      render();
      $(`#rv-q${jump.dataset.rvJump}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }

    const act = t.closest("[data-act]");
    if (act) {
      const a = act.dataset.act, id = act.dataset.id;
      if (a === "close") closeDrawer();
      if (a === "grade-one") gradeOne(id);
      if (a === "grade-stop") stopLocalGrade();
      if (a === "open-folder") openFolder("folder");
      if (a === "key-save") saveOfficialKey(false);
      if (a === "key-remove") saveOfficialKey(true);
      if (a === "open-inbox") openFolder("inbox");
      if (a === "pull-full") startPullFlow({ full: true });
      if (a === "pull-pick-go") { state.pullPick = null; startPullFlow({ limit: state.pullLimit }); state.pullLimit = 0; }  // כמה למשוך נשמר בזרימה
      if (a === "pull-pick-close") { state.pullPick = null; render(); }
      if (a === "open-upload") openFolder("upload");
      if (a === "recheck") { if (LOCAL.on) location.reload(); else connect(true); }
      if (a === "copy-connect") {
        // הלוח של הדפדפן, ואם הוא מסרב (דפדפן מוטמע, דף לא מאובטח): הדרך הישנה, טקסט מסומן והעתקה
        (navigator.clipboard ? navigator.clipboard.writeText(CONNECT_COMMAND) : Promise.reject(new Error("no clipboard")))
          .catch(() => {
            const t = Object.assign(document.createElement("textarea"), { value: CONNECT_COMMAND });
            t.style.cssText = "position:fixed;opacity:0";
            document.body.append(t);
            t.select();
            const copied = document.execCommand("copy");
            t.remove();
            if (!copied) throw new Error("copy");
          })
          .then(() => toast("הפקודה הועתקה. מדביקים אותה ב-PowerShell ולוחצים Enter.", ICON.check))
          .catch(() => toast("לא הצלחתי להעתיק. מסמנים את השורה ומעתיקים ביד (Ctrl+C).", ICON.warn));
      }
      if (a === "send-confirm" && LOCAL.batch?.assignmentId === cur().id) startLocalSend(LOCAL.batch.id);
      if (a === "send-cancel") { LOCAL.batch = null; render(); }
      if (a === "grades-flow") startSendFlow("grades");
      if (a === "grades-confirm" && LOCAL.gradesAsk?.assignmentId === cur().id) startLocalGrades();
      if (a === "grades-cancel") { LOCAL.gradesAsk = null; render(); }
      if (a === "send-stop") stopLocalSend();
      if (a === "send-resume" && LOCAL.sending?.batch_id) startLocalSend(LOCAL.sending.batch_id);
      if (a === "ready-close" && LOCAL.rd) { LOCAL.rd.flow = false; render(); }
      if (a === "ready-install-ask" && LOCAL.rd) { LOCAL.rd.installAsk = true; render(); }
      if (a === "ready-install-no" && LOCAL.rd) { LOCAL.rd.installAsk = false; render(); }
      if (a === "ready-install-yes" && LOCAL.rd) startReadyInstall(LOCAL.rd);
      if (a === "ready-login-retry" && LOCAL.rd) startReadyLogin(LOCAL.rd, true);
      if (a === "ready-check" && LOCAL.rd) checkReady(LOCAL.rd);
      if (a === "save-name") saveName();
      if (a === "rename") { state.renaming = true; state.nameDraft = null; render(); $("#my-name")?.focus(); }
      if (a === "rename-cancel") { state.renaming = false; state.nameDraft = null; render(); }
      if (a === "claim") changeClaims({ take: [id] });
      if (a === "grade-more") { state.gradeShown += GRADE_PAGE * 2; render(); return; }
      if (a === "release") changeClaims({ release: [id] });
      if (a === "claim-next") changeClaims({ next: Math.max(1, state.teamCount || 1) });
      if (a === "release-mine") changeClaims({ release: info().toGrade.filter(isMine).map((s) => s.id) });
      if (a === "grade-pick-go") gradePicked();
      if (a === "grade-pick-close") { state.gradePick = null; render(); }
      if (a === "task-take" || a === "task-release") changeTask(id, act.dataset.stage, a === "task-take");
      return;
    }

    const goto = t.closest("[data-goto-tab]");
    if (goto) { const [st, tab] = goto.dataset.gotoTab.split(":"); state.tab[st] = tab; if (goto.getAttribute("href") === "#" + route()) render(); }

    const tab = t.closest("[data-tab]");
    if (tab) { const [st, k] = tab.dataset.tab.split(":"); state.tab[st] = k; render(); return; }

    const chip = t.closest("[data-filter]");
    if (chip) { state.filter = chip.dataset.filter; render(); return; }

    const reset = t.closest("[data-reset]");
    if (reset) {
      const st = reset.dataset.reset;
      state.instr[st] = DEFAULT_GRADE_INSTR;
      store.set(`instr.${st}`, state.instr[st]);
      render(); toast("ההנחיות חזרו לברירת המחדל"); return;
    }

    // שער השלמות: פרטים ותיקון
    if (t.closest("[data-integrity-toggle]")) { state.integrityOpen = !state.integrityOpen; render(); return; }
    if (t.closest("[data-integrity-fix]")) { runIntegrityFix(); return; }

    // סטטיסטיקה: מטלה שנבחרה בטבלה
    const so = t.closest("[data-stats-open]");
    if (so) { state.statsKey = so.dataset.statsOpen; location.hash = "#/stats"; return; }
    const sk = t.closest("[data-stats-key]");
    if (sk) { state.statsKey = sk.dataset.statsKey; render(); return; }

    const as = t.closest("[data-assign]");
    if (as) { state.assignmentId = as.dataset.assign; state.filter = "all"; resetOpen(); renderPickers(); render(); window.scrollTo({ top: 0, behavior: "smooth" }); return; }

    if (t.closest("[data-row-link]")) return;  // "ערוך ציון" בשורה: הקישור עצמו פותח את העמוד, בלי החלונית
    const row = t.closest("[data-open]");
    if (row) { openDrawer(row.dataset.open); return; }


    if (t.id === "scrim") closeDrawer();
    if (t.closest(".nav a")) $("#sidebar").classList.remove("open");
  });

  // לחיצה כפולה על ריבוע במסלול: מורידה את העבודה למחשב
  document.addEventListener("dblclick", (e) => {
    const dot = e.target.closest?.("[data-dl]");
    if (dot) { e.preventDefault(); downloadDot(dot); }
  });
  const reviewSub = () => (route() === "/review" && cur()?.subs.find((x) => x.id === state.review.id)) || null;

  // המשוב לסטודנט נשאר פתוח גם כשהמסך מצויר מחדש
  document.addEventListener("toggle", (e) => { if (e.target.matches?.(".rv-fb")) state.review.fbOpen = e.target.open; }, true);

  document.addEventListener("submit", (e) => {
    if (!e.target.matches("[data-rv-form]")) return;
    e.preventDefault();
    saveReview(e.target.dataset.rvForm);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && reviewSub()) { e.preventDefault(); saveReview(state.review.id); return; }
    if (e.key === "Enter" && e.target.matches?.("[data-grade-count]")) { gradePicked(); return; }
    if (e.key === "Enter" && e.target.matches?.("[data-pull-limit]")) { state.pullPick = null; startPullFlow({ limit: state.pullLimit }); state.pullLimit = 0; return; }
    if (e.key === "Escape" && state.pullPick) { state.pullPick = null; render(); return; }
    if (e.key === "Escape" && state.gradePick) { state.gradePick = null; render(); return; }
    if (e.key === "Escape") { closeDrawer(); $("#sidebar").classList.remove("open"); }
    if (e.key === "Enter" && e.target.matches("[data-open]")) openDrawer(e.target.dataset.open);
    if (e.key === "Enter" && e.target.matches("[data-assign]")) e.target.click();
    if (e.key === "Enter" && e.target.matches("[data-name-draft]")) saveName();
  });

  let savedTimer;
  function flashSaved(st) {
    const el = $(`#saved-${st}`);
    if (!el) return;
    el.classList.add("on");
    clearTimeout(savedTimer);
    savedTimer = setTimeout(() => el.classList.remove("on"), 1400);
  }

  document.addEventListener("input", (e) => {
    const t = e.target;
    // בבדיקה הידנית לא מציירים מחדש בכל הקשה: רק הציון הכולל מתעדכן
    const rvs = reviewSub();
    if (rvs && t.matches("[data-rv-reason]")) {
      const d = draft(rvs);
      d.reason = t.value;
      const btn = $("[data-rv-submit]");
      if (btn && !noRubric() && !overRubric(d.points).length) {
        btn.disabled = state.review.saving || !t.value.trim();
        btn.title = t.value.trim() ? "Ctrl+Enter" : "צריך לכתוב סיבה לשינוי";
      }
      return;
    }
    if (rvs && (t.dataset.rvPts != null || t.dataset.rvComment != null || t.matches("[data-rv-feedback]"))) {
      const d = draft(rvs);
      if (t.dataset.rvPts != null) {
        const q = rubric().questions[t.dataset.rvPts];
        if (t.value !== "") d.points[t.dataset.rvPts] = Math.min(q.pts, Math.max(0, half(Number(t.value) || 0)));
      } else if (t.dataset.rvComment != null) d.comments[t.dataset.rvComment] = t.value;
      else d.feedback = t.value;
      d.changed = true;
      const total = $("#rv-total");
      if (total) total.textContent = draftTotal(d);
      return;
    }
    if (t.dataset.query) { state.query[t.dataset.query] = t.value; render(); return; }
    if (t.dataset.moodleId) { state.moodleDraft[t.dataset.moodleId] = t.value; return; }
    if (t.matches("[data-key-text]")) { keyDraft(cur()).text = t.value; return; }
    if (t.dataset.keyPt != null) { keyDraft(cur()).points[t.dataset.keyPt] = t.value; return; }
    if (t.matches("[data-name-draft]")) { state.nameDraft = t.value; return; }
    if (t.matches("[data-grade-count]")) {
      state.gradeCount = Math.max(1, parseInt(t.value, 10) || 1);
      store.set("gradeCount", state.gradeCount);
      // רק התווית של הכפתור משתנה, בלי לצייר מחדש: הסמן נשאר בשדה
      const go = $("[data-act=grade-pick-go]");
      if (go) go.innerHTML = `${ICON.grade}בדוק ${Math.min(state.gradeCount, Number(t.max) || state.gradeCount)}`;
      return;
    }
    if (t.matches("[data-pull-limit]")) {
      state.pullLimit = Math.max(0, parseInt(t.value, 10) || 0);
      // רק התווית והסימון משתנים, בלי לצייר מחדש: הסמן נשאר בשדה
      const go = $("[data-pull-go]");
      if (go) go.textContent = pullGoLabel();
      document.querySelectorAll("[data-pull-chip]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.pullChip) === state.pullLimit)));
      return;
    }
    if (t.matches("[data-team-count]")) { state.teamCount = Math.max(1, parseInt(t.value, 10) || 1); store.set("teamCount", state.teamCount); return; }
    if (t.dataset.instr) {
      const st = t.dataset.instr;
      state.instr[st] = t.value;
      store.set(`instr.${st}`, t.value);
      flashSaved(st);
      updatePrompt(); return;
    }
    if (t.dataset.set && t.type !== "checkbox" && t.tagName !== "SELECT") setPath(t.dataset.set, t.type === "number" ? Number(t.value) : t.value);
  });

  document.addEventListener("change", (e) => {
    const t = e.target;
    if (t.dataset.set && (t.type === "checkbox" || t.tagName === "SELECT")) { setPath(t.dataset.set, t.type === "checkbox" ? t.checked : t.value); updatePrompt(); }
    if (t.dataset.rvPts != null && reviewSub()) render();
    if (t.matches("[data-key-file]")) { keyDraft(cur()).file = t.files[0] || null; render(); }
    if (t.dataset.keyPt != null) render();  // הודעת "חסר ניקוד" מתעדכנת כשיוצאים מהשדה
  });

  function persistSetting(key) { store.set(key, state[key]); }
  function setPath(path, value) {
    const [root, key] = path.split(".");
    state[root][key] = value;
    persistSetting(root);
  }
  function updatePrompt() { const el = $("#prompt-preview"); if (el) el.textContent = promptPreview(); }

  $("#course-select").addEventListener("change", (e) => {
    state.courseId = e.target.value;
    const list = D.assignments.filter((a) => a.courseId === state.courseId);
    state.assignmentId = (list.find((a) => a.phase === "current") || list[0])?.id;
    state.filter = "all";
    resetOpen();
    closeDrawer(); renderPickers(); render();
  });
  $("#assignment-select").addEventListener("change", (e) => { state.assignmentId = e.target.value; state.filter = "all"; resetOpen(); closeDrawer(); render(); });
  function resetOpen() {
    state.mistakeOpen = null;
    state.review.id = null;
    if (route() === "/review" && location.hash.includes("?")) history.replaceState(null, "", "#/review");
  }

  $("#menu-btn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));

  // ערכת צבעים
  const applyTheme = (t) => { if (t) document.documentElement.dataset.theme = t; };
  applyTheme(store.get("theme", null));
  $("#theme-btn").addEventListener("click", () => {
    const curTheme = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = curTheme === "dark" ? "light" : "dark";
    applyTheme(next);
    store.set("theme", next);
  });

  window.addEventListener("hashchange", () => { closeDrawer(); render(); window.scrollTo(0, 0); $("#main").focus({ preventScroll: true }); });

  // ---------- החיבור למערכת שבמחשב (dashboard/web_server.py) ----------
  function api(path, opts = {}) {
    return fetch(BASE + path, { cache: "no-store", ...opts, headers: { "Content-Type": "application/json", "X-Assignment-Checker": "1" } })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw Object.assign(new Error(data.error || `המערכת במחשב החזירה שגיאה ${r.status}`), { status: r.status });
        return data;
      }, () => { throw new Error("אין חיבור למערכת במחשב. אם המחשב נדלק עכשיו, מחכים דקה; אחרת מפעילים את start.bat."); });
  }

  // מה כרום אומר על הגישה של האתר הציבורי למערכת שבמחשב (Local Network Access): "granted", "prompt", "denied",
  // או null כשאין דרך לדעת (אתר מקומי, דפדפן אחר). השם של ההרשאה השתנה בין גרסאות כרום
  async function localAccess() {
    if (ON_LOCAL_HOST || !navigator.permissions) return null;
    for (const name of ["loopback-network", "local-network-access"]) {
      try { return (await navigator.permissions.query({ name })).state; } catch { /* שם שהגרסה הזו לא מכירה */ }
    }
    return null;
  }

  // השלב השני בדף "לא מחובר", לפי מה שכרום אומר על ההרשאה
  function accessStep() {
    if (LOCAL.access === "denied") {
      return `<b>כרום חוסם לאתר את הגישה למערכת שבמחשב.</b> לוחצים על הסמל שליד הכתובת למעלה, נכנסים ל"הגדרות האתר",
        ובשורה "אפליקציות ושירותים במכשיר" (או "גישה לרשת המקומית") בוחרים "אפשר". חוזרים לכאן, והאתר מתחבר לבד.`;
    }
    if (LOCAL.access === "granted") {
      return `כרום כבר מאשר לאתר לגשת למערכת שבמחשב, אז <b>המערכת פשוט לא רצה עכשיו</b>: אולי המחשב רק נדלק, או שהיא באמצע
        עדכון אוטומטי (עד 3 דקות). האתר מתחבר לבד ברגע שהיא עולה. אם זה נמשך, מריצים את הפקודה שלמטה.`;
    }
    return `כרום ישאל אם לאפשר לאתר לגשת לאפליקציות ולשירותים במכשיר: לוחצים <b>"אפשר"</b>. זה קורה פעם אחת בכל מחשב.
      אם החלון לא הופיע, לוחצים "התחבר".`;
  }

  // המערכת עונה ב-api/health. באתר הציבורי כרום שואל פעם אחת אם לאפשר גישה למכשיר, ועד התשובה הבקשה מחכה
  async function detectLocal(timeoutMs) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const r = await fetch(BASE + "api/health", { cache: "no-store", signal: ctrl.signal });
      if (!r.ok) return false;
      LOCAL.health = await r.json();
      return LOCAL.health?.ok === true;
    } catch {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  // בלי מחוון יש רק את שמות השאלות. ניקוד 0 לכל אחת: לא מחלקים את הציון בעצמנו, ואין ציונים
  const noRubricQ = (labels, why) => ({ questions: labels.map((l, i) => ({ n: i + 1, pts: 0, req: l })), missing: why || `למטלה אין מחוון. ${RUBRIC_RULE}` });

  // המערכת בודקת ברקע אם Claude Code מחובר (זה לוקח כמה שניות). שואלים שוב עד שיש תשובה, ומעדכנים את המסך
  let healthTimer = null;
  function followHealth() {
    if (healthTimer) return;
    healthTimer = setTimeout(async () => {
      healthTimer = null;
      const h = await api("api/health").catch(() => null);
      if (!h) return;
      LOCAL.health = { ...LOCAL.health, ...h };
      renderStatus();
      render();
      if (h.checking) followHealth();
    }, 2500);
  }

  // given: מצב שכבר הגיע (הכפתור "סנכרון" מקבל אותו מ-api/refresh), במקום לבקש את api/state
  async function loadLocal(given = null) {
    try {
      const [data, health] = given ? [given, null] : await Promise.all([api("api/state"), api("api/health").catch(() => null)]);
      // מסד הנתונים הסטטיסטי (api/stats): נטען עם המצב, גם אחרי "סנכרון"
      const [statsData, integrityData] = await Promise.all([api("api/stats").catch(() => null), api("api/integrity").catch(() => null)]);
      D.stats = Array.isArray(statsData) ? statsData : [];
      D.integrity = Array.isArray(integrityData) ? integrityData : [];  // שער השלמות (datastore doctor): בעיות לכל מטלה
      LOCAL.sig = JSON.stringify(data);
      D.courses.splice(0, D.courses.length, ...data.courses);
      D.assignments.splice(0, D.assignments.length, ...data.assignments.map((a) => ({
        ...a, phase: a.subs.length ? "current" : "new", gradedAt: a.gradedAt || null, returnedAt: a.returnedAt || null, lastFresh: null,
        rubricQ: a.rubric?.length ? { questions: a.rubric.map((q, i) => ({ n: i + 1, pts: q.points, req: q.label, criteria: q.criteria || "", deductions: q.deductions || [] })), missing: a.noRubric || "" } : null,
      })));
      Object.keys(D.rubrics).forEach((k) => delete D.rubrics[k]);
      data.courses.forEach((c) => {
        const labels = data.assignments.find((a) => a.courseId === c.id && a.questionLabels?.length)?.questionLabels;
        D.rubrics[c.id] = noRubricQ(labels || ["שאלה 1"]);
      });
      D.runs.splice(0, D.runs.length, ...data.assignments
        .flatMap((a) => (a.log || []).map((l) => ({ ...l, where: `${a.course}, ${a.title}` })))
        .sort((x, y) => (y.at || "").localeCompare(x.at || "")));
      // מודל מחובר = Claude Code מחובר במחשב (דרכו Claude in Chrome עובד במודל)
      LOCAL.health = { ...LOCAL.health, ...(health || {}), root: data.root, claude: data.claude, claudeVia: data.claudeVia };
      LOCAL.me = data.me || null;
      D.usage = data.usage || null;
      if (health?.checking) followHealth();
      if (!LOCAL.polling) LOCAL.sending = data.sending || null;
      // בדיקה שרצה כשהדף נטען: מציגים את ההתקדמות ואת כפתור העצירה
      const g = data.grading;
      const gA = g?.running && D.assignments.find((a) => a.courseFolder === g.course && a.folder === g.assignment);
      if (gA && !LOCAL.gradeFollow && !state.run[gA.id]) {
        const run = (state.run[gA.id] = { stage: "grade", steps: STAGES.grade.steps.map((_, i) => (i === 0 ? "done" : i === 1 ? "running" : "pending")) });
        setTimeout(() => followGrade(gA, run), 0);
      }
      if (!D.assignments.some((a) => a.id === state.assignmentId)) {
        const first = D.assignments.find((a) => a.subs.length) || D.assignments[0];
        state.assignmentId = first?.id;
      }
      state.courseId = D.assignments.find((a) => a.id === state.assignmentId)?.courseId || D.courses[0]?.id;
    } catch (e) {
      toast(`הטעינה מתיקיית OneDrive נכשלה: ${e.message}`, ICON.warn);
    }
    renderPickers();
    render();
    if (LOCAL.sending?.running && !LOCAL.polling) followSend();  // העלאה שרצה כשהדף נטען: ממשיכים לעקוב אחריה
    if (!Object.values(state.run).some((r) => r.stage === "pull")) resumePull();
  }

  // מה שנמשך, נבדק או הועלה במחשב אחר (ההגשות מגיעות דרך OneDrive) מופיע לבד, בלי רענון: כל 20 שניות וכשחוזרים
  // ללשונית. רק כשהלשונית גלויה, שום דבר לא רץ כאן ולא מקלידים, ומציירים מחדש רק אם משהו בתיקייה השתנה
  // "משוך הגשות" אמיתי: השרת מושך ממודל (אם יש טוקן) ומקובצי ZIP בקליטה, ישר לתיקיית OneDrive
  // full: את כל ההגשות ממודל. בלי: אחרי משיכה ראשונה, רק מי שההגשה שלו השתנתה מאז המשיכה הקודמת. limit: כמה למשוך (0 = הכול).
  // הכפתורים קוראים ל-startPullFlow, שבודק קודם שהמחשב מחובר ל-Claude
  async function runLocalPull(full = false, limit = 0) {
    const A = cur();
    if (!A || state.run[A.id] || !LOCAL.health?.root) return;
    // הגשה שעוד לא נמשכה: המשיכה הראשונה שומרת את מזהה המטלה במודל (dashboard/actions.py new_assignment)
    const moodleId = A.empty ? parseMoodleId(state.moodleDraft[A.id]) : null;
    if (A.empty && !moodleId) {
      toast("קודם מדביקים את הקישור למטלה במודל (או את המספר שאחרי id=), ואז מושכים.", ICON.warn);
      if (route() !== "/pull") location.hash = "#/pull";  // השדה נמצא בעמוד המשיכה
      setTimeout(() => $("#moodle-id")?.focus(), 50);
      return;
    }
    const run = (state.run[A.id] = { stage: "pull", startedAt: Date.now() });
    showPull(run, { phase: "find" });
    render();
    // השרת עונה רק בסוף המשיכה (הורדה של ZIP גדול: כמה דקות). בינתיים שואלים אותו כל שנייה כמה התקדמה
    let settled = false;
    const post = api("api/pull", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder, ...(moodleId && { moodleId }), ...(full && { full: true }), ...(!full && limit > 0 && { limit }) }) })
      .finally(() => { settled = true; });
    followPull(A, run, () => settled);
    try {
      const rep = await post;
      LOCAL.report = { ...rep, assignmentId: A.id };
      delete state.run[A.id];
      await loadLocal();
      // ה-ZIP היה של מטלה אחרת: עוברים אליה, כדי לראות את מה שנקלט
      const other = !rep.result.total && rep.routed?.find((x) => x.total);
      const target = other && D.assignments.find((a) => a.courseFolder === other.course && a.folder === other.assignment);
      if (target) {
        state.assignmentId = target.id;
        state.courseId = target.courseId;
        LOCAL.report.assignmentId = target.id;
        renderPickers();
        render();
        toast(`ה-ZIP שייך ל${target.title}, אז עברתי אליה: ${plural(other.total, "הגשה אחת נקלטה", "הגשות נקלטו")}`);
      } else {
        toast(rep.result.total ? `המשיכה הסתיימה: ${rep.summary}` : "המשיכה הסתיימה: לא נמצאו הגשות חדשות");
      }
    } catch (e) {
      delete state.run[A.id];
      // גם כשההורדה נכשלה, מזהה המודל כבר נשמר בתיקייה: טוענים מחדש כדי שהשדה יתחלף בקישור למודל
      if (moodleId) await loadLocal(); else render();
      toast(e.message, ICON.warn);
    }
  }

  async function followPull(A, run, over) {
    while (!over()) {
      await new Promise((r) => setTimeout(r, 1000));
      const p = await api("api/pull").catch(() => null);
      if (over() || state.run[A.id] !== run) return;
      if (p?.running && p.course === A.courseFolder && p.assignment === A.folder) showPull(run, p);
      render();
    }
  }

  // משיכה שרצה כשהדף נטען (רענון, או לשונית אחרת): מראים את המד עד שהיא נגמרת
  async function resumePull() {
    let p = await api("api/pull").catch(() => null);
    const A = p?.running && D.assignments.find((a) => a.courseFolder === p.course && a.folder === p.assignment);
    if (!A || state.run[A.id]) return;
    const run = (state.run[A.id] = { stage: "pull", startedAt: Date.parse(p.started_at) || Date.now() });
    while (p.running) {
      showPull(run, p);
      render();
      await new Promise((r) => setTimeout(r, 1000));
      p = (await api("api/pull").catch(() => null)) || { running: false, error: "החיבור למערכת נפל באמצע המשיכה." };
    }
    delete state.run[A.id];
    await loadLocal();
    toast(p.error || `המשיכה הסתיימה: ${p.summary}`, p.error ? ICON.warn : ICON.check);
  }

  // "בדוק" אמיתי: השרת שולח את ההגשות הממוספרות ל-Claude ברקע, והאתר שואל מה המצב עד שזה נגמר
  async function runLocalGrade(ids) {
    const A = cur();
    if (!A || state.run[A.id] || !ids.length) return;
    if (!LOCAL.health?.claude) { toast(NO_KEY, ICON.warn); return; }
    if (noRubric()) { toast(noRubric(), ICON.warn); return; }
    const run = (state.run[A.id] = { stage: "grade", steps: STAGES.grade.steps.map(() => "pending") });
    run.steps[0] = "running";
    A.subs.filter((s) => ids.includes(s.id)).forEach((s) => { s.status = "grading"; });
    render(); refreshDrawer();
    try {
      const c = state.claude;
      await api("api/grade", { method: "POST", body: JSON.stringify({
        course: A.courseFolder, assignment: A.folder, ids,
        model: c.model, parallel: c.parallel, sendSolution: c.sendSolution, instructions: state.instr.grade,
      }) });
      run.steps[0] = "done"; run.steps[1] = "running";
      await followGrade(A, run);
    } catch (e) {
      delete state.run[A.id];
      await loadLocal();
      refreshDrawer();
      toast(e.message, ICON.warn);
    }
  }

  // שואל את השרת על הבדיקה שרצה עד שהיא נגמרת. גם בדיקה שהתחילה לפני שהדף נטען (ואז אפשר לעצור אותה מכאן)
  async function followGrade(A, run) {
    if (LOCAL.gradeFollow) return;
    LOCAL.gradeFollow = true;
    let job;
    try {
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        job = await api("api/grade");
        const done = Object.keys(job.done || {}).length;
        run.stopping = !!job.stopping;
        run.progress = job.stopping ? `עוצר… (נבדקו ${done})` : `נבדקו ${done} מתוך ${job.total}…`;
        if (done) { run.steps[1] = "done"; run.steps[2] = "running"; }
        render();
        if (!job.running) break;
      }
    } finally {
      LOCAL.gradeFollow = false;
      delete state.run[A.id];
    }
    await loadLocal();
    refreshDrawer();
    const failed = Object.keys(job.report?.failed || {}).length, stopped = (job.report?.stopped || []).length;
    toast(job.error || `${stopped ? "הבדיקה נעצרה" : "הבדיקה הסתיימה"}: ${job.summary}`, job.error || failed || stopped ? ICON.warn : ICON.check);
  }

  async function stopLocalGrade() {
    const A = cur(), run = A && state.run[A.id];
    if (!run || run.stage !== "grade" || run.stopping) return;
    run.stopping = true;
    run.progress = "עוצר…";
    render();
    try {
      await api("api/grade/stop", { method: "POST", body: "{}" });
      toast("הבדיקה נעצרת: העבודות שכבר נשלחו ל-Claude יסתיימו ויישמרו");
    } catch (e) {
      run.stopping = false;
      render();
      toast(e.message, ICON.warn);
    }
  }

  // ---------- חלוקה בצוות: לקיחה, החזרה, ומה שאחרים סימנו ----------
  async function saveName() {
    const name = (state.nameDraft ?? "").trim();
    if (!name) { toast("צריך לכתוב שם", ICON.warn); $("#my-name")?.focus(); return; }
    try {
      LOCAL.me = await api("api/me", { method: "POST", body: JSON.stringify({ name }) });
      state.renaming = false;
      state.nameDraft = null;
      await loadLocal();
      toast(`נשמר: ${LOCAL.me.name}. מעכשיו אפשר לקחת עבודות.`);
    } catch (e) {
      toast(e.message, ICON.warn);
    }
  }

  // מעדכן את s.claim לפי מה שהשרת קרא מהתיקייה, בלי לחכות לטעינה הבאה
  function applyClaims(A, view) {
    A.subs.forEach((s) => { s.claim = view.claims?.[s.id] || null; });
  }

  async function changeClaims(body) {
    const A = cur();
    if (!A || !LOCAL.on) return;
    try {
      const rep = await api("api/claims", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder, ...body }) });
      applyClaims(A, rep);
      render();
      const others = Object.keys(rep.others || {}).length;
      const done = rep.released?.length ? `${plural(rep.released.length, "עבודה אחת חזרה", "עבודות חזרו")} לפנויות`
        : rep.taken?.length ? `${plural(rep.taken.length, "עבודה אחת סומנה", "עבודות סומנו")} עליך` : "לא נמצאו עבודות פנויות";
      toast(others ? `${done}. ${plural(others, "עבודה אחת כבר נלקחה", "עבודות כבר נלקחו")} על ידי מישהו אחר.` : done,
        others || !(rep.taken?.length || rep.released?.length) ? ICON.warn : ICON.check);
    } catch (e) {
      toast(e.message, ICON.warn);
    }
  }

  // לוקח (או משחרר) את המשיכה או את ההחזרה של מטלה. stage: "pull" או "ret"
  async function changeTask(assignmentId, stage, take) {
    const A = D.assignments.find((a) => a.id === assignmentId);
    if (!A || !LOCAL.on || !TASK_STAGE[stage]) return;
    try {
      const rep = await api("api/tasks", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder, stage: TASK_STAGE[stage], take }) });
      A.owners = { ...A.owners, [TASK_STAGE[stage]]: rep.owner };
      render();
      toast(take ? `${STAGES[stage].name} של ${A.title} אצלך עכשיו` : `${STAGES[stage].name} של ${A.title} שוחררה`);
    } catch (e) {
      toast(e.message, ICON.warn);
    }
  }

  // מה שקורה בתיקיית OneDrive (בודקים אחרים לוקחים עבודות, ציונים מגיעים, מישהו משך או העלה) מופיע לבד:
  // כל כמה שניות שואלים את המערכת על חתימת התיקייה, וכשהיא משתנה טוענים מחדש. רק כשהדף גלוי
  let changesBusy = false, lastSig = null;
  // בזמן הקלדה או בחירה לא מציירים מחדש (רשימה פתוחה הייתה נסגרת). אבל הפוקוס נשאר על השדה גם אחרי שסיימו (למשל
  // אחרי שבחרו מטלה ברשימה למעלה), ואז האתר הפסיק להתעדכן עד שלחצו במקום אחר. לכן חוסמים רק בשניות שאחרי שנגעו בשדה
  let fieldTouched = 0;
  ["pointerdown", "keydown", "input"].forEach((t) => document.addEventListener(t, (e) => {
    if (e.target.matches?.("input, textarea, select")) fieldTouched = Date.now();
  }, true));
  const FIELD_IDLE_MS = 15000;
  const editing = () => !!document.activeElement?.matches?.("input, textarea, select") && Date.now() - fieldTouched < FIELD_IDLE_MS;
  async function pollChanges() {
    if (changesBusy || LOCAL.syncing || !LOCAL.on || !LOCAL.health?.root || document.hidden) return;
    // לא באמצע ריצה ולא בזמן הקלדה: הסיבוב שאחרי יטען
    if (LOCAL.polling || Object.keys(state.run).length || editing()) return;
    changesBusy = true;
    try {
      const { sig, version } = await api("api/changes");
      // המערכת התעדכנה לבד מ-GitHub (dashboard/updater.py) ועלתה מחדש: טוענים את הדף, כדי שגם האתר יהיה החדש.
      // רק כאן, כשלא רץ כלום ולא מקלידים (התנאים שלמעלה)
      if (version && LOCAL.version && version !== LOCAL.version) {
        toast("המערכת התעדכנה לגרסה חדשה. טוען מחדש…", ICON.check);
        setTimeout(() => location.reload(), 1500);
        return;
      }
      if (version) LOCAL.version = version;
      if (lastSig !== null && sig !== lastSig) { await loadLocal(); refreshDrawer(); }
      lastSig = sig;
    } catch {
      // המערכת לא ענתה הפעם. מנסים שוב בסיבוב הבא
    } finally {
      changesBusy = false;
    }
  }
  const CHANGES_POLL_MS = 5000;

  // ---------- "סנכרון": קוראים מחדש את כל תיקיית OneDrive ומראים מה השתנה ----------
  // השרת (POST api/refresh) קורא הכול מהדיסק ובודק ש-OneDrive עצמו עובד במחשב: רץ, מחובר לאוניברסיטה, ואין קבצים
  // מכאן שעוד לא עלו. מה שהמסך מציג לכל מטלה נספר לפני ואחרי, כדי לומר בדיוק מה התעדכן
  function stageCounts() {
    const out = {};
    D.assignments.filter((a) => !a.empty).forEach((a) => {
      const I = info(a);
      out[`${a.courseFolder}/${a.folder}`] = { a, pulled: I.subs.length, graded: I.graded.length, returned: I.returned.length };
    });
    return out;
  }

  function syncChanges(before, after) {
    const what = [["pulled", "נמשכו"], ["graded", "נבדקו"], ["returned", "הוחזרו"]];
    return Object.entries(after).flatMap(([k, n]) => {
      const o = before[k] || { pulled: 0, graded: 0, returned: 0 };
      const parts = what.filter(([f]) => n[f] !== o[f]).map(([f, w]) => `${w} ${n[f]} (קודם ${o[f]})`);
      return parts.length ? [`${n.a.title}, ${n.a.course}: ${parts.join(", ")}`] : [];
    });
  }

  function oneDriveNotes(od) {
    if (!od) return [];
    const out = [];
    if (od.synced === false) out.push({ warn: true, text: "התיקייה במחשב הזה היא עותק מקומי ולא תיקייה של OneDrive: מה שאחרים בצוות עושים לא מגיע אליה לבד." });
    if (od.signin) out.push({ warn: true, text: "OneDrive לא מצליח להתחבר לאוניברסיטה (צריך אימות דו-שלבי), ולכן לא מביא את מה שהשתנה בענן. מפעילים את הקיצור \"חיבור OneDrive BGU\" בשולחן העבודה, מתחברים ומאשרים בטלפון, ולוחצים שוב על סנכרון." });
    if (od.started) out.push({ warn: true, text: "OneDrive לא רץ במחשב, אז הפעלתי אותו. עד שיביא את מה שהשתנה בענן יכולות לעבור כמה דקות: כדאי ללחוץ שוב על סנכרון בעוד דקה." });
    else if (od.running === false) out.push({ warn: true, text: "OneDrive לא רץ במחשב ולא הצלחתי להפעיל אותו. מפעילים אותו מתפריט התחל ולוחצים שוב על סנכרון." });
    if (od.pending) out.push({ warn: true, text: `${plural(od.pending, "קובץ אחד מהמחשב הזה עוד לא עלה", "קבצים מהמחשב הזה עוד לא עלו")} ל-OneDrive (למשל ${od.pendingFiles?.[0] || ""}). שאר הצוות יראה אותם כשיעלו, בדרך כלל תוך דקה.` });
    if (!out.length && od.synced) out.push({ warn: false, text: "האפליקציה של OneDrive רצה ומחוברת, וכל הקבצים של המחשב הזה כבר בענן." });
    return out;
  }

  let syncPopTimer = null;
  function showSyncPop(title, lines, notes, warn) {
    const pop = $("#sync-pop");
    pop.className = `sync-pop${warn ? " warn" : ""}`;
    pop.innerHTML = `<button class="btn ghost small sync-x" aria-label="סגור">✕</button>
      <h3>${warn ? ICON.warn : ICON.check}<span>${esc(title)}</span></h3>
      ${lines.length ? `<ul>${lines.slice(0, 8).map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}
      ${lines.length > 8 ? `<p class="sync-more">ועוד ${lines.length - 8}</p>` : ""}
      ${notes.map((n) => `<p class="sync-od${n.warn ? " warn" : ""}">${esc(n.text)}</p>`).join("")}`;
    pop.hidden = false;
    $(".sync-x", pop).addEventListener("click", () => { pop.hidden = true; });
    clearTimeout(syncPopTimer);
    if (!warn) syncPopTimer = setTimeout(() => { pop.hidden = true; }, 15000);
  }

  // הכפתור מופיע אצל כולם באתר הציבורי, גם בלי מערכת במחשב (לפני 2026-11-03 הוא הוסתר שם, ולכן רק מי שהמערכת רצה
  // אצלו ראה אותו). בלי מערכת הוא מביא מיד את לוח המספרים שהמחשב המפרסם קרא מתיקיית OneDrive (syncPublic)
  const publicSync = () => !ON_LOCAL_HOST && !!PUBLIC_STATUS_URL;

  function renderSyncBtn() {
    const b = $("#sync-btn");
    b.hidden = !LOCAL.on && !publicSync();
    b.disabled = LOCAL.syncing;
    b.classList.toggle("busy", LOCAL.syncing);
    $("span", b).textContent = LOCAL.syncing ? "מסנכרן…" : "סנכרון";
    b.title = (LOCAL.syncedAt ? `סונכרן לאחרונה ב-${LOCAL.syncedAt.slice(11, 16)}. ` : "")
      + (LOCAL.on ? "קורא מחדש את תיקיית OneDrive ומעדכן את כל המספרים במסך" : "מביא את המספרים האחרונים שנקראו מתיקיית OneDrive");
  }

  // המספרים של הלוח הציבורי, באותה צורה כמו stageCounts, כדי ש-syncChanges יאמר מה השתנה
  function publicCounts(d) {
    const out = {};
    (d?.courses || []).forEach((c) => (c.assignments || []).filter((a) => !a.empty).forEach((a) => {
      out[`${c.name}/${a.title}`] = { a: { title: a.title, course: c.name }, pulled: a.pulled, graded: a.graded, returned: a.returned };
    }));
    return out;
  }

  const localNow = () => { const t = new Date(); return new Date(t - t.getTimezoneOffset() * 60000).toISOString().slice(0, 19); };

  // אין מערכת במחשב הזה: אין ממה לקרוא את OneDrive כאן, אז מביאים את מה שהמחשב המפרסם קרא ממנו. הוא בודק את התיקייה
  // כל 2 דקות ומפרסם כל שינוי (PUBLISH_CHECK_S ב-dashboard/public_status.py)
  async function syncPublic() {
    LOCAL.syncing = true;
    renderSyncBtn();
    const had = !!PUB.data, before = publicCounts(PUB.data);
    try {
      const d = await fetchPublic(true);
      PUB.data = d;
      PUB.error = "";
      PUB.loading = false;
      LOCAL.syncedAt = localNow();
      if (!LOCAL.on && !cur()) render();
      const lines = had ? syncChanges(before, publicCounts(d)) : [];
      const stale = (Date.now() - Date.parse(d.publishedAt)) / 3600000 > PUBLIC_STALE_H;
      const from = d.publishedBy ? `המחשב של ${d.publishedBy}` : "המחשב שמפרסם את המספרים";
      const notes = [
        stale ? { warn: true, text: `${from} לא פרסם מספרים מאז ${when(d.publishedAt)}. הוא כנראה כבוי, אז ייתכן שהמספרים ישנים.` }
          : { warn: false, text: `המספרים כאן מגיעים מ${from}: הוא בודק את תיקיית OneDrive כל 2 דקות ומפרסם כל שינוי. הפרסום האחרון: ${when(d.publishedAt)}.` },
        { warn: false, text: "כדי לסנכרן ישירות מ-OneDrive במחשב שלך, ולמשוך, לבדוק ולהחזיר ממנו, מחברים אותו פעם אחת (ההוראות בדף, מתחת ללוח)." },
      ];
      const title = lines.length ? `${plural(lines.length, "מטלה אחת התעדכנה", "מטלות התעדכנו")} מתיקיית OneDrive`
        : "הכול מעודכן: אלה המספרים האחרונים מתיקיית OneDrive";
      showSyncPop(title, lines, notes, stale);
    } catch (e) {
      showSyncPop("הסנכרון לא הצליח", [], [{ warn: true, text: `לא הצלחתי להביא את המספרים (${e.message}). בודקים את החיבור לאינטרנט ולוחצים שוב.` }], true);
    } finally {
      LOCAL.syncing = false;
      renderSyncBtn();
    }
  }

  // מערכת מלפני הכפתור (2026-11-03) עונה 404 על api/refresh. היא גם מלפני העדכון העצמי, אז היא לא תתעדכן בלי לעלות מחדש
  const OLD_SYSTEM = "המערכת שרצה במחשב הזה ישנה: היא מלפני כפתור הסנכרון, והיא לא מתעדכנת לבד. היא מתעדכנת מ-GitHub כשהיא עולה, "
    + "אז מפעילים מחדש את המחשב (או סוגרים את start.bat ומפעילים אותו שוב). מאז היא מתעדכנת לבד, והכפתור יעבוד.";

  async function syncNow() {
    if (LOCAL.syncing) return;
    if (!LOCAL.on) { if (publicSync()) await syncPublic(); return; }
    LOCAL.syncing = true;
    renderSyncBtn();
    const hadRoot = !!LOCAL.health?.root, before = stageCounts();
    try {
      const rep = await api("api/refresh", { method: "POST", body: "{}" });
      await loadLocal(rep.state);
      lastSig = rep.sig;
      LOCAL.syncedAt = rep.at;
      refreshDrawer();
      renderStatus();
      const lines = hadRoot ? syncChanges(before, stageCounts()) : [];
      const notes = oneDriveNotes(rep.onedrive);
      const title = !hadRoot ? "המערכת מחוברת לתיקיית OneDrive"
        : lines.length ? `${plural(lines.length, "מטלה אחת התעדכנה", "מטלות התעדכנו")} מתיקיית OneDrive`
        : "הכול מעודכן: המספרים במסך זהים לתיקיית OneDrive";
      showSyncPop(title, lines, notes, notes.some((n) => n.warn));
    } catch (e) {
      const old = e.status === 404;
      showSyncPop(old ? "המערכת במחשב הזה ישנה" : "הסנכרון לא הצליח", [], [{ warn: true, text: old ? OLD_SYSTEM : e.message }], true);
    } finally {
      LOCAL.syncing = false;
      renderSyncBtn();
    }
  }
  $("#sync-btn").addEventListener("click", syncNow);
  document.addEventListener("click", (e) => {
    const pop = $("#sync-pop");
    if (!pop.hidden && !e.target.closest?.("#sync-pop, #sync-btn")) pop.hidden = true;
  });

  function openFolder(which) {
    const A = cur();
    if (!LOCAL.on || !A) return;
    api("api/open", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder, which }) })
      .then(() => toast(which === "inbox" ? "תיקיית ההורדות נפתחה בסייר הקבצים" : which === "upload" ? "תיקיית ההעלאה נפתחה בסייר הקבצים" : "תיקיית המטלה נפתחה בסייר הקבצים", ICON.folder))
      .catch((e) => toast(e.message, ICON.warn));
  }

  function renderStatus() {
    const live = LOCAL.on && !!LOCAL.health?.root;
    const badge = $("#mode-badge");
    badge.textContent = live ? "מחובר ל-OneDrive" : LOCAL.on ? "OneDrive לא נמצא" : LOCAL.probing ? "מתחבר…" : "המערכת לא מחוברת";
    badge.className = `demo-badge ${live ? "ok" : ""}`;
    badge.title = live ? LOCAL.health.root : "הנתונים מגיעים מהמערכת שרצה במחשב (start.bat)";
    const set = (id, ok, text) => {
      const el = $(id);
      el.classList.toggle("ok", ok);
      $(".dot", el).className = `dot ${ok ? "ok" : "warn"}`;
      $("em", el).textContent = text;
    };
    set("#conn-moodle", !!LOCAL.health?.moodle, LOCAL.health?.moodle ? "דרך Claude בכרום" : LOCAL.on ? "צריך להתחבר" : "לא מחובר");
    set("#conn-claude", !!LOCAL.health?.claude, LOCAL.health?.claude ? "מחובר" : LOCAL.on ? "עוד לא מחובר" : "לא מחובר");
    set("#conn-drive", live, live ? "מחובר" : "לא מחובר");
    renderSyncBtn();
    $("#proto-note").textContent = live
      ? (LOCAL.health?.claude ? "כל המספרים במסך נקראים מתיקיית OneDrive של הקורס." : "כל המספרים במסך נקראים מתיקיית OneDrive של הקורס. הבדיקה עם Claude עוד לא מחוברת (מחברים את Claude Code במחשב, או ANTHROPIC_API_KEY ב-.env).")
      : "האתר מציג רק נתונים אמיתיים, מהמערכת שרצה במחשב (start.bat). כרגע היא לא מחוברת.";
  }

  // מתחברים למערכת. באתר הציבורי מנסים שוב כל כמה שניות, עד שמפעילים את start.bat
  async function connect(manual = false) {
    if (LOCAL.probing || LOCAL.on) return;
    LOCAL.probing = true;
    LOCAL.access = await localAccess();
    renderStatus();
    if (manual || !booted) render();  // "מחכה לאישור בכרום" בזמן שכרום שואל
    const ok = await detectLocal(ON_LOCAL_HOST ? 20000 : 60000);  // במחשב עצמו המערכת עונה, גם אם לאט: מחכים, לא "לא מחובר"
    LOCAL.probing = false;
    LOCAL.access = await localAccess();
    if (ok) {
      LOCAL.on = true;
      if (LOCAL.health.root) await loadLocal();
      if (!ON_LOCAL_HOST) toast("האתר מחובר למערכת שבמחשב");
    }
    // ניסיון שנכשל ברקע לא מצייר את המסך מחדש
    if (ok || manual || !booted) { renderPickers(); render(); } else renderStatus();
  }

  let booted = false;
  (async () => {
    state.loading = ON_LOCAL_HOST;  // באתר הציבורי מראים מיד איך מתחברים, בלי לחכות
    render();
    if (!ON_LOCAL_HOST) {  // לוח המספרים הציבורי, למי שאין במחשב שלו מערכת. נטען במקביל לניסיון החיבור
      loadPublic();
      setInterval(loadPublic, 60000);
    }
    await connect();
    state.loading = false;
    booted = true;
    renderPickers();
    render();
    if (!ON_LOCAL_HOST) setInterval(() => { if (!LOCAL.on) connect(); }, 5000);
    setInterval(pollChanges, CHANGES_POLL_MS);
    document.addEventListener("visibilitychange", pollChanges);
  })();
})();
