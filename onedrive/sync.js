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
  // קבצים שלא מעלים אף פעם: קבצים זמניים של Windows ו-Office, קבצים חצי כתובים, ומנעולים (כמו dashboard/sync.py)
  const SKIP = /(^|\/)(desktop\.ini|thumbs\.db|~\$[^/]*|[^/]*\.tmp|[^/]* in progress\.txt)$/i;
  // שעון המחשב ושעון השרת לא מסונכרנים בדיוק: הפרש קטן מזה לא נחשב "חדש יותר"
  const CLOCK_SLACK_MS = 2 * 60 * 1000;

  // ---------- ההשוואה (בלי רשת, כדי שאפשר לבדוק אותה לבד) ----------
  // local: [{path, size, mtime}] (path יחסי לתיקיית הקורס, mtime במילישניות)
  // remote: {path: {size, mtime}}
  function plan(local, remote) {
    const out = { upload: [], same: [], remoteNewer: [], skipped: [] };
    for (const f of local) {
      if (SKIP.test(f.path)) { out.skipped.push(f.path); continue; }
      const r = remote[f.path];
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

  if (typeof window === "undefined") { module.exports = { plan, SKIP }; return; }
  window.__ecsPlan = plan;  // לבדיקות

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
  // כל הקבצים מתחת לתיקייה בוואן דרייב: {נתיב יחסי: {size, mtime}}. תיקייה שעוד לא קיימת: ריק
  async function listRemote(base) {
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
      for (const d of data.Folders || []) if (d.Name !== "Forms") await walk(folder + "/" + d.Name, rel + d.Name + "/");
    }
    await walk(base, "");
    return out;
  }
  const made = new Set();
  async function ensureFolder(path) {
    // יוצר את התיקייה ואת כל ההורים שלה, מתחת ל-ROOT. תיקייה שכבר קיימת: SharePoint מחזיר הצלחה
    const parts = path.slice(ROOT.length + 1).split("/");
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
  async function localJson(what) {
    const r = await fetch(LOCAL + what);
    if (!r.ok) throw new Error(`${r.status} local ${what}`);
    return r.json();
  }

  // מעלה רשימה, PARALLEL בכל פעם, ובסוף בודק שהכל בוואן דרייב באותו גודל. מחזיר מה שנכשל ומה שלא הגיע
  async function runUpload(base, todo, progress) {
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
    const remote = await listRemote(base);
    return { failed, missing: todo.filter((f) => !remote[f.path] || remote[f.path].size !== f.size).map((f) => f.path) };
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
      <b style="font-size:16px">העלאה לוואן דרייב: רק מה שהשתנה</b>
      <button id="ecs-close" style="border:0;background:none;font-size:18px;cursor:pointer">×</button>
    </div>
    <p style="margin:8px 0">"סנכרון מהמחשב" לוקח את הקבצים מ-start.bat. אם הוא לא רץ, בוחרים את תיקיית הקורס ביד.</p>
    <input id="ecs-pick" type="file" webkitdirectory multiple style="display:none">
    <button id="ecs-auto" style="background:#0f6cbd;color:#fff;border:0;border-radius:6px;padding:8px 14px;cursor:pointer">סנכרון מהמחשב</button>
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
      const p = plan(local, await listRemote(base));
      todo = p.upload;
      const bytes = todo.reduce((s, f) => s + f.size, 0);
      const news = todo.filter((f) => f.why === "new").length;
      Object.assign(state, { stage: "planned", upload: todo.map((f) => [f.path, f.why]), same: p.same.length, remoteNewer: p.remoteNewer });
      say(`תיקייה: ${course}\nחדשים: ${news}\nהשתנו: ${todo.length - news}\nזהים, לא נוגעים: ${p.same.length}\n` +
        (p.remoteNewer.length ? `חדשים יותר בוואן דרייב, לא נדרסים: ${p.remoteNewer.length}\n  ${p.remoteNewer.slice(0, 8).join("\n  ")}\n` : "") +
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
  // dryRun: רק משווה ומדווח מה היה עולה, בלי להעלות כלום
  async function syncAll({ dryRun = false } = {}) {
    const report = [];
    Object.assign(state, { stage: dryRun ? "dry run" : "auto", report });
    let courses;
    try { courses = (await localJson("courses")).courses; } catch (e) {
      Object.assign(state, { stage: "error", error: "השרת המקומי לא עונה. צריך להפעיל את start.bat. (" + e.message + ")" });
      say(state.error); return state;
    }
    for (const c of courses) {
      const cbase = ROOT + "/" + c;
      say(`${c}: משווה...`);
      const local = (await localJson(`list?course=${encodeURIComponent(c)}`)).files.map((f) => ({ ...f, course: c }));
      const p = plan(local, await listRemote(cbase));
      const row = { course: c, local: local.length, new: p.upload.filter((f) => f.why === "new").length,
        changed: p.upload.filter((f) => f.why === "changed").length, same: p.same.length, remoteNewer: p.remoteNewer };
      report.push(row);
      if (dryRun) row.wouldUpload = p.upload.map((f) => [f.path, f.why]);
      else if (p.upload.length) {
        const r = await runUpload(cbase, p.upload, (done, total) => say(`${c}: מעלה ${done} מתוך ${total}...\nלא לסגור את הלשונית ולא לעבור דף.`));
        Object.assign(row, { failed: r.failed, missing: r.missing });
      }
    }
    state.stage = "done";
    say(report.map((r) => `${r.course}: ${r.new} חדשים, ${r.changed} השתנו, ${r.same} זהים` +
      (r.remoteNewer.length ? `, ${r.remoteNewer.length} חדשים יותר בוואן דרייב (לא נדרסו)` : "") +
      (r.missing && r.missing.length ? `\n  לא הגיעו: ${r.missing.length}` : "")).join("\n") + "\n\nהסתיים.");
    return state;
  }
  window.__ecsSyncAll = syncAll;
  $("ecs-auto").onclick = () => syncAll();
})();
