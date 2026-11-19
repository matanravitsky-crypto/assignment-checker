// סנכרון עם הוואן דרייב של המרצה, בשני הכיוונים, בלי לגרור ובלי "Replace" על כל התיקייה.
//
// מריצים את הקובץ בלשונית של הוואן דרייב (bgu365-my.sharepoint.com): בקונסול של כרום (F12), או Claude עם javascript_tool:
//   eval(await (await fetch("http://127.0.0.1:8765/api/sync/script.js")).text()); window.__ecsLive.start()
// בפינת הדף נפתח חלון קטן, ויש בו שלוש דרכים:
//   חי: window.__ecsLive.start() (או "סנכרון חי" בחלון) מסנכרן כל כמה דקות, כל עוד הלשונית פתוחה, ומדווח
//     לשרת המקומי (POST /api/sync/status), כך שהאתר מראה "מחובר בלייב, סונכרן לפני N דקות".
//   פעם אחת: window.__ecsSyncAll() (או "סנכרון עכשיו"). dryRun: true רק משווה ומדווח, בלי לגעת בכלום.
//   ידני, בלי שרת מקומי: "בחירת תיקיית קורס", בוחרים את התיקייה במחשב, ואז "העלאה" (העלאה בלבד).
// הקבצים עוברים מחשב ↔ דפדפן ↔ וואן דרייב דרך השרת המקומי (start.bat, http://127.0.0.1:8765/api/sync/), לא דרך Claude.
// בפעם הראשונה כרום שואל אם לאפשר לאתר לגשת לרשת המקומית: לוחצים "אפשר" (פעם אחת).
//
// ההשוואה (plan) היא בין שלושה: הקובץ במחשב, הקובץ בוואן דרייב, ומה שני הצדדים היו בסנכרון הקודם (snapshot,
// שהשרת המקומי שומר במחשב). מה שהשתנה רק במחשב עולה; מה שהשתנה רק בענן יורד; מה שהיה בענן בסנכרון הקודם
// ונעלם משם (הועבר או נמחק בענן) לא נמחק במחשב אלא עובר ל-"Removed from OneDrive/<תאריך>/" בתיקיית המטלה;
// מה שהשתנה בשני הצדדים לא נדרס באף כיוון, ומופיע בדוח ובאתר לבדיקה ידנית (בחלון: "קח מהענן" / "קח מהמחשב").
// בלי סנכרון קודם (הפעם הראשונה): גודל שונה והצד החדש יותר מנצח; גודל זהה ולא חדש יותר במחשב: זהים. לא מוחקים
// שום דבר בוואן דרייב, אף פעם. מנעולים, קבצים זמניים, ZIP, Key history ו-Removed from OneDrive לא נוגעים בהם.
// מטלה שבדיקה, משיכה או העלאה רצות בה עכשיו (מנעול "... in progress.txt" טרי, במחשב או בענן) מחכה לסיבוב הבא.
//
// התוצאה נשמרת גם ב-window.__ecsSync, כדי ש-Claude יוכל לקרוא אותה (מספרים ושמות קבצים ממוספרים בלבד).

(() => {
  const SITE = "/personal/mein_bgu_ac_il";
  const ROOT = SITE + "/Documents/YallaLinearit/Exercise Checking System";
  // השרת המקומי (start.bat). window.__ecsLocal מחליף אותו, למשל שרת בדיקה על פורט אחר
  const LOCAL = window.__ecsLocal || "http://127.0.0.1:8765/api/sync/";
  const PARALLEL = 3;
  // קבצים שלא מסנכרנים אף פעם, בשום כיוון: קבצים זמניים של Windows ו-Office, קבצים חצי כתובים, מנעולים, אף פעם לא ZIP
  // (קובצי ה-ZIP של מודל נשארים במחשב שהוריד), ומה שהענן הסיר (הארכיון של המחשב). כמו dashboard/sync.py
  const SKIP = /(^|\/)(desktop\.ini|thumbs\.db|~\$[^/]*|[^/]*\.tmp|[^/]* in progress\.txt|[^/]*\.zip|Removed from OneDrive\/.*)$/i;
  // לא כותבים ולא מזיזים במחשב (רק מעלים): ההיסטוריה של טבלת המפתח
  const PROTECTED = /(^|\/)Key history(\/|$)/i;
  const LOCK = /^([^/]+)\/[^/]* in progress\.txt$/i;
  const LOCK_MINUTES = 30;
  // שעון המחשב ושעון השרת לא מסונכרנים בדיוק: הפרש קטן מזה לא נחשב "השתנה"
  const CLOCK_SLACK_MS = 2 * 60 * 1000;
  // בדיקות שהוצאו מהספירה עוברות בוואן דרייב ל-"<מטלה>/Old test grading/", עם README.txt שנכתב ברגע ההעברה
  // (2026-11-03: בדיקות הניסיון של 23/10-30/10). עותק מקומי שעוד מחזיק אותן במקומן הקודם לא מחזיר אותן:
  // קובץ של בדיקה (עבודה מסומנת, הערות, מי לקח מה, קובץ ציונים) שחסר בוואן דרייב ונכתב לפני ההעברה לא עולה.
  // מה שנבדק אחרי ההעברה עולה כרגיל. (עם סנכרון קודם שראה את הקובץ בענן, הוא עובר ל-Removed from OneDrive)
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
  // מטלות שמנעול טרי בהן בוואן דרייב (מחשב אחר מושך, בודק או מעלה בהן עכשיו)
  function remoteBusy(remote, now = Date.now()) {
    const out = new Set();
    for (const [path, r] of Object.entries(remote)) {
      const m = path.match(LOCK);
      if (m && now - r.mtime < LOCK_MINUTES * 60 * 1000) out.add(m[1]);
    }
    return [...out];
  }

  // ---------- ההשוואה (בלי רשת, כדי שאפשר לבדוק אותה לבד) ----------
  // local: [{path, size, mtime}] (path יחסי לתיקיית הקורס, mtime במילישניות)
  // remote: {path: {size, mtime}}
  // snap: {path: {l, ls, r, rs}}: הזמן והגודל של הקובץ במחשב (l, ls) ובענן (r, rs) בסנכרון הקודם. ריק: הפעם הראשונה
  // busy: תיקיות מטלות שלא נוגעים בהן בסיבוב הזה
  function plan(local, remote, snap = {}, busy = []) {
    const out = { upload: [], download: [], remove: [], conflict: [], same: [], skipped: [], archived: [], held: [] };
    snap = snap || {};
    const archived = archivedAt(remote);
    const localBy = {};
    for (const f of local) localBy[f.path] = f;
    const isBusy = (p) => busy.some((a) => p === a || p.startsWith(a + "/"));
    const changed = (now, size, mtime) => size === undefined || now.size !== size || Math.abs(now.mtime - mtime) > CLOCK_SLACK_MS;
    for (const path of [...new Set([...Object.keys(localBy), ...Object.keys(remote)])].sort()) {
      if (SKIP.test(path)) { out.skipped.push(path); continue; }
      const L = localBy[path], R = remote[path], S = snap[path];
      if (isBusy(path)) { out.held.push(path); continue; }
      const canWrite = !PROTECTED.test(path);
      if (L && !R) {
        // היה בענן בסנכרון הקודם והמחשב לא נגע בו מאז: הועבר או נמחק בענן
        if (S && S.r !== undefined && !changed(L, S.ls, S.l)) {
          if (canWrite) out.remove.push({ ...L });
          else out.skipped.push(path);
          continue;
        }
        const slash = path.indexOf("/"), assignment = path.slice(0, slash);
        if (slash > 0 && archived[assignment] !== undefined && GRADING_OUTPUT.test(path.slice(slash + 1))
            && L.mtime <= archived[assignment] + CLOCK_SLACK_MS) {
          out.archived.push(path);
          continue;
        }
        out.upload.push({ ...L, why: "new" });
        continue;
      }
      if (!L && R) {
        if (canWrite) out.download.push({ path, size: R.size, mtime: R.mtime, why: "new", expect: null });
        else out.skipped.push(path);
        continue;
      }
      // אותו גודל ואותו זמן בשני הצדדים: זהים, מה שלא היה בסנכרון הקודם (כך התנגשות שאדם פתר נגמרת)
      if (L.size === R.size && Math.abs(L.mtime - R.mtime) <= CLOCK_SLACK_MS) { out.same.push(path); continue; }
      if (S) {
        const lc = changed(L, S.ls, S.l), rc = changed(R, S.rs, S.r);
        if (!lc && !rc) out.same.push(path);
        else if (lc && !rc) out.upload.push({ ...L, why: "changed" });
        else if (!lc && rc) {
          if (canWrite) out.download.push({ path, size: R.size, mtime: R.mtime, why: "changed", expect: L.mtime });
          else out.skipped.push(path);
        } else out.conflict.push({ path, local: { size: L.size, mtime: L.mtime }, remote: { size: R.size, mtime: R.mtime }, why: "both" });
        continue;
      }
      // בלי סנכרון קודם: כמו פעם, ובנוסף מה שחדש יותר בענן יורד
      const localNewer = L.mtime > R.mtime + CLOCK_SLACK_MS, remoteNewer = R.mtime > L.mtime + CLOCK_SLACK_MS;
      if (L.size === R.size && !localNewer) out.same.push(path);
      else if (localNewer) out.upload.push({ ...L, why: "changed" });
      // keep: בלי סנכרון קודם אין לדעת אם הגרסה שבמחשב נערכה כאן, אז היא נשמרת קודם ב-Removed from OneDrive
      else if (remoteNewer && canWrite) out.download.push({ path, size: R.size, mtime: R.mtime, why: "changed", expect: L.mtime, keep: true });
      else if (remoteNewer) out.skipped.push(path);
      else out.conflict.push({ path, local: { size: L.size, mtime: L.mtime }, remote: { size: R.size, mtime: R.mtime }, why: "same time" });
    }
    return out;
  }

  // ---------- טבלת המפתח בין מחשבים ----------
  // כל אחד בצוות יכול למשוך, כל אחד למחשב שלו. אם שני מחשבים משכו את אותה מטלה, לכל אחד טבלת מפתח משלו, ומי שמעלה
  // אחרון היה דורס את השנייה: סטודנטים נעלמים מהטבלה המשותפת, או ששני סטודנטים מקבלים אותו מספר, וקובץ 0481.pdf של
  // סטודנט אחד דורס את 0481.pdf של אחר. לכן לפני שמעלים מטלה שהטבלה שלה בוואן דרייב שונה מזו שבמחשב, משווים את התוכן:
  // הטבלה במחשב חייבת להכיל כל סטודנט שבוואן דרייב, עם אותו מספר, בלי מספר של מישהו אחר. אחרת לא מעלים כלום מהמטלה
  // הזו (לא את הטבלה ולא את ההגשות), ומדווחים. טבלה במחשב שרק מוסיפה סטודנטים חדשים עולה כרגיל.
  // באותו אופן לכיוון השני: טבלה שיורדת מהענן חייבת להכיל כל סטודנט שבמחשב, עם אותו מספר, אחרת היא התנגשות.
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
  // מה לא מתאים בין הטבלה שתדרוס (localCsv) לזו שתידרס (remoteCsv), במספרים בלבד. ריק: אפשר
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

  if (typeof window === "undefined") { module.exports = { plan, SKIP, keyProblems, withoutConflicts, csvRows, remoteBusy }; return; }
  window.__ecsPlan = plan;  // לבדיקות
  window.__ecsKeyProblems = keyProblems;
  window.__ecsWithoutConflicts = withoutConflicts;
  window.__ecsRemoteBusy = remoteBusy;
  window.__ecsLive?.stop?.(true);  // הסקריפט נטען שוב: הלולאה הקודמת נעצרת, שלא ירוצו שתיים

  // ---------- SharePoint ----------
  const q = (s) => encodeURIComponent(s.replace(/'/g, "''"));
  let digest = null, digestAt = 0;
  const loginError = (status) => Object.assign(new Error(`הוואן דרייב ענה ${status}: צריך להתחבר שוב לחשבון האוניברסיטה בלשונית הזו (לרענן את הדף).`), { needsLogin: true });
  async function getDigest() {
    if (!digest || Date.now() - digestAt > 20 * 60 * 1000) {
      const r = await fetch(SITE + "/_api/contextinfo", { method: "POST", headers: { Accept: "application/json;odata=nometadata" } });
      if (r.status === 401 || r.status === 403) throw loginError(r.status);
      let data;
      try { data = await r.json(); } catch { throw loginError(r.status); }
      digest = data.FormDigestValue; digestAt = Date.now();
    }
    return digest;
  }
  async function api(url, opts = {}) {
    const headers = { Accept: "application/json;odata=nometadata", ...(opts.headers || {}) };
    if (opts.method === "POST") headers["X-RequestDigest"] = await getDigest();
    const r = await fetch(SITE + "/_api/web/" + url, { ...opts, headers });
    if (r.status === 401 || r.status === 403) throw loginError(r.status);
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
  async function remoteBytes(base, path) {
    const r = await fetch(SITE + `/_api/web/GetFileByServerRelativeUrl('${q(base + "/" + path)}')/$value`);
    if (r.status === 401 || r.status === 403) throw loginError(r.status);
    if (!r.ok) throw new Error(`${r.status} onedrive ${path}`);
    return r.arrayBuffer();
  }

  // ---------- המחשב ----------
  const LOCAL_HEADERS = { "X-Assignment-Checker": "1" };
  // הקובץ מהמחשב: מהתיקייה שנבחרה, או מהשרת המקומי
  async function localBytes(f) {
    if (f.file) return f.file.arrayBuffer();
    const r = await fetch(LOCAL + `file?course=${encodeURIComponent(f.course)}&path=${encodeURIComponent(f.path)}`);
    if (!r.ok) throw new Error(`${r.status} local ${f.path}`);
    return r.arrayBuffer();
  }
  async function localJson(what) {
    const r = await fetch(LOCAL + what);
    if (!r.ok) throw new Error(`${r.status} local ${what}`);
    return r.json();
  }
  // POST לשרת המקומי. body: אובייקט (JSON) או bytes. מחזיר {status, data}; 409 = הקובץ במחשב השתנה בינתיים, 423 = מנעול
  async function localPost(what, body) {
    const raw = body instanceof ArrayBuffer || body instanceof Blob;
    const r = await fetch(LOCAL + what, { method: "POST", body: raw ? body : JSON.stringify(body),
      headers: { ...LOCAL_HEADERS, "Content-Type": raw ? "application/octet-stream" : "application/json" } });
    const data = await r.json().catch(() => ({}));
    if (!r.ok && r.status !== 409 && r.status !== 423) throw new Error(`${r.status} local ${what.split("?")[0]}: ${data.error || ""}`);
    return { status: r.status, data };
  }
  // לכל מטלה שהטבלה שלה בוואן דרייב שונה מזו שבמחשב (גודל או זמן): {תיקיית המטלה: [מה לא מתאים]}
  async function keyCheck(base, local, remote, snap = {}) {
    const out = {};
    for (const f of local) {
      if (!(f.path === KEY_NAME || f.path.endsWith("/" + KEY_NAME))) continue;
      const r = remote[f.path], s = snap[f.path];
      if (!r || (r.size === f.size && Math.abs(r.mtime - f.mtime) <= CLOCK_SLACK_MS)) continue;
      // שני הצדדים כמו בסנכרון הקודם (הטבלה עלתה אז, והזמן בענן הוא זמן ההעלאה): אין מה להשוות
      if (s && s.ls === f.size && Math.abs(s.l - f.mtime) <= CLOCK_SLACK_MS && s.rs === r.size && Math.abs(s.r - r.mtime) <= CLOCK_SLACK_MS) continue;
      const dir = f.path.slice(0, Math.max(0, f.path.length - KEY_NAME.length - 1));
      let there;
      try { there = new TextDecoder().decode(await remoteBytes(base, f.path)); } catch (e) {
        out[dir] = [`אי אפשר לקרוא את טבלת המפתח שבוואן דרייב (${e.message})`]; continue;
      }
      out[dir] = keyProblems(new TextDecoder().decode(await localBytes(f)), there);
    }
    return out;
  }
  const keyReport = (problems) => Object.entries(problems).filter(([, p]) => p.length)
    .map(([dir, p]) => `${dir || "התיקייה"}: לא סונכרנה (לא עלה ולא ירד כלום ממנה). טבלת המפתח במחשב הזה לא מתאימה לזו שבוואן דרייב ` +
      `(מחשב אחר משך את המטלה): ${p.join("; ")}. צריך לאחד את הטבלאות לפני שמסנכרנים, אחרת סטודנטים היו נעלמים או מקבלים מספר של מישהו אחר.`);

  // מעלה רשימה, PARALLEL בכל פעם, ובסוף בודק שהכל בוואן דרייב באותו גודל. מחזיר מה שנכשל, מה שלא הגיע, והרשימה החדשה
  async function runUpload(base, todo, progress, recursive = true) {
    const queue = [...todo], failed = [];
    let done = 0;
    async function worker() {
      while (queue.length) {
        const f = queue.shift();
        try { await uploadFile(base, f); } catch (e) {
          if (e.needsLogin) throw e;
          try { await uploadFile(base, f); } catch (e2) { if (e2.needsLogin) throw e2; failed.push([f.path, String(e2.message)]); }
        }
        progress(++done, todo.length, failed.length);
      }
    }
    await Promise.all(Array.from({ length: PARALLEL }, worker));
    const remote = await listRemote(base, recursive);
    return { failed, remote, missing: todo.filter((f) => !remote[f.path] || remote[f.path].size !== f.size).map((f) => f.path) };
  }
  // מוריד רשימה מהוואן דרייב למחשב דרך השרת המקומי. טבלת מפתח שיורדת על טבלה קיימת: רק אם היא מכילה את כל הסטודנטים
  // שבמחשב, עם אותם מספרים. מחזיר מה ירד (לסנכרון הבא), מה נכשל, ומה התנגש (השתנה במחשב בינתיים, או מנעול)
  async function runDownload(base, course, todo, progress, stamp) {
    const queue = [...todo], done = [], failed = [], conflict = [], held = [];
    let n = 0;
    async function worker() {
      while (queue.length) {
        const f = queue.shift();
        try {
          let bytes;
          try { bytes = await remoteBytes(base, f.path); } catch (e) {
            if (e.needsLogin) throw e;
            await new Promise((ok) => setTimeout(ok, 1500));  // רשת שנפלה לרגע: ניסיון שני
            bytes = await remoteBytes(base, f.path);
          }
          if (f.expect !== null && (f.path === KEY_NAME || f.path.endsWith("/" + KEY_NAME))) {
            const mine = await localBytes({ course, path: f.path });
            const p = keyProblems(new TextDecoder().decode(bytes), new TextDecoder().decode(mine));
            if (p.length) { conflict.push([f.path, `טבלת המפתח שבוואן דרייב לא מכילה את זו שבמחשב: ${p.join("; ")}`]); continue; }
          }
          let expect = f.expect;
          if (f.keep && expect !== null) {
            // הגרסה שבמחשב נשמרת קודם בארכיון (בסיבוב הראשון, בלי סנכרון קודם, אין לדעת אם נערכה כאן)
            const k = await localPost("remove", { course, path: f.path, expect, stamp });
            if (k.status === 409) { conflict.push([f.path, k.data.error || ""]); continue; }
            if (k.status === 423) { held.push(f.path); continue; }
            expect = null;
          }
          const r = await localPost(`put?course=${encodeURIComponent(course)}&path=${encodeURIComponent(f.path)}&mtime=${f.mtime}` +
            (expect !== null ? `&expect=${expect}` : ""), bytes);
          if (r.status === 409) conflict.push([f.path, r.data.error || ""]);
          else if (r.status === 423) held.push(f.path);
          else done.push({ ...f, mtime: r.data.mtime ?? f.mtime });
        } catch (e) {
          if (e.needsLogin) throw e;
          failed.push([f.path, String(e.message)]);
        } finally {
          progress(++n, todo.length, failed.length);
        }
      }
    }
    await Promise.all(Array.from({ length: PARALLEL }, worker));
    return { done, failed, conflict, held };
  }
  // מעביר במחשב את מה שנעלם מהוואן דרייב ל-"Removed from OneDrive/<stamp>/". כל הסיבוב באותה תיקיית תאריך
  async function runRemove(course, todo, stamp) {
    const done = [], failed = [], conflict = [], held = [];
    for (const f of todo) {
      try {
        const r = await localPost("remove", { course, path: f.path, expect: f.mtime, stamp });
        if (r.status === 409) conflict.push([f.path, r.data.error || ""]);
        else if (r.status === 423) held.push(f.path);
        else done.push(f.path);
      } catch (e) { failed.push([f.path, String(e.message)]); }
    }
    return { done, failed, conflict, held };
  }
  const stampNow = () => {
    const d = new Date(), p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}`;
  };

  // ---------- החלון בדף ----------
  document.getElementById("ecs-sync")?.remove();
  const box = document.createElement("div");
  box.id = "ecs-sync";
  box.dir = "rtl";
  box.style.cssText = "position:fixed;bottom:16px;left:16px;z-index:99999;width:400px;max-height:70vh;overflow:auto;" +
    "background:#fff;color:#222;border:2px solid #0f6cbd;border-radius:10px;padding:14px;font:14px Segoe UI,Arial,sans-serif;box-shadow:0 6px 24px #0003";
  const BTN = "border:0;border-radius:6px;padding:8px 14px;cursor:pointer;margin:2px";
  box.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center">
      <b style="font-size:16px">בודק חכם ↔ וואן דרייב: רק מה שהשתנה</b>
      <button id="ecs-close" style="border:0;background:none;font-size:18px;cursor:pointer">×</button>
    </div>
    <p style="margin:8px 0">הסנכרון החי מעלה ומוריד כל כמה דקות, כל עוד הלשונית פתוחה. "סנכרון עכשיו" עושה סיבוב אחד. בלי start.bat בוחרים את תיקיית הקורס ביד (העלאה בלבד).</p>
    <input id="ecs-pick" type="file" webkitdirectory multiple style="display:none">
    <button id="ecs-live" style="${BTN};background:#107c10;color:#fff">סנכרון חי: הפעל</button>
    <button id="ecs-auto" style="${BTN};background:#0f6cbd;color:#fff">סנכרון עכשיו</button>
    <button id="ecs-choose" style="${BTN};background:#fff;color:#0f6cbd;border:1px solid #0f6cbd">בחירת תיקיית קורס</button>
    <div id="ecs-live-status" style="margin-top:8px;color:#555"></div>
    <div id="ecs-status" style="margin-top:10px;white-space:pre-line"></div>
    <div id="ecs-conflicts" style="margin-top:8px"></div>
    <button id="ecs-go" style="display:none;margin-top:10px;${BTN};background:#107c10;color:#fff"></button>`;
  document.body.appendChild(box);
  const $ = (id) => box.querySelector("#" + id);
  const say = (t) => { $("ecs-status").textContent = t; };
  const state = window.__ecsSync = { stage: "ready" };
  $("ecs-close").onclick = () => box.remove();
  $("ecs-choose").onclick = () => $("ecs-pick").click();

  // ---------- ידני: תיקייה שנבחרה (העלאה בלבד: בלי שרת מקומי אין לאן להוריד) ----------
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
      const remoteNewer = p.download.filter((f) => f.why === "changed").map((f) => f.path);
      Object.assign(state, { stage: "planned", upload: todo.map((f) => [f.path, f.why]), same: p.same.length, remoteNewer, archived: p.archived.length });
      say(`תיקייה: ${course}\nחדשים: ${news}\nהשתנו: ${todo.length - news}\nזהים, לא נוגעים: ${p.same.length}\n` +
        (remoteNewer.length ? `חדשים יותר בוואן דרייב, לא נדרסים: ${remoteNewer.length}\n  ${remoteNewer.slice(0, 8).join("\n  ")}\n` : "") +
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

  // ---------- שני הכיוונים: כל הקורסים, דרך השרת המקומי ----------
  // dryRun: רק משווה ומדווח מה היה קורה, בלי לגעת בכלום (גם לא בסנכרון הקודם שנשמר)
  let running = false;
  async function syncAll({ dryRun = false } = {}) {
    if (running) return state;
    running = true;
    const report = [];
    Object.assign(state, { stage: dryRun ? "dry run" : "sync", report, error: null, needsLogin: false, startedAt: new Date().toISOString() });
    try {
      let courses;
      try { courses = (await localJson("courses")).courses; } catch (e) {
        throw Object.assign(new Error("השרת המקומי לא עונה. צריך להפעיל את start.bat. (" + e.message + ")"), { local: true });
      }
      const stamp = stampNow();
      // "" הוא התיקייה הראשית: רק הקבצים שבה (README, הפרוטוקול, "Pull only on this computer.txt"), בלי הקורסים
      for (const c of ["", ...courses]) {
        const cbase = c ? ROOT + "/" + c : ROOT;
        const label = c || "התיקייה הראשית";
        say(`${label}: משווה...`);
        const list = await localJson(`list?course=${encodeURIComponent(c)}`);
        const local = list.files.map((f) => ({ ...f, course: c }));
        const remote = await listRemote(cbase, c !== "");
        const snap = (await localJson(`snapshot?course=${encodeURIComponent(c)}`)).snapshot || {};
        const busy = [...new Set([...(list.busy || []), ...(c ? remoteBusy(remote) : [])])];
        const p = plan(local, remote, snap, busy);
        // מטלה שטבלת המפתח שלה לא מתאימה בין המחשב לוואן דרייב: לא נוגעים בה בשום כיוון (0001.pdf של סטודנט אחד
        // היה דורס את 0001.pdf של אחר), עד שאדם מאחד את הטבלאות
        const kp = await keyCheck(cbase, local, remote, snap);
        for (const k of ["upload", "download", "remove"]) p[k] = withoutConflicts(p[k], kp);
        const row = { course: label, local: local.length, remote: Object.keys(remote).length,
          new: p.upload.filter((f) => f.why === "new").length, changed: p.upload.filter((f) => f.why === "changed").length,
          download: p.download.length, remove: p.remove.length, same: p.same.length, held: p.held.length, busy,
          conflicts: p.conflict.map((x) => [x.path, x.why === "both" ? "השתנה גם במחשב וגם בוואן דרייב" : "גודל שונה באותו זמן"]),
          archived: p.archived.length, keyConflicts: keyReport(kp), failed: [], missing: [], downloaded: 0, removed: 0 };
        report.push(row);
        if (dryRun) {
          Object.assign(row, { wouldUpload: p.upload.map((f) => [f.path, f.why]), wouldDownload: p.download.map((f) => [f.path, f.why]),
            wouldRemove: p.remove.map((f) => f.path) });
          continue;
        }
        const next = {};
        const keep = (path) => { if (snap[path]) next[path] = snap[path]; };
        for (const path of p.same) {
          const L = local.find((f) => f.path === path), R = remote[path];
          next[path] = { l: L.mtime, ls: L.size, r: R.mtime, rs: R.size };
        }
        [...p.held, ...p.archived, ...p.skipped, ...p.conflict.map((x) => x.path)].forEach(keep);
        let after = remote;
        if (p.upload.length) {
          const r = await runUpload(cbase, p.upload, (done, total) => say(`${label}: מעלה ${done} מתוך ${total}...\nלא לסגור את הלשונית ולא לעבור דף.`), c !== "");
          after = r.remote;
          Object.assign(row, { failed: r.failed, missing: r.missing });
          for (const f of p.upload) {
            if (r.missing.includes(f.path) || r.failed.some(([pth]) => pth === f.path)) keep(f.path);
            else next[f.path] = { l: f.mtime, ls: f.size, r: after[f.path].mtime, rs: after[f.path].size };
          }
        }
        if (p.download.length) {
          const r = await runDownload(cbase, c, p.download, (done, total) => say(`${label}: מוריד ${done} מתוך ${total}...`), stamp);
          row.downloaded = r.done.length;
          row.failed.push(...r.failed);
          row.conflicts.push(...r.conflict);
          row.held += r.held.length;
          for (const f of r.done) next[f.path] = { l: f.mtime, ls: f.size, r: f.mtime, rs: f.size };
          for (const f of p.download) if (!r.done.some((d) => d.path === f.path)) keep(f.path);
        }
        if (p.remove.length) {
          say(`${label}: מעביר ${p.remove.length} קבצים שנעלמו מהוואן דרייב ל-"Removed from OneDrive"...`);
          const r = await runRemove(c, p.remove, stamp);
          row.removed = r.done.length;
          row.failed.push(...r.failed);
          row.conflicts.push(...r.conflict);
          row.held += r.held.length;
          for (const f of p.remove) if (!r.done.includes(f.path)) keep(f.path);
        }
        await localPost(`snapshot?course=${encodeURIComponent(c)}`, { course: c, snapshot: next });
      }
      state.stage = "done";
      if (!dryRun) state.syncedAt = new Date().toISOString();
    } catch (e) {
      Object.assign(state, { stage: "error", error: String(e.message), needsLogin: !!e.needsLogin });
    } finally {
      running = false;
    }
    say(report.map((r) => `${r.course}: ${r.new} חדשים ו-${r.changed} השתנו עלו, ${r.downloaded}${r.download !== r.downloaded ? ` מתוך ${r.download}` : ""} ירדו, ` +
      `${r.removed} הוסרו בענן ועברו לארכיון, ${r.same} זהים` +
      (r.conflicts.length ? `\n  התנגשויות (לא נגעתי): ${r.conflicts.length}` : "") +
      (r.held ? `\n  מחכים לסיבוב הבא (בדיקה/משיכה רצה): ${r.held}` : "") +
      (r.archived ? `\n  ${ARCHIVED_NOTE(r.archived)}` : "") +
      (r.missing.length ? `\n  לא הגיעו: ${r.missing.length}` : "") +
      (r.failed.length ? `\n  נכשלו: ${r.failed.length}` : "") +
      (r.keyConflicts.length ? "\n  " + r.keyConflicts.join("\n  ") : "")).join("\n") +
      (state.error ? `\n\nשגיאה: ${state.error}` : "\n\nהסתיים."));
    showConflicts();
    return state;
  }
  window.__ecsSyncAll = syncAll;
  $("ecs-auto").onclick = () => live.round(true);

  // ---------- התנגשויות: אדם מחליט ----------
  // side "cloud": הגרסה שבמחשב עוברת ל-Removed from OneDrive, והגרסה מהענן יורדת. side "computer": הגרסה שבמחשב עולה
  async function resolve(course, path, side) {
    const cbase = course ? ROOT + "/" + course : ROOT;
    const local = (await localJson(`list?course=${encodeURIComponent(course)}`)).files.find((f) => f.path === path);
    const remote = (await listRemote(cbase, course !== ""))[path];
    const snapshot = (await localJson(`snapshot?course=${encodeURIComponent(course)}`)).snapshot || {};
    if (side === "cloud") {
      if (!remote) throw new Error("הקובץ כבר לא בוואן דרייב");
      if (local) {
        const r = await localPost("remove", { course, path, expect: local.mtime, stamp: stampNow() });
        if (r.status !== 200) throw new Error(r.data.error || `${r.status}`);
      }
      const bytes = await remoteBytes(cbase, path);
      const r = await localPost(`put?course=${encodeURIComponent(course)}&path=${encodeURIComponent(path)}&mtime=${remote.mtime}`, bytes);
      if (r.status !== 200) throw new Error(r.data.error || `${r.status}`);
      snapshot[path] = { l: r.data.mtime ?? remote.mtime, ls: remote.size, r: remote.mtime, rs: remote.size };
    } else {
      if (!local) throw new Error("הקובץ כבר לא במחשב");
      await uploadFile(cbase, { ...local, course });
      const now = (await listRemote(cbase, course !== ""))[path];
      if (!now) throw new Error("ההעלאה לא הגיעה לוואן דרייב");
      snapshot[path] = { l: local.mtime, ls: local.size, r: now.mtime, rs: now.size };
    }
    await localPost(`snapshot?course=${encodeURIComponent(course)}`, { course, snapshot });
    return syncAll();
  }
  window.__ecsResolve = resolve;
  function showConflicts() {
    const el = $("ecs-conflicts");
    const rows = (state.report || []).flatMap((r) => r.conflicts.map(([path, why]) => ({ course: r.course === "התיקייה הראשית" ? "" : r.course, path, why })));
    if (!rows.length) { el.innerHTML = ""; return; }
    el.innerHTML = `<b>התנגשויות (${rows.length}): אותו קובץ השתנה בשני הצדדים. מי מנצח?</b>` + rows.slice(0, 30).map((x, i) =>
      `<div style="margin:4px 0;border-top:1px solid #eee;padding-top:4px"><span dir="ltr">${x.course ? x.course + "/" : ""}${x.path}</span><br><small>${x.why}</small><br>` +
      `<button data-i="${i}" data-side="cloud" style="${BTN};background:#eee">קח מהענן</button>` +
      `<button data-i="${i}" data-side="computer" style="${BTN};background:#eee">קח מהמחשב</button></div>`).join("");
    el.querySelectorAll("button").forEach((b) => { b.onclick = async () => {
      const x = rows[Number(b.dataset.i)];
      b.disabled = true;
      try { await resolve(x.course, x.path, b.dataset.side); } catch (e) { say("שגיאה: " + e.message); b.disabled = false; }
    }; });
  }

  // ---------- חי: סיבוב כל כמה דקות, כל עוד הלשונית פתוחה, ודיווח לשרת המקומי ----------
  const live = window.__ecsLive = {
    on: false, minutes: 2, timer: null, beat: null, lastError: null,
    start({ minutes = 2 } = {}) {
      live.stop(true);
      live.on = true; live.minutes = Math.max(1, Number(minutes) || 2);
      live.timer = setInterval(() => live.round(), live.minutes * 60 * 1000);
      live.beat = setInterval(() => live.report(), 30 * 1000);
      $("ecs-live").textContent = "סנכרון חי: עצור";
      $("ecs-live").style.background = "#a4262c";
      live.report().catch(() => {});  // האתר רואה "מחובר בלייב" מיד, עוד לפני שהסיבוב הראשון נגמר
      live.round();
      return live;
    },
    stop(quiet = false) {
      clearInterval(live.timer); clearInterval(live.beat);
      live.timer = live.beat = null;
      const was = live.on;
      live.on = false;
      if (box.isConnected) { $("ecs-live").textContent = "סנכרון חי: הפעל"; $("ecs-live").style.background = "#107c10"; $("ecs-live-status").textContent = was ? "הסנכרון החי נעצר." : ""; }
      if (was && !quiet) live.report().catch(() => {});
    },
    async round(manual = false) {
      if (running) return;
      if (!manual && !live.on) return;
      await syncAll();
      live.lastError = state.error;
      await live.report().catch(() => {});
      live.show();
    },
    // מה האתר מראה בשורת "OneDrive": חי, מתי סונכרן, מה קרה. מספרים ושמות קבצים ממוספרים בלבד
    async report() {
      const rows = state.report || [];
      const sum = (k) => rows.reduce((s, r) => s + (r[k] || 0), 0);
      const body = { running: live.on, interval_s: live.minutes * 60, syncedAt: state.syncedAt || null, stage: state.stage,
        error: state.error || null, needsLogin: !!state.needsLogin,
        summary: { uploaded: sum("new") + sum("changed") - rows.reduce((s, r) => s + (r.missing?.length || 0), 0),
          downloaded: sum("downloaded"), removed: sum("removed"), same: sum("same"),
          held: sum("held"), archived: sum("archived"), failed: rows.reduce((s, r) => s + (r.failed?.length || 0), 0) },
        conflicts: rows.flatMap((r) => r.conflicts.map(([p]) => (r.course === "התיקייה הראשית" ? "" : r.course + "/") + p))
          .concat(rows.flatMap((r) => r.keyConflicts)),
        busy: rows.flatMap((r) => (r.busy || []).map((a) => `${r.course}/${a}`)),
        failed: rows.flatMap((r) => (r.failed || []).map(([p, why]) => `${r.course}/${p}: ${why}`)) };
      await localPost("status", body);
    },
    show() {
      if (!box.isConnected) return;
      const at = state.syncedAt ? new Date(state.syncedAt) : null;
      $("ecs-live-status").textContent = (live.on ? `חי: סיבוב כל ${live.minutes} דקות. ` : "") +
        (at ? `סונכרן לאחרונה ב-${at.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })}.` : "") +
        (state.error ? ` השגיאה האחרונה: ${state.error}` : "");
    },
  };
  $("ecs-live").onclick = () => (live.on ? live.stop() : live.start());
})();
