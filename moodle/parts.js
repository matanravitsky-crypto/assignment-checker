// הורדת כל ההגשות של מטלה ממודל בחלקים קטנים, במקום ZIP אחד שמודל קוטע בערך ב-2GB.
//
// רץ בלשונית של מודל (הדף "הגשות" של המטלה), עם החיבור של מי שמחובר בה, ונטען מהשרת המקומי:
//   eval(await (await fetch("http://127.0.0.1:8765/api/pull/parts.js")).text());
//   await window.__ecsParts.start({ cmid: "3438636", base: "http://127.0.0.1:8765/api/pull/" })
//
// מה הוא עושה:
//   1. אוסף את מספרי המשתמש של כל מי שהגיש, מכל העמודים של טבלת ההגשות (קורא בלבד, בלי ללחוץ).
//      רק שורות שהסטטוס שלהן "הוגש". בסוף משווה למספר "הוגש" שבעמוד הראשי של המטלה.
//   2. מבקש ממודל ZIP לכל חלק של CHUNK סטודנטים: בדיוק מה שהכפתור "Download" של הגשות מסומנות שולח
//      (action=gradingbatchoperation, operation=downloadselected), לתוך iframe מוסתר כדי שהדף לא יעבור.
//   3. אחרי כל חלק שואל את השרת המקומי (/api/pull/zip) אם ה-ZIP הגיע שלם ועם מספר הסטודנטים הנכון.
//      חלק קטוע מתבקש שוב בשני חצאים. בסוף מודיע לשרת (/api/pull/finish) שסיים.
//
// החלוקה היא לפי סטודנטים ולא לפי עמודים, ולכן סטודנט שמגיש באמצע ההורדה לא מזיז אף אחד בין חלקים.
// הסקריפט לא משנה כלום במודל: הוא רק מבקש הורדות. המצב נשמר ב-window.__ecsParts.state (מספרים בלבד).

(() => {
  const CHUNK = 50;
  const POLL_MS = 3000;
  const PART_TIMEOUT_MS = 15 * 60 * 1000;   // חלק אחד: מודל בונה את ה-ZIP, וכרום מוריד אותו
  const SUBMITTED = /הוגש|submitted/i;       // הסטטוס של שורה שהוגשה (ולא "אין הגשה")
  const NOT_SUBMITTED = /אין הגשה|no submission/i;

  const state = { stage: "ready", users: 0, submitted: null, parts: 0, done: 0, retried: 0, error: null };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const root = () => (window.M && M.cfg && M.cfg.wwwroot) || location.origin + "/moodle";

  // ---------- 1. מי הגיש ----------
  async function page(cmid, p) {
    const r = await fetch(`${root()}/mod/assign/view.php?id=${encodeURIComponent(cmid)}&action=grading&page=${p}`, { credentials: "include" });
    if (!r.ok) throw new Error(`Moodle ${r.status}`);
    return new DOMParser().parseFromString(await r.text(), "text/html");
  }

  async function collect(cmid) {
    const users = new Set();
    for (let p = 0; p < 200; p++) {
      const doc = await page(cmid, p);
      if (/login\/index\.php/.test(doc.querySelector("form")?.action || "")) throw new Error("needs_login");
      let fresh = 0;
      for (const box of doc.querySelectorAll('input[name="selectedusers"]')) {
        const row = box.closest("tr");
        const text = row ? row.textContent : "";
        if (!SUBMITTED.test(text) || NOT_SUBMITTED.test(text)) continue;
        if (!users.has(box.value)) { users.add(box.value); fresh++; }
      }
      if (!fresh) break;   // עמוד בלי אף אחד חדש: הגענו לסוף
    }
    return [...users];
  }

  async function submittedCount(cmid) {
    // "הוגש" בסיכום של העמוד הראשי של המטלה
    const r = await fetch(`${root()}/mod/assign/view.php?id=${encodeURIComponent(cmid)}`, { credentials: "include" });
    const text = new DOMParser().parseFromString(await r.text(), "text/html").body.innerText;
    const m = text.match(/(?:הוגש|Submitted)\s*\n?\s*(\d+)/);
    return m ? Number(m[1]) : null;
  }

  // ---------- 2. בקשת ZIP לחלק ----------
  function request(cmid, ids) {
    let frame = document.getElementById("ecs-parts-frame");
    if (!frame) {
      frame = document.createElement("iframe");
      frame.id = frame.name = "ecs-parts-frame";
      frame.style.display = "none";
      document.body.appendChild(frame);
    }
    const form = document.createElement("form");
    form.method = "post";
    form.action = root() + "/mod/assign/view.php";
    form.target = frame.name;
    const fields = { id: cmid, action: "gradingbatchoperation", operation: "downloadselected",
      selectedusers: ids.join(","), sesskey: M.cfg.sesskey };
    for (const [k, v] of Object.entries(fields)) {
      const input = document.createElement("input");
      input.type = "hidden"; input.name = k; input.value = v;
      form.appendChild(input);
    }
    document.body.appendChild(form);
    form.submit();
    form.remove();
  }

  // ---------- 3. השרת המקומי בודק כל ZIP ----------
  async function waitForZip(base, cmid, since, expect) {
    const until = Date.now() + PART_TIMEOUT_MS;
    while (Date.now() < until) {
      await sleep(POLL_MS);
      let r;
      try {
        r = await (await fetch(`${base}zip?mid=${encodeURIComponent(cmid)}&since=${since}&expect=${expect}`)).json();
      } catch (e) {
        continue;   // השרת עונה לאט או לרגע לא: מנסים שוב
      }
      if (r.status !== "waiting") return r;
    }
    return { status: "timeout" };
  }

  async function run(cmid, base, chunk) {
    try {
      state.stage = "collecting";
      const users = await collect(cmid);
      state.users = users.length;
      state.submitted = await submittedCount(cmid).catch(() => null);
      if (!users.length) throw new Error("no_submissions");
      const queue = [];
      for (let i = 0; i < users.length; i += chunk) queue.push(users.slice(i, i + chunk));
      state.parts = queue.length;
      state.stage = "downloading";
      while (queue.length) {
        const ids = queue.shift();
        const since = Date.now();
        request(cmid, ids);
        const r = await waitForZip(base, cmid, since, ids.length);
        if (r.status === "ok") { state.done++; continue; }
        if ((r.status === "broken" || r.status === "timeout") && ids.length > 1) {
          // חלק קטוע או שלא הגיע: אותם סטודנטים, בשני חצאים
          const half = Math.ceil(ids.length / 2);
          queue.unshift(ids.slice(0, half), ids.slice(half));
          state.parts++; state.retried++;
          continue;
        }
        throw new Error(r.message || r.status);
      }
      state.stage = "done";
    } catch (e) {
      state.stage = "error";
      state.error = String(e.message || e);
    } finally {
      const q = new URLSearchParams({ mid: cmid, stage: state.stage, users: state.users, submitted: state.submitted ?? "",
        parts: state.done, error: state.error || "" });
      fetch(`${base}finish?${q}`).catch(() => {});
    }
  }

  window.__ecsParts = {
    state,
    // מתחיל ומחזיר מיד (ההורדה נמשכת ברקע בלשונית). chunk: כמה סטודנטים בכל ZIP
    start({ cmid, base, chunk = CHUNK }) {
      if (state.stage === "collecting" || state.stage === "downloading") return { started: false, reason: "already running" };
      Object.assign(state, { stage: "starting", users: 0, submitted: null, parts: 0, done: 0, retried: 0, error: null });
      run(String(cmid), base, chunk);
      return { started: true };
    },
  };
})();
