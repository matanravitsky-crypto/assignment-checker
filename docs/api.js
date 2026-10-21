// שכבת החיבור בין המסך לצד השרת.
//
// כרגע הכל מדומה בדפדפן (mode: "demo"). כשיהיה צד שרת, כל פונקציה כאן תוחלף
// בקריאה אמיתית, והמסך לא ישתנה:
//   pull         → POST /api/pull    { assignmentId, instructions }        מושך הגשות ממודל
//   grade        → POST /api/grade   { assignmentId, ids, rubric, ... }    שולח עבודות ל-Claude
//   returnGrades → POST /api/return  { assignmentId, ids, format }         מעלה ציונים וקבצים למודל
//
// כל פונקציה מדווחת התקדמות דרך onStep(index, "running" | "done") לפי שלבי הריצה,
// ומעדכנת עבודות בודדות דרך onItem(submission).
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
