#!/usr/bin/env python3
"""Check rubric.json before anything is rendered: shape and types first, then the sums, the deductions,
the error types and the text. One Hebrew line per problem, exit 1 on any. Also importable: `problems(r)`."""
import sys
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Hebrew on a Windows console
import json, re, sys

TYPES = {"הבנה", "חוסר", "חישוב", "סימון", "נימוק חסר"}
DED = re.compile(r"^\s*(\d+|\d+\s*[–-]\s*\d+|\d+\s*/\s*\d+|עד \d+)\s*$")
MARKDOWN = re.compile(r"\*\*|`")
LATEX_RAW = re.compile(r"(?<!\\)[%&#]")  # render_tex escapes these; the check is only for `~`
UNBALANCED = re.compile(r"(?<!\\)\$")


def ded_vals(s):
    return [int(x) for x in re.findall(r"\d+", s)]


def ded_max(s):
    return max(ded_vals(s))


def _int(v):
    """A whole number: int, or a float / digit string that is whole. None otherwise."""
    if isinstance(v, bool): return None
    if isinstance(v, int): return v
    if isinstance(v, float) and v.is_integer(): return int(v)
    if isinstance(v, str) and v.strip().isdigit(): return int(v.strip())
    return None


def _text(e, where, s, field="desc"):
    """Text problems the renderers can't fix: Markdown, unbalanced $, `~`."""
    if not isinstance(s, str): return
    if MARKDOWN.search(s): e.append(f"{where}: Markdown בטקסט ('**' או גרשיים הפוכים); ב-PDF זה יודפס כמו שהוא: {s[:40]}")
    if len(UNBALANCED.findall(s)) % 2: e.append(f"{where}: מספר אי-זוגי של סימני $ (נוסחה לא נסגרה): {s[:40]}")
    if "~" in s: e.append(f"{where}: הסימן ~ הופך לרווח ב-LaTeX; לכתוב \\textasciitilde או להשמיט: {s[:40]}")


def _steps(e, where, steps, points):
    if not isinstance(steps, list) or not steps:
        e.append(f"{where}: אין שלבים (steps)"); return
    tot = 0
    for i, x in enumerate(steps, 1):
        if not isinstance(x, dict) or not str(x.get("desc", "")).strip():
            e.append(f"{where}: שלב {i} בלי תיאור (desc)"); continue
        p = _int(x.get("points"))
        if p is None or p < 0: e.append(f"{where}: שלב {i} ('{str(x['desc'])[:30]}') עם נקודות לא תקינות: {x.get('points')!r}"); continue
        tot += p; _text(e, f"{where} שלב {i}", x["desc"])
    if tot != points: e.append(f"{where}: שלבים מסתכמים ל-{tot} ולא ל-{points}")


def problems(r):
    e = []
    if not isinstance(r, dict):
        return ["rubric.json צריך להיות אובייקט אחד ({...})"]
    if not str(r.get("course", "")).strip(): e.append("חסר שם קורס (course); בלעדיו הכותרת העליונה לא מתהדרת")
    qs = r.get("questions")
    if not isinstance(qs, list) or not qs:
        e.append("אין שאלות (questions): רשימה ריקה או חסרה"); return e
    grand = 0; seen_n = set()
    for qi, q in enumerate(qs, 1):
        if not isinstance(q, dict): e.append(f"שאלה מספר {qi} אינה אובייקט"); continue
        n = q.get("n")
        if not isinstance(n, str) or not n.strip():
            e.append(f"שאלה מספר {qi}: 'n' חייב להיות מחרוזת כמו \"קבוצות 11\" (סוף התווית של השאלה), לא {n!r}"); n = f"#{qi}"
        elif n.strip().isdigit():
            e.append(f"שאלה {n}: 'n' הוא מספר בלבד; כשיש שני דפים עם אותו מספר שאלה הבוט יקח נקודות של השאלה הלא נכונה. לכתוב \"<דף> {n}\"")
        if n in seen_n: e.append(f"שאלה {n} מופיעה פעמיים")
        seen_n.add(n)
        qp = _int(q.get("points"))
        if qp is None or qp <= 0: e.append(f"שאלה {n}: נקודות לא תקינות ({q.get('points')!r}); חייב מספר שלם חיובי"); qp = 0
        grand += qp
        secs = q.get("sections")
        if not isinstance(secs, list) or not secs:
            e.append(f"שאלה {n}: אין סעיפים (sections)"); continue
        total = 0; letters = set()
        for si, s in enumerate(secs, 1):
            if not isinstance(s, dict): e.append(f"שאלה {n}: סעיף מספר {si} אינו אובייקט"); continue
            letter = str(s.get("letter", "")).strip()
            sid = f"שאלה {n} סעיף {letter or '?'}"
            if not letter: e.append(f"שאלה {n}: סעיף מספר {si} בלי אות (letter)")
            elif letter in letters: e.append(f"{sid}: האות מופיעה פעמיים")
            letters.add(letter)
            sp = _int(s.get("points"))
            if sp is None or sp <= 0: e.append(f"{sid}: נקודות לא תקינות ({s.get('points')!r}); חייב מספר שלם חיובי"); continue
            count = _int(s.get("count", 1))
            if count is None or count < 1: e.append(f"{sid}: count לא תקין ({s.get('count')!r})"); count = 1
            if count > 1 and len([x for x in re.split(r"[,\s]+", letter) if x]) != count:
                e.append(f"{sid}: count={count} אבל ב-letter יש {len([x for x in re.split(r'[,\s]+', letter) if x])} אותיות")
            total += sp * count
            if not str(s.get("answer", "")).strip(): e.append(f"{sid}: אין תשובה (answer)")
            _text(e, sid, s.get("answer")); _text(e, sid, s.get("title")); _text(e, sid, s.get("note"))
            _steps(e, sid, s.get("steps"), sp)
            for m in s.get("alt_methods", []) or []:
                if not isinstance(m, dict) or not str(m.get("name", "")).strip():
                    e.append(f"{sid}: דרך חלופית בלי שם (name)"); continue
                _steps(e, f"{sid} דרך '{m['name']}'", m.get("steps"), sp)
            for ei, er in enumerate(s.get("errors", []) or [], 1):
                if not isinstance(er, dict) or not str(er.get("desc", "")).strip():
                    e.append(f"{sid}: שורת טעות {ei} בלי תיאור (desc)"); continue
                desc = str(er["desc"])[:30]; _text(e, f"{sid} טעות {ei}", er["desc"])
                if er.get("type") not in TYPES: e.append(f"{sid}: סוג טעות לא מוכר '{er.get('type')}' ({desc}); מותר: {', '.join(sorted(TYPES))}")
                ok = True
                for k in ("regular", "strict"):
                    v = str(er.get(k, ""))
                    if not DED.match(v): e.append(f"{sid}: ניכוי לא תקין '{v}' ({desc})"); ok = False
                    else:
                        vals = ded_vals(v)
                        if len(vals) == 2 and vals[0] > vals[1]: e.append(f"{sid}: טווח הפוך '{v}' ({desc})"); ok = False
                        elif ded_max(v) > sp: e.append(f"{sid}: ניכוי {v} גדול מהסעיף ({sp}) ({desc})"); ok = False
                if ok:
                    reg, strict = ded_max(str(er["regular"])), ded_max(str(er["strict"]))
                    if strict < reg:
                        e.append(f"{sid}: מחמיר קטן מרגיל ({desc})")
                    # מחמיר הוא משטר בדיקה קשוח: תמיד נקודה יותר מרגיל, אלא אם רגיל כבר בגובה הסעיף (Ori, 2026-10-29)
                    elif strict == reg and reg < sp:
                        e.append(f"{sid}: מחמיר שווה לרגיל ({desc}); מחמיר = רגיל + 1 עד גובה הסעיף")
                    elif strict > reg + 1:
                        e.append(f"{sid}: מחמיר גדול מרגיל ביותר מנקודה ({reg} לעומת {strict}, {desc}); הכלל: מחמיר = רגיל + 1")
        if total != qp: e.append(f"שאלה {n}: סעיפים מסתכמים ל-{total} ולא ל-{qp}")
    for a in r.get("american", []) or []:
        if not isinstance(a, dict) or not str(a.get("answer", "")).strip(): e.append(f"שאלה {a.get('n') if isinstance(a, dict) else '?'}: אין תשובה")
        ap = _int(a.get("points")) if isinstance(a, dict) else None
        if ap is None: e.append(f"שאלה אמריקאית {a.get('n') if isinstance(a, dict) else '?'}: נקודות לא תקינות")
        else: grand += ap
    expected = _int(r.get("max_grade", 100)) or 100
    if grand != expected: e.append(f"סך הנקודות הוא {grand} ולא {expected}")
    for g in r.get("general_rules", []) or []:
        if not isinstance(g, dict) or not str(g.get("label", "")).strip() or not str(g.get("text", "")).strip():
            e.append("כלל בדיקה (general_rules) בלי label או text")
        else: _text(e, f"כלל '{g['label'][:20]}'", g["text"])
    return e


def load(path):
    try:
        with open(path, encoding="utf-8-sig") as f: return json.load(f)
    except FileNotFoundError: sys.exit(f"הקובץ לא נמצא: {path}")
    except json.JSONDecodeError as ex: sys.exit(f"rubric.json אינו JSON תקין: שורה {ex.lineno}, עמודה {ex.colno}: {ex.msg}")


def main(path):
    r = load(path)
    e = problems(r)
    if e:
        print("rubric.json לא תקין:"); [print("  -", x) for x in e]; sys.exit(1)
    tot = sum(int(q["points"]) for q in r["questions"]) + sum(int(a["points"]) for a in r.get("american", []) or [])
    print(f"OK — {len(r['questions'])} שאלות, {tot} נק' סה\"כ")


if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit("שימוש: validate_rubric.py <rubric.json>")
    main(sys.argv[1])
