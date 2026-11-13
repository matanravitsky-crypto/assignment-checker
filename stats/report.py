"""דוח הבדיקה של מטלה אחת כ-PDF לצוות: `python -m stats report <מזהה מטלה> [--pdf <נתיב>]`.

הכול מהמסד (`stats.read`): היקף וזמן, עלות וטוקנים לפי מודל, ציונים והתפלגות, ניקוד לכל סעיף, טעויות נפוצות,
השוואה לבדיקה ישנה שהועברה הצידה, ותובנות שעולות מהמספרים. מספרים בלבד: אין מספרי הגשה, אין שמות.
הגרפים ב-matplotlib (PNG), העמודים ב-PyMuPDF Story (HTML עם כיוון ימין-לשמאל וגופן Arial מ-Windows; בלי Windows,
הגופן של המערכת). הקובץ נשמר ליד ה-JSON של המטלה: "Statistics/<קורס>/Assignment N - grading report <תאריך>.pdf".
"""
from __future__ import annotations

import gc
import html
import io
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path

from moodle import paths

from . import compute as _compute
from . import read
from .store import stats_dir

FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"   # Arial: גופן עברי שנמצא בכל Windows
FONT_FILES = {"regular": "arial.ttf", "bold": "arialbd.ttf"}
# הצבעים: מערכת אחת לכל הגרפים (dataviz): כחול אחד לכמות, כתום לסדרה שנייה, אפור לטקסט משני
BLUE, BLUE_DARK, BLUE_LIGHT, ORANGE, AQUA, YELLOW = "#2a78d6", "#184f95", "#9ec5f4", "#eb6834", "#1baf7a", "#eda100"
INK, INK_2, RULE, SURFACE = "#0b0b0b", "#52514e", "#d9d8d3", "#fcfcfb"
PAGE = "a4"
MARGIN = 42
MAX_PAGES = 40
TOP_MISTAKES = 3          # כמה טעויות לכל שאלה בטבלה
CHART_MISTAKES = 10       # כמה טעויות בגרף
TEXT_WIDTH = 60           # אורך ניסוח טעות בגרף, בתווים


# ---------- עזרים ----------

def _fmt(x, digits: int = 1, suffix: str = "") -> str:
    if x is None:
        return "—"
    if isinstance(x, float) and not float(x).is_integer():
        return f"{x:,.{digits}f}{suffix}"
    return f"{int(x):,}{suffix}"


def _pct(x) -> str:
    return "—" if x is None else f"{_fmt(x, 0)}%"


def _usd(x, digits: int = 2) -> str:
    return "—" if x is None else f"${x:,.{digits}f}"


def _span(a: str | None, b: str | None) -> str:
    """"מ-23/10/2026 עד 30/10/2026", או יום אחד "11/11/2026, 13:35 עד 14:49"."""
    try:
        ta, tb = datetime.fromisoformat(str(a)), datetime.fromisoformat(str(b))
    except (TypeError, ValueError):
        return "—"
    if ta.date() == tb.date():
        return f"{_ltr(ta.strftime('%d/%m/%Y'))}, {ta.strftime('%H:%M')} עד {tb.strftime('%H:%M')}"
    return f"מ-{_ltr(ta.strftime('%d/%m/%Y'))} עד {_ltr(tb.strftime('%d/%m/%Y'))}"


def _when(s: str | None, with_date: bool = True) -> str:
    try:
        t = datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return "—"
    return _ltr(t.strftime("%d/%m/%Y %H:%M") if with_date else t.strftime("%H:%M"))


def _ltr(s: str) -> str:
    """"11/11/2026 13:35" נשאר בסדר הזה גם בתוך טקסט עברי (שני רצפים של ספרות היו מתהפכים)."""
    return "\u202a" + s + "\u202c"


def _minutes(seconds) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    if s < 90:
        return f"{s} שניות"
    if s < 3600 * 2:
        return f"{s // 60} דקות"
    return f"{s / 3600:.1f} שעות"


def _tokens(n) -> str:
    if n is None:
        return "—"
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1000:.0f}K"
    return f"{n:,}"


def _h(s) -> str:
    return html.escape(str(s if s is not None else "—"))


LATEX = [("\\mathbb R", "ℝ"), ("\\mathbb{R}", "ℝ"), ("\\mathbb C", "ℂ"), ("\\mathbb{C}", "ℂ"), ("\\varnothing", "∅"),
         ("\\emptyset", "∅"), ("\\notin", "∉"), ("\\in", "∈"), ("\\subseteq", "⊆"), ("\\subset", "⊂"), ("\\neq", "≠"),
         ("\\ne", "≠"), ("\\leq", "≤"), ("\\le", "≤"), ("\\geq", "≥"), ("\\ge", "≥"), ("\\cup", "∪"), ("\\cap", "∩"),
         ("\\setminus", "∖"), ("\\times", "×"), ("\\cdot", "·"), ("\\mid", "|"), ("\\sqrt", "√"), ("\\infty", "∞"),
         ("\\Rightarrow", "⇒"), ("\\Leftrightarrow", "⇔"), ("\\to", "→"), ("\\pm", "±"), ("\\left", ""), ("\\right", ""),
         ("\\{", "{"), ("\\}", "}"), ("\\,", " "), ("\\;", " "), ("\\ ", " ")]


def _plain(text: str) -> str:
    """ניסוח טעות מהמחוון, בלי LaTeX: "$A\\neq B$" → "A≠B"."""
    text = str(text)
    text = re.sub(r"\\(?:overline|bar)\{([^}]*)\}", "\\1̄", text)
    text = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"\1/\2", text)
    for a, b in LATEX:
        text = text.replace(a, b)
    text = re.sub(r"\\[A-Za-z]+", "", text).replace("\\", "")
    return re.sub(r"\s+", " ", text.replace("$", "")).strip()


def _short(text: str, width: int = TEXT_WIDTH) -> str:
    text = _plain(text)
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def _group(label: str) -> str:
    """"קבוצות 11א" → "קבוצות 11": הסעיפים של שאלה אחת מתקבצים לפי מספר השאלה; תווית בלי אות בסוף היא קבוצה לעצמה."""
    m = re.match(r"^(.*?\d+)\s*[א-ת]{1,2}['׳]?$", str(label))
    return m.group(1) if m else str(label)


def groups(per_question: list[dict]) -> list[tuple[str, list[dict]]]:
    out: list[tuple[str, list[dict]]] = []
    for q in per_question:
        g = _group(q["label"])
        if out and out[-1][0] == g:
            out[-1][1].append(q)
        else:
            out.append((g, [q]))
    return out


def _bidi(s: str) -> str:
    """טקסט עברי לגרף. matplotlib עד 3.10 מצייר משמאל לימין, אז מסדרים את האותיות בסדר התצוגה;
    מ-3.11 הוא מסדר בעצמו, וסידור כפול הופך את הטקסט."""
    try:
        import matplotlib
        if tuple(int(x) for x in matplotlib.__version__.split(".")[:2]) >= (3, 11):
            return s
        from bidi.algorithm import get_display
        return get_display(s)
    except Exception:  # noqa: BLE001  (python-bidi חסר: הטקסט יוצג הפוך, הגרף עדיין נבנה)
        return s


# ---------- גרפים (PNG) ----------

def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    regular = FONT_DIR / FONT_FILES["regular"]
    if regular.is_file():
        font_manager.fontManager.addfont(str(regular))
        bold = FONT_DIR / FONT_FILES["bold"]
        if bold.is_file():
            font_manager.fontManager.addfont(str(bold))
        plt.rcParams["font.family"] = [font_manager.FontProperties(fname=str(regular)).get_name(), "DejaVu Sans"]
    else:
        plt.rcParams["font.family"] = ["DejaVu Sans"]  # בלי Windows: יש בו אותיות עבריות
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": RULE, "axes.labelcolor": INK_2, "xtick.color": INK_2,
                         "ytick.color": INK_2, "axes.spines.top": False, "axes.spines.right": False,
                         "figure.facecolor": "white", "axes.facecolor": "white", "savefig.dpi": 200})
    return plt


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.08)
    import matplotlib.pyplot as plt
    plt.close(fig)
    return buf.getvalue()


def chart_histogram(grade: dict, max_grade) -> bytes | None:
    h = grade.get("histogram") or {}
    bins, counts = h.get("bins") or [], h.get("counts") or []
    if not bins or not any(counts):
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.4, 2.9))
    labels = [f"{b['from']}–{b['to'] - 1 if i < len(bins) - 1 else b['to']}" for i, b in enumerate(bins)]
    bars = ax.bar(range(len(bins)), counts, color=BLUE, width=0.78)
    ax.set_xticks(range(len(bins)), labels)
    ax.yaxis.grid(True, color=RULE, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    for b, c in zip(bars, counts):
        if c:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + max(counts) * 0.015, f"{c}", ha="center", va="bottom", fontsize=8, color=INK)
    if grade.get("mean") is not None and max_grade:
        x = grade["mean"] / max_grade * len(bins) - 0.5
        ax.axvline(x, color=INK_2, linestyle=(0, (3, 3)), linewidth=1)
        ax.text(0.02, 0.95, _bidi(f"- - - ממוצע {_fmt(grade['mean'])}"), transform=ax.transAxes, ha="left", va="top", fontsize=8, color=INK_2)
    ax.set_ylim(0, max(counts) * 1.18)
    ax.set_title(_bidi("עבודות לפי ציון"), fontsize=9, color=INK_2, loc="right")
    return _png(fig)


def chart_sections(per_question: list[dict]) -> bytes | None:
    qs = [q for q in per_question if q.get("success_pct") is not None]
    if not qs:
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.4, max(2.4, 0.26 * len(qs) + 0.8)))
    ys = list(range(len(qs)))[::-1]
    vals = [q["success_pct"] for q in qs]
    ax.barh(ys, vals, color=BLUE, height=0.68)
    ax.set_yticks(ys, [_bidi(q["label"]) for q in qs])
    ax.set_xlim(0, 112)
    ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.xaxis.grid(True, color=RULE, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines["left"].set_color(RULE)
    ax.tick_params(axis="y", length=0)
    for y, v, q in zip(ys, vals, qs):
        ax.text(v + 1.2, y, f"{v}%", va="center", fontsize=7.5, color=INK)
    # קו בין שאלה לשאלה
    pos = 0
    for _, items in groups(qs)[:-1]:
        pos += len(items)
        ax.axhline(len(qs) - pos - 0.5, color=RULE, linewidth=0.8)
    ax.set_xlabel(_bidi("אחוז ההצלחה הממוצע בסעיף"))
    return _png(fig)


def top_mistakes(per_question: list[dict], n: int = CHART_MISTAKES) -> list[dict]:
    rows = [{**m, "label": q["label"]} for q in per_question for m in q.get("mistakes") or []]
    rows.sort(key=lambda m: (-m["count"], m["label"], m["text"]))
    return rows[:n]


def chart_mistakes(per_question: list[dict]) -> bytes | None:
    rows = top_mistakes(per_question)
    if not rows:
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.4, max(2.2, 0.36 * len(rows) + 0.7)))
    ys = list(range(len(rows)))[::-1]
    ax.barh(ys, [m["count"] for m in rows], color=ORANGE, height=0.66)
    ax.set_yticks(ys, [_bidi(f"{m['label']}: {_short(m['text'], 48)}") for m in rows], fontsize=7.5)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_color(RULE)
    ax.xaxis.grid(True, color=RULE, linewidth=0.6)
    ax.set_axisbelow(True)
    top = max(m["count"] for m in rows)
    for y, m in zip(ys, rows):
        ax.text(m["count"] + top * 0.015, y, f"{m['count']} ({m['pct']}%)" if m.get("pct") is not None else f"{m['count']}",
                va="center", fontsize=7.5, color=INK)
    ax.set_xlim(0, top * 1.25)
    ax.set_xlabel(_bidi("עבודות"))
    return _png(fig)


def chart_cost(usage: dict | None) -> bytes | None:
    models = (usage or {}).get("by_model") or []
    if not models:
        return None
    plt = _plt()
    fig, axes = plt.subplots(1, 2, figsize=(6.4, max(1.6, 0.5 * len(models) + 1.1)), gridspec_kw={"width_ratios": [1, 1.4]})
    ys = list(range(len(models)))[::-1]
    names = [m["model"] for m in models]
    ax = axes[0]
    ax.barh(ys, [m["cost_per_run"] or 0 for m in models], color=BLUE, height=0.6)
    ax.set_yticks(ys, names, fontsize=8)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_color(RULE)
    top = max((m["cost_per_run"] or 0) for m in models) or 1
    for y, m in zip(ys, models):
        ax.text((m["cost_per_run"] or 0) + top * 0.03, y, _usd(m["cost_per_run"], 2), va="center", fontsize=8, color=INK)
    ax.set_xlim(0, top * 1.45)
    ax.set_title(_bidi("עלות לעבודה (שוות ערך ל-API)"), fontsize=9, color=INK_2)
    ax.set_xticks([])
    ax = axes[1]
    kinds = [("cache_read", "cache read", BLUE_LIGHT), ("cache_write", "cache write", BLUE), ("output", "output", BLUE_DARK), ("input", "input", ORANGE)]
    left = [0.0] * len(models)
    for key, name, color in kinds:
        vals = [m.get(key) or 0 for m in models]
        ax.barh(ys, vals, left=left, color=color, height=0.6, label=name, edgecolor="white", linewidth=1)
        left = [a + b for a, b in zip(left, vals)]
    ax.set_yticks(ys, ["" for _ in models])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_color(RULE)
    ax.set_xticks([])
    for y, total in zip(ys, left):
        ax.text(total + max(left) * 0.02, y, _tokens(total), va="center", fontsize=8, color=INK)
    ax.set_xlim(0, max(left) * 1.3 if max(left) else 1)
    ax.set_title(_bidi("טוקנים לכל הריצה"), fontsize=9, color=INK_2)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), fontsize=7, frameon=False, ncol=4)
    return _png(fig)


# ---------- התובנות: משפטים מהמספרים ----------

def insights(s: dict) -> list[str]:
    out: list[str] = []
    c, g, qs = s["counts"], s["grade"], [q for q in s["per_question"] if q.get("success_pct") is not None]
    if g["n"]:
        out.append(f"הציון הממוצע {_fmt(g['mean'])} והחציון {_fmt(g['median'])} מתוך {_fmt(s['max_grade'])}; "
                   f"{_pct(g['pass_pct'])} מהעבודות עוברות ו-{g['full_marks']} קיבלו ציון מלא.")
    weak = sorted(qs, key=lambda q: q["success_pct"])[:3]
    if weak:
        parts = []
        for q in weak:
            top = (q.get("mistakes") or [None])[0]
            parts.append(f"{q['label']} ({q['success_pct']}%" + (f", בעיקר: {_short(top['text'], 55)}" if top else "") + ")")
        out.append("הסעיפים שבהם הסטודנטים נופלים הכי הרבה, וכדאי לחזור עליהם בתרגול: " + "; ".join(parts) + ".")
    strong = [q["label"] for q in qs if q["success_pct"] >= 95]
    if strong:
        out.append(f"{len(strong)} סעיפים נפתרים כמעט תמיד נכון ({_pct(95)} ומעלה): " + ", ".join(strong[:8]) + (" ועוד" if len(strong) > 8 else "") + ".")
    zero = [q for q in qs if (q.get("zero_pct") or 0) >= 15]
    if zero:
        out.append("סעיפים שבהם נפוץ ניקוד אפס (סעיף חסר או שגוי לגמרי): " + ", ".join(f"{q['label']} ({q['zero_pct']}%)" for q in zero[:6]) + ".")
    if c["graded"]:
        kinds = ", ".join(f"{_compute_kind(k)} {n}" for k, n in (c.get("review_kinds") or {}).items())
        share = 100 * c["needs_review"] / c["graded"]
        out.append(f"{c['needs_review']} מתוך {c['graded']} עבודות ({share:.0f}%) מחכות לבודק אנושי" + (f" ({kinds})" if kinds else "") + "; "
                   + ("זה בתוך היעד של 5-6%." if share <= 6 else "זה מעל היעד של 5-6%: כדאי לבדוק מה שולח אותן."))
    u, t = s.get("usage") or {}, s.get("timing") or {}
    if u.get("runs") and c.get("pending"):
        left = c["pending"]
        est_cost = (u.get("cost_per_run") or 0) * left
        est_time = (t.get("seconds_per_work") or 0) * left
        out.append(f"בקצב הזה, {left} העבודות שנותרו יעלו בערך {_usd(est_cost, 0)} (שווה ערך ל-API) וייקחו בערך {_minutes(est_time)} "
                   f"של ריצה רצופה.")
    for e in s.get("earlier") or []:
        eg, eu = e.get("grade") or {}, e.get("usage") or {}
        if eg.get("n") and g["n"]:
            out.append(f"לעומת הבדיקה הקודמת ({eg['n']} עבודות, ממוצע {_fmt(eg['mean'])}), הממוצע עכשיו {_fmt(g['mean'])}"
                       + (f" והעלות לעבודה {_usd(u.get('cost_per_run'))} לעומת {_usd(eu.get('cost_per_run'))}" if u.get("cost_per_run") and eu.get("cost_per_run") else "") + ".")
            break
    return out


KIND_NAMES = {"missing_question": "שאלה חסרה", "missing_page": "עמוד חסר", "other_assignment": "מטלה אחרת",
              "unreadable_file": "קובץ לא קריא", "unreadable": "לא קריא", "missing": "חסר", "uncertain": "לא בטוח",
              "format": "פורמט", "failed": "הבדיקה נכשלה", "other": "אחר"}


def _compute_kind(kind: str) -> str:
    return KIND_NAMES.get(kind, kind)


# ---------- ה-HTML של הדוח ----------

CSS = """
body { font-family: Arial, sans-serif; direction: rtl; font-size: 10pt; color: %(ink)s; line-height: 1.35; }
h1 { font-size: 21pt; color: %(blue_dark)s; margin: 0 0 4pt 0; }
h2 { font-size: 14pt; color: %(blue_dark)s; margin: 14pt 0 6pt 0; border-bottom: 1.5pt solid %(blue)s; padding-bottom: 2pt; }
h3 { font-size: 11pt; color: %(ink)s; margin: 10pt 0 3pt 0; }
p { margin: 0 0 5pt 0; }
.meta { color: %(ink2)s; font-size: 9.5pt; margin-bottom: 8pt; }
.note { color: %(ink2)s; font-size: 8.5pt; }
table { border-collapse: collapse; width: 100%%; margin: 4pt 0 8pt 0; }
th { text-align: right; font-size: 9pt; color: %(ink2)s; border-bottom: 1pt solid %(blue)s; padding: 3pt 4pt; }
td { text-align: right; font-size: 9.5pt; border-bottom: 0.5pt solid %(rule)s; padding: 3pt 4pt; vertical-align: top; }
td.num, th.num { text-align: left; direction: ltr; }
tr.group td { font-weight: bold; color: %(blue_dark)s; border-top: 1pt solid %(blue)s; padding-top: 5pt; }
table.kpi { margin: 6pt 0 10pt 0; }
table.kpi td { border-top: 1.5pt solid %(blue)s; border-bottom: 1.5pt solid %(blue)s; text-align: center; padding: 7pt 2pt; width: 16%%; }
table.cols td { border: none; padding: 0 5pt; vertical-align: top; }
table.inner td { border-bottom: 0.5pt solid %(rule)s; padding: 2pt 3pt; font-size: 8.5pt; }
table.inner th { padding: 2pt 3pt; font-size: 8pt; }
table.small td { font-size: 9pt; padding: 2pt 4pt; }
.kpi .v { font-size: 17pt; font-weight: bold; color: %(blue_dark)s; direction: ltr; }
.kpi .k { font-size: 8.5pt; color: %(ink2)s; }
img { margin: 4pt 0; }
ul { margin: 2pt 18pt 6pt 0; padding: 0; }
li { margin-bottom: 4pt; }
.break { page-break-before: always; }
""" % {"ink": INK, "ink2": INK_2, "blue": BLUE, "blue_dark": BLUE_DARK, "rule": RULE}


def _font_css() -> str:
    out = []
    if (FONT_DIR / FONT_FILES["regular"]).is_file():
        out.append("@font-face { font-family: Arial; src: url(%s); }" % FONT_FILES["regular"])
    if (FONT_DIR / FONT_FILES["bold"]).is_file():
        out.append("@font-face { font-family: Arial; src: url(%s); font-weight: bold; }" % FONT_FILES["bold"])
    return "\n".join(out)


def _kpi(cells: list[tuple[str, str]]) -> str:
    return "<table class='kpi'><tr>" + "".join(f"<td><div class='v'>{_h(v)}</div><div class='k'>{_h(k)}</div></td>" for k, v in cells) + "</tr></table>"


def _table(head: list[str], rows: list[list], num_cols: set[int] = frozenset(), widths: list[str] | None = None, cls: str = "") -> str:
    def cell(tag, i, v):
        cls = " class='num'" if i in num_cols else ""
        w = f" style='width:{widths[i]}'" if widths and i < len(widths) else ""
        return f"<{tag}{cls}{w}>{_h(v)}</{tag}>"
    out = [f"<table class='{cls}'><tr>" + "".join(cell("th", i, v) for i, v in enumerate(head)) + "</tr>"]
    for r in rows:
        if isinstance(r, dict) and r.get("group"):
            out.append(f"<tr class='group'><td colspan='{len(head)}'>{_h(r['group'])}</td></tr>")
        else:
            out.append("<tr>" + "".join(cell("td", i, v) for i, v in enumerate(r)) + "</tr>")
    return "".join(out) + "</table>"


def _img(name: str | None, width: int = 500) -> str:
    return f"<p><img src='{name}' width='{width}'></p>" if name else ""


def _section_tables(qs: list[dict]) -> tuple[list, list]:
    """שורה לכל שאלה (סעיפים, ניקוד, ממוצע, הצלחה, הסעיף החלש), ושורות הסעיפים עם שורת כותרת לכל שאלה."""
    summary: list = []
    rows: list = []
    for gname, items in groups(qs):
        pts = sum(q["points"] or 0 for q in items)
        means = [q["mean"] for q in items if q["mean"] is not None]
        share = _pct(_compute._half_up(100 * sum(means) / pts)) if pts and means else "—"
        weakest = min(items, key=lambda q: q["success_pct"] if q["success_pct"] is not None else 101)
        summary.append([gname, _fmt(len(items)), _fmt(pts), _fmt(sum(means)) if means else "—", share,
                        f"{weakest['label']} ({_pct(weakest['success_pct'])})" if len(items) > 1 else "—"])
        rows.append({"group": f"{gname}: {_fmt(pts)} נק', ממוצע {_fmt(sum(means)) if means else '—'} ({share})"})
        for q in items:
            rows.append([q["label"], _fmt(q["points"]), _fmt(q["mean"]), _pct(q["success_pct"]), _pct(q["full_marks_pct"]), _pct(q["zero_pct"]), _fmt(q["unsure"])])
    return summary, rows


def report_html(s: dict, charts: dict[str, str], today: date) -> str:
    c, g, t, u = s["counts"], s["grade"], s.get("timing") or {}, s.get("usage") or {}
    qs = s["per_question"]
    max_grade = s.get("max_grade") or 100
    parts: list[str] = []

    # עמוד 1: כותרת, מספרים ראשיים, התפלגות
    parts.append(f"<h1>דוח בדיקה: {_h(s.get('title') or s.get('folder'))}</h1>")
    parts.append(f"<p class='meta'>{_h(s['course'])} · {_h(s['folder'])} · מזהה מודל {_h(s.get('moodle_id'))} · "
                 f"הדוח הופק ב-{today.strftime('%d/%m/%Y')} מתוך מסד הסטטיסטיקה (חושב {_when(s.get('computed_at'))}). "
                 f"מספרים בלבד: אין בו שום פרט מזהה של סטודנט.</p>")
    parts.append(_kpi([("עבודות נבדקו", _fmt(c["graded"])), ("ממוצע", _fmt(g["mean"])), ("חציון", _fmt(g["median"])),
                       ("עוברים", _pct(g["pass_pct"])), ("לבדיקה ידנית", _fmt(c["needs_review"])),
                       ("עלות הריצה", _usd(u.get("cost_usd"), 0) if u.get("runs") else "—")]))
    parts.append("<h2>ציונים</h2>")
    parts.append(_img(charts.get("histogram")))
    parts.append(_table(["עבודות עם ציון", "ממוצע", "חציון", "סטיית תקן", "מינימום", "מקסימום", "ציון מלא", "עוברים (60%+)"],
                        [[_fmt(g["n"]), _fmt(g["mean"]), _fmt(g["median"]), _fmt(g["sd"]), _fmt(g["min"]), _fmt(g["max"]),
                          _fmt(g["full_marks"]), _pct(g["pass_pct"])]], num_cols=set(range(8))))
    if g.get("out_of_range"):
        parts.append(f"<p class='note'>{g['out_of_range']} ציונים מחוץ לטווח 0–{_fmt(max_grade)} לא נספרו.</p>")
    summary, section_rows = _section_tables(qs)
    if len(summary) > 1:
        parts.append("<h3>לפי שאלה</h3>")
        parts.append(_table(["שאלה", "סעיפים", "ניקוד", "ממוצע", "הצלחה", "הסעיף החלש"], summary, num_cols={1, 2, 3, 4}))

    # עמוד 2: היקף וזמן, עלות
    parts.append("<h2 class='break'>היקף וזמן</h2>")
    parts.append(_table(["הוגשו", "נבדקו", "עוד לא נבדקו", "אושרו", "לבדיקה ידנית", "נכשלו", "בודקים"],
                        [[_fmt(c["submitted"]), _fmt(c["graded"]), _fmt(c["pending"]), _fmt(c["approved"]), _fmt(c["needs_review"]),
                          _fmt(c["failed"]), ", ".join(f"{b['name']} ({b['graded']})" for b in s["graders"]["by"]) or "—"]],
                        num_cols=set(range(6))))
    kinds = c.get("review_kinds") or {}
    if kinds:
        parts.append("<h3>למה עבודות מחכות לאדם</h3>")
        parts.append(_table(["סיבה", "עבודות", "מתוך הנבדקות"],
                            [[_compute_kind(k), _fmt(n), _pct(_compute._pct(n, c["graded"]))] for k, n in sorted(kinds.items(), key=lambda kv: -kv[1])],
                            num_cols={1, 2}))
    runs = t.get("sessions") or []
    if runs:
        parts.append("<h3>הריצות</h3>")
        parts.append(f"<p>{_fmt(t.get('works'))} עבודות עם חותמת זמן, {_span(t.get('first'), t.get('last'))}. "
                     f"זמן קיר לעבודה: {_minutes(t.get('seconds_per_work'))} בממוצע (כמה עבודות נבדקות במקביל"
                     + (f"; ריצה של עבודה אחת: חציון {_minutes(u['run_seconds']['median'])}, ממוצע {_minutes(u['run_seconds']['mean'])}" if u.get("run_seconds") else "")
                     + ").</p>")
        shown = runs if len(runs) <= 12 else runs[-12:]
        rows = [[_when(r["started"]), _when(r["finished"], with_date=False), _fmt(r["works"]), _minutes(r["seconds"]), _minutes(r["seconds_per_work"])] for r in shown]
        parts.append(_table(["התחילה", "נגמרה", "עבודות", "משך", "לעבודה"], rows, num_cols={0, 1, 2, 3, 4}))
        if len(runs) > 12:
            parts.append(f"<p class='note'>מוצגות 12 הריצות האחרונות מתוך {len(runs)}.</p>")
    parts.append("<h2>עלות וטוקנים</h2>")
    if u.get("runs"):
        parts.append(f"<p>{_fmt(u['runs'])} ריצות של Claude Code, {_usd(u['cost_usd'])} בסך הכול ו-{_usd(u['cost_per_run'])} לעבודה בממוצע, "
                     f"שווה ערך למחיר ה-API (הבדיקה רצה במנוי של הצוות ולא מחויבת בנפרד). "
                     f"{_pct(round(100 * (u.get('cache_read_share') or 0)))} מהקלט הגיע מהמטמון (cache).</p>")
        parts.append(_img(charts.get("cost")))
        rows = [[m["model"], _fmt(m["runs"]), _tokens(m["input"]), _tokens(m["cache_write"]), _tokens(m["cache_read"]), _tokens(m["output"]),
                 _usd(m["cost_usd"]), _usd(m["cost_per_run"], 3)] for m in u["by_model"]]
        rows.append(["סך הכול", _fmt(u["runs"]), _tokens(u["input"]), _tokens(u["cache_write"]), _tokens(u["cache_read"]), _tokens(u["output"]),
                     _usd(u["cost_usd"]), _usd(u["cost_per_run"], 3)])
        parts.append(_table(["מודל", "ריצות", "input", "cache write", "cache read", "output", "עלות", "לעבודה"], rows, num_cols=set(range(1, 8))))
        parts.append("<p class='note'>המקור: יומן השימוש של Claude Code בתיקיית הנתונים (Grading usage.jsonl), שורה לכל ריצה. "
                     "שורה משויכת למטלה לפי המפתח שלה, ובלעדיו לפי זמן הריצה.</p>")
    else:
        parts.append("<p>אין שורות ביומן השימוש של Claude Code למטלה הזו (הבדיקה רצה דרך ה-API, או שהיומן לא נכתב).</p>")

    # עמוד 3: לפי סעיף
    if qs:
        parts.append("<h2 class='break'>ניקוד לפי שאלה וסעיף</h2>")
        parts.append(f"<p>{len(qs)} סעיפים במחוון. אחוז ההצלחה הוא ממוצע האחוז שקיבלה כל עבודה מניקוד הסעיף.</p>")
        parts.append(_img(charts.get("sections"), 400))
        parts.append("<p class='note'>\"מלא\" ו\"אפס\": אחוז העבודות שקיבלו את כל הניקוד בסעיף, או כלום. \"לא בטוח\": כמה עבודות Claude סימן שאינו בטוח בסעיף.</p>")
        head = ["סעיף", "ניקוד", "ממוצע", "הצלחה", "מלא", "אפס", "לא בטוח"]
        if len(section_rows) > 12:
            half = (len(section_rows) + 1) // 2
            cut = half
            for i in range(half, min(half + 3, len(section_rows))):  # לא לפתוח עמודה בשורה של שאלה
                if isinstance(section_rows[i], dict):
                    cut = i
                    break
            parts.append("<table class='cols'><tr><td style='width:50%'>" + _table(head, section_rows[:cut], num_cols={1, 2, 3, 4, 5, 6}, cls="inner")
                         + "</td><td style='width:50%'>" + _table(head, section_rows[cut:], num_cols={1, 2, 3, 4, 5, 6}, cls="inner") + "</td></tr></table>")
        else:
            parts.append(_table(head, section_rows, num_cols={1, 2, 3, 4, 5, 6}))
        if s.get("over_rubric"):
            parts.append(f"<p class='note'>{s['over_rubric']} עבודות עם ניקוד מחוץ למחוון לא נספרות לפי סעיף.</p>")

    # עמוד 4: טעויות נפוצות
    any_mistakes = any(q.get("mistakes") for q in qs)
    if any_mistakes:
        parts.append("<h2 class='break'>טעויות נפוצות</h2>")
        parts.append("<p>האחוז הוא מתוך העבודות הבדוקות שיש להן הערות בדיקה. \"ירד\": כמה נקודות ירדו עליה בדרך כלל; "
                     "★ = טעות שכתובה במחוון.</p>")
        parts.append(_img(charts.get("mistakes")))
        rows = []
        for gname, items in groups(qs):
            ms = sorted((({**m, "label": q["label"]}) for q in items for m in q.get("mistakes") or []), key=lambda m: (-m["count"], m["label"], m["text"]))
            if not ms:
                continue
            rows.append({"group": gname})
            for m in ms[:TOP_MISTAKES]:
                rows.append([m["label"], ("★ " if m.get("in_rubric") else "") + _short(m["text"], 95), _fmt(m["count"]), _pct(m["pct"]), _fmt(m["deduction"])])
        parts.append(_table(["סעיף", "הטעות", "עבודות", "אחוז", "ירד"], rows, num_cols={2, 3, 4}, widths=["14%", "62%", "8%", "8%", "8%"], cls="small"))

    # עמוד 5: השוואה ותובנות
    parts.append("<h2>תובנות לצוות</h2>")
    parts.append("<ul>" + "".join(f"<li>{_h(x)}</li>" for x in insights(s)) + "</ul>")
    earlier = s.get("earlier") or []
    if earlier:
        parts.append("<h2>לעומת הבדיקה הקודמת</h2>")
        rows = []
        for e in earlier:
            ec, eg, et, eu = e.get("counts") or {}, e.get("grade") or {}, e.get("timing") or {}, e.get("usage") or {}
            rows.append([e.get("folder"), _span(et.get("first"), et.get("last")), _fmt(eg.get("n")), _fmt(eg.get("mean")),
                         _fmt(eg.get("median")), _pct(eg.get("pass_pct")), _fmt(ec.get("needs_review")), _usd(eu.get("cost_per_run")), _minutes(et.get("seconds_per_work"))])
        rows.append(["הבדיקה הנוכחית", _span(t.get("first"), t.get("last")), _fmt(g["n"]), _fmt(g["mean"]), _fmt(g["median"]),
                     _pct(g["pass_pct"]), _fmt(c["needs_review"]), _usd(u.get("cost_per_run")), _minutes(t.get("seconds_per_work"))])
        parts.append(_table(["בדיקה", "מתי", "עבודות", "ממוצע", "חציון", "עוברים", "לבדיקה ידנית", "עלות לעבודה", "זמן קיר לעבודה"], rows, num_cols={2, 3, 4, 5, 6, 7, 8}))
        parts.append("<p class='note'>הבדיקה הקודמת נבדקה לפי מחוון אחר, אז הציונים לפי סעיף לא מושווים. "
                     "העלות שלה כוללת גם עבודות שנבדקו יותר מפעם אחת.</p>")
    parts.append(f"<p class='note'>הופק על ידי python -m stats report. הקובץ: {_h(paths.STATISTICS)}/{_h(s['course'])}/. "
                 "הסטטיסטיקה מחושבת מחדש כשהציונים או הערות הבדיקה משתנים.</p>")
    return "\n".join(parts)


# ---------- עמודים ----------

def _write_pdf(html_text: str, archive, out: Path, footer: str) -> int:
    import pymupdf

    css = _font_css() + "\n" + CSS
    story = pymupdf.Story(html=html_text, user_css=css, archive=archive)
    page_rect = pymupdf.paper_rect(PAGE)
    body = page_rect + (MARGIN, MARGIN, -MARGIN, -MARGIN - 18)
    tmp = out.with_name(out.name + ".tmp")
    writer = pymupdf.DocumentWriter(str(tmp))
    n = 0
    more = True
    while more and n < MAX_PAGES:
        n += 1
        dev = writer.begin_page(page_rect)
        more, _ = story.place(body)
        story.draw(dev)
        foot = pymupdf.Story(html=f"<p style='font-size:8pt;color:{INK_2}'>{_h(footer)} · עמוד {n}</p>", user_css=css, archive=archive)
        foot.place(pymupdf.Rect(MARGIN, page_rect.height - MARGIN - 8, page_rect.width - MARGIN, page_rect.height - 10))
        foot.draw(dev)
        writer.end_page()
    writer.close()
    del writer, story  # DocumentWriter משחרר את הקובץ רק כשהוא נמחק: לפני ההחלפה
    gc.collect()
    os.replace(tmp, out)
    return n


def report_path(assignment_dir: Path, today: date | None = None) -> Path:
    a = Path(assignment_dir)
    n = _compute.slot(a.name)
    name = paths.STATS_REPORT.format(n if n is not None else a.name, (today or date.today()).isoformat())
    return stats_dir(a.parent.parent) / a.parent.name / name


def build_report(assignment_dir: Path, out: Path | None = None, today: date | None = None, stats: dict | None = None) -> Path:
    """בונה את ה-PDF מהמסד (stats.read) ומחזיר את הנתיב. out=None: ליד ה-JSON של המטלה."""
    import pymupdf

    a = Path(assignment_dir)
    today = today or date.today()
    s = stats if stats is not None else read(a)
    out = Path(out) if out else report_path(a, today)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stats-report-") as tmp:
        charts: dict[str, str] = {}
        for name, png in (("histogram", chart_histogram(s["grade"], s.get("max_grade"))),
                          ("sections", chart_sections(s["per_question"])),
                          ("mistakes", chart_mistakes(s["per_question"])),
                          ("cost", chart_cost(s.get("usage")))):
            if png:
                (Path(tmp) / f"{name}.png").write_bytes(png)
                charts[name] = f"{name}.png"
        archive = pymupdf.Archive(tmp)
        if FONT_DIR.is_dir():
            archive.add(str(FONT_DIR))
        footer = f"{s.get('title') or s.get('folder')} · {s['course']} · {today.strftime('%d/%m/%Y')}"
        _write_pdf(report_html(s, charts, today), archive, out, footer)
    return out


def preview_png(pdf: Path, out: Path, page: int = 0, dpi: int = 110) -> Path:
    """תמונה של עמוד אחד מה-PDF, לתצוגה מקדימה."""
    import pymupdf

    doc = pymupdf.open(str(pdf))
    try:
        doc[page].get_pixmap(dpi=dpi).save(str(out))
    finally:
        doc.close()
    return out
