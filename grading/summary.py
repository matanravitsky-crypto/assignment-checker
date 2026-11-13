"""עמוד הסיכום של עבודה בדוקה, בכיוון "תעודה": למעלה הציון בטבעת, שם המטלה ומשפט אחד; באמצע מפה של
השאלות (כל סעיף משבצת: ירוק ✓ ניקוד מלא, כתום ✗ ירדו נקודות, אדום ✗ אפס); למטה רק מה שירד, עם ההערה.
תחליף ל-grade._summary_page: אותה חתימה. הצורות מצוירות ב-PyMuPDF, והטקסט העברי ב-grading/rtl.py: כל שורה
מסודרת כאן וכל קטע (עברית / ביטוי מתמטי) נכתב במקומו. עד 2026-11-14 הטקסט נכתב ב-insert_htmlbox, וה-bidi של MuPDF
(שמתעלם מכל סימן כיוון) הפך "-4" ל-"4-" ו-"1+8=-7" ל-"7-=1+8"."""
from __future__ import annotations

import re

import pymupdf

from . import rtl
from .grade import (Context, Graded, _FONT, _pts, assigned, shown_labels)

# ---------- הפלטה של "בודק חכם" (website/styles.css) ----------
def _rgb(h: str) -> tuple[float, float, float]:
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


INK, INK2, INK3 = "#162040", "#4F5A79", "#7F8AA8"
RULE, SHEET2 = "#D7DFEF", "#F5F7FC"
OK, OK_SOFT = "#157A57", "#DFF3EA"
WARN, WARN_SOFT = "#B46A00", "#FBEFD9"
BAD, BAD_SOFT = "#C8102E", "#FCE8EB"
NOTE, NOTE_SOFT = "#2340A8", "#E3E9FA"
NEUTRAL, NEUTRAL_SOFT = "#7F8AA8", "#EEF2F9"

W, H = 595.0, 842.0          # A4: עמוד הסיכום תמיד באותו גודל, גם כשהסריקה בגודל אחר
M = 38.0                     # שוליים

# גופן מודגש מאותה תיקייה של הגופן העברי (ה-archive של grade), לכותרות ולמספרים
_BOLD_NAMES = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "NotoSansHebrew-Bold.ttf", "FreeSansBold.ttf"]
_BOLD = next((_FONT.parent / n for n in _BOLD_NAMES if _FONT and (_FONT.parent / n).is_file()), None)

_SECTION = re.compile(r"^(.*\d)\s*([א-ת])$")   # "קבוצות 11ב" -> "קבוצות 11", "ב"


def _kind(p: float, full: float) -> str:
    if full <= 0:
        return "none"
    return "full" if p >= full else "zero" if p <= 0 else "part"


_COLORS = {"full": (OK, OK_SOFT), "part": (WARN, WARN_SOFT), "zero": (BAD, BAD_SOFT), "none": (NEUTRAL, NEUTRAL_SOFT)}


def _band(frac: float) -> tuple[str, str]:
    """הצבע של הטבעת והמשפט שליד הציון."""
    if frac >= 1:
        return OK, "כל הכבוד!"
    if frac >= 0.85:
        return OK, "כמעט מושלם"
    if frac >= 0.6:
        return WARN, "יש מה לתקן"
    return BAD, "יש מה לתקן"


class _Pen:
    """טקסט קצר בלי עברית רב-אותית (מספרים, אות סעיף אחת): insert_text, מהיר ומדויק. כל השאר: para (rtl)."""

    def __init__(self, page: pymupdf.Page, archive):
        self.page, self.archive = page, archive
        self.fonts = {}
        for name, path in (("hb", _BOLD), ("hr", _FONT)):
            if path:
                page.insert_font(fontname=name, fontfile=str(path))
                self.fonts[name] = pymupdf.Font(fontfile=str(path))
        if not self.fonts:
            self.fonts["helv"] = pymupdf.Font("helv")

    def _font(self, bold: bool) -> str:
        want = "hb" if bold else "hr"
        return want if want in self.fonts else next(iter(self.fonts))

    def width(self, text: str, size: float, bold: bool = False) -> float:
        return self.fonts[self._font(bold)].text_length(text, fontsize=size)

    def text(self, x: float, y: float, text: str, size: float, color: str, bold: bool = False, align: str = "left") -> None:
        """y = קו הבסיס. align: left / center / right ביחס ל-x."""
        w = self.width(text, size, bold)
        x0 = x - w if align == "right" else x - w / 2 if align == "center" else x
        self.page.insert_text((x0, y), text, fontsize=size, fontname=self._font(bold), color=_rgb(color))

    def para(self, rect: pymupdf.Rect, text: str, size: float, color: str, bold: bool = False, align: str = "right",
             lh: float = 1.25, shrink: bool = True) -> float:
        """עברית (עם ביטויים מתמטיים) במלבן, מלמעלה, מימין לשמאל. מוקטן עד שנכנס. מחזיר את הגובה שנכתב."""
        return rtl.draw(self.page, rect, text, size, color, bold=bold, align=align, lh=lh, shrink=shrink,
                        min_size=2.0) or 0.0


def _stack(page: pymupdf.Page, rect: pymupdf.Rect, items: list[dict], lh: float) -> None:
    """פסקאות זו מתחת לזו במלבן (text, size, color, bold, mt = רווח מעל). הכול מוקטן יחד עד שנכנס (כמו scale_low=0)."""
    items = [it for it in items if str(it["text"]).strip()]

    def height(s: float) -> float:
        return sum(it.get("mt", 0) * s + rtl.measure(it["text"], rect.width, it["size"] * s, it.get("bold", False), lh)
                   for it in items)
    s = 1.0
    while s > 0.3 and height(s) > rect.height:
        s *= 0.95
    y = rect.y0
    for it in items:
        y += it.get("mt", 0) * s
        size = it["size"] * s
        lay = rtl.layout(it["text"], rect.width / size, it.get("bold", False))
        rtl.write(page, pymupdf.Rect(rect.x0, y, rect.x1, y + 1), lay, size, it["color"], bold=it.get("bold", False), lh=lh)
        y += len(lay.lines) * size * lh


def _icon(page: pymupdf.Page, x: float, y: float, s: float, kind: str, color: str) -> None:
    """✓ או ✗ בריבוע s שהפינה השמאלית-העליונה שלו ב-(x, y)."""
    sh = page.new_shape()
    if kind == "full":
        sh.draw_polyline([(x + s * .08, y + s * .55), (x + s * .4, y + s * .88), (x + s * .95, y + s * .12)])
    else:
        sh.draw_line((x + s * .15, y + s * .15), (x + s * .85, y + s * .85))
        sh.draw_line((x + s * .85, y + s * .15), (x + s * .15, y + s * .85))
    sh.finish(color=_rgb(color), width=max(1.4, s * .17), lineCap=1, lineJoin=1, closePath=False)
    sh.commit()


def _ring(page: pymupdf.Page, pen: _Pen, cx: float, cy: float, r: float, g: Graded, ctx: Context, color: str) -> None:
    frac = max(0.0, min(1.0, g.grade / ctx.max_grade)) if ctx.max_grade else 0
    sh = page.new_shape()
    sh.draw_circle((cx, cy), r)
    sh.finish(color=_rgb("#E6EBF5"), width=r * .2, fill=(1, 1, 1))
    if frac >= 1:
        sh.draw_circle((cx, cy), r)
        sh.finish(color=_rgb(color), width=r * .2)
    elif frac > 0:   # מלמעלה, עם כיוון השעון (beta שלילי = עם כיוון השעון בעמוד)
        sh.draw_sector((cx, cy), (cx, cy - r), -360 * frac, fullSector=False)
        sh.finish(color=_rgb(color), width=r * .2, lineCap=1, closePath=False)
    sh.commit()
    num = _pts(g.grade)
    size = r * (0.78 if len(num) <= 2 else 0.62)
    pen.text(cx, cy + size * .3, num, size, INK, bold=True, align="center")
    pen.para(pymupdf.Rect(cx - r, cy + size * .42, cx + r, cy + size * .42 + 14), f"מתוך {_pts(ctx.max_grade)}",
             8.5, INK3, align="center")


def _groups(ctx: Context, g: Graded) -> list[dict]:
    """השאלות לפי קבוצה: "קבוצות 11א".."קבוצות 11ה" -> קבוצה "קבוצות 11" עם הסעיפים א..ה."""
    out: list[dict] = []
    rows = zip(ctx.questions, shown_labels(ctx.questions), g.points, g.comments, assigned(ctx))
    for i, (q, label, p, c, shown) in enumerate(rows):
        if not shown:
            continue
        m = _SECTION.match(label)
        name, sec = (m.group(1), m.group(2)) if m else (label, "")
        item = {"i": i, "label": label, "sec": sec, "p": float(p), "full": float(q.points), "comment": c or "",
                "kind": _kind(float(p), float(q.points))}
        if out and out[-1]["name"] == name and sec:
            out[-1]["items"].append(item)
        else:
            out.append({"name": name, "items": [item]})
    return out


def _grid(page: pymupdf.Page, pen: _Pen, groups: list[dict], top: float, budget: float) -> float:
    """המפה: שורה לכל שאלה (שם וסיכום מימין, משבצת לכל סעיף משמאלו). כשאין סעיפים בכלל: שורה אחת של
    משבצות, אחת לכל שאלה. מחזיר את ה-y שבו המפה נגמרת."""
    flat = all(len(gr["items"]) == 1 and not gr["items"][0]["sec"] for gr in groups)
    gap = 6.0
    inner = W - 2 * M
    if flat:   # "שאלה 11", "שאלה 13"...: כרטיס לכל שאלה, בשורה אחת לרוחב העמוד (או כמה)
        items = [gr["items"][0] for gr in groups]
        for it in items:
            it["sec"] = it["label"]
        n = len(items)
        cw = max(92.0, min(118.0, (inner - (n - 1) * gap) / n))
        per = max(1, int((inner + gap) / (cw + gap) + 1e-6))
        k = (n + per - 1) // per
        ch, row_pad = 50.0, 8.0
        while ch > 40 and k * (ch + gap) - gap + 2 * row_pad > budget:
            ch -= 1
        if k * (ch + gap) - gap + 2 * row_pad <= budget:
            for j, it in enumerate(items):
                col, line = j % per, j // per
                x1 = W - M - col * (cw + gap)
                y0 = top + row_pad + line * (ch + gap)
                _tile(page, pen, pymupdf.Rect(x1 - cw, y0, x1, y0 + ch), it)
            y = top + k * (ch + gap) - gap + 2 * row_pad
            page.draw_line((M, y), (W - M, y), color=_rgb(RULE), width=0.6)
            return y
        groups = [{"name": "", "items": items}]   # הרבה שאלות: משבצות בשורה אחת, קטנות יותר

    label_w = 96.0
    longest = max(len(it["sec"]) for gr in groups for it in gr["items"])
    most = max(len(gr["items"]) for gr in groups)
    if longest <= 4:   # רוחב משבצת: 70, וצר יותר (עד 56) כדי שכל הסעיפים של שאלה ייכנסו בשורה אחת
        cw = max(56.0, min(70.0, (inner - label_w - 8 - (most - 1) * gap) / most))
    else:
        cw = 112.0
    lines = []
    for gr in groups:
        avail = inner - (label_w + 8 if gr["name"] else 0)
        per = max(1, int((avail + gap) / (cw + gap) + 1e-6))
        n = len(gr["items"])
        lines.append((n + per - 1) // per)
    # גובה משבצת: 26, וקטן יותר כשיש הרבה שורות (עד 20)
    ch = 26.0 if longest <= 4 else 30.0
    row_pad = 7.0
    while ch > 20 and sum(k * (ch + gap) - gap + 2 * row_pad for k in lines) > budget:
        ch -= 1
        row_pad = max(4.0, row_pad - 0.5)
    y = top
    for gr, k in zip(groups, lines):
        row_h = k * (ch + gap) - gap + 2 * row_pad
        x_right = W - M
        if gr["name"]:
            got = sum(it["p"] for it in gr["items"])
            full = sum(it["full"] for it in gr["items"])
            single = len(gr["items"]) == 1
            box = pymupdf.Rect(x_right - label_w, y + row_pad - 1, x_right, y + row_h)
            h = pen.para(box, gr["name"], 11, INK, bold=True)
            if not single:
                pen.para(pymupdf.Rect(box.x0, box.y0 + h, box.x1, box.y1 + 4), f"{_pts(got)}/{_pts(full)} נקודות",
                         8.5, INK3)
            x_right -= label_w + 8
        per = max(1, int((x_right - M + gap) / (cw + gap) + 1e-6))
        for j, it in enumerate(gr["items"]):
            col, line = j % per, j // per
            x1 = x_right - col * (cw + gap)
            r = pymupdf.Rect(x1 - cw, y + row_pad + line * (ch + gap), x1, y + row_pad + line * (ch + gap) + ch)
            _cell(page, pen, r, it)
        y += row_h
        page.draw_line((M, y), (W - M, y), color=_rgb(RULE), width=0.6)
    return y


def _tile(page: pymupdf.Page, pen: _Pen, r: pymupdf.Rect, it: dict) -> None:
    """כרטיס של שאלה בלי סעיפים: למעלה שם השאלה ו-✓/✗, למטה הניקוד בגדול."""
    color, soft = _COLORS[it["kind"]]
    page.draw_rect(r, color=_rgb(color), fill=_rgb(soft), width=0.7, radius=0.16, stroke_opacity=0.4)
    page.draw_rect(pymupdf.Rect(r.x1 - 3.2, r.y0 + 6, r.x1 - 1.3, r.y1 - 6), color=None, fill=_rgb(color), radius=0.5)
    pad = 8.0
    s = 12.0
    if it["kind"] != "none":
        _icon(page, r.x0 + pad, r.y0 + pad - 1, s, "full" if it["kind"] == "full" else "x", color)
    pen.para(pymupdf.Rect(r.x0 + pad + s + 4, r.y0 + pad - 2.5, r.x1 - pad - 2, r.y0 + pad + 14), it["sec"],
             10.5, INK, bold=True)
    got, full = _pts(it["p"]), _pts(it["full"])
    size = min(16.0, r.height * .32)
    w_got = pen.width(got, size, bold=True)
    w_full = pen.width(f"/{full}", size * .7)
    x0 = (r.x0 + r.x1) / 2 - (w_got + w_full) / 2
    base = r.y1 - pad
    pen.text(x0, base, got, size, color, bold=True)
    pen.text(x0 + w_got, base, f"/{full}", size * .7, INK2)


def _cell(page: pymupdf.Page, pen: _Pen, r: pymupdf.Rect, it: dict) -> None:
    """משבצת בשורה אחת, מימין לשמאל: אות הסעיף, הניקוד, ✓/✗."""
    color, soft = _COLORS[it["kind"]]
    page.draw_rect(r, color=_rgb(color), fill=_rgb(soft), width=0.7, radius=0.22, stroke_opacity=0.4)
    page.draw_rect(pymupdf.Rect(r.x1 - 3, r.y0 + 4, r.x1 - 1.2, r.y1 - 4), color=None, fill=_rgb(color), radius=0.5)
    pad = 6.5
    size = min(11.0, r.height * .42)
    base = (r.y0 + r.y1) / 2 + size * .36
    s = size * .95
    if it["kind"] != "none":
        _icon(page, r.x0 + pad, (r.y0 + r.y1) / 2 - s / 2, s, "full" if it["kind"] == "full" else "x", color)
    sec = it["sec"]
    sec_w = 0.0
    if sec and (len(sec) == 1 or not re.search(r"[֐-׿]", sec)):
        pen.text(r.x1 - pad - 1.5, base, sec, size, INK, bold=True, align="right")
        sec_w = pen.width(sec, size, bold=True)
    elif sec:   # שם שלם (שאלות בלי מספר קצר)
        sec_w = r.width * .5
        pen.para(pymupdf.Rect(r.x1 - pad - sec_w, r.y0 + 2, r.x1 - pad, r.y1 - 2), sec, 8.5, INK, bold=True, lh=1.15)
    got, full = _pts(it["p"]), _pts(it["full"])
    w_got = pen.width(got, size, bold=True)
    w_full = pen.width(f"/{full}", size * .8)
    # הניקוד באמצע הרווח שבין הסימן לאות
    left, right = r.x0 + pad + s + 2, r.x1 - pad - 1.5 - sec_w - 3
    if w_got + w_full > right - left:   # "0.5/3": קטן יותר, כדי שלא יעלה על האות
        k = max(0.6, (right - left) / (w_got + w_full))
        size, w_got, w_full = size * k, w_got * k, w_full * k
    x0 = (left + right) / 2 - (w_got + w_full) / 2
    pen.text(x0, base, got, size, color, bold=True)
    pen.text(x0 + w_got, base, f"/{full}", size * .8, INK2)


def _legend(page: pymupdf.Page, pen: _Pen, y: float, kinds: set[str]) -> None:
    """מקרא קטן בצד שמאל של כותרת המפה. נקרא מימין לשמאל: סימן ואז מילה."""
    x = M
    for kind, word in (("zero", "אפס"), ("part", "ירדו נקודות"), ("full", "ניקוד מלא")):  # משמאל לימין
        if kind not in kinds:
            continue
        color, soft = _COLORS[kind]
        w = pen.width(word, 8.5) + 4
        pen.para(pymupdf.Rect(x, y - 10.2, x + w, y + 4), word, 8.5, INK2)
        bx = x + w + 3
        page.draw_rect(pymupdf.Rect(bx, y - 9, bx + 11, y + 2), color=_rgb(color), fill=_rgb(soft), width=0.6, radius=0.25)
        _icon(page, bx + 2, y - 7, 7, "full" if kind == "full" else "x", color)
        x = bx + 11 + 14


def summary_page(doc: pymupdf.Document, g: Graded, ctx: Context, archive, extra: list[str] | None = None) -> None:
    """עמוד ראשון חדש: הציון בטבעת, מפת השאלות, איפה ירדו נקודות, המשוב (ואחריו הערות שלא היה להן מקום על העבודה)."""
    page = doc.new_page(0, width=W, height=H)
    pen = _Pen(page, archive)
    groups = _groups(ctx, g)
    items = [it for gr in groups for it in gr["items"]]
    lost = [it for it in items if it["kind"] in ("part", "zero")]
    notes = [(it, g.mistakes[it["i"]]) for it in items
             if it["kind"] == "full" and it["i"] < len(g.mistakes) and g.mistakes[it["i"]] and it["comment"]]
    frac = g.grade / ctx.max_grade if ctx.max_grade else 0
    color, verdict = _band(frac)

    # ---------- הכותרת: כרטיס עם הטבעת משמאל ----------
    head = pymupdf.Rect(M, M, W - M, M + 112)
    page.draw_rect(head, color=_rgb(RULE), fill=_rgb(SHEET2), width=0.8, radius=0.12)
    page.draw_rect(pymupdf.Rect(head.x1 - 5, head.y0 + 14, head.x1 - 1.5, head.y1 - 14), color=None, fill=_rgb(color), radius=0.5)
    r = 41.0
    _ring(page, pen, head.x0 + 26 + r, (head.y0 + head.y1) / 2, r, g, ctx, color)
    graded = [it for it in items if it["kind"] != "none"]
    n_full = sum(it["kind"] == "full" for it in graded)
    unit = "סעיפים" if any(it["sec"] for it in items) and not all(len(gr["items"]) == 1 for gr in groups) else "שאלות"
    if not graded:
        line = ""
    elif not lost:
        line = f"ניקוד מלא בכל {len(graded)} ה{unit}."
    else:
        one = "בסעיף אחד" if unit == "סעיפים" else "בשאלה אחת"
        two = "בשני סעיפים" if unit == "סעיפים" else "בשתי שאלות"
        where = one if len(lost) == 1 else two if len(lost) == 2 else f"ב-{len(lost)} {unit}"
        line = (f"ניקוד מלא ב-{n_full} מתוך {len(graded)} {unit}. "
                f"ירדו נקודות {where}, {'והוא מפורט' if len(lost) == 1 else 'והם מפורטים'} למטה.")
    _stack(page, pymupdf.Rect(head.x0 + 2 * r + 46, head.y0 + 14, head.x1 - 18, head.y1 - 10), [
        {"text": ctx.course, "size": 9.5, "color": INK3},
        {"text": ctx.title, "size": 16, "color": INK, "bold": True, "mt": 2},
        {"text": verdict, "size": 19, "color": color, "bold": True, "mt": 7},
        {"text": line, "size": 10.5, "color": INK2, "mt": 3}], lh=1.3)

    # ---------- המפה ----------
    y = head.y1 + 22
    pen.para(pymupdf.Rect(W / 2, y - 12, W - M, y + 4), "הניקוד בכל שאלה", 12, INK, bold=True)
    _legend(page, pen, y, {it["kind"] for it in items})
    y += 7
    page.draw_line((M, y), (W - M, y), color=_rgb(RULE), width=0.6)
    y = _grid(page, pen, groups, y, budget=0.36 * H)

    # ---------- איפה ירדו נקודות, הערות בלי הורדה, משוב ----------
    footer = H - M - 4
    page.draw_line((M, footer - 8), (W - M, footer - 8), color=_rgb(RULE), width=0.5)
    pen.para(pymupdf.Rect(M, footer - 4, W - M, footer + 12),
             "הסימונים וההערות המלאות כתובים על העבודה עצמה, בעמודים הבאים.", 8.5, INK3)

    blocks: list[tuple] = []
    if lost:
        blocks.append(("title", "איפה איבדתם נקודות", BAD, 0, 5))
        blocks.append(("table", [(it["label"], f"-{_pts(it['full'] - it['p'])}", *_COLORS[it["kind"]], True, it["comment"])
                                 for it in lost]))
    if notes:
        blocks.append(("title", "שימו לב (בלי הורדת נקודות)", NOTE, 12, 5))
        blocks.append(("table", [(it["label"], "✓", NOTE, NOTE_SOFT, False, it["comment"]) for it, _ in notes]))
    if g.feedback:
        # שורה לכל נושא (המשוב כתוב בשורות: מה טוב, "מה לתקן:", ואז שאלה בכל שורה), עם רווח קטן ביניהן
        lines = [l.strip() for l in str(g.feedback).splitlines() if l.strip()]
        blocks += [("title", "משוב", INK, 12, 3)] + [("p", l, 3 if i else 0) for i, l in enumerate(lines)]
    if extra:
        blocks.append(("title", "הערות נוספות", INK, 12, 3))
        blocks += [("p", t, 3) for t in extra]
    if blocks:
        _body(page, pymupdf.Rect(M, y + 14, W - M, footer - 14), blocks)


LH = 1.35   # גובה שורה בחלק התחתון


def _lines(page, x0: float, x1: float, y: float, text: str, size: float, color: str, bold: bool, draw: bool,
           align: str = "right") -> float:
    """פסקה ברוחב x0..x1 שמתחילה ב-y. מחזיר את הגובה שלה."""
    lay = rtl.layout(text, (x1 - x0) / size, bold)
    if draw:
        rtl.write(page, pymupdf.Rect(x0, y, x1, y + 1), lay, size, color, bold=bold, align=align, lh=LH)
    return len(lay.lines) * size * LH


def _table(page, rect: pymupdf.Rect, y: float, rows: list[tuple], s: float, draw: bool) -> float:
    """טבלה מימין לשמאל: שם השאלה (מודגש, על רקע בצבע), התג ("-4" או ✓) על אותו רקע, וההערה, עם קו דק מתחת.
    מחזיר את הגובה שלה."""
    size, pad = 10 * s, 2.5 * s
    lw = min(max(rtl.width(r[0], size, bold=True) for r in rows), rect.width * 0.4) + 14 * s
    tw = max(rtl.width(r[1], size, bold=r[4]) for r in rows) + 12 * s
    xt = rect.x1 - lw - tw                    # הקצה הימני של עמודת ההערה
    top = y
    for label, tag, color, soft, bold, text in rows:
        h_label = _lines(page, rect.x1 - lw + 2 * s, rect.x1 - 6 * s, y + pad, label, size, INK, True, False)
        h_text = _lines(page, rect.x0 + 2 * s, xt - 8 * s, y + pad, text, size, INK, False, False)
        row_h = max(h_label, h_text, size * LH) + 2 * pad
        if draw:
            page.draw_rect(pymupdf.Rect(xt, y, rect.x1, y + row_h - 1.5 * s), color=None, fill=_rgb(soft))
            page.draw_line((rect.x0, y + row_h - 0.3), (xt, y + row_h - 0.3), color=_rgb(RULE), width=0.6)
            _lines(page, rect.x1 - lw + 2 * s, rect.x1 - 6 * s, y + pad, label, size, INK, True, True)
            _lines(page, xt + 2 * s, rect.x1 - lw, y + pad, tag, size, color, bold, True, align="center")
            _lines(page, rect.x0 + 2 * s, xt - 8 * s, y + pad, text, size, INK, False, True)
        y += row_h
    return y - top


def _body(page: pymupdf.Page, rect: pymupdf.Rect, blocks: list[tuple]) -> None:
    """החלק התחתון: כותרות, טבלאות ופסקאות זו מתחת לזו. הכול מוקטן יחד עד שנכנס לעמוד אחד."""
    def run(s: float, draw: bool) -> float:
        y = rect.y0
        for k, b in enumerate(blocks):
            if b[0] == "title":
                _, text, color, mt, mb = b
                y += (mt if k else 0) * s
                y += _lines(page, rect.x0, rect.x1, y, text, 12 * s, color, True, draw) + mb * s
            elif b[0] == "p":
                y += _lines(page, rect.x0, rect.x1, y, b[1], 10 * s, INK2, False, draw) + b[2] * s
            else:
                y += _table(page, rect, y, b[1], s, draw)
        return y - rect.y0

    s = 1.0
    while s > 0.3 and run(s, False) > rect.height:
        s *= 0.95
    run(s, True)
