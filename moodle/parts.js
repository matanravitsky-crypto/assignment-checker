// הורדת כל ההגשות של מטלה ממודל בחלקים קטנים, במקום ZIP אחד שמודל קוטע בערך ב-2GB.
//
// רץ בלשונית של מודל (הדף "הגשות" של המטלה), עם החיבור של מי שמחובר בה. Claude בכרום מריץ אותו כמו שהוא
// (moodle/claude_driver.py, PARTS_PROMPT), אחרי בדיקת sha256 של הטקסט, ואז:
//   window.__ecsParts.start({ cmid: "3453769", run: "12345678" })
// ומחכה בריצה עד הסוף: await window.__ecsParts.wait(25000), שוב ושוב עד ש-over הוא true.
//
// הדף לא מדבר עם המחשב: מדיניות האבטחה של מודל (connect-src) חוסמת כל פנייה ל-http://127.0.0.1. הכל עובר
// דרך תיקיית ההורדות:
//   1. אוסף את מספרי המשתמש של כל מי שהגיש, מכל העמודים של טבלת ההגשות (קורא בלבד, בלי ללחוץ).
//   2. מבקש ממודל ZIP לכל חלק של CHUNK סטודנטים: בדיוק מה שהכפתור "Download" של הגשות מסומנות שולח
//      (action=gradingbatchoperation, operation=downloadselected), ומקבל אותו לזיכרון של הדף.
//   3. בודק שה-ZIP שלם (רשומת הסיום של ZIP והתיקייה המרכזית) וסופר בו את התיקיות של הסטודנטים. ZIP שלם
//      נשמר בתיקיית ההורדות בשם שמודל נתן לו. חלק שלא הגיע שלם מתבקש שוב בשני חצאים.
//   אחרי שלב 1 שומר שם "ECS pull <cmid> <run> plan.json" (כמה סטודנטים וכמה חלקים), בשביל מד ההתקדמות באתר.
//   4. בסוף שומר בתיקיית ההורדות קובץ סיכום קטן, "ECS pull <cmid> <run>.json": מספרים בלבד (כמה הגישו, כמה
//      חלקים, הגודל וכמה סטודנטים בכל חלק). המשיכה במחשב (dashboard/pull_parts.py) מחכה לקובץ הזה.
//
// החלוקה היא לפי סטודנטים ולא לפי עמודים, ולכן סטודנט שמגיש באמצע ההורדה לא מזיז אף אחד בין חלקים.
// הסקריפט לא משנה כלום במודל: הוא רק מבקש הורדות. בלי תבניות טקסט (backtick): הוא נכנס ל-String.raw בהנחיה.

(() => {
  const CHUNK = 50;
  const TRIES = 3;                          // חלק של סטודנט אחד שלא מגיע שלם: עוד שני ניסיונות ואז עוצרים
  const SUBMITTED = /הוגש|submitted/i;       // הסטטוס של שורה שהוגשה (ולא "אין הגשה")
  const NOT_SUBMITTED = /אין הגשה|no submission/i;

  const state = { stage: "ready", users: 0, submitted: null, parts: 0, done: 0, retried: 0, error: null };
  const saved = [];                         // {size, students} לכל חלק שנשמר
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const root = () => (window.M && M.cfg && M.cfg.wwwroot) || location.origin + "/moodle";
  const page = (cmid, extra) => root() + "/mod/assign/view.php?id=" + encodeURIComponent(cmid) + (extra || "");

  // ---------- 1. מי הגיש ----------
  async function html(url) {
    const r = await fetch(url, { credentials: "include" });
    if (!r.ok) throw new Error("Moodle " + r.status);
    if (/login\/index\.php/.test(r.url)) throw new Error("needs_login");
    return new DOMParser().parseFromString(await r.text(), "text/html");
  }

  async function collect(cmid) {
    const users = new Set();
    for (let p = 0; p < 200; p++) {
      const doc = await html(page(cmid, "&action=grading&page=" + p));
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
    const text = (await html(page(cmid))).body.innerText;
    const m = text.match(/(?:הוגש|Submitted)\s*\n?\s*(\d+)/);
    return m ? Number(m[1]) : null;
  }

  // ---------- 2. ה-ZIP של חלק ----------
  async function request(cmid, ids) {
    const body = new URLSearchParams({ id: cmid, action: "gradingbatchoperation", operation: "downloadselected",
      selectedusers: ids.join(","), sesskey: M.cfg.sesskey });
    const r = await fetch(root() + "/mod/assign/view.php", { method: "POST", body, credentials: "include" });
    if (!r.ok) throw new Error("Moodle " + r.status);
    const disposition = r.headers.get("content-disposition") || "";
    const m = disposition.match(/filename\*=UTF-8''([^;]+)/i) || disposition.match(/filename="?([^";]+)/i);
    const blob = await r.blob();
    const length = Number(r.headers.get("content-length") || 0);
    return { blob, name: m ? decodeURIComponent(m[1]) : "", cut: length > 0 && length !== blob.size };
  }

  // ---------- 3. ZIP שלם? ----------
  const u16 = (b, i) => b[i] | (b[i + 1] << 8);
  const u32 = (b, i) => (b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24)) >>> 0;

  // מספר הסטודנטים ב-ZIP (התיקיות "<שם>_<מזהה>_assignsubmission_..."), או null כשה-ZIP לא שלם
  async function studentsIn(blob) {
    const tailStart = Math.max(0, blob.size - 65557);
    const tail = new Uint8Array(await blob.slice(tailStart).arrayBuffer());
    let end = -1;
    for (let i = tail.length - 22; i >= 0; i--) {
      if (u32(tail, i) === 0x06054b50) { end = i; break; }
    }
    if (end < 0) return null;
    const count = u16(tail, end + 10), size = u32(tail, end + 12), offset = u32(tail, end + 16);
    if (!count || offset + size > blob.size) return null;
    const dir = new Uint8Array(await blob.slice(offset, offset + size).arrayBuffer());
    const decoder = new TextDecoder("utf-8");
    const students = new Set();
    let i = 0;
    for (let n = 0; n < count; n++) {
      if (i + 46 > dir.length || u32(dir, i) !== 0x02014b50) return null;
      const nameLength = u16(dir, i + 28), extra = u16(dir, i + 30), comment = u16(dir, i + 32);
      const name = decoder.decode(dir.subarray(i + 46, i + 46 + nameLength));
      const m = name.match(/_(\d+)_assignsubmission_/);
      if (m) students.add(m[1]);
      i += 46 + nameLength + extra + comment;
    }
    return students.size;
  }

  function save(blob, name) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 120000);
  }

  // ---------- הכל ----------
  async function run(cmid, runId, chunk) {
    try {
      state.stage = "collecting";
      const users = await collect(cmid);
      state.users = users.length;
      state.submitted = await submittedCount(cmid).catch(() => null);
      if (!users.length) throw new Error("no_submissions");
      const queue = [];
      for (let i = 0; i < users.length; i += chunk) queue.push({ ids: users.slice(i, i + chunk), tries: 0 });
      state.parts = queue.length;
      // התוכנית, כדי שהמחשב ידע מראש מתוך כמה (מד ההתקדמות באתר)
      save(new Blob([JSON.stringify({ cmid: cmid, run: runId, users: users.length, parts: queue.length })],
        { type: "application/json" }), "ECS pull " + cmid + " " + runId + " plan.json");
      state.stage = "downloading";
      while (queue.length) {
        const part = queue.shift();
        let got = null, students = null;
        try {
          got = await request(cmid, part.ids);
          students = got.cut ? null : await studentsIn(got.blob);
        } catch (e) {
          if (String(e.message) === "needs_login") throw e;
        }
        if (students !== null) {
          save(got.blob, got.name || ("submissions-" + cmid + ".zip"));
          saved.push({ size: got.blob.size, students: students, asked: part.ids.length });
          state.done++;
          await sleep(1500);   // שכרום יספיק לכתוב את הקובץ לפני החלק הבא
          continue;
        }
        state.retried++;
        if (part.ids.length > 1) {
          // לא הגיע שלם: אותם סטודנטים, בשני חצאים
          const half = Math.ceil(part.ids.length / 2);
          queue.unshift({ ids: part.ids.slice(0, half), tries: 0 }, { ids: part.ids.slice(half), tries: 0 });
          state.parts++;
        } else if (part.tries + 1 < TRIES) {
          queue.unshift({ ids: part.ids, tries: part.tries + 1 });
          await sleep(5000);
        } else {
          throw new Error("a submission did not arrive whole");
        }
      }
      state.stage = "done";
    } catch (e) {
      state.stage = "error";
      state.error = String(e.message || e).slice(0, 200);
    } finally {
      const summary = { cmid: cmid, run: runId, stage: state.stage, users: state.users, submitted: state.submitted,
        retried: state.retried, error: state.error, parts: saved };
      save(new Blob([JSON.stringify(summary)], { type: "application/json" }), "ECS pull " + cmid + " " + runId + ".json");
    }
  }

  window.__ecsParts = {
    state,
    // מתחיל ומחזיר מיד (ההורדה נמשכת ברקע בלשונית). run: מזהה הריצה שהמחשב מחכה לקובץ הסיכום שלה
    start({ cmid, run: runId, chunk = CHUNK }) {
      if (state.stage === "collecting" || state.stage === "downloading") return { started: false, reason: "already running" };
      if (!/^\d+$/.test(String(cmid)) || !/^\d+$/.test(String(runId))) return { started: false, reason: "bad ids" };
      Object.assign(state, { stage: "starting", users: 0, submitted: null, parts: 0, done: 0, retried: 0, error: null });
      saved.length = 0;
      run(String(cmid), String(runId), chunk);
      return { started: true };
    },
    // מחכה עד ms אלפיות שנייה, או עד שההורדה הסתיימה, ומחזיר את המצב. Claude קורא לזה שוב ושוב עד הסוף:
    // כרום סוגר את הלשונית של ריצת Claude בערך שתי דקות אחרי שהריצה נגמרת, וזה היה קוטע את ההורדה
    wait(ms) {
      const until = Date.now() + Math.min(Number(ms) || 25000, 60000);
      return new Promise((resolve) => {
        const tick = () => {
          const over = state.stage === "done" || state.stage === "error";
          if (over || Date.now() >= until) resolve(Object.assign({ over: over }, state));
          else setTimeout(tick, 1000);
        };
        tick();
      });
    },
  };
})();
