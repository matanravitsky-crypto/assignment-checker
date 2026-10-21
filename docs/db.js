// מסד הנתונים המשותף (Supabase): התחברות עם GitHub, טעינה, שמירה ועדכונים חיים.
//
// מצבים (DB.mode):
//   off      אין הגדרות חיבור ב-config.js, האתר במצב הדגמה
//   guest    יש חיבור, אבל המשתמש לא התחבר: רואה הדגמה
//   outsider התחבר עם GitHub אבל לא ברשימת הצוות: רואה הדגמה
//   team     חבר צוות: קורא וכותב למסד המשותף
window.DB = (() => {
  const cfg = window.APP_CONFIG || {};
  const configured = !!(cfg.supabaseUrl && cfg.supabaseAnonKey && window.supabase);
  const TABLES = ["members", "courses", "assignments", "rubrics", "submissions", "stage_instructions", "settings", "runs"];

  let sb = null;
  let user = null, login = null, member = false, admin = false;
  let changes = null, presence = null;
  const listeners = new Set();
  const emit = (type, data) => listeners.forEach((fn) => fn(type, data));
  const must = ({ data, error }) => { if (error) throw new Error(error.message); return data; };

  // ---------- המרה בין האתר למסד ----------
  const toSub = (r) => ({
    id: r.id, assignmentId: r.assignment_id, name: r.student_name, studentId: r.student_id, email: r.email,
    submittedAt: r.submitted_at, late: r.late, scanned: r.scanned, files: r.files || [], status: r.status,
    q: r.q, score: r.score, issue: r.issue, feedback: r.feedback, updatedBy: r.updated_by,
  });
  const fromSub = (s, assignmentId) => ({
    id: s.id, assignment_id: assignmentId, student_name: s.name, student_id: s.studentId, email: s.email,
    submitted_at: s.submittedAt, late: !!s.late, scanned: !!s.scanned, files: s.files, status: s.status,
    q: s.q, score: s.score, issue: s.issue, feedback: s.feedback,
  });
  const toAssignment = (r) => ({
    id: r.id, courseId: r.course_id, n: r.n, title: r.title, due: r.due, phase: r.phase,
    pulledAt: r.pulled_at, gradedAt: r.graded_at, returnedAt: r.returned_at, lastFresh: r.last_fresh,
    solutionFile: r.solution_file, solutionPath: r.solution_path, subs: [],
  });
  const fromAssignment = (A) => ({
    id: A.id, course_id: A.courseId, n: A.n, title: A.title, due: new Date(A.due).toISOString(), phase: A.phase,
    pulled_at: A.pulledAt, graded_at: A.gradedAt, returned_at: A.returnedAt, last_fresh: A.lastFresh,
    solution_file: A.solutionFile ?? null, solution_path: A.solutionPath ?? null,
  });
  const toRun = (r) => ({ id: r.id, at: r.at, kind: r.kind, text: r.text, where: r.where_text, actor: r.actor });

  async function all(table, order) {
    const out = [];
    for (let from = 0; ; from += 1000) {
      let q = sb.from(table).select("*");
      if (order) q = q.order(order, { ascending: true });
      const rows = must(await q.range(from, from + 999));
      out.push(...rows);
      if (rows.length < 1000) return out;
    }
  }
  async function upsert(table, rows) {
    for (let i = 0; i < rows.length; i += 500) must(await sb.from(table).upsert(rows.slice(i, i + 500)));
  }

  async function resolveUser(session) {
    user = session?.user || null;
    login = null; member = false; admin = false;
    if (!user) return;
    const [l, m, a] = await Promise.all([sb.rpc("current_github_login"), sb.rpc("is_member"), sb.rpc("is_admin")]);
    login = l.data || user.user_metadata?.user_name || null;
    member = !!m.data;
    admin = !!a.data;
  }

  function subscribe() {
    if (changes) return;
    changes = sb.channel("db-changes");
    TABLES.forEach((table) => changes.on("postgres_changes", { event: "*", schema: "public", table }, (p) =>
      emit("change", { table, type: p.eventType, row: p.new, old: p.old })));
    changes.subscribe();

    presence = sb.channel("online", { config: { presence: { key: login } } });
    presence.on("presence", { event: "sync" }, () => {
      const people = Object.values(presence.presenceState()).map((list) => list[0]).filter(Boolean);
      emit("presence", people);
    });
    presence.subscribe(async (status) => {
      if (status === "SUBSCRIBED") await presence.track({ login, avatar: user.user_metadata?.avatar_url || null, since: Date.now() });
    });
  }

  return {
    configured,
    get mode() { return !configured ? "off" : !user ? "guest" : member ? "team" : "outsider"; },
    get login() { return login; },
    get avatar() { return user?.user_metadata?.avatar_url || (login ? `https://github.com/${login}.png?size=80` : null); },
    get admin() { return admin; },
    get url() { return cfg.supabaseUrl; },
    on(fn) { listeners.add(fn); },
    toSub, toRun, toAssignment,

    async init() {
      if (!configured) return;
      sb = window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseAnonKey, {
        auth: { flowType: "pkce", detectSessionInUrl: true, persistSession: true },
      });
      const { data } = await sb.auth.getSession();
      // אחרי החזרה מ-GitHub הכתובת מכילה ?code=..., מנקים אותה
      if (/[?&]code=/.test(location.search)) history.replaceState(null, "", location.pathname + location.hash);
      await resolveUser(data.session);
      sb.auth.onAuthStateChange((_event, session) => {
        if ((session?.user?.id || null) === (user?.id || null)) return;
        resolveUser(session).then(() => emit("auth"));
      });
      if (member) subscribe();
    },

    signIn() {
      return sb.auth.signInWithOAuth({ provider: "github", options: { redirectTo: location.origin + location.pathname } });
    },
    async signOut() {
      await sb.auth.signOut();
      location.reload();
    },

    async loadAll() {
      const [courses, assignments, rubrics, subs, instr, settings, members, runs] = await Promise.all([
        all("courses", "id"), all("assignments", "id"), all("rubrics"), all("submissions", "submitted_at"),
        all("stage_instructions"), all("settings"), all("members", "github_username"),
        sb.from("runs").select("*").order("at", { ascending: false }).limit(300).then(must),
      ]);
      const byId = Object.fromEntries(assignments.map((r) => [r.id, toAssignment(r)]));
      subs.forEach((r) => byId[r.assignment_id]?.subs.push(toSub(r)));
      return {
        courses: courses.map((c) => ({ id: c.id, name: c.name })),
        assignments: Object.values(byId),
        rubrics: Object.fromEntries(rubrics.map((r) => [r.course_id, { questions: r.questions, emphases: r.emphases }])),
        instructions: Object.fromEntries(instr.map((r) => [r.stage, { body: r.body, by: r.updated_by, at: r.updated_at }])),
        settings: Object.fromEntries(settings.map((r) => [r.key, r.value])),
        members, runs: runs.map(toRun),
      };
    },

    // ---------- שמירה ----------
    saveSubmissions: (A, subs) => upsert("submissions", subs.map((s) => fromSub(s, A.id))),
    saveAssignment: (A) => upsert("assignments", [fromAssignment(A)]),
    saveRubric: (courseId, r) => upsert("rubrics", [{ course_id: courseId, questions: r.questions, emphases: r.emphases }]),
    saveInstruction: (stage, body) => upsert("stage_instructions", [{ stage, body }]),
    saveSetting: (key, value) => upsert("settings", [{ key, value }]),
    async addRun(run) {
      const row = must(await sb.from("runs").insert({ at: run.at, kind: run.kind, text: run.text, where_text: run.where }).select().single());
      return toRun(row);
    },

    // ---------- צוות ----------
    async addMember(username, role = "staff") { must(await sb.from("members").insert({ github_username: username.trim(), role })); },
    async removeMember(username) { must(await sb.from("members").delete().eq("github_username", username)); },
    async listMembers() { return all("members", "github_username"); },

    // ---------- קבצים ----------
    async uploadSolution(A, file) {
      const path = `${A.id}/${Date.now()}-${file.name.replace(/[^\w.\-]+/g, "_")}`;
      must(await sb.storage.from("solutions").upload(path, file, { upsert: true, contentType: file.type || "application/pdf" }));
      return path;
    },
    async solutionUrl(path) {
      return must(await sb.storage.from("solutions").createSignedUrl(path, 3600)).signedUrl;
    },

    // ---------- נתוני דוגמה ----------
    async seed(demo) {
      await upsert("courses", demo.courses.map((c) => ({ id: c.id, name: c.name })));
      await upsert("assignments", demo.assignments.map(fromAssignment));
      await upsert("rubrics", Object.entries(demo.rubrics).map(([id, r]) => ({ course_id: id, questions: r.questions, emphases: r.emphases })));
      await upsert("submissions", demo.assignments.flatMap((A) => A.subs.map((s) => fromSub(s, A.id))));
      await upsert("stage_instructions", Object.entries(demo.instructions).map(([stage, body]) => ({ stage, body })));
      await upsert("settings", Object.entries(demo.settings).map(([key, value]) => ({ key, value })));
      for (const r of [...demo.runs].reverse()) must(await sb.from("runs").insert({ at: r.at, kind: r.kind, text: r.text, where_text: r.where }));
    },
    async wipe() {
      must(await sb.from("runs").delete().gte("id", 0));
      must(await sb.from("courses").delete().neq("id", ""));
      must(await sb.from("stage_instructions").delete().neq("stage", ""));
      must(await sb.from("settings").delete().neq("key", ""));
    },
  };
})();
