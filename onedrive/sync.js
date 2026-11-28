// העלאה לוואן דרייב של המרצה: רק מה שהשתנה, בלי לגרור ובלי "Replace" על כל התיקייה.
//
// מריצים את הקובץ בלשונית של הוואן דרייב (bgu365-my.sharepoint.com), למשל Claude עם javascript_tool.
// בפינת הדף נפתח חלון קטן, ויש בו שתי דרכים:
//   אוטומטי: הקבצים באים מהשרת המקומי (start.bat, http://127.0.0.1:8765/api/sync/), בלי שום לחיצה.
//     Claude מפעיל את window.__ecsSyncAll() (או "סנכרון מהמחשב" בחלון), והסקריפט עובר על כל הקורסים.
//     בפעם הראשונה כרום שואל אם לאפשר לאתר לגשת לרשת המקומית: לוחצים "אפשר" (פעם אחת).
//   ידני: "בחירת תיקיית קורס", בוחרים את התיקייה במחשב (למשל Exercise Checking System\Linear Algebra), ואז "העלאה".
// בשתי הדרכים הסקריפט משווה כל קובץ לקובץ באותו שם בוואן דרייב, מעלה רק את החדשים ואת אלה שהשתנו,
// ובסוף בודק שבוואן דרייב יש בדיוק מה שהועלה.
//
// מה נחשב "השתנה": גודל אחר, או קובץ במחשב שנשמר אחרי הגרסה שבוואן דרייב. קובץ שבוואן דרייב חדש יותר
// מהמחשב (למשל Grades.csv שהצוות עדכן) לא נדרס: הוא מופיע ברשימה "חדש יותר בוואן דרייב", ולא נוגעים בו.
// לא נמחק שום קובץ בוואן דרייב.
//
// התוצאה נשמרת גם ב-window.__ecsSync, כדי ש-Claude יוכל לקרוא אותה (מספרים ושמות קבצים ממוספרים בלבד).

(() => {
  const SITE = "/personal/mein_bgu_ac_il";
  const ROOT = SITE + "/Documents/YallaLinearit/Exercise Checking System";
  // השרת המקומי (start.bat). window.__ecsLocal מחליף אותו, למשל שרת בדיקה על פורט אחר
  const LOCAL = window.__ecsLocal || "http://127.0.0.1:8765/api/sync/";
  const PARALLEL = 3;
  // קבצים שלא מעלים אף פעם: קבצים זמניים של Windows ו-Office, קבצים חצי כתובים, מנעולים, ואף פעם לא ZIP
  // (קובצי ה-ZIP של מודל נשארים במחשב שהוריד), וגם הקבצים של Finder ב-Mac (.DS_Store, ._<שם>). כמו dashboard/sync.py
  const SKIP = /(^|\/)(desktop\.ini|thumbs\.db|\.DS_Store|\._[^/]*|~\$[^/]*|[^/]*\.tmp|[^/]* in progress\.txt|[^/]*\.zip)$/i;
  // שעון המחשב ושעון השרת לא מסונכרנים בדיוק: הפרש קטן מזה לא נחשב "חדש יותר"
  const CLOCK_SLACK_MS = 2 * 60 * 1000;
  // בדיקות שהוצאו מהספירה עוברות בוואן דרייב ל-"<מטלה>/Old test grading/", עם README.txt שנכתב ברגע ההעברה
  // (2026-11-03: בדיקות הניסיון של 23/10-30/10). עותק מקומי שעוד מחזיק אותן במקומן הקודם לא מחזיר אותן:
  // קובץ של בדיקה (עבודה מסומנת, הערות, מי לקח מה, קובץ ציונים) שחסר בוואן דרייב ונכתב לפני ההעברה לא עולה.
  // מה שנבדק אחרי ההעברה עולה כרגיל
  const ARCHIVE = "Old test grading";
  const GRADING_OUTPUT = /^(2 - Graded with comments\/(?!README\.txt$)[^/]+|Grading notes\/[^/]+|Who grades what\/[^/]+|Grades[^/]*\.csv)$/i;

  // מטלה → מתי הועברו הבדיקות שלה לארכיון (זמן ה-README שבארכיון בוואן דרייב)
  const ARCHIVE_README = new RegExp(`^([^/]+)/${ARCHIVE}/README\\.txt$`);
  const ARCHIVED_NOTE = (n) => `${n} קבצים של בדיקות ישנות לא הועלו: בוואן דרייב הן הועברו ל-"${ARCHIVE}". ` +
    `כדאי להעביר אותם גם במחשב הזה לתיקייה "${ARCHIVE}" של המטלה.`;
  function archivedAt(remote) {
    const out = {};
    for (const [path, r] of Object.entries(remote)) {
      const m = path.match(ARCHIVE_README);
      if (m) out[m[1]] = r.mtime;
    }
    return out;
  }

  // ---------- ההשוואה (בלי רשת, כדי שאפשר לבדוק אותה לבד) ----------
  // local: [{path, size, mtime}] (path יחסי לתיקיית הקורס, mtime במילישניות)
  // remote: {path: {size, mtime}}
  function plan(local, remote) {
    const out = { upload: [], same: [], remoteNewer: [], skipped: [], archived: [] };
    const archived = archivedAt(remote);
    for (const f of local) {
      if (SKIP.test(f.path)) { out.skipped.push(f.path); continue; }
      const r = remote[f.path];
      const slash = f.path.indexOf("/"), assignment = f.path.slice(0, slash);
      if (!r && slash > 0 && archived[assignment] !== undefined && GRADING_OUTPUT.test(f.path.slice(slash + 1))
          && f.mtime <= archived[assignment] + CLOCK_SLACK_MS) {
        out.archived.push(f.path);
        continue;
      }
      if (!r) { out.upload.push({ ...f, why: "new" }); continue; }
      const localNewer = f.mtime > r.mtime + CLOCK_SLACK_MS;
      if (f.size !== r.size || localNewer) {
        if (localNewer) out.upload.push({ ...f, why: "changed" });
        else out.remoteNewer.push(f.path);
      } else {
        out.same.push(f.path);
      }
    }
    return out;
  }

  // ---------- בשני הכיוונים (2026-11-20, בשביל Mac) ----------
  // ב-Mac אפליקציית OneDrive לא יכולה לסנכרן את התיקייה של המרצה (חשבונות הצוות אורחים ב-BGU, ו-BGU דורשת מהם
  // אימות דו-שלבי שהאפליקציה לא מציגה). הדפדפן כן מציג אותו, אז הסקריפט גם מוריד: מה שחדש בוואן דרייב נשמר במחשב
  // דרך השרת המקומי (/api/sync/put), שמסרב לדרוס קובץ שהשתנה במחשב מאז ההשוואה.
  // base: {נתיב: {local: [גודל, זמן], remote: [גודל, זמן]}} מהסנכרון האחרון במחשב הזה. איתו יודעים מי השתנה:
  //   רק המחשב → מעלים. רק הוואן דרייב → מורידים. שניהם → התנגשות: לא נוגעים באף צד, ומדווחים.
  //   סונכרן פעם ונעלם מצד אחד (נמחק או הועבר שם) → לא מחזירים אותו: מדווחים (goneRemote / goneLocal).
  // בלי base (קובץ שעוד לא סונכרן מהמחשב הזה): גודל שונה → הצד שנשמר אחרון, בהפרש של יותר מ-CLOCK_SLACK_MS; אחרת
  //   התנגשות. אותו גודל → כמו קודם: עולה אם הוא חדש יותר במחשב, ואחרת זהה (ונרשם ב-base מעכשיו).
  const LOCK = /(^|\/)[^/]* in progress\.txt$/i;
  const LOCK_FRESH_MS = 30 * 60 * 1000;
  const sameAs = (a, b) => Array.isArray(b) && a[0] === b[0] && Math.abs(a[1] - b[1]) <= 1000;
  // מטלות שבוואן דרייב רצה בהן עכשיו משיכה, בדיקה או העלאה (מנעול טרי שמחשב מסונכרן העלה): לא מורידים מהן
  function busyRemote(remote, now = Date.now()) {
    const out = new Set();
    for (const [path, r] of Object.entries(remote)) {
      if (LOCK.test(path) && path.includes("/") && now - r.mtime < LOCK_FRESH_MS) out.add(path.slice(0, path.indexOf("/")));
    }
    return out;
  }
  function plan2(local, remote, base = {}, { up = true, down = true, now = Date.now() } = {}) {
    const out = { upload: [], download: [], same: [], conflict: [], remoteNewer: [], localNewer: [], skipped: [],
      archived: [], goneRemote: [], goneLocal: [], busy: [], record: {} };
    const archived = archivedAt(remote);
    const busy = busyRemote(remote, now);
    const seen = new Set();
    const get = (f, r, why) => {
      const assignment = f.path.includes("/") ? f.path.slice(0, f.path.indexOf("/")) : "";
      if (!down) { if (f.size !== undefined) out.remoteNewer.push(f.path); }  // רק בוואן דרייב: כמו קודם, לא מדווחים
      else if (busy.has(assignment)) out.busy.push(f.path);
      else out.download.push({ path: f.path, size: r.size, mtime: r.mtime, expect: f.size === undefined ? "none" : `${f.size}:${f.mtime}`, why });
    };
    const put = (f, why) => { if (up) out.upload.push({ ...f, why }); else out.localNewer.push(f.path); };
    for (const f of local) {
      seen.add(f.path);
      if (SKIP.test(f.path)) { out.skipped.push(f.path); continue; }
      const r = remote[f.path], b = base[f.path];
      const slash = f.path.indexOf("/"), assignment = f.path.slice(0, slash);
      if (!r) {
        if (b) out.goneRemote.push(f.path);
        else if (slash > 0 && archived[assignment] !== undefined && GRADING_OUTPUT.test(f.path.slice(slash + 1))
            && f.mtime <= archived[assignment] + CLOCK_SLACK_MS) out.archived.push(f.path);
        else put(f, "new");
        continue;
      }
      const L = [f.size, f.mtime], R = [r.size, r.mtime];
      if (b) {
        const lc = !sameAs(L, b.local), rc = !sameAs(R, b.remote);
        if (!lc && !rc) out.same.push(f.path);
        else if (lc && !rc) put(f, "changed");
        else if (!lc && rc) get(f, r, "changed");
        else out.conflict.push(f.path);
        continue;
      }
      const localNewer = f.mtime > r.mtime + CLOCK_SLACK_MS, remoteNewer = r.mtime > f.mtime + CLOCK_SLACK_MS;
      if (f.size === r.size) {
        if (localNewer) put(f, "changed");
        else { out.same.push(f.path); out.record[f.path] = { local: L, remote: R }; }
      } else if (localNewer) put(f, "changed");
      else if (remoteNewer) get(f, r, "changed");
      else out.conflict.push(f.path);
    }
    for (const [path, r] of Object.entries(remote)) {
      if (seen.has(path) || SKIP.test(path) || LOCK.test(path)) continue;
      if (base[path]) { out.goneLocal.push(path); continue; }
      get({ path }, r, "new");
    }
    return out;
  }

  // ---------- טבלת המפתח בין מחשבים ----------
  // כל אחד בצוות יכול למשוך, כל אחד למחשב שלו. אם שני מחשבים משכו את אותה מטלה, לכל אחד טבלת מפתח משלו, ומי שמעלה
  // אחרון היה דורס את השנייה: סטודנטים נעלמים מהטבלה המשותפת, או ששני סטודנטים מקבלים אותו מספר, וקובץ 0481.pdf של
  // סטודנט אחד דורס את 0481.pdf של אחר. לכן לפני שמעלים מטלה שהטבלה שלה בוואן דרייב שונה מזו שבמחשב, משווים את התוכן:
  // הטבלה במחשב חייבת להכיל כל סטודנט שבוואן דרייב, עם אותו מספר, בלי מספר של מישהו אחר. אחרת לא מעלים כלום מהמטלה
  // הזו (לא את הטבלה ולא את ההגשות), ומדווחים. טבלה במחשב שרק מוסיפה סטודנטים חדשים עולה כרגיל.
  const KEY_NAME = "Key - number to student.csv";
  function csvRows(text) {
    const rows = [];
    let row = [], cell = "", quoted = false;
    const t = String(text || "").replace(/^﻿/, "");
    for (let i = 0; i < t.length; i++) {
      const ch = t[i];
      if (quoted) {
        if (ch === '"' && t[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') quoted = false; else cell += ch;
      } else if (ch === '"') quoted = true;
      else if (ch === ",") { row.push(cell); cell = ""; }
      else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && t[i + 1] === "\n") i++;
        row.push(cell); cell = "";
        if (row.some((c) => c !== "")) rows.push(row);
        row = [];
      } else cell += ch;
    }
    row.push(cell);
    if (row.some((c) => c !== "")) rows.push(row);
    const head = rows.shift() || [];
    return rows.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ""])));
  }
  // מה לא מתאים בין הטבלה שבמחשב לזו שבוואן דרייב, במספרים בלבד. ריק: אפשר להעלות
  function keyProblems(localCsv, remoteCsv) {
    const map = (csv) => {
      const byPid = new Map(), byNumber = new Map();
      for (const r of csvRows(csv)) {
        if (!r.participant_id || !r.number) continue;
        byPid.set(r.participant_id, r.number);
        byNumber.set(r.number, r.participant_id);
      }
      return { byPid, byNumber };
    };
    const local = map(localCsv), remote = map(remoteCsv);
    const missing = [], moved = [], taken = [];
    for (const [pid, number] of remote.byPid) {
      if (!local.byPid.has(pid)) missing.push(number);
      else if (local.byPid.get(pid) !== number) moved.push(number);
    }
    for (const [number, pid] of local.byNumber) {
      if (remote.byNumber.has(number) && remote.byNumber.get(number) !== pid) taken.push(number);
    }
    const out = [];
    const few = (a) => a.sort().slice(0, 15).join(", ") + (a.length > 15 ? ` ועוד ${a.length - 15}` : "");
    if (missing.length) out.push(`${missing.length} סטודנטים שבוואן דרייב חסרים בטבלה שבמחשב (${few(missing)})`);
    if (moved.length) out.push(`${moved.length} סטודנטים עם מספר אחר במחשב (${few(moved)})`);
    if (taken.length) out.push(`${taken.length} מספרים שבמחשב שייכים בוואן דרייב לסטודנט אחר (${few(taken)})`);
    return out;
  }
  // upload בלי הקבצים של מטלות שהטבלה שלהן לא מתאימה. problems: {תיקיית מטלה (יחסית לקורס): [בעיות]}
  function withoutConflicts(upload, problems) {
    const bad = Object.keys(problems).filter((dir) => problems[dir].length);
    return upload.filter((f) => !bad.some((dir) => f.path === dir || f.path.startsWith(dir + "/")));
  }

  if (typeof window === "undefined") {
    module.exports = { plan, plan2, busyRemote, SKIP, keyProblems, withoutConflicts, csvRows }; return;
  }
  window.__ecsPlan = plan;  // לבדיקות
  window.__ecsPlan2 = plan2;
  window.__ecsKeyProblems = keyProblems;
  window.__ecsWithoutConflicts = withoutConflicts;

  // ---------- SharePoint ----------
  const q = (s) => encodeURIComponent(s.replace(/'/g, "''"));
  let digest = null, digestAt = 0;
  async function getDigest() {
    if (!digest || Date.now() - digestAt > 20 * 60 * 1000) {
      const r = await fetch(SITE + "/_api/contextinfo", { method: "POST", headers: { Accept: "application/json;odata=nometadata" } });
      digest = (await r.json()).FormDigestValue; digestAt = Date.now();
    }
    return digest;
  }
  async function api(url, opts = {}) {
    const headers = { Accept: "application/json;odata=nometadata", ...(opts.headers || {}) };
    if (opts.method === "POST") headers["X-RequestDigest"] = await getDigest();
    const r = await fetch(SITE + "/_api/web/" + url, { ...opts, headers });
    if (!r.ok) throw new Error(`${r.status} ${url.slice(0, 80)}`);
    return r.status === 204 ? null : r.json();
  }
  // כל הקבצים מתחת לתיקייה בוואן דרייב: {נתיב יחסי: {size, mtime}}. תיקייה שעוד לא קיימת: ריק.
  // recursive=false: רק הקבצים שבתיקייה עצמה (לתיקייה הראשית, בלי לעבור על כל הקורסים)
  async function listRemote(base, recursive = true) {
    const out = {};
    async function walk(folder, rel) {
      let data;
      try {
        data = await api(`GetFolderByServerRelativeUrl('${q(folder)}')?$expand=Files,Folders&$select=Name,Files/Name,Files/Length,Files/TimeLastModified,Folders/Name`);
      } catch (e) {
        if (String(e.message).startsWith("404")) return;
        throw e;
      }
      for (const f of data.Files || []) out[rel + f.Name] = { size: Number(f.Length), mtime: Date.parse(f.TimeLastModified) };
      if (recursive) for (const d of data.Folders || []) if (d.Name !== "Forms") await walk(folder + "/" + d.Name, rel + d.Name + "/");
    }
    await walk(base, "");
    return out;
  }
  const made = new Set();
  async function ensureFolder(path) {
    // יוצר את התיקייה ואת כל ההורים שלה, מתחת ל-ROOT. תיקייה שכבר קיימת: SharePoint מחזיר הצלחה.
    // ROOT עצמה כבר קיימת, ולכן קובץ בתיקייה הראשית לא יוצר כלום
    const parts = path.slice(ROOT.length + 1).split("/").filter(Boolean);
    let cur = ROOT;
    for (const p of parts) {
      cur += "/" + p;
      if (made.has(cur)) continue;
      await api(`folders/add('${q(cur)}')`, { method: "POST" });
      made.add(cur);
    }
  }
  async function uploadFile(base, f) {
    const full = base + "/" + f.path;
    const folder = full.slice(0, full.lastIndexOf("/"));
    const name = full.slice(full.lastIndexOf("/") + 1);
    await ensureFolder(folder);
    await api(`GetFolderByServerRelativeUrl('${q(folder)}')/Files/add(url='${q(name)}',overwrite=true)`,
      { method: "POST", body: await localBytes(f) });
  }

  // ---------- המחשב ----------
  // הקובץ מהמחשב: מהתיקייה שנבחרה, או מהשרת המקומי
  async function localBytes(f) {
    if (f.file) return f.file.arrayBuffer();
    const r = await fetch(LOCAL + `file?course=${encodeURIComponent(f.course)}&path=${encodeURIComponent(f.path)}`);
    if (!r.ok) throw new Error(`${r.status} local ${f.path}`);
    return r.arrayBuffer();
  }
  // לכל מטלה שהטבלה שלה בוואן דרייב שונה מזו שבמחשב (גודל או זמן): {תיקיית המטלה: [מה לא מתאים]}
  async function keyCheck(base, local, remote) {
    const out = {};
    for (const f of local) {
      if (!(f.path === KEY_NAME || f.path.endsWith("/" + KEY_NAME))) continue;
      const r = remote[f.path];
      if (!r || (r.size === f.size && Math.abs(r.mtime - f.mtime) <= CLOCK_SLACK_MS)) continue;
      const dir = f.path.slice(0, Math.max(0, f.path.length - KEY_NAME.length - 1));
      const there = await fetch(SITE + `/_api/web/GetFileByServerRelativeUrl('${q(base + "/" + f.path)}')/$value`);
      if (!there.ok) { out[dir] = [`אי אפשר לקרוא את טבלת המפתח שבוואן דרייב (${there.status})`]; continue; }
      out[dir] = keyProblems(new TextDecoder().decode(await localBytes(f)), await there.text());
    }
    return out;
  }
  const keyReport = (problems) => Object.entries(problems).filter(([, p]) => p.length)
    .map(([dir, p]) => `${dir || "התיקייה"}: לא הועלתה. טבלת המפתח במחשב הזה לא מתאימה לזו שבוואן דרייב (מחשב אחר משך את ` +
      `המטלה): ${p.join("; ")}. צריך לאחד את הטבלאות לפני שמעלים, אחרת סטודנטים היו נעלמים או מקבלים מספר של מישהו אחר.`);

  async function localJson(what) {
    const r = await fetch(LOCAL + what);
    if (!r.ok) throw new Error(`${r.status} local ${what}`);
    return r.json();
  }

  // ---------- הורדה: מהוואן דרייב למחשב ----------
  async function listFolders(folder) {
    const data = await api(`GetFolderByServerRelativeUrl('${q(folder)}')/Folders?$select=Name`);
    return (data.value || []).map((d) => d.Name).filter((n) => n !== "Forms");
  }
  async function remoteText(base, path) {
    const r = await fetch(SITE + `/_api/web/GetFileByServerRelativeUrl('${q(base + "/" + path)}')/$value`);
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r;
  }
  const localPost = (what, body) => fetch(LOCAL + what, {
    method: "POST", headers: { "X-Assignment-Checker": "1", "Content-Type": "application/octet-stream" }, body });
  // טבלת מפתח שמורידים חייבת להכיל כל סטודנט שבטבלה שבמחשב, עם אותו מספר (ההפך מההעלאה). אחרת לא מורידים כלום מהמטלה
  async function downloadKeyCheck(base, c, download, local) {
    const out = {};
    const byPath = new Map(local.map((f) => [f.path, f]));
    for (const f of download) {
      if (!(f.path === KEY_NAME || f.path.endsWith("/" + KEY_NAME)) || f.expect === "none") continue;
      const dir = f.path.slice(0, Math.max(0, f.path.length - KEY_NAME.length - 1));
      try {
        const there = await (await remoteText(base, f.path)).text();
        out[dir] = keyProblems(there, new TextDecoder().decode(await localBytes({ ...byPath.get(f.path), course: c })));
      } catch (e) { out[dir] = [`אי אפשר להשוות את טבלאות המפתח (${e.message})`]; }
    }
    return out;
  }
  const keyDownReport = (problems) => Object.entries(problems).filter(([, p]) => p.length)
    .map(([dir, p]) => `${dir || "התיקייה"}: לא הורדה. טבלת המפתח בוואן דרייב לא מכילה את כל מה שבמחשב הזה: ${p.join("; ")}.` +
      " צריך לאחד את הטבלאות, אחרת סטודנטים היו נעלמים או מקבלים מספר של מישהו אחר.");
  // מוריד רשימה, PARALLEL בכל פעם. השרת המקומי מסרב (409) לקובץ שהשתנה במחשב מאז ההשוואה: לא מנסים אותו שוב
  async function runDownload(base, c, todo, progress) {
    const queue = [...todo], done = [], failed = [], refused = [];
    async function one(f) {
      const body = await (await remoteText(base, f.path)).arrayBuffer();
      if (body.byteLength !== f.size) throw new Error("השתנה בוואן דרייב בזמן ההורדה");
      const r = await localPost(`put?course=${encodeURIComponent(c)}&path=${encodeURIComponent(f.path)}` +
        `&mtime=${f.mtime}&expect=${encodeURIComponent(f.expect)}`, body);
      const j = await r.json().catch(() => ({}));
      if (r.status === 409) return refused.push([f.path, j.error || "נדחה"]);
      if (!r.ok) throw new Error(j.error || `${r.status} local put`);
      done.push({ path: f.path, local: [j.size, j.mtime], remote: [f.size, f.mtime] });
    }
    async function worker() {
      while (queue.length) {
        const f = queue.shift();
        try { await one(f); } catch (e) {
          try { await one(f); } catch (e2) { failed.push([f.path, String(e2.message)]); }
        }
        progress(done.length + failed.length + refused.length, todo.length);
      }
    }
    await Promise.all(Array.from({ length: PARALLEL }, worker));
    return { done, failed, refused };
  }
  async function recordState(c, entries) {
    if (!Object.keys(entries).length) return;
    const r = await localPost(`state?course=${encodeURIComponent(c)}`, JSON.stringify(entries));
    if (!r.ok) throw new Error(`${r.status} local state`);
  }

  // מעלה רשימה, PARALLEL בכל פעם, ובסוף בודק שהכל בוואן דרייב באותו גודל. מחזיר מה שנכשל ומה שלא הגיע
  async function runUpload(base, todo, progress, recursive = true) {
    const queue = [...todo], failed = [];
    let done = 0;
    async function worker() {
      while (queue.length) {
        const f = queue.shift();
        try { await uploadFile(base, f); } catch (e) {
          try { await uploadFile(base, f); } catch (e2) { failed.push([f.path, String(e2.message)]); }
        }
        progress(++done, todo.length, failed.length);
      }
    }
    await Promise.all(Array.from({ length: PARALLEL }, worker));
    const remote = await listRemote(base, recursive);
    return { failed, remote, missing: todo.filter((f) => !remote[f.path] || remote[f.path].size !== f.size).map((f) => f.path) };
  }

  // ---------- החלון בדף ----------
  document.getElementById("ecs-sync")?.remove();
  const box = document.createElement("div");
  box.id = "ecs-sync";
  box.dir = "rtl";
  box.style.cssText = "position:fixed;bottom:16px;left:16px;z-index:99999;width:380px;max-height:70vh;overflow:auto;" +
    "background:#fff;color:#222;border:2px solid #0f6cbd;border-radius:10px;padding:14px;font:14px Segoe UI,Arial,sans-serif;box-shadow:0 6px 24px #0003";
  box.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center">
      <b style="font-size:16px">סנכרון עם הוואן דרייב: רק מה שהשתנה</b>
      <button id="ecs-close" style="border:0;background:none;font-size:18px;cursor:pointer">×</button>
    </div>
    <p style="margin:8px 0">"סנכרון מהמחשב" מעלה מ-start.bat (ב-Mac: start.sh). "בשני הכיוונים" גם מוריד למחשב את מה שחדש בוואן דרייב. אם השרת לא רץ, בוחרים את תיקיית הקורס ביד.</p>
    <input id="ecs-pick" type="file" webkitdirectory multiple style="display:none">
    <button id="ecs-auto" style="background:#0f6cbd;color:#fff;border:0;border-radius:6px;padding:8px 14px;cursor:pointer">סנכרון מהמחשב</button>
    <button id="ecs-both" style="background:#0f6cbd;color:#fff;border:0;border-radius:6px;padding:8px 14px;cursor:pointer">בשני הכיוונים</button>
    <button id="ecs-choose" style="background:#fff;color:#0f6cbd;border:1px solid #0f6cbd;border-radius:6px;padding:8px 14px;cursor:pointer">בחירת תיקיית קורס</button>
    <div id="ecs-status" style="margin-top:10px;white-space:pre-line"></div>
    <button id="ecs-go" style="display:none;margin-top:10px;background:#107c10;color:#fff;border:0;border-radius:6px;padding:8px 14px;cursor:pointer"></button>`;
  document.body.appendChild(box);
  const $ = (id) => box.querySelector("#" + id);
  const say = (t) => { $("ecs-status").textContent = t; };
  const state = window.__ecsSync = { stage: "ready" };
  $("ecs-close").onclick = () => box.remove();
  $("ecs-choose").onclick = () => $("ecs-pick").click();

  // ---------- ידני: תיקייה שנבחרה ----------
  let todo = [], base = "";
  $("ecs-pick").onchange = async () => {
    const files = [...$("ecs-pick").files];
    if (!files.length) return;
    const course = files[0].webkitRelativePath.split("/")[0];
    base = ROOT + "/" + course;
    const local = files.map((file) => ({ path: file.webkitRelativePath.slice(course.length + 1), size: file.size, mtime: file.lastModified, file }));
    Object.assign(state, { stage: "comparing", course, local: local.length });
    say(`משווה ${local.length} קבצים ב-"${course}" לוואן דרייב...`);
    try {
      const remote = await listRemote(base);
      const p = plan(local, remote);
      const kp = await keyCheck(base, local, remote);
      const conflicts = keyReport(kp);
      todo = withoutConflicts(p.upload, kp);
      state.keyConflicts = conflicts;
      const bytes = todo.reduce((s, f) => s + f.size, 0);
      const news = todo.filter((f) => f.why === "new").length;
      Object.assign(state, { stage: "planned", upload: todo.map((f) => [f.path, f.why]), same: p.same.length, remoteNewer: p.remoteNewer, archived: p.archived.length });
      say(`תיקייה: ${course}\nחדשים: ${news}\nהשתנו: ${todo.length - news}\nזהים, לא נוגעים: ${p.same.length}\n` +
        (p.remoteNewer.length ? `חדשים יותר בוואן דרייב, לא נדרסים: ${p.remoteNewer.length}\n  ${p.remoteNewer.slice(0, 8).join("\n  ")}\n` : "") +
        (p.archived.length ? `${ARCHIVED_NOTE(p.archived.length)}\n` : "") +
        (conflicts.length ? conflicts.join("\n") + "\n" : "") +
        `סה"כ להעלאה: ${(bytes / 1e6).toFixed(1)} MB`);
      if (todo.length) { $("ecs-go").textContent = `העלאה של ${todo.length} קבצים`; $("ecs-go").style.display = ""; }
      else say($("ecs-status").textContent + "\n\nהכל כבר בוואן דרייב. אין מה להעלות.");
    } catch (e) {
      state.stage = "error"; state.error = String(e.message); say("שגיאה: " + e.message);
    }
  };
  $("ecs-go").onclick = async () => {
    $("ecs-go").style.display = "none";
    $("ecs-choose").disabled = true;
    Object.assign(state, { stage: "uploading", done: 0, total: todo.length });
    const r = await runUpload(base, todo, (done, total, failed) => {
      state.done = done;
      say(`מעלה... ${done} מתוך ${total}` + (failed ? `\nנכשלו: ${failed}` : "") + "\nלא לסגור את הלשונית ולא לעבור דף.");
    });
    Object.assign(state, { stage: "done", failed: r.failed, missing: r.missing });
    say(r.missing.length
      ? `הסתיים, אבל ${r.missing.length} קבצים לא הגיעו כמו שצריך:\n  ${r.missing.slice(0, 10).join("\n  ")}\nאפשר לבחור את התיקייה שוב: יעלו רק החסרים.`
      : `הסתיים: ${todo.length} קבצים הועלו ונבדקו, הכל הגיע.`);
    $("ecs-choose").disabled = false;
  };

  // ---------- אוטומטי: כל הקורסים, מהשרת המקומי ----------
  // dryRun: רק משווה ומדווח מה היה עולה ויורד, בלי לגעת בכלום.
  // down: גם מוריד מהוואן דרייב את מה שחדש שם (ב-Mac, ובכל מחשב שלא מסנכרן את התיקייה באפליקציית OneDrive).
  // up: false = רק מוריד. ברירת המחדל כמו קודם: רק מעלה
  async function syncAll({ dryRun = false, down = false, up = true } = {}) {
    const report = [];
    Object.assign(state, { stage: dryRun ? "dry run" : "auto", report });
    let courses;
    try { courses = (await localJson("courses")).courses; } catch (e) {
      Object.assign(state, { stage: "error", error: "השרת המקומי לא עונה. צריך להפעיל את start.bat (ב-Mac: start.sh). (" + e.message + ")" });
      say(state.error); return state;
    }
    if (down) {
      try { courses = [...new Set([...courses, ...await listFolders(ROOT)])].sort(); } catch (e) {
        Object.assign(state, { stage: "error", error: "אי אפשר לקרוא את התיקיות בוואן דרייב: " + e.message });
        say(state.error); return state;
      }
    }
    const ms = (list) => (list.reduce((s, f) => s + f.size, 0) / 1e6).toFixed(1);
    // "" הוא התיקייה הראשית: רק הקבצים שבה (README, הפרוטוקול, "Pull only on this computer.txt"), בלי הקורסים
    for (const c of ["", ...courses]) {
      const cbase = c ? ROOT + "/" + c : ROOT;
      const label = c || "התיקייה הראשית";
      say(`${label}: משווה...`);
      const compare = async () => {
        const l = await localJson(`list?course=${encodeURIComponent(c)}`);
        const local = l.files.map((f) => ({ ...f, course: c }));
        const remote = await listRemote(cbase, c !== "");
        const canDown = down && l.writable !== false;
        return { l, local, remote, p: plan2(local, remote, l.state || {}, { up, down: canDown }) };
      };
      let { l, local, remote, p } = await compare();
      const row = { course: label, local: local.length, same: p.same.length, conflict: p.conflict,
        goneRemote: p.goneRemote.length, goneLocal: p.goneLocal.length, busy: p.busy.length, archived: p.archived.length,
        remoteNewer: p.remoteNewer, keyConflicts: [], new: 0, changed: 0, downNew: 0, downChanged: 0 };
      if (down && l.writable === false) row.notWritable = l.notWritable;
      report.push(row);
      // קודם מורידים: טבלת מפתח חדשה יותר מהוואן דרייב צריכה להגיע לפני שמשווים את הטבלה להעלאה
      if (p.download.length) {
        const kd = await downloadKeyCheck(cbase, c, p.download, local);
        p.download = withoutConflicts(p.download, kd);
        row.keyConflicts.push(...keyDownReport(kd));
        row.downNew = p.download.filter((f) => f.why === "new").length;
        row.downChanged = p.download.length - row.downNew;
        row.downMB = ms(p.download);
        if (dryRun) row.wouldDownload = p.download.map((f) => [f.path, f.why]);
        else {
          const r = await runDownload(cbase, c, p.download, (done, total) => say(`${label}: מוריד ${done} מתוך ${total}...\nלא לסגור את הלשונית ולא לעבור דף.`));
          await recordState(c, Object.fromEntries(r.done.map((d) => [d.path, { local: d.local, remote: d.remote }])));
          Object.assign(row, { downFailed: r.failed, refused: r.refused });
          if (r.done.length) ({ l, local, remote, p } = await compare());
        }
      }
      if (!dryRun) await recordState(c, p.record);
      if (up) {
        const kp = await keyCheck(cbase, local, remote);
        p.upload = withoutConflicts(p.upload, kp);
        row.keyConflicts.push(...keyReport(kp));
        row.new = p.upload.filter((f) => f.why === "new").length;
        row.changed = p.upload.length - row.new;
        if (dryRun) row.wouldUpload = p.upload.map((f) => [f.path, f.why]);
        else if (p.upload.length) {
          const r = await runUpload(cbase, p.upload, (done, total) => say(`${label}: מעלה ${done} מתוך ${total}...\nלא לסגור את הלשונית ולא לעבור דף.`), c !== "");
          Object.assign(row, { failed: r.failed, missing: r.missing });
          // מה שהגיע נרשם כמסונכרן, עם הזמן שלו בוואן דרייב אחרי ההעלאה (אחרת הוא היה נראה "חדש יותר שם" ויורד בחזרה)
          if (r.remote) {
            const bad = new Set([...r.missing, ...r.failed.map(([path]) => path)]);
            await recordState(c, Object.fromEntries(p.upload.filter((f) => !bad.has(f.path) && r.remote[f.path])
              .map((f) => [f.path, { local: [f.size, f.mtime], remote: [r.remote[f.path].size, r.remote[f.path].mtime] }])));
          }
        }
      }
    }
    state.stage = "done";
    say(report.map((r) => `${r.course}: ` + [
      up ? `${r.new} חדשים ו-${r.changed} שהשתנו עלו` : "",
      down ? `${r.downNew} חדשים ו-${r.downChanged} שהשתנו ירדו` + (r.downMB ? ` (${r.downMB} MB)` : "") : "",
      `${r.same} זהים`].filter(Boolean).join(", ") +
      (r.remoteNewer.length ? `, ${r.remoteNewer.length} חדשים יותר בוואן דרייב (לא נדרסו)` : "") +
      (r.notWritable ? `\n  ${r.notWritable}` : "") +
      (r.conflict.length ? `\n  ${r.conflict.length} קבצים השתנו גם במחשב וגם בוואן דרייב, ולא נגעתי באף צד: ${r.conflict.slice(0, 8).join(", ")}` : "") +
      (r.busy ? `\n  ${r.busy} קבצים לא ירדו: במטלה שלהם רצה עכשיו משיכה, בדיקה או העלאה במחשב אחר` : "") +
      (r.goneRemote ? `\n  ${r.goneRemote} קבצים נמחקו או הועברו בוואן דרייב: לא הועלו שוב` : "") +
      (r.goneLocal ? `\n  ${r.goneLocal} קבצים נמחקו או הועברו במחשב: לא הורדו שוב` : "") +
      (r.archived ? `\n  ${ARCHIVED_NOTE(r.archived)}` : "") +
      (r.missing && r.missing.length ? `\n  לא הגיעו לוואן דרייב: ${r.missing.length}` : "") +
      (r.downFailed && r.downFailed.length ? `\n  לא ירדו: ${r.downFailed.length}` : "") +
      (r.refused && r.refused.length ? `\n  ${r.refused.map(([, why]) => why).slice(0, 5).join("\n  ")}` : "") +
      (r.keyConflicts.length ? "\n  " + r.keyConflicts.join("\n  ") : "")).join("\n") + "\n\nהסתיים.");
    return state;
  }
  window.__ecsSyncAll = syncAll;
  $("ecs-auto").onclick = () => syncAll();
  $("ecs-both").onclick = () => syncAll({ down: true });
})();
