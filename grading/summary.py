"""עמוד הסיכום של עבודה בדוקה, בכיוון "תעודה": למעלה הציון בטבעת, שם המטלה ומשפט אחד; באמצע מפה של
השאלות (כל סעיף משבצת: ירוק ✓ ניקוד מלא, כתום ✗ ירדו נקודות, אדום ✗ אפס); למטה רק מה שירד, עם ההערה.
תחליף ל-grade._summary_page: אותה חתימה. הצורות מצוירות ב-PyMuPDF, והטקסט העברי ב-insert_htmlbox."""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from .grade import (Context, Graded, _CSS, _FONT, _esc, _pts, _rich, assigned, shown_labels)

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
CSS = _CSS + (f" @font-face {{font-family: heb; font-weight: bold; src: url({_BOLD.name});}}" if _BOLD else "")

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
    """טקסט קצר בלי עברית רב-אותית (מספרים, אות סעיף אחת): insert_text, מהיר ומדויק. כל השאר: insert_htmlbox."""

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

    def html(self, rect: pymupdf.Rect, html: str) -> tuple[float, float]:
        return self.page.insert_htmlbox(rect, html, css=CSS, archive=self.archive, scale_low=0)


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
    pen.html(pymupdf.Rect(cx - r, cy + size * .42, cx + r, cy + size * .42 + 14),
             f'<div dir="rtl" style="text-align:center; font-size:8.5px; color:{INK3}">מתוך {_pts(ctx.max_grade)}</div>')


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
            tail = "" if single else (
                f'<br><span style="font-size:8.5px; color:{INK3}; font-weight:normal">'
                f'{_rich(f"{_pts(got)}/{_pts(full)}")} נקודות</span>')
            pen.html(pymupdf.Rect(x_right - label_w, y + row_pad - 1, x_right, y + row_h),
                     f'<div dir="rtl" style="font-size:11px; font-weight:bold; color:{INK}; line-height:1.25">'
                     f'{_rich(gr["name"])}{tail}</div>')
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
    pen.html(pymupdf.Rect(r.x0 + pad + s + 4, r.y0 + pad - 2.5, r.x1 - pad - 2, r.y0 + pad + 14),
             f'<div dir="rtl" style="font-size:10.5px; font-weight:bold; color:{INK}">{_rich(it["sec"])}</div>')
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
        pen.html(pymupdf.Rect(r.x1 - pad - sec_w, r.y0 + 2, r.x1 - pad, r.y1 - 2),
                 f'<div dir="rtl" style="font-size:8.5px; font-weight:bold; color:{INK}; line-height:1.15">{_rich(sec)}</div>')
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
        pen.html(pymupdf.Rect(x, y - 10.2, x + w, y + 4),
                 f'<div dir="rtl" style="font-size:8.5px; color:{INK2}">{word}</div>')
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
        line = (f"ניקוד מלא ב-{n_full} מתוך {len(graded)} {unit}. "
                f"ירדו נקודות ב-{len(lost)} {unit}, והם מפורטים למטה.")
    pen.html(pymupdf.Rect(head.x0 + 2 * r + 46, head.y0 + 14, head.x1 - 18, head.y1 - 10),
             f'<div dir="rtl" style="color:{INK}; line-height:1.3">'
             f'<p style="margin:0; font-size:9.5px; color:{INK3}">{_esc(ctx.course)}</p>'
             f'<p style="margin:2px 0 0; font-size:16px; font-weight:bold">{_esc(ctx.title)}</p>'
             f'<p style="margin:7px 0 0; font-size:19px; font-weight:bold; color:{color}">{verdict}</p>'
             f'<p style="margin:3px 0 0; font-size:10.5px; color:{INK2}">{_rich(line)}</p></div>')

    # ---------- המפה ----------
    y = head.y1 + 22
    pen.html(pymupdf.Rect(W / 2, y - 12, W - M, y + 4),
             f'<div dir="rtl" style="font-size:12px; font-weight:bold; color:{INK}">הניקוד בכל שאלה</div>')
    _legend(page, pen, y, {it["kind"] for it in items})
    y += 7
    page.draw_line((M, y), (W - M, y), color=_rgb(RULE), width=0.6)
    y = _grid(page, pen, groups, y, budget=0.36 * H)

    # ---------- איפה ירדו נקודות, הערות בלי הורדה, משוב ----------
    footer = H - M - 4
    page.draw_line((M, footer - 8), (W - M, footer - 8), color=_rgb(RULE), width=0.5)
    pen.html(pymupdf.Rect(M, footer - 4, W - M, footer + 12),
             f'<div dir="rtl" style="font-size:8.5px; color:{INK3}">'
             'הסימונים וההערות המלאות כתובים על העבודה עצמה, בעמודים הבאים.</div>')

    def rows(entries, color, soft, minus):
        out = []
        for it, extra_text in entries:
            delta = it["full"] - it["p"]
            tag = (f'<b style="color:{color}">{_rich(f"-{_pts(delta)}")}</b>' if minus
                   else f'<span style="color:{color}">✓</span>')
            text = it["comment"] or extra_text
            # שם, ניקוד והערה בשלושה תאים: "שאלה 11" ליד "-6" באותו תא התערבבו ל-"6- 11".
            # MuPDF מסדר עמודות של טבלה תמיד משמאל לימין, גם ב-dir="rtl": לכן התאים כתובים בסדר הפוך
            cell = f'background-color:{soft}; border-bottom:1.5px solid #FFFFFF; white-space:nowrap'
            out.append(
                f'<tr><td style="padding:2.5px 8px 2.5px 2px; border-bottom:0.6px solid {RULE}"><div dir="rtl">{_rich(text)}</div></td>'
                f'<td style="{cell}; padding:2.5px 2px 2.5px 7px">&#160;{tag}</td>'
                f'<td style="{cell}; padding:2.5px 6px 2.5px 2px"><b>{_rich(it["label"])}</b>&#160;&#160;</td></tr>')
        return "".join(out)

    parts = []
    if lost:
        body = "".join(rows([(it, "")], *_COLORS[it["kind"]], True) for it in lost)
        parts.append(f'<p style="margin:0 0 5px; font-size:12px; font-weight:bold; color:{BAD}">איפה איבדתם נקודות</p>'
                     f'<table style="width:100%; border-collapse:collapse">{body}</table>')
    if notes:
        parts.append(f'<p style="margin:12px 0 5px; font-size:12px; font-weight:bold; color:{NOTE}">'
                     'שימו לב (בלי הורדת נקודות)</p>'
                     f'<table style="width:100%; border-collapse:collapse">'
                     f'{rows([(it, "") for it, _ in notes], NOTE, NOTE_SOFT, False)}</table>')
    if g.feedback:
        parts.append(f'<p style="margin:12px 0 3px; font-size:12px; font-weight:bold; color:{INK}">משוב</p>'
                     f'<p style="margin:0; color:{INK2}">{_rich(g.feedback)}</p>')
    if extra:
        parts.append(f'<p style="margin:12px 0 3px; font-size:12px; font-weight:bold; color:{INK}">הערות נוספות</p>'
                     + "".join(f'<p style="margin:0 0 3px; color:{INK2}">{_rich(t)}</p>' for t in extra))
    if parts:
        pen.html(pymupdf.Rect(M, y + 14, W - M, footer - 14),
                 f'<div dir="rtl" style="font-size:10px; line-height:1.35; color:{INK}">{"".join(parts)}</div>')
