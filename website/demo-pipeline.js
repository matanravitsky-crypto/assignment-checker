// הדמיה של שלושת השלבים, לאתר הציבורי בלבד (Vercel).
// בגרסה המחוברת (start.bat) הכפתורים פונים לשרת המקומי (dashboard/web_server.py): /api/pull ו-/api/return,
// שמפעילים את הקוד האמיתי ב-moodle/. ראו runLocalPull ו-runLocalReturn ב-app.js.
window.PipelineAPI = (() => {
  const D = window.DEMO;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const step = async (onStep, i, ms, work) => { onStep(i, "running"); await wait(ms); const out = work?.(); onStep(i, "done"); return out; };

  return {
    mode: "demo",

    async pull(A, ctx, onStep) {
      await step(onStep, 0, 700);
      const fresh = await step(onStep, 1, 900, () => D.newSubmissions(A, A.subs.length ? 1 + Math.floor(Math.random() * 3) : 21 + Math.floor(Math.random() * 6)));
      await step(onStep, 2, 1000);
      await step(onStep, 3, 650);
      return fresh;
    },

    async grade(A, subs, ctx, onStep, onItem) {
      await step(onStep, 0, 600);
      await step(onStep, 1, 500, () => subs.forEach((s) => { s.status = "grading"; onItem(s); }));
      onStep(2, "running");
      for (const s of subs) {
        await wait(420);
        D.gradeSubmission(s);
        onItem(s);
      }
      onStep(2, "done");
      await step(onStep, 3, 550);
    },

    async returnGrades(A, subs, ctx, onStep, onItem) {
      await step(onStep, 0, 800);
      onStep(1, "running");
      for (const s of subs) {
        await wait(160);
        s.status = "returned";
        onItem(s);
      }
      onStep(1, "done");
      await step(onStep, 2, 800);
      await step(onStep, 3, 600);
    },
  };
})();
