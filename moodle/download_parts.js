// Downloads all submissions of one assignment in parts, from the grading page, in the user's own logged-in Chrome.
//
// BGU Moodle ends the "download all submissions" ZIP early when it is big (on 2026-10-23: 356, 913, 889 and 475 MB of
// about 2.4 GB, after one to two minutes), and Chrome still saves the cut file as a finished .zip. So this script
// asks Moodle for the submissions of about PART_SIZE students at a time (the grading table's "download selected"),
// and saves each part to Downloads as soon as it is in: "<Moodle's name> part 003 of 015.zip". Last it saves
// "<Moodle's name>.json", the list of the parts with their sizes: Python (moodle/ingest.py) waits for that list,
// and takes the parts only if every one of them is there. (One file of all the parts failed: Chrome could not save
// a 2.25 GB file built in the page.)
//
// All or nothing: a part counts only when its ZIP is whole and its central directory reads (studentsIn). A part
// that is not is asked for again in two halves; one student whose file comes without a ZIP (Moodle sends a single
// file as it is) is asked for again with a student who already came, so that Moodle zips the two. Only that
// failing too stops the whole download with an error, and then no list is saved and nothing is taken. The list
// has, per part, how many students were asked for and how many came (a student without a file comes in no part).
//
// Claude runs this with the javascript tool. It returns at once with how many students and parts there are, and goes
// on in the background; window.__moodleParts shows the progress. The tab must stay open until the list is saved, so
// Claude waits in its run until state is "saved" (Claude in Chrome closes the tab of an ended run within ~2 minutes:
// on 2026-10-23 the parts stopped at 14 of 15, 2:18 after the run ended).
// Only what changed: __SINCE__ is replaced by a time (milliseconds since 1970, digits only; 0 = everyone). Then only
// students whose "last modified (submission)" in the grading table is at or after it are downloaded, and the others
// keep what an earlier pull brought (moodle/anonymize.py keeps every student who is not in a download). A date the
// script can't read counts as changed; a student with no submission date has nothing to download.
// The due date: read from the assignment's own page, saved in the list as "due" (local time, "2026-10-26T23:59:00"),
// so the night pull of dashboard/scheduler.py knows when the assignment closes without anyone typing it.
// __ASSIGNMENT_ID__ is replaced by the Moodle id (digits only). No backtick and no dollar-brace anywhere: Claude gets
// this inside String.raw, and the page checks its SHA-256 before it runs (moodle/claude_driver.py download_prompt).
(async () => {
  const ID = "__ASSIGNMENT_ID__";
  const SINCE = Number("__SINCE__");
  const PART_SIZE = 40;  // ~150 MB per part at ~4 MB per submission: about 10 seconds, well before Moodle cuts
  const TRIES = 3;
  const BASE = "/moodle/mod/assign/view.php";
  if (!location.pathname.endsWith(BASE) || new URLSearchParams(location.search).get("id") !== ID) {
    return { error: "not on the grading page of assignment " + ID };
  }
  if (window.__moodleParts && window.__moodleParts.state === "downloading") {
    return { error: "already downloading" };
  }
  // Moodle's "download in folders" is a personal option for every assignment: off, the parts come without a folder per
  // student, and those students have no participant id (2026-10-23: two pulls at once, each clicking it, left it off)
  const folders = document.querySelector('input[type="checkbox"][id^="downloadasfolders"]');
  if (folders && !folders.checked) return { error: "the option to download in folders per student is off" };

  // Moodle's dates, as it shows them: "יום שישי, 23 אוקטובר 2026, 2:01 PM" (or in English, "Friday, 23 October 2026, 2:01 PM")
  const MONTHS = { "ינואר": 0, "פברואר": 1, "מרץ": 2, "מרס": 2, "אפריל": 3, "מאי": 4, "יוני": 5, "יולי": 6, "אוגוסט": 7,
    "ספטמבר": 8, "אוקטובר": 9, "נובמבר": 10, "דצמבר": 11, january: 0, february: 1, march: 2, april: 3, may: 4, june: 5,
    july: 6, august: 7, september: 8, october: 9, november: 10, december: 11 };
  const when = (text) => {
    const m = (text || "").match(/(\d{1,2})\s+([^\s\d,]+)\s+(\d{4}),?\s+(\d{1,2}):(\d{2})\s*(AM|PM)?/i);
    const month = m ? MONTHS[m[2].toLowerCase()] : undefined;
    if (month === undefined) return null;
    const pm = (m[6] || "").toUpperCase();
    const hour = pm ? Number(m[4]) % 12 + (pm === "PM" ? 12 : 0) : Number(m[4]);
    return new Date(Number(m[3]), month, Number(m[1]), hour, Number(m[5]));
  };
  const pad2 = (n) => String(n).padStart(2, "0");
  const local = (d) => d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) + "T" +
    pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":00";

  // Every student in the grading table, page after page (the table's own filter and page size apply)
  const users = [], changed = [];
  for (let page = 0; page < 200; page++) {
    const r = await fetch(BASE + "?id=" + ID + "&action=grading&page=" + page, { credentials: "same-origin" });
    if (!r.ok || /login/.test(r.url)) return { error: "the grading page did not open (" + r.status + ")" };
    const doc = new DOMParser().parseFromString(await r.text(), "text/html");
    // the column "עדכון אחרון (הגשה)" / "Last modified (submission)", by its header: the column numbers move
    let column = null;
    for (const th of doc.querySelectorAll("table thead th")) {
      if (/\((הגשה|submission)\)/i.test(th.textContent)) column = [...th.classList].find((k) => /^c\d+$/.test(k)) || null;
    }
    let fresh = 0;
    for (const box of doc.querySelectorAll('input[name="selectedusers"]')) {
      const v = box.value;
      if (!/^\d+$/.test(v) || users.includes(v)) continue;
      users.push(v);
      fresh++;
      const cell = column && box.closest("tr") ? box.closest("tr").querySelector("td." + column) : null;
      const text = cell ? cell.textContent : null;
      if (SINCE > 0 && text !== null && !/\d{4}/.test(text)) continue;  // no submission: nothing to download
      const at = when(text);
      if (SINCE > 0 && at && at.getTime() < SINCE) continue;  // not changed since the last pull
      changed.push(v);
    }
    if (!fresh) break;
  }
  if (!users.length) return { error: "no students in the grading table" };

  // The due date, from the assignment's page ("תאריך הגשה: ..." / "Due: ..."); null when it is not there
  let due = null;
  try {
    const v = await fetch(BASE + "?id=" + ID, { credentials: "same-origin" });
    const page = new DOMParser().parseFromString(await v.text(), "text/html");
    for (const el of page.querySelectorAll('[data-region="activity-dates"] div, .activity-dates div, table tr')) {
      const text = el.textContent.replace(/\s+/g, " ");
      if (/תאריך הגשה|מועד הגשה|\bDue\b/i.test(text) && !/סגיר|cut-off|נפתח|opened|הארכה|extension/i.test(text)) {
        const d = when(text);
        if (d) { due = local(d); break; }
      }
    }
  } catch (e) { due = null; }

  // Even parts (561 → 15 of 37-38, not 14 of 40 and one of 1)
  const queue = [];
  if (changed.length) {
    const count = Math.ceil(changed.length / PART_SIZE), each = Math.ceil(changed.length / count);
    for (let i = 0; i < changed.length; i += each) queue.push({ ids: changed.slice(i, i + each), tries: 0 });
  }
  const planned = queue.length;
  const S = (window.__moodleParts = { state: "downloading", users: users.length, changed: changed.length,
                                      parts: planned, done: 0, retried: 0, empty: 0 });

  const u16 = (b, i) => b[i] | (b[i + 1] << 8);
  const u32 = (b, i) => (b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24)) >>> 0;
  // How many students a ZIP holds, from its central directory; null if the ZIP is cut or is no ZIP at all.
  // A file that is not in a student's folder throws: the folders option went off, and asking again will not help
  const studentsIn = async (blob) => {
    const tail = new Uint8Array(await blob.slice(Math.max(0, blob.size - 65557)).arrayBuffer());
    let end = -1;
    for (let i = tail.length - 22; i >= 0; i--) {
      if (u32(tail, i) === 0x06054b50) { end = i; break; }
    }
    if (end < 0) return null;
    const entries = u16(tail, end + 10), size = u32(tail, end + 12), offset = u32(tail, end + 16);
    if (!entries || offset + size > blob.size) return null;
    const dir = new Uint8Array(await blob.slice(offset, offset + size).arrayBuffer());
    const decoder = new TextDecoder("utf-8"), students = new Set();
    let i = 0;
    for (let n = 0; n < entries; n++) {
      if (i + 46 > dir.length || u32(dir, i) !== 0x02014b50) return null;
      const nameLength = u16(dir, i + 28), extra = u16(dir, i + 30), comment = u16(dir, i + 32);
      const name = decoder.decode(dir.subarray(i + 46, i + 46 + nameLength));
      const m = name.match(/^[^/\\]+_(\d+)_assignsubmission_[a-z]+[/\\]/);
      if (m) students.add(m[1]);
      else if (!/[/\\]$/.test(name)) throw new Error("no_folders");
      i += 46 + nameLength + extra + comment;
    }
    return students.size;
  };
  const fileName = (r) => {
    const cd = r.headers.get("Content-Disposition") || "";
    const star = cd.match(/filename\*=UTF-8''([^;]+)/i);
    if (star) return decodeURIComponent(star[1]);
    const plain = cd.match(/filename="?([^";]+)"?/i);
    return plain ? plain[1] : null;
  };
  const save = (blob, name) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 120000);  // Chrome has saved it by then; the memory goes back
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const pad = (n) => String(n).padStart(3, "0");
  // One request: { blob, name } for a ZIP that reads, "empty" when none of them has a file, null otherwise
  const ask = async (ids) => {
    const body = new URLSearchParams({
      id: ID, action: "gradingbatchoperation", operation: "downloadselected",
      selectedusers: ids.join(","), sesskey: M.cfg.sesskey,
      "_qf__mod_assign\\form\\grading_batch_operations_form": "1",
    });
    const r = await fetch(BASE, { method: "POST", body, credentials: "same-origin" });
    if (/login/.test(r.url)) throw new Error("needs_login");
    if (!r.ok) return null;
    if (/text\/html/.test(r.headers.get("Content-Type") || "")) return "empty";
    const blob = await r.blob(), students = await studentsIn(blob);
    return students === null ? null : { blob, name: fileName(r), students };
  };

  (async () => {
    const files = [];
    let stem = null, helper = null;  // helper: a student whose ZIP already came, to pair with a single file
    try {
      while (queue.length) {
        const part = queue.shift();
        const got = await ask(part.ids);
        if (got === "empty") { S.empty += part.ids.length; continue; }
        if (got) {
          stem = stem || (got.name || "").replace(/\.zip$/i, "") || "moodle-" + ID;
          // "of 015": the parts planned so far, so the progress bar knows the total from the first part on
          const name = stem + " part " + pad(files.length + 1) + " of " + pad(S.parts) + ".zip";
          save(got.blob, name);  // at once: the page never holds more than one part
          files.push({ name, size: got.blob.size, students: got.students, asked: part.ids.length });
          if (!helper && got.students === part.ids.length) helper = part.ids[0];
          S.done = files.length;
          await sleep(1500);  // Chrome writes the part to disk before the next one comes
          continue;
        }
        S.retried++;
        if (part.ids.length > 1 && !part.paired) {  // not whole: the same students, in two halves
          const half = Math.ceil(part.ids.length / 2);
          queue.unshift({ ids: part.ids.slice(0, half), tries: 0 }, { ids: part.ids.slice(half), tries: 0 });
          S.parts++;
        } else if (part.tries + 1 < TRIES) {  // one student: with a helper, so that Moodle sends a ZIP
          const ids = helper && !part.ids.includes(helper) ? [part.ids[0], helper] : part.ids;
          queue.unshift({ ids, tries: part.tries + 1, paired: ids.length > 1 });
          await sleep(3000);
        } else {
          throw new Error("the submissions of one student did not arrive whole " + TRIES + " times");
        }
      }
      // The list comes last: parts of a download that stopped halfway have no list, and Python never takes them
      // "since" and "changed": only what changed since then was asked for (0: everyone), so no part is not "incomplete"
      const list = { users: S.users, changed: S.changed, since: SINCE, due, parts: files.length, empty: S.empty,
                     retried: S.retried, failed: [], files };
      save(new Blob([JSON.stringify(list)], { type: "application/json" }), (stem || "moodle-" + ID) + ".json");
      S.state = "saved";
    } catch (e) {
      S.state = "error";
      S.error = String(e && e.message || e).slice(0, 200);
      if (S.error === "no_folders") S.error = "a part came without a folder per student: the option to download in folders is off";
    }
  })();
  return { users: users.length, changed: changed.length, parts: planned, due };
})();
