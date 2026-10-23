"""ניקוד לפי סעיפים: Claude מסווג, הקוד מנקד (§6 במחוון של המטלה).

כשבמחוון שבתיקייה "פדגוגי" יש לכל שאלה חלוקה לסעיפים ("| קבוצות 11 | 20 | א 3 · ב 3 · ג 8 · ד 3 · ה 3 |")
וטבלה לכל סעיף, Claude לא נותן ניקוד לשאלה. לכל סעיף הוא מחזיר את השורה בטבלה שהתאימה (row_id), את ערך
השורה (base), את מתאמי הסעיף ואת התגיות. הקוד:
  - לוקח את ערך השורה מהטבלה עצמה, ולא מ-Claude, כשהשורה היא שורה של כל הסעיף
  - מבטל מתאמים ותגיות שהכללים אוסרים (שכבר כלולים בשורה, או בשורה חלקית)
  - מחיל את התקרות של ההורדות הגלובליות, ומנכה אותן מהסעיפים שבהם נרשמו
כך אותה טעות מקבלת אותה הורדה אצל כל הסטודנטים, וכל ניקוד אפשר לבדוק חזרה עד השורה במחוון.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

ADJUSTERS = ["FALSE-STEP", "FINAL_COPY", "CONFLICT"]
NOTATION = ["N1", "N3", "N4", "N6"]
TAGS = ["W", "EMPTYSET", "TUPLESET", "DOMAIN", "UNION", "SIDE", *NOTATION, "OOS"]
# סדר הניכוי בתוך סעיף (תגיות לא מורידות יותר מערך הסעיף), והתקרה של כל אחת בכל המטלה
ORDER = ["W", "EMPTYSET", "TUPLESET", "DOMAIN", "UNION", "SIDE"]
CAPS = {"W": 4, "EMPTYSET": 2, "TUPLESET": 2, "DOMAIN": 1, "UNION": 1}
FORM_CAP = 6   # כל הורדות הצורה יחד, כולל הסימון
SIDE_CAP = 2
NOTATION_FROM = 3  # הורדת סימון אחת כשבשלושה סעיפים או יותר יש תגית סימון
FORM_TAGS = {"W", "EMPTYSET", "TUPLESET", "DOMAIN", "UNION", *NOTATION}


@dataclass
class Part:
    id: str              # "11א"
    question: int        # מספר השאלה ב-ctx.questions, מ-0
    points: float
    by_components: bool = False  # מנוקד לפי רכיבים (7ג: חסר + חסר + צורה): הערך הוא סכום של Claude


@dataclass
class Row:
    base: float | None   # None: הערך לא מספר אחד ("חצי לכל חסר")
    tags: list[str] = field(default_factory=list)    # תגיות שהשורה עצמה נוקבת בהן ("· DOMAIN")
    embeds: list[str] = field(default_factory=list)  # מתאמים שכבר כלולים בשורה ("(כולל FALSE-STEP)")


def _cells(line: str) -> list[str]:
    return [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]


def question_number(label: str) -> str:
    """"דף קבוצות 11" → "11"."""
    m = re.search(r"(\d+)\s*$", label)
    return m.group(1) if m else ""


def parse_parts(text: str, labels: list[str], points: list[float]) -> list[list[Part]]:
    """לכל שאלה: הסעיפים שלה, מטבלת הניקוד ("| קבוצות 11 | 20 | א 3 · ב 3 |"). שאלה שסכום הסעיפים שלה
    לא שווה לניקוד שלה לא מתחלקת לסעיפים (רשימה ריקה), כדי שטבלה חלקית לא תשנה ציון."""
    found: dict[int, list[Part]] = {}
    for line in text.splitlines():
        cells = _cells(line)
        if len(cells) < 3 or not re.fullmatch(r"\d+(\.\d+)?", cells[1]):
            continue
        pairs = re.findall(r"([א-ת]+)\s+(\d+(?:\.\d+)?)", cells[2].replace("*", ""))
        if not pairs:
            continue
        for i, label in enumerate(labels):
            if i not in found and re.search(r"(^|\s)" + re.escape(cells[0]) + "$", label):
                num = question_number(label)
                found[i] = [Part(num + letter, i, float(p)) for letter, p in pairs]
    out = []
    for i, label in enumerate(labels):
        parts = found.get(i, [])
        out.append(parts if parts and math.isclose(sum(p.points for p in parts), points[i]) else [])
    by_id = {p.id: p for parts in out for p in parts}
    # "#### 7ג (5): $2$ (2) + $-1+2i$ (2) + צורה (1)": סעיף שמנוקד לפי רכיבים
    for line in text.splitlines():
        if line.startswith("####") and re.search(r"\(\d+(?:\.\d+)?\)\s*\+", line):
            for pid in re.findall(r"(\d+[א-ת]+)\s*\(\d", line):
                if pid in by_id:
                    by_id[pid].by_components = True
    return out


def _row(cell: str) -> Row:
    m = re.match(r"(\d+(?:\.\d+)?)(?![\d.]|\s*(?:לחסר|מתוך))", cell)
    tags = []
    for t in re.findall(r"[·+]\s*([A-Z][A-Z0-9_]*(?:[−-]1)?(?:/N\d)*)", cell):
        t = "W" if t.startswith("W") else t.split("/")[0]
        if t in TAGS and t not in tags:
            tags.append(t)
    embeds = [e for e in re.findall(r"כולל ([A-Z_-]+)", cell) if e in ADJUSTERS + ["SIDE"]]
    return Row(float(m.group(1)) if m else None, tags, embeds)


def parse_rows(text: str) -> dict[str, Row]:
    """כל שורה בטבלאות הסעיפים: "| 12ד-3 | מה כתוב | 4 · TUPLESET (=3) | הערה |"."""
    rows: dict[str, Row] = {}
    for line in text.splitlines():
        cells = _cells(line)
        if len(cells) >= 3 and re.fullmatch(r"\d+[א-ת]*-\S+", cells[0]) and cells[0] not in rows:
            rows[cells[0]] = _row(cells[2])
    return rows


def row_fits(row_id: str, part: Part) -> bool:
    """"12ד-3" שייכת ל-12ד, "6-6" לכל סעיף של שאלה 6, "8אב-4" ל-8א ול-8ב."""
    m = re.match(r"(\d+)([א-ת]*)-", row_id)
    if not m:
        return False
    num, letters = m.groups()
    own = re.match(r"(\d+)([א-ת]+)", part.id)
    return bool(own) and own.group(1) == num and (not letters or own.group(2) in letters)


def _clamp(x: float, top: float) -> float:
    return min(max(x, 0), top)


def _num(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0
    return x if math.isfinite(x) else 0


@dataclass
class PartScore:
    part: str
    question: int
    max: float
    row_id: str
    base: float
    adjusters: list[str]
    tags: list[str]
    final_answer: str
    unsure: bool
    points: float = 0          # אחרי הכול: מתאמים, תגיות ותקרות
    status: str = "graded"


def score(got: list[dict], questions: list[list[Part]], rows: dict[str, Row]) -> tuple[list[PartScore], list[str], list[str]]:
    """מה ש-Claude החזיר לכל סעיף → ניקוד לכל סעיף. מחזיר גם מה הקוד תיקן (fixes) ואילו סעיפים חסרים בתשובה."""
    answers: dict[str, dict] = {}
    for a in got:
        if isinstance(a, dict):
            answers.setdefault(str(a.get("part") or "").strip(), a)
    out: list[PartScore] = []
    fixes: list[str] = []
    absent: list[str] = []
    deduct: list[dict[str, float]] = []
    for part in (p for parts in questions for p in parts):
        a = answers.get(part.id)
        if a is None:
            absent.append(part.id)
            a = {"status": "missing"}
        ids = [r.strip() for r in str(a.get("row_id") or "").split(",") if r.strip()]
        ps = PartScore(part.id, part.question, part.points, ", ".join(ids), 0, [], [], str(a.get("final_answer") or "").strip(),
                       a.get("unsure") is True or ids == ["NONE"], status="missing" if a.get("status") == "missing" else "graded")
        if ps.status == "missing":
            out.append(ps)
            deduct.append({})
            continue
        row = rows.get(ids[0]) if len(ids) == 1 else None
        if row is not None and not row_fits(ids[0], part):
            fixes.append(f"{part.id}: השורה {ids[0]} שייכת לסעיף אחר")
            row = None
        claimed = _clamp(_num(a.get("base")), part.points)
        base = claimed
        if row is not None and row.base is not None and not part.by_components:
            base = _clamp(row.base, part.points)
            if base != claimed:
                fixes.append(f"{part.id}: ערך השורה {ids[0]} הוא {base:g}, לא {claimed:g}")
        full = base >= part.points
        embeds = row.embeds if row else []
        named = set(row.tags) if row else set()
        adjusters = []
        for x in a.get("adjusters") or []:
            if x not in ADJUSTERS or x in adjusters:
                continue
            if x in embeds:
                fixes.append(f"{part.id}: {x} כבר כלול בשורה {ids[0]}")
            elif not full:
                fixes.append(f"{part.id}: {x} רק בשורה שערכה המקסימום")
            else:
                adjusters.append(x)
        tags = [t for t in (row.tags if row else []) if t != "OOS"]
        for t in a.get("tags") or []:
            if t not in TAGS or t in tags:
                continue
            if t in FORM_TAGS and not full and t not in named:
                fixes.append(f"{part.id}: תגית צורה {t} לא נרשמת בשורה חלקית")
            elif t == "SIDE" and "SIDE" in embeds:
                fixes.append(f"{part.id}: SIDE כבר כלול בשורה {ids[0]}")
            else:
                tags.append(t)
        ps.base, ps.adjusters, ps.tags = base, adjusters, tags
        ps.points = _clamp(base - len(adjusters), part.points)
        room, d = ps.points, {}
        for t in ORDER:
            if t in tags:
                d[t] = min(1, room)
                room -= d[t]
        out.append(ps)
        deduct.append(d)

    # ההורדות הגלובליות, עם התקרות, מנוכות מהסעיפים שבהם נרשמו, לפי הסדר
    form_left = FORM_CAP
    for t in ORDER[:-1]:
        left = CAPS[t]
        for ps, d in zip(out, deduct):
            take = min(d.get(t, 0), left, form_left)
            ps.points -= take
            left -= take
            form_left -= take
    if sum(1 for ps in out if set(ps.tags) & set(NOTATION)) >= NOTATION_FROM and form_left >= 1:
        ps = next((ps for ps in out if set(ps.tags) & set(NOTATION) and ps.points >= 1), None)
        if ps:
            ps.points -= 1
    side_left = SIDE_CAP
    for ps, d in zip(out, deduct):
        take = min(d.get("SIDE", 0), side_left)
        ps.points -= take
        side_left -= take
    return out, fixes, absent
