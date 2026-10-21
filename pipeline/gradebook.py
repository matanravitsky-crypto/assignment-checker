"""טבלת הציונים ציונים.xlsx בתיקיית המטלה.

זה המקום שבו הצוות עובד: פותחים את הקובץ ב-Excel Online (כמה אנשים יכולים לערוך
יחד), עוברים על הציונים, מתקנים ומסמנים "מאושר". המערכת שומרת על מה שהצוות כתב:
כשהיא מעדכנת את הקובץ, היא משנה רק את העמודות שלה, ולא נוגעת בציון, במשוב ובאישור.

חשוב: לא להריץ משיכה בזמן שמישהו עורך את הקובץ, אחרת OneDrive עלול ליצור עותק כפול.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

SHEET = "ציונים"

# מצבים של הגשה
PENDING = "ממתינה לבדיקה"
CHECKED = "נבדקה"
RETURNED = "הוחזרה"
NEEDS_ATTENTION = "דורשת טיפול"


def columns(questions: int) -> list[str]:
    return [
        "מזהה במודל", "שם מלא", "ת״ז", "מייל", "הוגשה", "קבצים", "עמודים", "מצב",
        *[f"ש{i}" for i in range(1, questions + 1)],
        "ציון", "משוב", "מאושר", "הערות מערכת",
    ]


# העמודות שהמערכת מעדכנת בכל משיכה. כל השאר שייכות לצוות ולבדיקה.
SYSTEM_COLUMNS = {"שם מלא", "ת״ז", "מייל", "הוגשה", "קבצים", "עמודים", "הערות מערכת"}

_WIDTHS = {"מזהה במודל": 12, "שם מלא": 22, "ת״ז": 12, "מייל": 26, "הוגשה": 17, "קבצים": 26, "עמודים": 8,
           "מצב": 15, "ציון": 8, "משוב": 50, "מאושר": 9, "הערות מערכת": 30}


class GradeBook:
    def __init__(self, path: Path, questions: int = 4):
        self.path = path
        self.cols = columns(questions)
        if path.exists():
            self.wb = load_workbook(path)
            self.ws = self.wb[SHEET] if SHEET in self.wb.sheetnames else self.wb.active
            header = [c.value for c in self.ws[1]]
            # עמודות שנוספו בגרסה חדשה של המערכת נוספות בסוף, בלי לשבור קובץ קיים
            for col in self.cols:
                if col not in header:
                    header.append(col)
                    self.ws.cell(row=1, column=len(header), value=col)
            self.cols = header
        else:
            self.wb = Workbook()
            self.ws = self.wb.active
            self.ws.title = SHEET
            self.ws.append(self.cols)
            self._style_new_sheet()

    def _style_new_sheet(self) -> None:
        ws = self.ws
        ws.sheet_view.rightToLeft = True
        ws.freeze_panes = "C2"
        head_fill = PatternFill("solid", fgColor="E3E9FA")
        for i, name in enumerate(self.cols, start=1):
            cell = ws.cell(row=1, column=i)
            cell.font = Font(bold=True)
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.column_dimensions[cell.column_letter].width = _WIDTHS.get(name, 7)
        approve_col = ws.cell(row=1, column=self.cols.index("מאושר") + 1).column_letter
        dv = DataValidation(type="list", formula1='"כן,לא"', allow_blank=True)
        dv.add(f"{approve_col}2:{approve_col}2000")
        ws.add_data_validation(dv)

    # ---------- קריאה וכתיבה ----------
    def _col(self, name: str) -> int:
        return self.cols.index(name) + 1

    def rows(self) -> dict[str, int]:
        """מזהה במודל → מספר שורה."""
        out = {}
        for r in range(2, self.ws.max_row + 1):
            v = self.ws.cell(row=r, column=self._col("מזהה במודל")).value
            if v is not None:
                out[str(v)] = r
        return out

    def get(self, moodle_id: str) -> dict:
        r = self.rows().get(str(moodle_id))
        if not r:
            return {}
        return {name: self.ws.cell(row=r, column=i + 1).value for i, name in enumerate(self.cols)}

    def upsert(self, moodle_id: str, values: dict, change: str, problem: bool = False) -> None:
        """מוסיף שורה או מעדכן שורה קיימת.

        change הוא "new", "updated" או "same" (מה קרה לקבצים בתיקייה).
        problem אומר שאי אפשר לבדוק את ההגשה (למשל קובץ ריק), ואז המצב "דורשת טיפול".
        בהגשה חדשה המצב הוא "ממתינה לבדיקה". אם סטודנט הגיש מחדש אחרי שכבר נבדק,
        המצב חוזר ל"ממתינה לבדיקה" ונכתבת הערה, כדי שאף אחד לא יפספס.
        """
        rows = self.rows()
        r = rows.get(str(moodle_id))
        if r is None:
            r = self.ws.max_row + 1
            self.ws.cell(row=r, column=self._col("מזהה במודל"), value=str(moodle_id))
        for name, value in values.items():
            if name in SYSTEM_COLUMNS:
                self.ws.cell(row=r, column=self._col(name), value=value)

        status_cell = self.ws.cell(row=r, column=self._col("מצב"))
        fresh = NEEDS_ATTENTION if problem else PENDING
        if change == "new":
            status_cell.value = fresh
        elif change == "updated":
            was = status_cell.value
            status_cell.value = fresh
            if was in (CHECKED, RETURNED):
                note = self.ws.cell(row=r, column=self._col("הערות מערכת"))
                note.value = "; ".join(x for x in [note.value, f"הוגשה מחדש אחרי ש{was}"] if x)
        elif status_cell.value is None:
            status_cell.value = fresh

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp.xlsx")
        self.wb.save(tmp)
        tmp.replace(self.path)


def fmt_time(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""
