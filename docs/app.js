(() => {
  const D = window.DEMO;
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------- State ----------
  const state = {
    courseId: D.courses[0].id,
    subs: D.submissions.map((s) => ({ ...s })),
    filter: "all",
    query: "",
    busy: null, // "pull" | "grade" | "return"
    openId: null,
  };

  const STATUS = {
    received: "התקבלה",
    grading: "בבדיקה",
    review: "ממתינה לאישור",
    returned: "הוחזרה",
    error: "דורשת טיפול",
  };

  const STAGES = [
    { key: "received", name: "משיכה מהאוניברסיטה", sub: "הגשות שנמשכו ומחכות לבדיקה" },
    { key: "grading", name: "בדיקה וציון", sub: "Claude בודק לפי המחוון והדגשים" },
    { key: "review", name: "סימון ואישור", sub: "הערות מסומנות, מחכות לאישור מתרגל" },
    { key: "returned", name: "החזרה לאתר", sub: "ציון והערות נשלחו לאתר האוניברסיטה" },
  ];

  const ICON = {
    pull: '<svg viewBox="0 0 24 24"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>',
    grade: '<svg viewBox="0 0 24 24"><path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4z"/><path d="M18 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/></svg>',
    ret: '<svg viewBox="0 0 24 24"><path d="M12 20V9M7 14l5-5 5 5M5 4h14"/></svg>',
    spin: '<svg class="spin" viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 9 9"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    arrow: '<svg viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg>',
    file: '<svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5"/></svg>',
    redo: '<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4"/></svg>',
    pen: '<svg viewBox="0 0 24 24"><path d="M4 20l4-1 11-11-3-3L5 16z"/></svg>',
    warn: '<svg viewBox="0 0 24 24"><path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.5"/></svg>',
  };

  const course = () => D.courses.find((c) => c.id === state.courseId);
  const courseSubs = () => state.subs.filter((s) => s.courseId === state.courseId);
  const byStatus = (st) => courseSubs().filter((s) => s.status === st);
  const fmt = (iso, opts = { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) =>
    new Date(iso).toLocaleString("he-IL", opts);
  const initials = (name) => name.split(" ").map((p) => p[0]).slice(0, 2).join("");

  // ---------- Toast ----------
  function toast(msg, icon = ICON.check) {
    const el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = icon + `<span>${esc(msg)}</span>`;
    $("#toasts").append(el);
    setTimeout(() => el.remove(), 3200);
  }

  // ---------- Pipeline actions (סימולציה) ----------
  const extraNames = ["רותם שגיא", "אלה כספי", "בן ממן", "ספיר נגר", "יואב רז", "מור לנדאו", "עמית גולן", "הדר אלמוג", "נוי פלד"];
  let nextNo = 2000;

  function pull() {
    if (state.busy) return;
    state.busy = "pull"; render();
    setTimeout(() => {
      const n = 3 + Math.floor(Math.random() * 3);
      for (let i = 0; i < n; i++) {
        const name = extraNames[(nextNo + i) % extraNames.length];
        state.subs.unshift({
          id: `S-${nextNo++}`, name, studentId: String(204100000 + Math.floor(Math.random() * 800000)),
          email: `student${nextNo}@post.bgu.ac.il`, courseId: state.courseId,
          submittedAt: new Date().toISOString(), file: "hw.py", status: "received",
          score: null, flags: [], late: false, fresh: true,
        });
      }
      D.runs.unshift({ at: new Date().toISOString(), kind: "pull", text: `נמשכו ${n} הגשות חדשות ממערכת האוניברסיטה`, course: course().course });
      state.busy = null; render();
      toast(`נמשכו ${n} הגשות חדשות`);
    }, 1300);
  }

  function grade() {
    const queue = [...byStatus("grading"), ...byStatus("received")];
    if (state.busy || !queue.length) return;
    state.busy = "grade";
    queue.forEach((s) => (s.status = "grading"));
    render();
    queue.forEach((s, i) => {
      setTimeout(() => {
        s.status = "review";
        s.score = 58 + Math.floor(Math.random() * 41);
        if (s.score < 65) s.flags = ["ציון נמוך"];
        s.fresh = true;
        if (i === queue.length - 1) {
          state.busy = null;
          const avg = Math.round(queue.reduce((a, b) => a + b.score, 0) / queue.length);
          D.runs.unshift({ at: new Date().toISOString(), kind: "grade", text: `Claude סיים לבדוק ${queue.length} עבודות. ציון ממוצע ${avg}`, course: course().course });
          toast(`${queue.length} עבודות נבדקו ומחכות לאישור`);
        }
        render();
      }, 900 + i * 650);
    });
  }

  function returnApproved() {
    const ready = byStatus("review");
    if (state.busy || !ready.length) return;
    state.busy = "return"; render();
    setTimeout(() => {
      ready.forEach((s) => { s.status = "returned"; s.fresh = true; });
      D.runs.unshift({ at: new Date().toISOString(), kind: "return", text: `הוחזרו ${ready.length} ציונים והערות לאתר האוניברסיטה`, course: course().course });
      state.busy = null; render();
      toast(`${ready.length} ציונים והערות הוחזרו לאתר האוניברסיטה`);
    }, 1200);
  }

  function approveOne(id) {
    const s = state.subs.find((x) => x.id === id);
    const override = $("#override");
    if (override && override.value !== "") s.score = Math.max(0, Math.min(100, Number(override.value)));
    s.status = "returned"; s.fresh = true;
    closeDrawer(); render();
    toast(`הציון של ${s.name} הוחזר לאתר האוניברסיטה`);
  }

  function regradeOne(id) {
    const s = state.subs.find((x) => x.id === id);
    s.status = "grading"; s.flags = s.flags.filter((f) => f !== "קובץ לא נפתח");
    closeDrawer(); render();
    toast(`${s.name} נשלחה לבדיקה חוזרת`, ICON.redo);
    setTimeout(() => {
      s.status = "review"; s.score = s.score ?? 60 + Math.floor(Math.random() * 38); s.fresh = true; render();
    }, 1800);
  }

  // ---------- Pieces ----------
  function statusPill(st) { return `<span class="status ${st}">${STATUS[st]}</span>`; }

  function scoreCell(s) {
    if (s.score == null) return `<span class="score none">טרם נבדקה</span>`;
    return `<span class="score ${s.score < 65 ? "low" : ""}">${s.score}</span>`;
  }

  function pipelineHTML() {
    const subs = courseSubs();
    const counts = Object.fromEntries(STAGES.map((st) => [st.key, subs.filter((s) => s.status === st.key).length]));
    const errors = subs.filter((s) => s.status === "error").length;
    const b = state.busy;
    return `
      <section class="pipeline" aria-labelledby="pl-title">
        <div class="pipeline-head">
          <h2 id="pl-title">מסלול הבדיקה</h2>
          <span class="meta">${subs.length} הגשות בסך הכל${errors ? `, ${errors} דורשות טיפול ידני` : ""}</span>
          <div class="actions">
            <button class="btn secondary" data-act="pull" ${b ? "disabled" : ""}>${b === "pull" ? ICON.spin : ICON.pull}משוך הגשות</button>
            <button class="btn primary" data-act="grade" ${b || !counts.received ? "disabled" : ""}>${b === "grade" ? ICON.spin : ICON.grade}בדוק ${counts.received ? counts.received + " " : ""}עבודות</button>
            <button class="btn secondary" data-act="return" ${b || !counts.review ? "disabled" : ""}>${b === "return" ? ICON.spin : ICON.ret}החזר לאוניברסיטה</button>
          </div>
        </div>
        <div class="stages">
          ${STAGES.map((st, i) => `
            <div class="stage" data-stage="${st.key}">
              ${i ? `<span class="stage-arrow" aria-hidden="true">${ICON.arrow}</span>` : ""}
              <div class="stage-top"><span class="stage-no">${i + 1}</span><span class="stage-name">${st.name}</span></div>
              <p class="stage-sub">${st.sub}</p>
              <div class="stage-count">${counts[st.key]}<small>עבודות</small></div>
              <div class="stage-dots" aria-hidden="true">
                ${subs.filter((s) => s.status === st.key).map((s) => `<span class="sdot ${s.fresh ? "enter" : ""}" title="${esc(s.name)}"></span>`).join("")}
              </div>
            </div>`).join("")}
        </div>
      </section>`;
  }

  function filteredSubs() {
    const q = state.query.trim();
    return courseSubs()
      .filter((s) => state.filter === "all" || s.status === state.filter)
      .filter((s) => !q || s.name.includes(q) || s.studentId.includes(q) || s.id.includes(q));
  }

  function chipsHTML() {
    const subs = courseSubs();
    const opts = [["all", "הכל", subs.length], ...Object.keys(STATUS).map((k) => [k, STATUS[k], subs.filter((s) => s.status === k).length])];
    return `<div class="chips" role="group" aria-label="סינון לפי מצב">
      ${opts.map(([k, label, c]) => `<button class="chip" data-filter="${k}" aria-pressed="${state.filter === k}">${label}<span class="c">${c}</span></button>`).join("")}
    </div>`;
  }

  function tableHTML(rows, { full = false } = {}) {
    if (!courseSubs().length) {
      return `<div class="empty"><strong>עדיין לא נמשכו הגשות לקורס הזה</strong>לחצו על "משוך הגשות" כדי להביא את העבודות ממערכת האוניברסיטה.<br><br><button class="btn primary" data-act="pull">${ICON.pull}משוך הגשות</button></div>`;
    }
    if (!rows.length) return `<div class="empty"><strong>אין עבודות שמתאימות לסינון</strong>נסו לנקות את החיפוש או לבחור מצב אחר.</div>`;
    return `<div class="table-wrap"><table>
      <thead><tr>
        <th>סטודנט</th>
        <th class="col-hide">הוגשה</th>
        ${full ? `<th class="col-hide">קובץ</th>` : ""}
        <th>מצב</th>
        <th>ציון</th>
        <th class="col-hide-sm">הערות מערכת</th>
      </tr></thead>
      <tbody>
        ${rows.map((s) => `
          <tr data-open="${s.id}" tabindex="0" class="${s.fresh ? "flash" : ""}" aria-label="פתח את העבודה של ${esc(s.name)}">
            <td><div class="who"><span class="ini">${initials(s.name)}</span><div><b>${esc(s.name)}</b><small>${s.studentId}</small></div></div></td>
            <td class="col-hide muted num">${fmt(s.submittedAt)}</td>
            ${full ? `<td class="col-hide"><span class="ltr muted" style="font-family:var(--font-code);font-size:13px">${esc(s.file)}</span></td>` : ""}
            <td>${statusPill(s.status)}</td>
            <td>${scoreCell(s)}</td>
            <td class="col-hide-sm">${s.flags.map((f) => `<span class="flag">${esc(f)}</span>`).join("") || `<span class="muted">—</span>`}</td>
          </tr>`).join("")}
      </tbody></table></div>`;
  }

  function distHTML() {
    const graded = courseSubs().filter((s) => s.score != null);
    if (!graded.length) return `<p class="muted" style="margin:0">עוד אין ציונים בקורס הזה.</p>`;
    const buckets = [[0, 54], [55, 64], [65, 74], [75, 84], [85, 94], [95, 100]];
    const counts = buckets.map(([a, b]) => graded.filter((s) => s.score >= a && s.score <= b).length);
    const max = Math.max(...counts, 1);
    const avg = Math.round(graded.reduce((a, s) => a + s.score, 0) / graded.length);
    const sorted = graded.map((s) => s.score).sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];
    return `
      <div class="dist" role="img" aria-label="התפלגות ציונים">
        ${buckets.map(([a, b], i) => `<div class="bar ${a < 65 ? "low" : ""}" title="${counts[i]} סטודנטים"><i style="height:${(counts[i] / max) * 100}%"></i><span>${a}–${b}</span></div>`).join("")}
      </div>
      <div style="margin-top:12px">
        <div class="stat-line"><span>ממוצע</span><b>${avg}</b></div>
        <div class="stat-line"><span>חציון</span><b>${median}</b></div>
        <div class="stat-line"><span>מתחת ל-65</span><b>${graded.filter((s) => s.score < 65).length}</b></div>
      </div>`;
  }

  function rubricSummaryHTML() {
    const r = D.rubric;
    return `
      <ul class="criteria">
        ${r.criteria.map((c) => `<li><span>${c.name}</span><span class="w">${c.weight}%</span><span class="track"><i style="width:${c.weight}%"></i></span></li>`).join("")}
      </ul>
      <ul class="emph">${r.emphases.slice(0, 3).map((e) => `<li>${esc(e)}</li>`).join("")}</ul>`;
  }

  const LOG_ICON = { pull: ICON.pull, grade: ICON.grade, return: ICON.ret, error: ICON.warn };
  function logHTML(limit) {
    return `<ul class="log">${D.runs.slice(0, limit).map((r) => `
      <li><span class="ic ${r.kind}">${LOG_ICON[r.kind]}</span><div>${esc(r.text)}<time>${fmt(r.at)}</time></div></li>`).join("")}</ul>`;
  }

  function pageHead(title, desc, actions = "") {
    return `<div class="page-head"><div><h1>${title}</h1>${desc ? `<p>${desc}</p>` : ""}</div>${actions ? `<div class="actions">${actions}</div>` : ""}</div>`;
  }

  // ---------- Views ----------
  const views = {
    "/"() {
      const c = course();
      return `
        ${pageHead(esc(c.assignment), `${esc(c.course)}, קורס <span class="num">${c.code}</span>. מועד הגשה ${fmt(c.due, { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}.`)}
        ${pipelineHTML()}
        <div class="grid-2">
          <section class="panel" aria-labelledby="t-title">
            <div class="panel-head">
              <h2 id="t-title">הגשות</h2>
              <a class="end" href="#/submissions" style="font-size:13.5px;font-weight:500">לכל העבודות</a>
            </div>
            <div class="panel-body" style="padding-bottom:6px">${chipsHTML()}</div>
            ${tableHTML(filteredSubs().slice(0, 10))}
          </section>
          <div class="stack">
            <section class="panel"><div class="panel-head"><h3>התפלגות ציונים</h3></div><div class="panel-body">${distHTML()}</div></section>
            <section class="panel"><div class="panel-head"><h3>מחוון ודגשים</h3><a class="end" href="#/rubric" style="font-size:13.5px;font-weight:500">עריכה</a></div><div class="panel-body">${rubricSummaryHTML()}</div></section>
            <section class="panel"><div class="panel-head"><h3>פעילות אחרונה</h3></div><div class="panel-body" style="padding-block:4px">${logHTML(4)}</div></section>
          </div>
        </div>`;
    },

    "/submissions"() {
      const c = course();
      return `
        ${pageHead("עבודות", `כל ההגשות של ${esc(c.assignment)}. לחיצה על שורה פותחת את העבודה, ההערות והציון.`)}
        <section class="panel">
          <div class="panel-body">${chipsHTML()}</div>
          ${tableHTML(filteredSubs(), { full: true })}
        </section>`;
    },

    "/students"() {
      const q = state.query.trim();
      const people = state.subs
        .filter((s) => !q || s.name.includes(q) || s.studentId.includes(q))
        .reduce((m, s) => { (m[s.studentId] ||= { ...s, items: [] }).items.push(s); return m; }, {});
      const list = Object.values(people);
      return `
        ${pageHead("סטודנטים", "כל הסטודנטים שהגישו עבודות, עם הפרטים שמגיעים ממערכת האוניברסיטה.")}
        <section class="panel">
          <div class="table-wrap"><table>
            <thead><tr><th>סטודנט</th><th class="col-hide">דוא״ל</th><th>הגשות</th><th>ציון ממוצע</th><th class="col-hide-sm">עבודה אחרונה</th></tr></thead>
            <tbody>${list.map((p) => {
              const g = p.items.filter((s) => s.score != null);
              const avg = g.length ? Math.round(g.reduce((a, s) => a + s.score, 0) / g.length) : null;
              return `<tr data-open="${p.items[0].id}" tabindex="0">
                <td><div class="who"><span class="ini">${initials(p.name)}</span><div><b>${esc(p.name)}</b><small>${p.studentId}</small></div></div></td>
                <td class="col-hide muted"><span class="ltr">${esc(p.email)}</span></td>
                <td class="num">${p.items.length}</td>
                <td>${avg == null ? `<span class="score none">—</span>` : `<span class="score ${avg < 65 ? "low" : ""}">${avg}</span>`}</td>
                <td class="col-hide-sm">${statusPill(p.items[0].status)}</td>
              </tr>`;
            }).join("")}</tbody>
          </table></div>
        </section>`;
    },

    "/rubric"() {
      const r = D.rubric;
      const total = r.criteria.reduce((a, c) => a + c.weight, 0);
      return `
        ${pageHead("מחוון ודגשים", `מה Claude מקבל יחד עם כל עבודה ב${esc(course().assignment)}. המשקלות צריכים להסתכם ב-100.`,
          `<button class="btn primary" data-act="save-rubric">${ICON.check}שמור מחוון</button>`)}
        <div class="grid-2" style="margin-top:0">
          <div class="stack">
            <section class="panel">
              <div class="panel-head"><h2>קריטריונים</h2><span class="meta">משקל באחוזים</span></div>
              <div class="panel-body" id="rubric-rows">
                ${r.criteria.map((c, i) => `
                  <div class="rubric-row">
                    <span class="name">${c.name}</span>
                    <input type="number" min="0" max="100" value="${c.weight}" data-weight="${i}" aria-label="משקל ${c.name}">
                    <span class="desc">${esc(c.desc)}</span>
                  </div>`).join("")}
                <div class="total-line ${total !== 100 ? "bad" : ""}" id="total-line"><span>סך הכל</span><span class="num">${total}%</span></div>
              </div>
            </section>
            <section class="panel">
              <div class="panel-head"><h2>דגשים לבודק</h2><span class="meta">שורה לכל דגש</span></div>
              <div class="panel-body field">
                <textarea rows="6" aria-label="דגשים לבודק">${esc(r.emphases.join("\n"))}</textarea>
              </div>
            </section>
          </div>
          <section class="panel">
            <div class="panel-head"><h3>ההנחיה שנשלחת ל-Claude</h3></div>
            <div class="panel-body">
              <pre style="white-space:pre-wrap;margin:0;font:13px/1.7 var(--font-ui);color:var(--ink-2)">אתה בודק את ${esc(course().assignment)} בקורס ${esc(course().course)}.
בדוק את העבודה המצורפת לפי המחוון:
${r.criteria.map((c) => `• ${c.name} (${c.weight}%): ${c.desc}`).join("\n")}

דגשים:
${r.emphases.map((e) => `• ${e}`).join("\n")}

החזר JSON עם: ציון לכל קריטריון, ציון סופי, הערות לפי מספר שורה, ומשוב כללי לסטודנט.</pre>
            </div>
          </section>
        </div>`;
    },

    "/runs"() {
      return `
        ${pageHead("יומן ריצות", "כל פעולה שהמערכת ביצעה: משיכות, בדיקות, החזרות ושגיאות.")}
        <section class="panel"><div class="panel-body" style="padding-block:4px">${logHTML(50)}</div></section>`;
    },

    "/settings"() {
      const steps = [
        { t: "משיכה מהאוניברסיטה", d: "חיבור ל-API של אתר הקורסים: רשימת הגשות, קבצים ופרטי סטודנט.", tag: "בפיתוח", todo: true },
        { t: "בדיקה וציון", d: "שליחת כל עבודה ל-Claude יחד עם המחוון והדגשים, וקבלת ציון והערות במבנה קבוע.", tag: "בפיתוח", todo: true },
        { t: "סימון ואישור", d: "הצגת ההערות על גבי העבודה ואישור או תיקון של המתרגל לפני ששולחים.", tag: "שלד מוכן", todo: false },
        { t: "החזרה לאתר", d: "העלאת הציון, ההערות והקובץ המסומן חזרה לאתר האוניברסיטה.", tag: "בפיתוח", todo: true },
      ];
      return `
        ${pageHead("חיבורים והגדרות", "איך המערכת מתחברת לאתר האוניברסיטה ול-Claude, ומה מותר לה לעשות לבד.",
          `<button class="btn primary" data-act="save-settings">${ICON.check}שמור הגדרות</button>`)}
        <div class="flow">
          ${steps.map((s, i) => `<div class="flow-step"><span class="stage-no">${i + 1}</span><h3>${s.t}</h3><p>${s.d}</p><span class="tag ${s.todo ? "todo" : ""}">${s.tag}</span></div>`).join("")}
        </div>
        <div class="grid-2">
          <div class="stack">
            <section class="panel">
              <div class="panel-head"><h2>מערכת האוניברסיטה</h2><span class="end status returned">מחובר</span></div>
              <div class="panel-body form-grid">
                <div class="field full"><label for="f-url">כתובת האתר</label><input id="f-url" class="ltr" value="https://moodle.bgu.ac.il" dir="ltr"></div>
                <div class="field"><label for="f-token">מפתח גישה</label><input id="f-token" type="password" placeholder="יוגדר בשרת, לא בדפדפן" disabled></div>
                <div class="field"><label for="f-sync">תדירות משיכה</label><select id="f-sync"><option>כל 15 דקות</option><option selected>כל שעה</option><option>ידנית בלבד</option></select></div>
              </div>
            </section>
            <section class="panel">
              <div class="panel-head"><h2>Claude</h2><span class="end status returned">פעיל</span></div>
              <div class="panel-body form-grid">
                <div class="field"><label for="f-model">מודל</label><select id="f-model" dir="ltr"><option>claude-opus-5-5</option><option>claude-sonnet-5-5</option><option>claude-haiku-5-5</option></select><p class="hint">Opus לבדיקה מעמיקה, Haiku לבדיקות מהירות וזולות.</p></div>
                <div class="field"><label for="f-par">עבודות במקביל</label><input id="f-par" type="number" value="5" min="1" max="20"></div>
              </div>
            </section>
          </div>
          <section class="panel">
            <div class="panel-head"><h3>מדיניות</h3></div>
            <div class="panel-body" style="padding-block:4px">
              ${[
                ["אישור מתרגל לפני החזרה", "שום ציון לא נשלח לסטודנט בלי שמתרגל אישר אותו", true],
                ["סימון חשד להעתקה", "השוואה בין הגשות באותה מטלה", true],
                ["החזרה אוטומטית מעל 90", "ציונים גבוהים בלי הערות פתוחות יוחזרו מיד", false],
                ["הודעה לסטודנט", "מייל כשהציון מתפרסם באתר", false],
              ].map(([t, d, on], i) => `<div class="switch-row"><div><b id="sw${i}">${t}</b><small>${d}</small></div><span class="switch"><input type="checkbox" ${on ? "checked" : ""} aria-labelledby="sw${i}"><i></i></span></div>`).join("")}
            </div>
          </section>
        </div>`;
    },
  };

  // ---------- Drawer ----------
  function breakdownFor(score) {
    const base = D.breakdown, crit = D.rubric.criteria;
    const baseTotal = Object.values(base).reduce((a, b) => a + b, 0);
    const pts = crit.map((c) => Math.min(c.weight, Math.round((base[c.key] * score) / baseTotal)));
    let diff = score - pts.reduce((a, b) => a + b, 0);
    for (let i = 0; diff !== 0 && i < 20; i++) {
      const k = i % crit.length;
      if (diff > 0 && pts[k] < crit[k].weight) { pts[k]++; diff--; }
      else if (diff < 0 && pts[k] > 0) { pts[k]--; diff++; }
    }
    return crit.map((c, i) => ({ ...c, pts: pts[i] }));
  }

  function drawerHTML(s) {
    const head = `
      <div class="drawer-head">
        <div>
          <h2>${esc(s.name)}</h2>
          <div class="sub"><span class="num">ת.ז. ${s.studentId}</span><span>הוגשה ${fmt(s.submittedAt)}</span>${statusPill(s.status)}</div>
        </div>
        <button class="btn ghost close" data-act="close" aria-label="סגור">${ICON.close}</button>
      </div>`;

    if (s.status === "received" || s.status === "grading" || s.status === "error") {
      const msg = {
        received: ["העבודה עוד לא נבדקה", "היא נמשכה מהאוניברסיטה ומחכה בתור לבדיקה."],
        grading: ["Claude בודק את העבודה עכשיו", "ההערות והציון יופיעו כאן בעוד כמה שניות."],
        error: ["הקובץ לא נפתח", "הקובץ שהוגש פגום או בפורמט שלא נתמך. אפשר לנסות שוב או לבדוק ידנית."],
      }[s.status];
      return `${head}
        <div class="drawer-body" style="grid-template-columns:1fr">
          <div class="empty panel"><strong>${msg[0]}</strong>${msg[1]}</div>
        </div>
        <div class="drawer-foot">
          <span class="grow"></span>
          ${s.status !== "grading" ? `<button class="btn primary" data-act="regrade" data-id="${s.id}">${ICON.grade}${s.status === "error" ? "נסה שוב" : "בדוק עכשיו"}</button>` : ""}
        </div>`;
    }

    const bd = breakdownFor(s.score);
    const marks = D.sampleCode.filter((l) => l.mark).length;
    return `${head}
      <div class="drawer-body">
        <div>
          <div class="paper-sheet">
            <div class="file-bar">${ICON.file}<span class="ltr">${esc(s.file)}</span><span style="margin-inline-start:auto">${marks} הערות סומנו</span></div>
            <div class="code">
              ${D.sampleCode.map((l) => `
                <div class="ln ${l.mark ? "marked" : ""}"><span class="n">${l.n}</span><pre>${esc(l.code) || " "}</pre></div>
                ${l.mark ? `<div class="note"><b>שורה ${l.n}:</b> ${esc(l.mark).replace(/`([^`]+)`/g, "<code dir=\"ltr\">$1</code>")}</div>` : ""}`).join("")}
            </div>
          </div>
          <div class="feedback">
            <h3>${ICON.pen}משוב לסטודנט</h3>
            <textarea aria-label="משוב לסטודנט">${esc(D.feedback)}</textarea>
            <p class="hint">נכתב ע״י Claude לפי הדגשים. אפשר לערוך לפני ההחזרה.</p>
          </div>
        </div>
        <aside>
          <div class="grade-card">
            <div class="grade-ring">
              <span class="big">${s.score}</span>
              <span class="lbl"><b>ציון מוצע</b>מתוך 100</span>
            </div>
            <ul class="breakdown">
              ${bd.map((c) => `<li><div class="row"><span>${c.name}</span><b>${c.pts}/${c.weight}</b></div><div class="track"><i class="${c.pts / c.weight < 0.75 ? "short" : ""}" style="width:${(c.pts / c.weight) * 100}%"></i></div></li>`).join("")}
            </ul>
            <div class="override">
              <label for="override">תיקון ציון ידני</label>
              <input id="override" type="number" min="0" max="100" placeholder="${s.score}" ${s.status === "returned" ? "disabled" : ""}>
            </div>
            <div class="student-card">
              <div><span>דוא״ל</span><span class="ltr" style="color:var(--ink)">${esc(s.email)}</span></div>
              <div><span>מזהה הגשה</span><span class="num" style="color:var(--ink)">${s.id}</span></div>
              ${s.flags.length ? `<div><span>הערות מערכת</span><span>${s.flags.map((f) => `<span class="flag">${esc(f)}</span>`).join("")}</span></div>` : ""}
            </div>
          </div>
        </aside>
      </div>
      <div class="drawer-foot">
        ${s.status === "returned"
          ? `<span class="grow">הציון וההערות כבר נשלחו לאתר האוניברסיטה.</span><button class="btn secondary" data-act="close">סגור</button>`
          : `<span class="grow">אחרי האישור, הציון וההערות יעלו לאתר האוניברסיטה.</span>
             <button class="btn secondary" data-act="regrade" data-id="${s.id}">${ICON.redo}בדיקה חוזרת</button>
             <button class="btn primary" data-act="approve" data-id="${s.id}">${ICON.check}אשר והחזר</button>`}
      </div>`;
  }

  let lastFocus = null;
  function openDrawer(id) {
    const s = state.subs.find((x) => x.id === id);
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
    setTimeout(() => $(".close", d)?.focus(), 50);
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

  // ---------- Render ----------
  function route() { return (location.hash.replace(/^#/, "") || "/").split("?")[0]; }

  function render() {
    const r = views[route()] ? route() : "/";
    $("#main").innerHTML = views[r]();
    $$(".nav a").forEach((a) => (a.dataset.route === r ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    const pending = state.subs.filter((s) => s.status === "review").length;
    $("#nav-count-review").textContent = pending || "";
    // "fresh" מסמן אנימציה רק לרינדור אחד
    state.subs.forEach((s) => (s.fresh = false));
  }

  // ---------- Events ----------
  document.addEventListener("click", (e) => {
    const act = e.target.closest("[data-act]");
    if (act) {
      const a = act.dataset.act;
      if (a === "pull") pull();
      else if (a === "grade") grade();
      else if (a === "return") returnApproved();
      else if (a === "close") closeDrawer();
      else if (a === "approve") approveOne(act.dataset.id);
      else if (a === "regrade") regradeOne(act.dataset.id);
      else if (a === "save-rubric") toast("המחוון נשמר");
      else if (a === "save-settings") toast("ההגדרות נשמרו");
      return;
    }
    const chip = e.target.closest("[data-filter]");
    if (chip) { state.filter = chip.dataset.filter; render(); return; }
    const row = e.target.closest("[data-open]");
    if (row) { openDrawer(row.dataset.open); return; }
    if (e.target.id === "scrim") closeDrawer();
    if (e.target.closest(".nav a")) $(".sidebar").classList.remove("open");
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeDrawer(); $(".sidebar").classList.remove("open"); }
    if (e.key === "Enter" && e.target.matches("tr[data-open]")) openDrawer(e.target.dataset.open);
  });

  document.addEventListener("input", (e) => {
    if (e.target.matches("[data-weight]")) {
      D.rubric.criteria[+e.target.dataset.weight].weight = Number(e.target.value) || 0;
      const total = D.rubric.criteria.reduce((a, c) => a + c.weight, 0);
      const line = $("#total-line");
      line.classList.toggle("bad", total !== 100);
      line.lastElementChild.textContent = `${total}%`;
    }
  });

  $("#search").addEventListener("input", (e) => {
    state.query = e.target.value;
    if (route() === "/rubric" || route() === "/runs" || route() === "/settings") location.hash = "#/submissions";
    render();
    $("#search").focus();
  });

  const sel = $("#course-select");
  sel.innerHTML = D.courses.map((c) => `<option value="${c.id}">${esc(c.course)}: ${esc(c.assignment)}</option>`).join("");
  sel.addEventListener("change", () => { state.courseId = sel.value; state.filter = "all"; render(); });

  $("#menu-btn").addEventListener("click", () => $(".sidebar").classList.toggle("open"));

  // ערכת צבעים
  const themeBtn = $("#theme-btn");
  const applyTheme = (t) => { if (t) document.documentElement.dataset.theme = t; };
  try { applyTheme(localStorage.getItem("ac-theme")); } catch {}
  themeBtn.addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("ac-theme", next); } catch {}
  });

  window.addEventListener("hashchange", () => { closeDrawer(); render(); window.scrollTo(0, 0); });
  render();
})();
