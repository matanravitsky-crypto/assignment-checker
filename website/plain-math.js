// רכיב "מתמטיקה קריאה": הופך הערה עם LaTeX ("כמו $\{1,2\}\neq\varnothing$") למשפט עברי רגיל עם סימנים רגילים ("{1,2} ≠ ∅").
// העברית נשארת מימין לשמאל, כל ביטוי מתמטי מוצג משמאל לימין באותה שורה (<bdi dir="ltr">), בלי סימני $.
// הערה שנחתכה באמצע נוסחה ($ שנפתח ולא נסגר) מסתיימת ב"…" לפני הנוסחה השבורה, ולא מציגה קוד.
// הרכיב עצמאי: מקבל טקסט (ופונקציית הימלטות) ומחזיר HTML. לא קורא נתונים בעצמו, ו-app.js רק קורא לו.
(function (root) {
  // סוג הטעות נחתך ל-80 תווים בשמירה (grading/grade.py, _mistakes). טקסט באורך הזה או יותר נחתך כנראה באמצע
  const CUT_AT = 80;

  const SYMBOLS = {
    neq: "≠", ne: "≠", infty: "∞", varnothing: "∅", emptyset: "∅", cap: "∩", cup: "∪", in: "∈", notin: "∉",
    subseteq: "⊆", subset: "⊂", supseteq: "⊇", supset: "⊃", setminus: "∖", cdot: "·", times: "×", div: "÷",
    leq: "≤", le: "≤", geq: "≥", ge: "≥", pm: "±", mp: "∓", to: "→", rightarrow: "→", leftarrow: "←",
    Rightarrow: "⇒", Leftarrow: "⇐", Leftrightarrow: "⇔", iff: "⇔", implies: "⇒", forall: "∀", exists: "∃",
    land: "∧", lor: "∨", neg: "¬", lnot: "¬", sum: "Σ", alpha: "α", beta: "β", gamma: "γ", delta: "δ", lambda: "λ",
    mu: "μ", pi: "π", theta: "θ", sigma: "σ", omega: "ω", ldots: "…", dots: "…", cdots: "⋯", circ: "∘", perp: "⊥",
    parallel: "∥", approx: "≈", equiv: "≡", sim: "∼", angle: "∠", vec: "", overline: "", left: "", right: "",
  };
  const RELATIONS = new Set(["neq", "ne", "leq", "le", "geq", "ge", "in", "notin", "subseteq", "subset", "supseteq",
    "supset", "to", "rightarrow", "leftarrow", "Rightarrow", "Leftarrow", "Leftrightarrow", "iff", "implies", "approx",
    "equiv"]);
  const BLACKBOARD = { R: "ℝ", C: "ℂ", N: "ℕ", Z: "ℤ", Q: "ℚ" };
  const SUP = { 0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹", n: "ⁿ", "-": "⁻" };

  // ביטוי LaTeX אחד -> טקסט עם סימנים רגילים
  function symbols(src) {
    let s = String(src);
    s = s.replace(/\\mathbb\s*\{([A-Z])\}/g, (_, x) => BLACKBOARD[x] || x);
    s = s.replace(/\\(?:mathbf|mathrm|mathcal|text|textbf|operatorname)\s*\{([^{}]*)\}/g, "$1");
    s = s.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, "($1)/($2)");
    s = s.replace(/\\sqrt\s*\{([^{}]*)\}/g, "√($1)");
    s = s.replace(/\^\{?(-?[0-9n]+)\}?/g, (_, d) => [...d].map((c) => SUP[c]).join(""));
    s = s.replace(/_\{([^{}]*)\}/g, "_$1");
    s = s.replace(/\\([\{\}\(\)\[\]])/g, "$1");       // \{ \} \( \) -> { } ( )
    s = s.replace(/\\[,;:! ]/g, " ");                 // רווחי LaTeX
    // LaTeX בולע רווח אחרי שם פקודה; יחסים (≠, ∈, ⇒...) מקבלים רווח משני הצדדים, כדי שיהיו קריאים
    s = s.replace(/\\([A-Za-z]+)\s?/g, (_, name) => {
      if (!(name in SYMBOLS)) return name;
      return RELATIONS.has(name) ? ` ${SYMBOLS[name]} ` : SYMBOLS[name];
    });
    s = s.replace(/\\/g, "");
    return s.replace(/\s+/g, " ").trim();
  }

  // טקסט עם $...$ ו-$$...$$ -> [{ math: bool, text }]. $ שנפתח ולא נסגר: מה שאחריו נחתך, ו-cut=true
  function parts(str) {
    const text = String(str ?? "");
    const out = [];
    const re = /\$\$([\s\S]+?)\$\$|\$([^$]+?)\$/g;
    let last = 0, m, cut = false;
    while ((m = re.exec(text))) {
      if (m.index > last) out.push({ math: false, text: text.slice(last, m.index) });
      out.push({ math: true, text: symbols(m[1] ?? m[2]) });
      last = re.lastIndex;
    }
    let rest = text.slice(last);
    const dangling = rest.indexOf("$");
    if (dangling !== -1) { rest = rest.slice(0, dangling); cut = true; }
    if (rest) out.push({ math: false, text: rest });
    if (!cut && text.length >= CUT_AT && !/[.!?…)]$/.test(text.trim())) cut = true;
    return { parts: out, cut };
  }

  // אותו טקסט כטקסט רגיל (לבדיקות ולהעתקה)
  function plain(str) {
    const { parts: ps, cut } = parts(str);
    const s = ps.map((p) => p.text).join("").replace(/\s+/g, " ").trim();
    return cut ? `${s.replace(/[\s,;:-]+$/, "")}…` : s;
  }

  // ה-HTML של הרכיב. esc: פונקציית ההימלטות של האתר
  function html(str, esc) {
    const e = esc || ((s) => String(s));
    const { parts: ps, cut } = parts(str);
    const body = ps.map((p) => (p.math ? `<bdi class="pm" dir="ltr">${e(p.text)}</bdi>` : e(p.text))).join("");
    return cut ? `${body.replace(/[\s,;:-]+$/, "")}…` : body;
  }

  const api = { symbols, parts, plain, html, CUT_AT };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PlainMath = api;
})(typeof window !== "undefined" ? window : globalThis);
