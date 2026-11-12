// רכיב "חלוקת הניקוד": מציג את המחוון כרשימה כתובה, שאלה אחר שאלה, ומתחת לכל שאלה הסעיפים שלה עם הניקוד.
//   שאלה 11 (קבוצות) - 20 נקודות סך הכל
//   שאלה 11 סעיף א - 3 נקודות
// הרכיב עצמאי: מקבל רשימת סעיפי המחוון ({ req: "קבוצות 11א", pts: 3 }) ומחזיר טקסט או HTML. לא קורא נתונים בעצמו,
// כך שאפשר להזיז אותו, להחליף אותו או להסיר אותו בלי לגעת בשאר האתר. app.js רק קורא לו.
(function (root) {
  const pts = (n) => `${n} ${n === 1 ? "נקודה" : "נקודות"}`;

  // "קבוצות 11א" -> נושא "קבוצות", שאלה "11", סעיף "א". "8א" -> בלי נושא. "16" -> שאלה בלי סעיפים. אחרת: null
  function parseLabel(label) {
    const m = String(label ?? "").trim().match(/^(.*?)\s*(\d+)\s*([א-ת]\d*)?$/);
    return m ? { topic: m[1].trim(), num: m[2], sub: m[3] || "" } : null;
  }

  // מחבר סעיפים רצופים של אותה שאלה: [{ title, num, topic, total, parts: [{ sub, pts }] }]. סעיף שאי אפשר לפרק עומד לבד
  function group(items) {
    const out = [];
    for (const it of items || []) {
      const p = parseLabel(it.req);
      const total = Number(it.pts) || 0;
      if (!p) { out.push({ title: String(it.req ?? ""), num: "", topic: "", total, parts: [], plain: true }); continue; }
      const last = out[out.length - 1];
      if (last && !last.plain && last.num === p.num && last.topic === p.topic) { last.total += total; last.parts.push({ sub: p.sub, pts: total }); continue; }
      out.push({ title: "", num: p.num, topic: p.topic, total, parts: [{ sub: p.sub, pts: total }] });
    }
    return out;
  }

  const heading = (g) => g.plain ? g.title : `שאלה ${g.num}${g.topic ? ` (${g.topic})` : ""}`;

  // אותה רשימה כשורות טקסט (לבדיקות ולהעתקה)
  function lines(items) {
    const out = [];
    for (const g of group(items)) {
      const h = heading(g);
      if (g.plain || (g.parts.length === 1 && !g.parts[0].sub)) { out.push(`${h} - ${pts(g.total)}`); continue; }
      out.push(`${h} - ${pts(g.total)} סך הכל`);
      for (const p of g.parts) out.push(`שאלה ${g.num} סעיף ${p.sub} - ${pts(p.pts)}`);
    }
    return out;
  }

  // ה-HTML של הרכיב. esc: פונקציית ההימלטות של האתר
  function html(items, esc) {
    const e = esc || ((s) => String(s));
    const total = (items || []).reduce((a, it) => a + (Number(it.pts) || 0), 0);
    const rows = [];
    for (const g of group(items)) {
      const h = heading(g);
      if (g.plain || (g.parts.length === 1 && !g.parts[0].sub)) { rows.push(`<li class="rp-q"><b>${e(h)}</b> - ${e(pts(g.total))}</li>`); continue; }
      rows.push(`<li class="rp-q"><b>${e(h)}</b> - ${e(pts(g.total))} סך הכל</li>`);
      for (const p of g.parts) rows.push(`<li class="rp-s">שאלה ${e(g.num)} סעיף ${e(p.sub)} - ${e(pts(p.pts))}</li>`);
    }
    return `<ul class="rp">${rows.join("")}<li class="rp-total"><b>סך הכל במחוון</b> - ${e(pts(total))}</li></ul>`;
  }

  const api = { parseLabel, group, lines, html };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.RubricPoints = api;
})(typeof window !== "undefined" ? window : globalThis);
