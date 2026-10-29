# rubric.json — the only file you edit

All strings are LaTeX (math in `$...$`). Every number is whole. Deductions are a whole number, a range `"2–4"`, or `"עד 7"`.
Types: `הבנה` · `חוסר` · `חישוב` · `סימון` · `נימוק חסר` — nothing else.

```json
{
  "course": "חדו\"א 2 להנדסת מערכות תוכנה ומידע",
  "code": "214-1-9761",
  "term": "מועד א', קיץ תשפ\"ו",
  "date": "13/10/2026",
  "lecturer": "ד\"ר דניס גולקו",
  "ta": "מר ליאור מנשה",
  "general_rules": [
    {"label": "מבנה", "text": "חלק א' – 4 שאלות של 25 נק'; נבדקות רק 3 השאלות שסומנו."}
  ],
  "questions": [
    {
      "n": 1, "points": 25,
      "sections": [
        {
          "letter": "א", "points": 10, "title": "ישרים נחתכים ומישור",
          "answer": "$a=-1$ (יחיד), נקודת החיתוך $(1,2,2)$, המישור $3x+5y+z=13$.",
          "solution": "\\ell_1: (1+t,\\,2-t,\\,2t) \\quad \\ell_2: (4+2s,\\,-1-s,\\,2a)",
          "steps": [
            {"desc": "בניית המערכת, פתרונה, $a=-1$ ונימוק היחידות", "points": 5},
            {"desc": "נקודת החיתוך $(1,2,2)$", "points": 1},
            {"desc": "וקטור נורמל ממכפלה וקטורית", "points": 2},
            {"desc": "משוואת המישור", "points": 2}
          ],
          "errors": [
            {"desc": "משוואת המישור חסרה", "type": "חוסר", "regular": "4", "strict": "4"},
            {"desc": "המישור בהצגה פרמטרית במקום משוואה אלגברית", "type": "הבנה", "regular": "3", "strict": "4"},
            {"desc": "סימון $\\cdot$ במקום $\\times$ לחישוב הנורמל", "type": "סימון", "regular": "1", "strict": "2"}
          ]
        }
      ]
    }
  ],
  "american": [
    {"n": 5, "answer": "ב", "points": 9, "reason": "הנקודות הקריטיות הן $(0,0)$ ו-$(1,1)$; ב-$(1,1)$ מינימום, ב-$(0,0)$ אוכף."}
  ]
}
```

Optional: `count` on a section — one block for several identical sections (`"letter": "א, ב, ד, ה", "points": 3, "count": 4`; the question's sum uses points × count). `alt_methods` — a list of `{"name": "לגרנז'", "steps": [{"desc": "...", "points": n}, ...]}`; each alternative's steps must sum to the section points (students who used it are graded by that split). `solution` (display math, one or two lines), `note` on a section (plain remark, e.g. "שגיאות קטנות בפירוק – הערה בלבד"), `american` (omit if none), `general_rules` (omit → defaults from `assets/default-rules.json`).

`validate_rubric.py` rejects: section steps ≠ section points · alt_method steps ≠ section points · sections ≠ question points · unknown type · deduction > section points · מחמיר < רגיל · מחמיר = רגיל while רגיל < section points (מחמיר is the strict regime: רגיל + 1, capped) · empty answer.
