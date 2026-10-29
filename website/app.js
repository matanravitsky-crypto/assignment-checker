(() => {
  // כל מה שהאתר מציג אמיתי: הנתונים מגיעים מהמערכת שרצה במחשב (start.bat, dashboard/web_server.py),
  // שקוראת את תיקיית OneDrive של הקורס. בלי המערכת אין מספרים במסך
  const D = { courses: [], assignments: [], rubrics: {}, runs: [], whoWorking: [], sysAlerts: [], usage: null };
  // באתר הציבורי (Vercel) פונים למערכת שבמחשב. כשהאתר נפתח מהמערכת עצמה, לאותה כתובת
  const ON_LOCAL_HOST = ["localhost", "127.0.0.1"].includes(location.hostname);
  const BASE = ON_LOCAL_HOST ? "" : "http://127.0.0.1:8765/";
  // אותו אתר, ישירות מהמערכת: עובד בלי הרשאת "גישה למכשיר" של כרום
  const LOCAL_SITE = "http://localhost:8765/";
  const REPO_URL = "https://github.com/matanravitsky-crypto/assignment-checker";
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
  };
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem("ac:" + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("ac:" + k, JSON.stringify(v)); } catch {} },
  };

  // כרום חוסם לאתר הציבורי גישה למחשב (הרשאת "גישה למכשיר", loopback-network), אבל מעבר לכתובת המקומית מותר תמיד.
  // מי שפתח פעם את המערכת מכאן ("פתח את המערכת") מועבר אליה לבד בכל כניסה. ?stay משאיר באתר הציבורי ומבטל את המעבר
  if (!ON_LOCAL_HOST) {
    if (new URLSearchParams(location.search).has("stay")) store.set("openLocal", false);
    else if (store.get("openLocal", false)) { location.replace(LOCAL_SITE + location.hash); return; }
  }

  // ---------- State ----------
  const state = {
    courseId: null,
    assignmentId: null,
    tab: { pull: "list", grade: "list", ret: "list" },
    filter: "all",
    query: { pull: "", grade: "", ret: "" },
    moodleDraft: {},  // assignmentId -> מה שהוקלד בשדה "מזהה המטלה במודל" של הגשה שעוד לא נמשכה
    run: {},          // assignmentId -> { stage, steps[] }
    seenDone: {},     // assignmentId:stage -> true, כדי להנפיש את ה-V רק ברגע ההשלמה
    openId: null,
    instr: { grade: store.get("instr.grade", DEFAULT_GRADE_INSTR) },  // נשלחות ל-Claude עם כל בדיקה
    claude: store.get("claude", { model: "claude-opus-5-5", parallel: 5, sendSolution: true }),
    loading: false,
    teamCount: store.get("teamCount", 20),  // כמה עבודות פנויות לוקחים בלחיצה אחת
    gradePick: null,  // assignmentId שהחלונית "כמה לבדוק" של כפתור הבדיקה פתוחה בו
    gradeCount: store.get("gradeCount", 100),  // כמה עבודות בודקים בלחיצה אחת
    nameDraft: null,  // מה שהוקלד בשדה "השם שלך"
    renaming: false,
    // לוח הבקרה: טעות נפוצה שנפתחה
    mistakeOpen: null,
    // הבדיקה הידנית: העבודה שפתוחה, סינון לפי סוג הבעיה, מה מוצג (מסומנת/מקורית) והטיוטה של כל עבודה עד השמירה
    review: { id: null, edits: {}, saving: false, pages: {}, marks: true, open: {}, fbOpen: false },
    // העתקות: איזו שכבה מוצגת, איזה זוג פתוח, ובדיקה שרצה עכשיו
    copy: { filter: "all", open: null, running: false, progress: "" },
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
      done: {
        pull: !!A.pulledAt,
        grade: ok.length > 0 && graded.length === ok.length,
        ret: ok.length > 0 && returned.length === ok.length,
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
    if (stage === "pull") runLocalPull();
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
      if (!mine) text = n ? `העלה ${n} למודל` : I.done.ret ? "הכל הועלה" : "אין עבודות להעלאה";
      if (LOCAL.sending?.running || LOCAL.starting) disabled = true;  // העלאה אחת בכל פעם, גם אם היא של מטלה אחרת
      if (LOCAL.sending?.running && sendingHere()) { text = sendProgressText(); spinning = true; }
      if (LOCAL.rd?.flow && LOCAL.rd.assignmentId === A.id && !mine) { text = "בודק שהמחשב מוכן…"; spinning = true; disabled = true; }
    }
    // משיכה והחזרה שמישהו אחר בצוות לקח: הכפתור אצלו. אפשר להעביר אליך מלוח המשימות
    const owner = ownerOf(A, stage);
    if (owner && owner.who !== myName() && !spinning) { text = `אצל ${owner.who}`; disabled = true; primary = false; }
    const icon = spinning ? ICON.spin : ICON[stage === "ret" ? "ret" : stage];
    const why = LOCAL.on && stage === "grade" && !LOCAL.health?.claude ? ` title="${esc(NO_KEY)}"` : "";
    // בזמן בדיקה: כפתור עצירה. מה שכבר נשלח ל-Claude מסתיים ונשמר, והשאר נשאר "ממתינה לבדיקה"
    const stopBtn = mine && stage === "grade" ? `<button class="btn danger ${big ? "lg" : ""}" data-act="grade-stop" ${run.stopping ? "disabled" : ""}
      title="העבודות שכבר נשלחו ל-Claude יסתיימו ויישמרו. השאר יחכו ללחיצה הבאה על 'בדוק'">${run.stopping ? ICON.spin : ICON.stop}${run.stopping ? "עוצר…" : "עצור בדיקה"}</button>` : "";
    const btn = `<button class="btn ${primary ? "primary" : "secondary"} ${big ? "lg" : ""}" data-run="${stage}" ${disabled ? "disabled" : ""}${why}
      ${stage === "grade" ? `aria-expanded="${state.gradePick === A.id}"` : ""}>${icon}${text}</button>${stopBtn}`;
    return stage === "grade" ? `<span class="pick-wrap">${btn}${disabled ? "" : gradePickHTML()}</span>` : btn;
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
              ${stageButton(st)}
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
          ${stageButton(stage, { big: true })}
        </div>
      </section>
      ${stage === "pull" ? pullBarHTML() : ""}
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
        cells = `<td>${progressHTML(I.graded.length, I.ok.length)}</td>
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
      grade: `<th>נבדקו</th><th class="col-hide-sm">מי בודק</th><th>מה נשאר לקחת</th>`,
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
        <div class="panel-head"><h3>העלאה למודל</h3><span class="end tag">${S.done || 0} מתוך ${S.total} הועלו</span></div>
        <div class="panel-body">
          <p class="send-line">${ICON.spin}<b>${sendProgressText()}</b></p>
          <div class="send-bar" role="progressbar" aria-label="התקדמות ההעלאה" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div>
          ${LOCAL.stopping ? `<p class="hint">ביקשת לעצור: ההעלאה תיעצר אחרי הקובץ הנוכחי.</p>` : ""}
          <div class="send-actions"><button class="btn secondary" data-act="send-stop" ${LOCAL.stopping ? "disabled" : ""}>עצור אחרי הקובץ הנוכחי</button></div>
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
  const newReady = (A, flow) => ({
    assignmentId: A.id, flow, data: null, looping: false, fetchedAt: 0, checking: false, checkTried: false, checkError: "",
    loginTried: false, loginError: "", installAsk: false, installTried: false, installError: "",
  });

  // הלחיצה על "העלה N למודל". אם הכול כבר מוכן (גם לפי הזיכרון של 30 הדקות), ממשיכים ישר להכנה
  async function startSendFlow() {
    const A = cur();
    if (!A || state.run[A.id] || LOCAL.sending?.running || LOCAL.starting || (LOCAL.rd?.flow && LOCAL.rd.assignmentId === A.id)) return;
    LOCAL.batch = null;
    const rd = (LOCAL.rd = newReady(A, true));
    state.run[A.id] = { stage: "ret", steps: RET_LOCAL_STEPS.map(() => "pending"), progress: "בודק שהמחשב מוכן…" };
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
    if (allReady(rd.data)) { rd.flow = false; prepareLocalSend(); return; }
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
          if (allReady(d)) { rd.flow = false; render(); prepareLocalSend(); break; }
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

  // חלון ההכנה: מופיע אחרי הלחיצה על "העלה N למודל", ונעלם כשהכול ✓ (ואז עוברים להכנת האצווה)
  function readyPanelHTML() {
    const rd = LOCAL.rd;
    if (!LOCAL.on || !rd?.flow || rd.assignmentId !== cur()?.id || !rd.data) return "";
    return `<section class="panel report send-panel ready-panel" aria-live="polite">
      <div class="panel-head"><h3>לפני ההעלאה: בודקים שהמחשב הזה מוכן</h3><button class="btn ghost small end" data-act="ready-close">ביטול</button></div>
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
    return `${teamHTML()}
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
              <td>${scoreHTML(s)}</td>
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
            <li><b>מושכים רק ממחשב שהתיקייה המשותפת מסונכרנת בו</b> (YallaLinearit ב-OneDrive). ממחשב עם עותק מקומי המשיכה נעצרת, כי טבלת המפתח שלו לא רואה מספרים שמחשב אחר כבר נתן.</li>
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

  // שלב 2: ההנחיות נשלחות ל-Claude. המחוון והפתרון נקראים מתיקיית המטלה (grading/grade.py)
  function gradeInstr() {
    const R = rubric(), A = cur();
    const total = R.questions.reduce((a, q) => a + q.pts, 0);
    return `<div class="split wide-first">
      <div class="stack">
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
              <div><dt>הציון</dt><dd>בינתיים עולה ידנית: במטלה מפעילים "Offline grading worksheet", מורידים את גיליון הציונים, <code dir="ltr">python -m moodle upload &lt;id&gt;</code> ממלא אותו, ומעלים דרך "העלאת גיליון ציונים"</dd></div>
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
      ${tabsHTML(stage)}<div class="tab-body" role="tabpanel" aria-labelledby="tab-${stage}-${t}">${body}</div>`;
  }

  function distHTML(I) {
    const g = I.graded.map((s) => s.score).filter((x) => typeof x === "number");
    if (!g.length) return `<p class="muted empty-line">יופיע אחרי שיהיו עבודות בדוקות.</p>`;
    const buckets = [[0, 49], [50, 59], [60, 69], [70, 79], [80, 89], [90, 100]];
    const counts = buckets.map(([a, b]) => g.filter((x) => x >= a && x <= b).length);
    const max = Math.max(...counts, 1);
    const sorted = [...g].sort((a, b) => a - b);
    return `
      <div class="dist-wrap">
        <div class="dist" role="img" aria-label="התפלגות ציונים">
          ${buckets.map(([a, b], i) => `<div class="bar ${a < 60 ? "low" : ""} ${counts[i] ? "" : "zero"}"><span class="v num">${counts[i] || ""}</span><i style="height:${(counts[i] / max) * 100}%"></i><span class="l num">${a}–${b}</span></div>`).join("")}
        </div>
        <dl class="kv">
          <div><dt>ממוצע</dt><dd class="num">${avg(g)}</dd></div>
          <div><dt>חציון</dt><dd class="num">${sorted[Math.floor(sorted.length / 2)]}</dd></div>
          <div><dt>מתחת ל-60</dt><dd class="num">${g.filter((x) => x < 60).length}</dd></div>
          <div><dt>ציון מלא</dt><dd class="num">${g.filter((x) => x === 100).length}</dd></div>
        </dl>
      </div>`;
  }

  // שורת המספרים מתחת למסלול: כמה נבדקו, ממוצע, חציון, פיזור, עוברים, כמה מחכות לאדם וכמה אושרו
  function statsRowHTML(A, I) {
    const max = A.maxGrade || 100;
    const g = I.graded.map((s) => s.score).filter((x) => typeof x === "number");
    const mean = g.length ? g.reduce((a, b) => a + b, 0) / g.length : null;
    const sd = g.length > 1 ? Math.sqrt(g.reduce((a, x) => a + (x - mean) ** 2, 0) / (g.length - 1)) : null;
    const pass = g.length ? Math.round((100 * g.filter((x) => x >= 0.6 * max).length) / g.length) : null;
    const queue = A.subs.filter(needsReview).length;
    const approved = I.graded.filter((s) => s.approved).length;
    const tile = (label, value, sub = "", cls = "", href = "") => `<${href ? `a href="${href}"` : "div"} class="stat ${cls}">
      <span class="stat-l">${label}</span><b class="stat-v num">${value}</b>${sub ? `<span class="stat-s">${sub}</span>` : ""}</${href ? "a" : "div"}>`;
    return `<section class="stat-row" aria-label="סטטיסטיקה">
      ${tile("נבדקו", `${I.graded.length}<small>/${I.ok.length}</small>`, I.ok.length ? `${Math.round((100 * I.graded.length) / I.ok.length)}% מההגשות` : "")}
      ${tile("ממוצע", fmt(mean), `מתוך ${max}`)}
      ${tile("חציון", fmt(median(g)), sd != null ? `סטיית תקן ${fmt(sd)}` : "")}
      ${tile("עוברים", pass != null ? `${pass}%` : "—", `ציון ${0.6 * max} ומעלה`)}
      ${tile("לבדיקה ידנית", queue, queue ? "לחיצה פותחת את התור" : "אין מה לבדוק", queue ? "warn" : "ok", "#/review")}
      ${tile("אושרו", `${approved}<small>/${I.graded.length}</small>`, "ציונים שאדם אישר")}
    </section>`;
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

  function perQuestionHTML(I) {
    const qs = rubric().questions;
    // רק עבודות עם ניקוד לכל שאלה (בשורות ישנות יש רק ציון סופי)
    const withQ = I.graded.filter((s) => Array.isArray(s.q) && s.q.length === qs.length);
    if (noRubric()) return `<p class="muted empty-line">אין מחוון, אז אין ניקוד לפי שאלה.</p>`;
    if (!withQ.length) return `<p class="muted empty-line">יופיע אחרי שיהיה ניקוד לכל שאלה.</p>`;
    // עבודה שהניקוד בה עובר את המחוון נבדקה לפי חלוקה אחרת: לא נספרת, אחרת יוצאים אחוזים מעל 100
    const fits = withQ.filter((s) => !overRubric(s.q).length), off = withQ.length - fits.length;
    const offNote = off ? `<p class="hint">${off === 1
      ? "עבודה אחת לא נספרת כאן: הניקוד בה עובר את המחוון (היא נבדקה לפי חלוקה אחרת), וצריך לבדוק אותה מחדש."
      : `${off} עבודות לא נספרות כאן: הניקוד בהן עובר את המחוון (הן נבדקו לפי חלוקה אחרת), וצריך לבדוק אותן מחדש.`}</p>` : "";
    if (!fits.length) return `<p class="muted empty-line">אין עדיין עבודות שנבדקו לפי המחוון.</p>${offNote}`;
    const rates = qs.map((q, i) => Math.min(100, avg(fits.map((s) => Math.round((s.q[i] / q.pts) * 100)))));
    const worst = rates.indexOf(Math.min(...rates));
    return `<ul class="qbars">${qs.map((q, i) => `
      <li class="${i === worst ? "worst" : ""}"><span>שאלה ${q.n}</span><span class="track"><i style="width:${rates[i]}%"></i></span><b class="num">${rates[i]}%</b></li>`).join("")}</ul>${offNote}`;
  }

  // עלות הבדיקה עד עכשיו, מתוך יומן השימוש של Claude Code. שווה ערך ל-API: הבדיקה רצה במנוי של הצוות, לא מחויבת
  function usageHTML() {
    const u = D.usage;
    if (!u) return "";
    const share = u.cacheReadShare == null ? "—" : `${Math.round(u.cacheReadShare * 100)}%`;
    const models = Object.entries(u.models || {}).map(([m, v]) => `<bdi>${esc(m)}</bdi> · ${v.runs} ריצות · <bdi>$${v.costUsd}</bdi>`).join("<br>");
    return `<section class="panel"><div class="panel-head"><h3>עלות הבדיקה</h3><span class="meta">שווה ערך ל-API, לא חיוב</span></div>
      <div class="panel-body"><div class="stat-row" style="grid-template-columns:repeat(3,minmax(0,1fr));margin-top:0">
        <div class="stat"><span class="stat-l">סך הכל</span><b class="stat-v num">$${u.costUsd}</b><span class="stat-s">${u.runs} ריצות</span></div>
        <div class="stat"><span class="stat-l">לעבודה</span><b class="stat-v num">$${u.avgUsd}</b><span class="stat-s">ממוצע לריצה</span></div>
        <div class="stat"><span class="stat-l">מהמטמון</span><b class="stat-v num">${share}</b><span class="stat-s">מהקלט נקרא ולא נכתב מחדש</span></div>
      </div><p class="muted" style="margin:12px 0 0">${models}</p></div></section>`;
  }

  function logHTML(limit, onlyHere) {
    const icon = { pull: ICON.pull, grade: ICON.grade, return: ICON.ret, error: ICON.warn };
    const list = D.runs.filter((r) => !onlyHere || (r.where || "").startsWith(course()?.name || "")).slice(0, limit);
    if (!list.length) return `<p class="muted empty-line" style="padding:12px 0">עוד אין פעילות.</p>`;
    return `<ul class="log">${list.map((r) => `
      <li><span class="ic ${r.kind}">${icon[r.kind]}</span><div>${esc(r.text)}<small>${esc(r.where || "")}<time class="num">${when(r.at)}</time>${r.actor ? `<span dir="ltr">${esc(r.actor)}</span>` : ""}</small></div></li>`).join("")}</ul>`;
  }

  function overviewHTML() {
    const list = D.assignments.filter((a) => a.courseId === state.courseId && !a.empty);
    const mark = (done, txt) => `<span class="ov ${done ? "done" : ""}">${done ? ICON.check : ""}${txt}</span>`;
    return `<div class="table-wrap"><table class="overview">
      <thead><tr><th>מטלה</th><th class="col-hide">מועד הגשה</th><th>משיכה</th><th>בדיקה</th><th>החזרה</th><th>ממוצע</th></tr></thead>
      <tbody>${list.map((A) => {
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
    </table></div>`;
  }

  function rubricSummaryHTML() {
    const R = rubric();
    return `
      <ul class="criteria">${R.questions.map((q) => `<li><span title="${esc(q.req)}">שאלה ${q.n}</span><span class="track"><i style="width:${q.pts}%"></i></span><b class="num">${q.pts}</b></li>`).join("")}</ul>`;
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
    return `
      <div class="page-head"><div><h1>המערכת לא מחוברת</h1>
        <p>האתר מציג רק נתונים אמיתיים, מתוך תיקיית OneDrive של הקורס. הם מגיעים מהמערכת שרצה במחשב שלך, ועכשיו היא לא מחוברת.</p></div></div>
      <section class="panel" style="margin-bottom:24px">
        <div class="panel-head"><h2>איך מתחברים</h2><span class="end tag warn">${LOCAL.probing ? "מנסה להתחבר…" : "לא מחובר"}</span></div>
        <div class="panel-body">
          <ol class="todo">
            <li>המערכת צריכה לרוץ במחשב. אחרי לחיצה אחת על <code dir="ltr">install-autostart.bat</code> בתיקייה assignment-checker היא עולה לבד, בלי חלון, בכל הדלקה של המחשב. (בלי זה: לחיצה כפולה על <code dir="ltr">start.bat</code>, והחלון השחור נשאר פתוח.)</li>
            <li>לוחצים "פתח את המערכת". אותו אתר נפתח בכתובת <code dir="ltr">http://localhost:8765</code>, עם הנתונים האמיתיים ובלי שום הרשאה. <b>מהפעם הבאה הקישור הזה מעביר לשם לבד.</b></li>
          </ol>
          <div class="row-start">
            <a class="btn primary lg" data-open-local href="${LOCAL_SITE}${esc(location.hash)}">${ICON.chev}פתח את המערכת</a>
            <button class="btn secondary small" data-act="recheck">${ICON.redo}נסה להתחבר מכאן</button>
          </div>
          <p class="hint">אפשר גם לעבוד מהכתובת הזו: אם כרום שואל אם לאפשר לאתר לגשת לאפליקציות ולשירותים במכשיר, לוחצים "אפשר", והאתר מתחבר לבד תוך כמה שניות.</p>
        </div>
      </section>
      <section class="panel" style="margin-bottom:24px">
        <div class="panel-head"><h2>פעם ראשונה במחשב הזה?</h2><span class="meta">פעם אחת לכל אחד מהצוות</span></div>
        <div class="panel-body">
          <ol class="todo">
            <li><b>גישה לתיקייה:</b> מבקשים מהמרצה גישה לתיקייה YallaLinearit. בדפדפן, על התיקייה: Add shortcut to My files. באפליקציית OneDrive במחשב מתחברים עם חשבון האוניברסיטה.</li>
            <li><b>התוכנות</b>, בחלון PowerShell: <code dir="ltr">winget install Python.Python.3.12</code>, <code dir="ltr">winget install 7zip.7zip</code>, <code dir="ltr">winget install Git.Git</code></li>
            <li><b>המערכת:</b> בחלון חדש, בתיקייה שבה רוצים לשמור אותה: <code dir="ltr">git clone ${REPO_URL}</code></li>
            <li><b>מפעילים, פעם אחת:</b> לחיצה כפולה על <code dir="ltr">install-autostart.bat</code> בתיקייה assignment-checker. מעכשיו המערכת עולה לבד, בלי חלון, בכל פעם שהמחשב נדלק, והקישור הזה פשוט עובד. בכל הפעלה היא מתעדכנת מ-GitHub, כך שכולם עובדים על אותה גרסה. (בלי הפעלה אוטומטית: לחיצה כפולה על <code dir="ltr">start.bat</code>, והחלון השחור נשאר פתוח.)</li>
          </ol>
          <div class="row-start"><a class="btn secondary small" href="${REPO_URL}#readme" target="_blank" rel="noopener">ההסבר המלא ב-GitHub</a></div>
        </div>
      </section>
      ${how}`;
  }

  // ---------- הגרסה המחוברת: תיקיית OneDrive דרך השרת המקומי ----------
  function bannerHTML() {
    const alerts = (D.sysAlerts || []).map((a) =>
      `<div class="banner ${a.kind === "error" ? "error" : "warn"}">${ICON.warn}${esc(a.text)}</div>`
    ).join("");
    if (LOCAL.on && !LOCAL.health?.root) {
      return alerts + `<div class="banner warn">${ICON.warn}<div><b>המערכת פועלת, אבל תיקיית OneDrive של הקורס עוד לא נמצאה במחשב.</b><pre class="banner-pre">${esc(LOCAL.health?.error || "")}</pre></div><button class="btn secondary small" data-act="recheck">בדוק שוב</button></div>`;
    }
    return alerts;
  }

  function whatNowHTML(A) {
    const wn = A?.whatNow;
    if (!wn || !wn.text) return "";
    const stepIcon = { pull: ICON.pull, grade: ICON.grade, rubric: ICON.pen, review: ICON.pen, ret: ICON.ret, done: ICON.check };
    const ownerSpan = wn.owner ? ` <span class="muted"> — אצל ${esc(wn.owner)}</span>` : "";
    return `<p class="what-now step-${esc(wn.step)}">${stepIcon[wn.step] || ""}${esc(wn.text)}${ownerSpan}</p>`;
  }

  function whoWorkingBarHTML() {
    const workers = D.whoWorking || [];
    if (!workers.length) return "";
    const ACT = { grading: "בודק", uploading: "מעלה" };
    const chips = workers.map((w) => {
      const act = ACT[w.activity] || "עובד";
      const where = w.folder ? ` — ${esc(w.folder)}` : "";
      return `<span class="who-chip">${esc(w.name)} ${act}${where}</span>`;
    }).join("");
    return `<div class="who-bar">${chips}</div>`;
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
    const over = overRubric(d.points), blocked = !!noRubric() || over.length > 0;
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
          <div class="rv-bar">
            <div class="rv-total"><b class="num" id="rv-total">${noRubric() ? "—" : draftTotal(d)}</b><span>/ ${max}</span></div>
            <button type="submit" class="btn primary" ${state.review.saving || blocked ? "disabled" : ""} title="${blocked ? "אפשר לאשר רק ניקוד לפי המחוון" : "Ctrl+Enter"}">${state.review.saving ? ICON.spin : ICON.check}${needsReview(s) ? (next ? "אשר ועבור לבאה" : "אשר") : "שמור"}</button>
          </div>
        </form>
      </div>`;
  }

  async function saveReview(id) {
    const A = cur(), s = A?.subs.find((x) => x.id === id);
    if (!s || state.review.saving) return;
    const d = draft(s), wasQueued = needsReview(s);
    if (noRubric() || overRubric(d.points).length) { toast(noRubric() || `אפשר לאשר רק ניקוד לפי המחוון. ${RUBRIC_RULE}`, ICON.warn); return; }
    const { queue } = reviewList(A);
    const at = queue.findIndex((x) => x.id === id);
    const next = wasQueued ? (queue[at + 1] || queue.find((x) => x.id !== id)) : null;
    state.review.saving = true;
    render();
    try {
      const r = await api("api/review", { method: "POST", body: JSON.stringify({
        course: A.courseFolder, assignment: A.folder, number: id,
        points: d.points, comments: d.comments, feedback: d.feedback, mistakes: d.picks,
      }) });
      delete state.review.edits[id];
      toast(`עבודה ${id} נשמרה: ${r.grade}`);
      state.review.saving = false;
      await loadLocal();
      const target = next ? `#/review?n=${next.id}` : wasQueued ? "#/review" : location.hash;
      if (location.hash === target) render(); else location.hash = target;
    } catch (e) {
      state.review.saving = false;
      render();
      toast(e.message, ICON.warn);
    }
  }

  // ---------- העתקות (copying/check.py): זוגות של הגשות שנראות כמו אותה עבודה. בלי Claude ובלי טוקנים ----------
  // שכבה 0: אותו קובץ או אותו מקור (קובץ, מטא-דאטה). שכבה 1: אותה סריקה בקובץ אחר (עמודים)
  const COPY_KIND = {
    file: { layer: 0, text: "אותו קובץ בדיוק" },
    doc_id: { layer: 0, text: "אותו מזהה מסמך פנימי: הקבצים נוצרו מאותו מסמך" },
    author: { layer: 0, text: "אותו מחבר במטא-דאטה של ה-PDF" },
    created: { layer: 0, text: "אותו רגע יצירה במטא-דאטה של ה-PDF" },
    page: { layer: 1, text: "עמודים זהים: אותה סריקה או תמונה" },
    text: { layer: 1, text: "עמוד מוקלד עם כמעט אותו טקסט" },
  };
  const COPY_LAYERS = [
    { key: "l0", layer: 0, name: "אותו קובץ או אותו מקור", what: "קובץ זהה אצל שני מספרים, או PDF שנוצר מאותו מסמך (מזהה פנימי, מחבר, רגע יצירה)" },
    { key: "l1", layer: 1, name: "אותו עמוד", what: "סריקה שנראית כמעט זהה לעמוד בהגשה אחרת (גם אחרי דחיסה או צילום מסך), או עמוד מוקלד עם אותו טקסט נדיר" },
  ];
  const inLayer = (p, layer) => p.reasons.some((r) => COPY_KIND[r.kind]?.layer === layer);
  const pairKey = (p) => `${p.a}-${p.b}`;

  // שתי ההגשות זו לצד זו: העמודים שנמצאו זהים, ובלי עמודים זהים העמוד הראשון של כל אחת
  function copyCompareHTML(A, p) {
    const found = p.reasons.find((r) => r.pages), pages = found?.pages || [[1, 1, null]];
    const score = (d) => (d == null ? "" : found.kind === "text" ? ` · ${d}% מהטקסט הנדיר משותף` : ` · ${d ? `${d} ביטים שונים מתוך 256` : "זהה"}`);
    const sub = (id) => A.subs.find((s) => s.id === id);
    const open = (id) => {
      const f = sub(id) && origFiles(sub(id))[0];
      return f ? `<a class="link" href="${fileUrl(f)}" target="_blank" rel="noopener">${ICON.file}פתח את ${id}</a>` : "";
    };
    return `<div class="cp-compare">
      <div class="cp-cols cp-cols-head"><div><b class="num">${p.a}</b>${open(p.a)}</div><div><b class="num">${p.b}</b>${open(p.b)}</div></div>
      ${pages.slice(0, 4).map(([pa, pb, d]) => `<div class="cp-cols">
        <figure><img loading="lazy" src="${pageUrl(A, p.a, pa)}" alt="עמוד ${pa} בהגשה ${p.a}"><figcaption>עמוד ${pa}</figcaption></figure>
        <figure><img loading="lazy" src="${pageUrl(A, p.b, pb)}" alt="עמוד ${pb} בהגשה ${p.b}"><figcaption>עמוד ${pb}${score(d)}</figcaption></figure>
      </div>`).join("")}
      ${pages.length > 4 ? `<p class="muted">ועוד ${pages.length - 4} זוגות של עמודים זהים</p>` : ""}
    </div>`;
  }

  function copyPairHTML(A, p) {
    const k = pairKey(p), isOpen = state.copy.open === k;
    const reasons = p.reasons.map((r) => COPY_KIND[r.kind]?.text + (r.pages ? ` (${r.pages.map(([a, b]) => (a === b ? `עמוד ${a}` : `${a}↔${b}`)).join(", ")})` : ""));
    return `<article class="cp-pair ${isOpen ? "open" : ""}">
      <button type="button" class="cp-pair-head" data-copy-open="${k}" aria-expanded="${isOpen}">
        <span class="cp-nums num">${p.a}<i>↔</i>${p.b}</span>
        <span class="tag ${p.level === "strong" ? "bad" : "warn"}">${p.level === "strong" ? "חשד חזק" : "כדאי להסתכל"}</span>
        <span class="cp-why">${reasons.map(esc).join(" · ")}</span>
        <span class="cp-chev" aria-hidden="true">${ICON.chev}</span>
      </button>
      ${isOpen ? copyCompareHTML(A, p) : ""}
    </article>`;
  }

  function copyingView() {
    const A = cur();
    if (!A) return offlineHTML();
    const C = A.copying, run = state.copy, pairs = C?.pairs || [];
    const shown = run.filter === "all" ? pairs : pairs.filter((p) => inLayer(p, COPY_LAYERS.find((l) => l.key === run.filter).layer));
    const strong = pairs.filter((p) => p.level === "strong").length;
    const button = (cls) => `<button type="button" class="btn ${cls}" data-copy-run ${run.running || !LOCAL.on ? "disabled" : ""}>
      ${run.running ? ICON.spin : ICON.search}${run.running ? esc(run.progress || "בודק…") : C ? "בדוק שוב" : "בדוק העתקות"}</button>`;
    const head = `<div class="page-head cp-top">
        <div><h1>העתקות</h1>
          <p>משווה את ההגשות זו לזו ומחפש עבודות שהן בעצם אותה עבודה. בלי Claude ובלי טוקנים: רק השוואה של הקבצים במחשב.</p>
          ${C ? `<p class="muted">נבדק ${when(C.checkedAt)} · ${plural(C.checked, "הגשה אחת", "הגשות")}${C.by ? ` · ${esc(C.by)}` : ""}</p>` : ""}</div>
        ${C ? button("secondary") : ""}
      </div>
      ${C?.stale ? `<div class="notice">${ICON.warn}<div>הגיעו הגשות חדשות או שקבצים השתנו מאז הבדיקה. כדאי לבדוק שוב: רק הקבצים החדשים ייקראו.</div></div>` : ""}`;
    if (!A.subs.length) return `${head}<section class="panel">${emptyPulled()}</section>`;
    if (!C) return `${head}<section class="rv-empty cp-empty">${ICON.search}<b>עוד לא נבדק</b>
      <p>הבדיקה משווה כל הגשה לכל האחרות: קבצים זהים, PDF שנוצר מאותו מסמך, ועמודים שהם אותה סריקה.<br>בפעם הראשונה זה לוקח כמה דקות. אחר כך רק הגשות חדשות נקראות.</p>
      ${button("primary")}</section>`;
    const layers = `<div class="cp-layers" role="group" aria-label="סוג החשד">
      <button type="button" class="cp-layer" data-copy-filter="all" aria-pressed="${run.filter === "all"}">
        <span class="cp-layer-n num">${pairs.length}</span><span><b>כל החשדות</b><small>${strong ? `${strong} מהם חשד חזק` : "אין חשד חזק"}</small></span></button>
      ${COPY_LAYERS.map((l) => `<button type="button" class="cp-layer" data-copy-filter="${l.key}" aria-pressed="${run.filter === l.key}">
        <span class="cp-layer-n num">${pairs.filter((p) => inLayer(p, l.layer)).length}</span>
        <span><b><span class="cp-layer-no">שכבה ${l.layer}</span>${l.name}</b><small>${l.what}</small></span></button>`).join("")}
    </div>`;
    const list = shown.length
      ? `<div class="cp-list">${shown.map((p) => copyPairHTML(A, p)).join("")}</div>`
      : `<section class="rv-empty">${ICON.check}<b>לא נמצא חשד להעתקה</b><p>${pairs.length ? "אין זוגות חשודים בשכבה הזו." : `אף הגשה לא זהה לאחרת, מתוך ${plural(C.checked, "הגשה אחת", "הגשות")}.`}</p></section>`;
    return `${head}${layers}${list}${copyRepeatedHTML(A, C.repeated || [])}
      <p class="cp-foot muted">זה רק חשד: ההחלטה אם זו העתקה היא של אדם. העתקה בכתב יד אחר (חבר שהעתיק את הפתרון בכתב ידו) לא נתפסת כאן.</p>`;
  }

  // עמודים שחוזרים אצל הרבה הגשות: בדרך כלל דף שאלות, אבל גם פתרון שעבר בקבוצה. לא זוגות: אדם מחליט
  function copyRepeatedHTML(A, groups) {
    if (!groups.length) return "";
    return `<section class="panel cp-repeated">
      <div class="panel-head"><h3>עמודים שחוזרים אצל הרבה הגשות</h3><span class="meta">בדרך כלל דף שאלות. אם זה פתרון, זו העתקה של קבוצה</span></div>
      <div class="panel-body">${groups.slice(0, 10).map((g) => {
        const [n, pg] = g.pages[0];
        return `<div class="cp-group">
          <img loading="lazy" src="${pageUrl(A, n, pg)}" alt="עמוד ${pg} בהגשה ${n}">
          <div><b>${g.numbers} הגשות</b> <span class="muted">${g.kind === "text" ? "אותו טקסט" : "אותה סריקה"}</span>
            <p class="num">${g.pages.slice(0, 40).map(([x, y]) => `${x}${y > 1 ? `/${y}` : ""}`).join(" · ")}${g.pages.length > 40 ? " …" : ""}</p></div>
        </div>`;
      }).join("")}</div>
    </section>`;
  }

  // "בדוק העתקות": השרת משווה את ההגשות ברקע (api/copying), והאתר שואל מה המצב עד שזה נגמר
  async function runCopying() {
    const A = cur();
    if (!A || state.copy.running || !LOCAL.on) return;
    Object.assign(state.copy, { running: true, progress: "" });
    render();
    try {
      await api("api/copying", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder }) });
      let job;
      for (;;) {
        await new Promise((r) => setTimeout(r, 1000));
        job = await api("api/copying");
        state.copy.progress = job.total ? `קורא קבצים ${job.done} מתוך ${job.total}…` : "בודק…";
        if (route() === "/copying") render();
        if (!job.running) break;
      }
      state.copy.running = false;
      await loadLocal();
      toast(job.error || job.summary, job.error ? ICON.warn : ICON.check);
    } catch (e) {
      state.copy.running = false;
      render();
      toast(e.message, ICON.warn);
    }
  }

  const views = {
    "/review": () => reviewView(),
    "/copying": () => copyingView(),
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
        ${whoWorkingBarHTML()}
        ${noRubric() ? rubricNoticeHTML() : ""}
        ${whatNowHTML(A)}
        ${pipelineHTML()}
        ${statsRowHTML(A, I)}
        ${reviewCalloutHTML(A)}
        <div class="grid-2">
          <div class="stack">
            <section class="panel"><div class="panel-head"><h2>התפלגות ציונים</h2><span class="meta">${I.graded.length} עבודות בדוקות</span></div><div class="panel-body">${distHTML(I)}</div></section>
            <section class="panel"><div class="panel-head"><h2>טעויות נפוצות</h2><span class="meta">לחיצה על טעות מראה מי עשה אותה</span></div><div class="panel-body">${mistakesHTML(A)}</div></section>
            <section class="panel"><div class="panel-head"><h3>הצלחה לפי שאלה</h3></div><div class="panel-body">${perQuestionHTML(I)}</div></section>
          </div>
          <div class="stack">
            <section class="panel"><div class="panel-head"><h3>מחוון</h3><a class="end link" href="#/grade" data-goto-tab="grade:instr">פרטים</a></div><div class="panel-body">${rubricSummaryHTML()}</div></section>
            ${usageHTML()}
            <section class="panel"><div class="panel-head"><h3>פעילות אחרונה</h3><a class="end link" href="#/runs">ליומן המלא</a></div><div class="panel-body tight">${logHTML(4, true)}</div></section>
          </div>
        </div>
        <section class="panel" style="margin-top:24px">
          <div class="panel-head"><h2>כל המטלות ב${esc(course().name)}</h2><span class="meta">לחיצה על שורה עוברת למטלה</span></div>
          ${overviewHTML()}
        </section>`;
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
      return `
        <div class="page-head"><div><h1>חיבורים והגדרות</h1><p>מה מחובר עכשיו.</p></div></div>
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
    const cb = $("#nav-copy-badge"), strong = (A.copying?.pairs || []).filter((p) => p.level === "strong").length;
    cb.textContent = strong || "";
    cb.title = strong ? `${strong} זוגות עם חשד חזק להעתקה` : "";
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
    cs.innerHTML = D.courses.map((c) => `<option value="${c.id}" ${c.id === state.courseId ? "selected" : ""}>${esc(c.name)}</option>`).join("") || "<option>אין קורסים</option>";
    as.innerHTML = list.map((a) => `<option value="${a.id}" ${a.id === state.assignmentId ? "selected" : ""}>${esc(a.title)}</option>`).join("") || "<option>אין מטלות</option>";
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
    else if (!cur() && !["/settings", "/runs"].includes(route())) html = offlineHTML();
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
    if (t.closest("a[data-open-local]")) store.set("openLocal", true);  // מהפעם הבאה הקישור הציבורי מעביר לכאן לבד
    const runBtn = t.closest("[data-run]");
    if (runBtn) { runStage(runBtn.dataset.run); return; }
    const gChip = t.closest("[data-grade-chip]");
    if (gChip) { state.gradeCount = Number(gChip.dataset.gradeChip); store.set("gradeCount", state.gradeCount); render(); return; }
    if (state.gradePick && !t.closest(".grade-pick")) { state.gradePick = null; render(); }  // לחיצה מחוץ לחלונית סוגרת אותה
    if (t.closest("[data-copy-run]")) { runCopying(); return; }
    const cpFilter = t.closest("[data-copy-filter]");
    if (cpFilter) { state.copy.filter = cpFilter.dataset.copyFilter; state.copy.open = null; render(); return; }
    const cpOpen = t.closest("[data-copy-open]");
    if (cpOpen) { const k = cpOpen.dataset.copyOpen; state.copy.open = state.copy.open === k ? null : k; render(); return; }

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
      if (a === "open-inbox") openFolder("inbox");
      if (a === "pull-full") runLocalPull(true);
      if (a === "open-upload") openFolder("upload");
      if (a === "recheck") { if (LOCAL.on) location.reload(); else connect(true); }
      if (a === "send-confirm" && LOCAL.batch?.assignmentId === cur().id) startLocalSend(LOCAL.batch.id);
      if (a === "send-cancel") { LOCAL.batch = null; render(); }
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

    const as = t.closest("[data-assign]");
    if (as) { state.assignmentId = as.dataset.assign; state.filter = "all"; resetOpen(); renderPickers(); render(); window.scrollTo({ top: 0, behavior: "smooth" }); return; }

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
    if (t.matches("[data-name-draft]")) { state.nameDraft = t.value; return; }
    if (t.matches("[data-grade-count]")) {
      state.gradeCount = Math.max(1, parseInt(t.value, 10) || 1);
      store.set("gradeCount", state.gradeCount);
      // רק התווית של הכפתור משתנה, בלי לצייר מחדש: הסמן נשאר בשדה
      const go = $("[data-act=grade-pick-go]");
      if (go) go.innerHTML = `${ICON.grade}בדוק ${Math.min(state.gradeCount, Number(t.max) || state.gradeCount)}`;
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
        if (!r.ok) throw new Error(data.error || `המערכת במחשב החזירה שגיאה ${r.status}`);
        return data;
      }, () => { throw new Error("אין חיבור למערכת במחשב. אם המחשב נדלק עכשיו, מחכים דקה; אחרת מפעילים את start.bat."); });
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

  async function loadLocal() {
    try {
      const [data, health] = await Promise.all([api("api/state"), api("api/health").catch(() => null)]);
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
      D.whoWorking.splice(0, D.whoWorking.length, ...(data.whoWorking || []));
      D.sysAlerts.splice(0, D.sysAlerts.length, ...(data.sysAlerts || []));
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
  // full: את כל ההגשות ממודל. בלי: אחרי משיכה ראשונה, רק מי שההגשה שלו השתנתה מאז המשיכה הקודמת
  async function runLocalPull(full = false) {
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
    const post = api("api/pull", { method: "POST", body: JSON.stringify({ course: A.courseFolder, assignment: A.folder, ...(moodleId && { moodleId }), ...(full && { full: true }) }) })
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
  async function pollChanges() {
    if (changesBusy || !LOCAL.on || !LOCAL.health?.root || document.hidden) return;
    // לא באמצע ריצה ולא בזמן הקלדה: הסיבוב שאחרי יטען
    if (LOCAL.polling || Object.keys(state.run).length || document.activeElement?.matches?.("input, textarea, select")) return;
    changesBusy = true;
    try {
      const { sig } = await api("api/changes");
      if (lastSig !== null && sig !== lastSig) { await loadLocal(); refreshDrawer(); }
      lastSig = sig;
    } catch {
      // המערכת לא ענתה הפעם. מנסים שוב בסיבוב הבא
    } finally {
      changesBusy = false;
    }
  }
  const CHANGES_POLL_MS = 5000;

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
    $("#proto-note").textContent = live
      ? (LOCAL.health?.claude ? "כל המספרים במסך נקראים מתיקיית OneDrive של הקורס." : "כל המספרים במסך נקראים מתיקיית OneDrive של הקורס. הבדיקה עם Claude עוד לא מחוברת (מחברים את Claude Code במחשב, או ANTHROPIC_API_KEY ב-.env).")
      : "האתר מציג רק נתונים אמיתיים, מהמערכת שרצה במחשב (start.bat). כרגע היא לא מחוברת.";
  }

  // מתחברים למערכת. באתר הציבורי מנסים שוב כל כמה שניות, עד שמפעילים את start.bat
  async function connect(manual = false) {
    if (LOCAL.probing || LOCAL.on) return;
    LOCAL.probing = true;
    renderStatus();
    const ok = await detectLocal(ON_LOCAL_HOST ? 20000 : 60000);  // במחשב עצמו המערכת עונה, גם אם לאט: מחכים, לא "לא מחובר"
    LOCAL.probing = false;
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
