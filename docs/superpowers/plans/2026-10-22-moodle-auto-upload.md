# העלאה אוטומטית למודל: תוכנית עבודה

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** כפתור "העלה למודל" באתר המקומי, שמכין את העבודות מ-`2 - Graded with comments`, ואחרי אישור אחד מעלה אותן למודל ZIP אחרי ZIP דרך Claude עם התוסף לכרום.

**Architecture:** הקוד ב-Python מחליט מה עולה, אורז, נועל, רושם ביומן ומנהל את הלולאה (`moodle/send.py`). Claude עושה רק את מה שבדפדפן: ריצה נפרדת של `claude -p --chrome` לכל ZIP (`moodle/claude_driver.py`), שמחזירה תשובה במבנה קבוע. השרת המקומי (`dashboard/`) מריץ את הלולאה ברקע, והאתר שואל אותו מה המצב.

**Tech Stack:** Python 3.14 (ספרייה סטנדרטית בלבד, בלי תלות חדשה), Claude Code CLI 2.1.x עם `--chrome`, ה-JS הקיים של האתר, pytest.

**Spec:** `docs/superpowers/specs/2026-10-22-moodle-auto-upload-design.md`

**שינוי אחד מהמסמך (הבחירה שלי):** במסמך Claude מריץ בעצמו את `python -m moodle record` אחרי כל ZIP. בתוכנית, הקוד ב-Python רושם ביומן אחרי שהוא קורא את התשובה של Claude. ככה ל-Claude אין גישה לשורת הפקודה בכלל, רק לכלים של הכרום. הפקודה `record` נשארת בשביל מי שמעלה ביד.

## Global Constraints

- עובדים על הענף `moodle-auto-upload`, ובסוף פותחים PR ל-`main`. לפני כל קומיט מריצים `python -m pytest` משורש הריפו. כרגע 47 בדיקות עוברות, והן צריכות להמשיך לעבור.
- הקוד והשמות באנגלית. כל מה שמשתמש רואה (אתר, הודעות שגיאה, פלט של CLI, `Upload steps.txt`) בעברית.
- אף שם, ת"ז או מייל של סטודנט לא נכנס ללוג, לאתר, לפלט, לתשובה של Claude, ל-git או לקובץ חדש בתיקייה המשותפת. רק מספרים (`0042`), שמות ZIP וכמויות. השמות קיימים רק בתוך ה-ZIP, כמו היום.
- בדיקות משתמשות רק בשמות בדויים (`tests/sample_files.NAMES`). אף בדיקה לא קוראת את `C:\Users\PC\BGU`.
- כל אצווה עולה רק אחרי "כן" של אדם: באתר, הכפתור בחלון האישור. בשורת הפקודה, `y` או `--yes`.
- כתובת ההעלאה היחידה: `https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id={id}&plugin=file&pluginsubtype=assignfeedback&action=viewpluginpage&pluginaction=uploadzip`, כאשר `id` נלקח מ-`Assignment details.json` של המטלה. לא משנים הגדרות מטלה ולא נוגעים בציונים.
- ZIP עד `CLAUDE_MAX_ZIP_BYTES = 9_000_000` (כבר קיים ב-`moodle/upload.py`).
- שמות הקבצים בתיקייה `3 - Ready to upload to Moodle`: `Upload log.csv` עם העמודות `number,file,sha256,zip,uploaded_at,by`, ו-`Upload batch.json`. בתיקיית המטלה: `Upload in progress.txt`, עם תוקף של 30 דקות מהעדכון האחרון.
- כל ריצה של Claude: `--chrome`, `--no-session-persistence`, `--add-dir` לתיקיית ההעלאה בלבד, כלים של `mcp__claude-in-chrome` בלבד, `--json-schema`, `--max-budget-usd` ו-timeout של התהליך.
- `moodle/` לא מייבא את `grading/`, כי `grading.grade` טוען את PyMuPDF, שנחסם במחשב של אורי.

## Review Focus

1. **קובץ בדוק שהשתנה בין "הכנה" ל"העלה":** מישהו הכין שוב בזמן שחלון האישור פתוח. אז `start` עם `batch_id` ישן נדחה ב-409 עם "הקבצים השתנו מאז ההכנה" (משימה 8, `test_start_with_stale_batch_is_refused`).
2. **התחברות שפגה באמצע אצווה:** ZIP 1 יובא, ובריצה על ZIP 2 Claude מחזיר `needs_login`. "המשך" מעלה מ-ZIP 2, ו-ZIP 1 לא עולה שוב (משימה 5, `test_resume_skips_zips_already_recorded`).
3. **שני מחשבים רשמו ביומן במקביל, ו-OneDrive יצר `Upload log-<PC>.csv`:** ההכנה נעצרת ומסבירה מה לאחד, כמו בעותק כפול של טבלת המפתח (משימה 4, `test_log_conflict_copy_blocks_prepare`).
4. **Claude לא מחובר, הפלט לא JSON, או שהריצה נתקעה:** האצווה נעצרת עם הסבר בעברית, ושום דבר לא נרשם (משימה 6, `test_parse_result_errors` ו-`test_timeout_is_an_error`).
5. **לסטודנט יש שני קבצים בדוקים, ואחד מהם גדול מדי:** כל המספר לא עולה ומופיע ב"גדולים מדי", ולא מועלה חצי ממנו שוב ושוב (משימה 4, `test_too_big_file_holds_back_the_whole_number`).

---

### Task 1: בדיקת היתכנות של המנוע (שער: אם נכשל, עוצרים וחוזרים למתן)

אין קוד בריפו. התוצאה היא קבוצת דגלים שעובדת, ונכנסת ל-`build_command` במשימה 6.

**דרוש מאדם:** מתן מריץ `claude auth login` ומתחבר בעצמו. Claude לא מקליד סיסמאות.

- [ ] **Step 1: לוודא התחברות**

Run: `claude auth status --json`
Expected: JSON שמראה שמחוברים. אם לא מחוברים: עוצרים ומבקשים ממתן להריץ `claude auth login`.

- [ ] **Step 2: ריצה מהשורה שמגיעה לכרום**

מתיקיית ה-scratchpad (לא מהריפו):
```bash
claude -p --chrome --no-session-persistence --setting-sources project --strict-mcp-config --allowedTools "mcp__claude-in-chrome" --output-format json --max-budget-usd 0.5 --json-schema '{"type":"object","properties":{"chrome":{"type":"boolean"},"moodle_logged_in":{"type":"boolean"},"message":{"type":"string"}},"required":["chrome","moodle_logged_in","message"]}' "Open https://moodle.bgu.ac.il/moodle/my/ in Chrome. Report whether the Chrome tools work and whether the page shows a logged-in Moodle user. Do not type anything into any field. Do not repeat any person's name."
```
Expected: `is_error: false`, ותשובה מובנית עם `chrome: true`. כדאי לרשום איפה בפלט נמצאת התשובה המובנית (למשל `structured_output` או בתוך `result`).

- [ ] **Step 3: לבדוק את המקרים שעלולים לתקוע**

1. אותה ריצה כשאפליקציית Claude (הדסקטופ) פתוחה ומחוברת לתוסף.
2. לבדוק שהתוסף לא פותח בקשת הרשאה לאתר, שאין מי שיאשר אותה. אם כן: מתן מאשר את moodle.bgu.ac.il בתוסף מראש, ומריצים שוב.
3. לבדוק שבפלט אין סימן ל-hooks או ל-plugins של המשתמש. אם יש: לנסות דגל אחר שמבודד, ולרשום מה עבד.

- [ ] **Step 4: להחליט**

אם שלב 2 עובד: לרשום בתחתית התוכנית, תחת "תוצאת משימה 1", את הדגלים שעבדו ואיפה נמצאת התשובה המובנית. אם לא עובד בשום צורה: לעצור את הביצוע, ולחזור למתן עם מה שנכשל. משימות 2–5 לא תלויות במנוע, ואפשר לבנות אותן רק אם מתן מאשר.

---

### Task 2: נעילה משותפת (`moodle/lock.py`)

**Files:**
- Create: `moodle/lock.py`
- Modify: `dashboard/actions.py` (`_me`, `_take_lock`, `LOCK_MINUTES`: עוברים להשתמש ב-`moodle.lock`)
- Test: `tests/moodle/test_lock.py`

**Interfaces:**
- Produces:
  - `LOCK_MINUTES = 30`
  - `class Locked(Exception)` עם `who: str`, `since: datetime`
  - `me() -> str`, מחזיר `"<user> (<host>)"`, כמו `_me` היום
  - `take(folder: Path, name: str, minutes: int = LOCK_MINUTES) -> Path` זורק `Locked` אם יש נעילה של מישהו אחר שהעדכון האחרון שלה מלפני פחות מ-`minutes` דקות. אחרת כותב `me()` ומחזיר את הנתיב.
  - `refresh(lock: Path) -> None` כותב שוב את `me()`, כדי שה-mtime יתעדכן.

- [ ] **Step 1: Write the failing tests**

```python
def test_take_writes_me_and_refuses_a_fresh_lock_of_someone_else(tmp_path):
    lock_path = take(tmp_path, "Upload in progress.txt")
    assert lock_path.read_text(encoding="utf-8") == me()
    lock_path.write_text("other (PC2)", encoding="utf-8")
    with pytest.raises(Locked) as e:
        take(tmp_path, "Upload in progress.txt")
    assert e.value.who == "other (PC2)"

def test_old_lock_is_ignored(tmp_path):
    p = tmp_path / "Upload in progress.txt"
    p.write_text("other (PC2)", encoding="utf-8")
    old = time.time() - 31 * 60
    os.utime(p, (old, old))
    assert take(tmp_path, p.name) == p

def test_refresh_moves_the_clock(tmp_path):
    p = take(tmp_path, "x.txt")
    old = time.time() - 29 * 60
    os.utime(p, (old, old))
    refresh(p)
    assert time.time() - p.stat().st_mtime < 5
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/moodle/test_lock.py -v`
Expected: FAIL (`ModuleNotFoundError: moodle.lock`)

- [ ] **Step 3: לממש את `moodle/lock.py`**, ולהעביר את `dashboard/actions._take_lock` לקרוא ל-`lock.take(a.dir, LOCK_FILE)`. `Locked` הופך ל-`UserError` עם אותו טקסט בעברית כמו היום.

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -q`
Expected: הכול עובר, כולל `test_pull_waits_for_someone_elses_pull` ו-`test_lock_is_released_when_pull_fails`.

- [ ] **Step 5: Commit**

```bash
git add moodle/lock.py dashboard/actions.py tests/moodle/test_lock.py
git commit -m "Share the folder lock between pull and upload"
```

---

### Task 3: יומן ההעלאה ורשימת האצווה (`moodle/upload_log.py`)

**Files:**
- Create: `moodle/upload_log.py`
- Modify: `moodle/paths.py` (מוסיפים `files_by_number`)
- Test: `tests/moodle/test_upload_log.py`

**Interfaces:**
- Consumes: `lock.me()` (משימה 2)
- Produces:
  - `paths.files_by_number(folder: Path, pattern: str = "*") -> dict[str, list[Path]]`: אותה התנהגות כמו `grading.grade.files_by_number` (`0001`, `0001-2`, ממוין לפי מספר ואז לפי הסדר).
  - `LOG_FILE = "Upload log.csv"`, `BATCH_FILE = "Upload batch.json"`, `LOG_FIELDS = ["number", "file", "sha256", "zip", "uploaded_at", "by"]`
  - `file_hash(path: Path) -> str`: SHA-256 בהקסה.
  - `read_log(assignment_dir: Path) -> list[dict]`: ריק אם אין יומן.
  - `last_hashes(assignment_dir: Path) -> dict[str, str]`: שם קובץ (`"0001-2.pdf"`) → ה-hash של ההעלאה האחרונה שלו.
  - `returned_numbers(assignment_dir: Path, marked: dict[str, list[Path]]) -> set[str]`: מספר נחשב מוחזר אם ל**כל** הקבצים שלו יש עכשיו אותו hash כמו בהעלאה האחרונה.
  - `log_conflicts(assignment_dir: Path) -> list[str]`: עותקים כפולים כמו `Upload log-DESKTOP.csv`.
  - `write_batch(assignment_dir: Path, batch: dict) -> None` ו-`read_batch(assignment_dir: Path) -> dict | None`. המבנה: `{"id": str, "assignment_id": str, "created_at": str, "zips": [{"name": str, "files": [{"number": str, "file": str, "sha256": str}]}]}`.
  - `record_zip(assignment_dir: Path, zip_name: str, by: str, now: datetime | None = None) -> int`: מוסיף ליומן שורה לכל קובץ של ה-ZIP לפי `Upload batch.json`, ומחזיר כמה שורות נכתבו. אם ה-ZIP לא נמצא ברשימת האצווה: `ValueError`.

היומן ורשימת האצווה נמצאים ב-`assignment_dir / paths.UPLOAD`, ובקידוד `utf-8-sig`, כמו שאר קובצי ה-CSV.

- [ ] **Step 1: Write the failing tests**

```python
def test_record_zip_appends_rows_from_the_batch(tmp_path):
    a = make_assignment(tmp_path)   # helper: UPLOAD dir + batch with zip "Graded - part 01.zip" holding 0001.pdf, 0002.pdf, 0002-2.pdf
    assert record_zip(a, "Graded - part 01.zip", by="me (PC)") == 3
    rows = read_log(a)
    assert [r["file"] for r in rows] == ["0001.pdf", "0002.pdf", "0002-2.pdf"]
    assert set(rows[0]) == set(LOG_FIELDS)

def test_record_unknown_zip_is_refused(tmp_path):
    a = make_assignment(tmp_path)
    with pytest.raises(ValueError):
        record_zip(a, "Graded - part 09.zip", by="me (PC)")

def test_returned_only_when_every_file_matches_its_last_upload(tmp_path):
    a = make_assignment(tmp_path)   # writes the marked files and hashes them into the batch
    record_zip(a, "Graded - part 01.zip", by="me (PC)")
    marked = paths.files_by_number(a / paths.MARKED, "*.pdf")
    assert returned_numbers(a, marked) == {"0001", "0002"}
    (a / paths.MARKED / "0002-2.pdf").write_bytes(b"changed")
    assert returned_numbers(a, paths.files_by_number(a / paths.MARKED, "*.pdf")) == {"0001"}

def test_log_conflict_copies_are_found(tmp_path):
    a = make_assignment(tmp_path)
    (a / paths.UPLOAD / "Upload log-DESKTOP-1.csv").write_text("x", encoding="utf-8")
    assert log_conflicts(a) == ["Upload log-DESKTOP-1.csv"]
```

- [ ] **Step 2: Run and see them fail**

Run: `python -m pytest tests/moodle/test_upload_log.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: לממש את `moodle/upload_log.py` ואת `paths.files_by_number`**

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -q`
Expected: הכול עובר

- [ ] **Step 5: Commit**

```bash
git add moodle/upload_log.py moodle/paths.py tests/moodle/test_upload_log.py
git commit -m "Upload log and batch list, by number, without names"
```

---

### Task 4: הכנת אצווה (`prepare_batch`)

**Files:**
- Create: `moodle/send.py` (החלק של ההכנה)
- Modify: `moodle/upload.py`: מפצלים את `build_feedback_zips` ל-`plan_parts` ול-`write_zips`, ומוסיפים שורה על `record` ל-`write_instructions`.
- Test: `tests/moodle/test_send_prepare.py`

**Interfaces:**
- Consumes: `upload_log.*`, `paths.files_by_number` (משימה 3), `anonymize.read_mapping`, `paths.read_info`
- Produces:
  - `upload.plan_parts(marked: Path, mapping: dict, max_bytes: int, numbers: set[str] | None = None) -> tuple[list[list[tuple[Path, str]]], list[str]]` מחזיר חלקים, שכל אחד מהם רשימה של (קובץ מקור, שם בתוך ה-ZIP), ואת רשימת הגדולים מדי. **שינוי התנהגות:** אם קובץ אחד של מספר גדול מ-`max_bytes`, כל המספר לא נכנס, ושם הקובץ הגדול מופיע ב-too_big.
  - `upload.write_zips(upload_dir: Path, parts) -> list[Path]` מוחק `Graded - part *.zip` ישנים וכותב חדשים. `build_feedback_zips` נשאר עם אותה חתימה ואותה תוצאה, ובנוי משתי הפונקציות האלה.
  - `@dataclass BatchSummary`: `id: str`, `assignment_id: str`, `title: str`, `students: int`, `files: int`, `zips: list[dict]` (`{"name", "count", "mb"}`), `too_big: list[str]`, `resubmitted: list[str]`, `not_approved: list[str]`
  - `class BatchBlocked(ValueError)`: הודעה בעברית.
  - `prepare_batch(assignment_dir: Path, max_bytes: int = upload.CLAUDE_MAX_ZIP_BYTES) -> BatchSummary`

**מה `prepare_batch` עושה, לפי הסדר:**
1. אם יש עותק כפול של היומן (`log_conflicts`): זורק `BatchBlocked` עם "ב-OneDrive נוצר עותק כפול של יומן ההעלאה (<שם>). צריך לאחד אותו עם `Upload log.csv` ולמחוק את העותק לפני העלאה נוספת."
2. לוקח את הקבצים הבדוקים לפי מספר, ומספר שלא בטבלת המפתח זורק `ValueError`, כמו היום.
3. מוריד מספרים שכבר הוחזרו (`returned_numbers`).
4. מוריד מספרים שהוגשו מחדש: הקובץ החדש ביותר שלהם ב-`1 - Submissions to grade` חדש יותר (לפי mtime) מהקובץ הבדוק החדש ביותר שלהם. הם נכנסים ל-`resubmitted`.
5. `not_approved`: מתוך המספרים שעולים, אלה שאין להם שורה מאושרת ב-`Grades.csv`. זה לידיעה בלבד. הערכים "", "0", "no", "false", "לא" נחשבים לא מאושרים, כמו ב-`grading.grade.is_approved`. **לא מייבאים את `grading`.**
6. `plan_parts` → `write_zips` → `write_batch` עם hash לכל קובץ מקור, ו-`id` חדש (למשל `created_at` ו-8 תווים של uuid4).
7. כותב `Upload steps.txt` עם `upload.write_instructions`.

- [ ] **Step 1: Write the failing tests**

```python
# fixture `assignment`: key 0001-0003 (fictional names), submissions in TO_GRADE written first, then small
# marked files (a few bytes) 0001.pdf, 0002.pdf in MARKED, so marked files are newer.
# helper write_grades(a, [(number, grade, approved)]) writes Grades.csv with number,grade,feedback,approved.
def test_prepare_skips_returned_and_builds_zips_with_a_batch(assignment):
    s = prepare_batch(assignment, max_bytes=10_000_000)
    assert (s.students, s.files, [z["name"] for z in s.zips]) == (2, 2, ["Graded - part 01.zip"])
    assert read_batch(assignment)["id"] == s.id
    record_zip(assignment, "Graded - part 01.zip", by="me (PC)")
    assert prepare_batch(assignment).students == 0

def test_resubmitted_after_grading_is_held_back(assignment):
    later = time.time() + 60
    os.utime(assignment / paths.TO_GRADE / "0002.pdf", (later, later))
    s = prepare_batch(assignment)
    assert s.resubmitted == ["0002"] and s.students == 1

def test_not_approved_is_reported_but_still_uploaded(assignment):
    write_grades(assignment, [("0001", "90", "yes"), ("0002", "80", "")])
    s = prepare_batch(assignment)
    assert s.not_approved == ["0002"] and s.students == 2

def test_too_big_file_holds_back_the_whole_number(assignment):
    (assignment / paths.MARKED / "0002-2.pdf").write_bytes(b"x" * 2000)
    s = prepare_batch(assignment, max_bytes=1500)
    assert s.too_big == ["0002-2.pdf"]
    assert {f["number"] for z in read_batch(assignment)["zips"] for f in z["files"]} == {"0001"}

def test_log_conflict_copy_blocks_prepare(assignment):
    (assignment / paths.UPLOAD / "Upload log-PC2.csv").write_text("x", encoding="utf-8")
    with pytest.raises(BatchBlocked):
        prepare_batch(assignment)
```

- [ ] **Step 2: Run and see them fail**

Run: `python -m pytest tests/moodle/test_send_prepare.py -v`
Expected: FAIL

- [ ] **Step 3: לממש את `prepare_batch` ואת הפיצול ב-`upload.py`.** ב-`write_instructions` מוסיפים אחרי רשימת ה-ZIP-ים: "מי שמעלה ביד: אחרי כל ZIP מריצים `python -m moodle record <מזהה> \"<שם ה-ZIP>\"`, כדי שהאתר ידע מה הוחזר."

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -q`
Expected: הכול עובר, כולל הבדיקות הקיימות ב-`tests/moodle/test_upload.py`.

- [ ] **Step 5: Commit**

```bash
git add moodle/send.py moodle/upload.py tests/moodle/test_send_prepare.py
git commit -m "Prepare an upload batch: only new or changed work, held-back lists"
```

---

### Task 5: הלולאה על ה-ZIP-ים (`run_batch`) ומנוע מדומה

**Files:**
- Modify: `moodle/send.py`
- Test: `tests/moodle/test_send_run.py`

**Interfaces:**
- Consumes: `lock.take`, `lock.refresh`, `lock.Locked`, `lock.me` (משימה 2), `upload_log.read_batch`, `record_zip`, `last_hashes` (משימה 3)
- Produces:
  - `@dataclass UploadResult`: `status: str` (אחד מ-`"imported" | "dry_run_ok" | "needs_login" | "mismatch" | "error"`), `rows: int | None = None`, `imported: int | None = None`, `skipped: int | None = None`, `message: str = ""`
  - `class MoodleDriver(Protocol)`: `upload_zip(self, info: dict, zip_path: Path, expected: int, dry_run: bool) -> UploadResult`
  - `class SimulatedDriver`: `__init__(self, results: list[UploadResult] | None = None, delay: float = 0.0)`. בכל קריאה הוא מחזיר את התוצאה הבאה ברשימה. כשהרשימה נגמרת הוא מחזיר `imported`, עם `rows` ו-`imported` שווים ל-`expected` (או `dry_run_ok` במצב יבש). הוא שומר את הקריאות ב-`self.calls: list[str]` (שמות ה-ZIP-ים). משמש בבדיקות, וגם באתר עם `MOODLE_DRIVER=simulate`.
  - `UPLOAD_LOCK = "Upload in progress.txt"`
  - `@dataclass RunReport`: `total_zips: int`, `done_zips: list[str]`, `recorded: int`, `stopped: str | None` (`None` כשהכול הסתיים, אחרת `"user" | "needs_login" | "mismatch" | "error" | "stale" | "locked"`), `message: str`
  - `run_batch(assignment_dir: Path, batch_id: str, driver: MoodleDriver, *, dry_run: bool = False, should_stop: Callable[[], bool] = lambda: False, on_progress: Callable[[int, int, str], None] | None = None) -> RunReport`

**הכללים של `run_batch`:**
- אם `batch_id` שונה מה-`id` ב-`Upload batch.json`: עוצר מיד עם `stale` וההודעה "הקבצים השתנו מאז ההכנה. צריך להכין שוב."
- לוקח את הנעילה `UPLOAD_LOCK`. אם `Locked`: עוצר עם `locked` וההודעה "<who> מעלה את המטלה הזו עכשיו (מ-HH:MM)."
- מדלג על ZIP שכל הקבצים שלו כבר ביומן עם אותו hash. זה מה שמאפשר להמשיך אחרי עצירה.
- לפני כל ZIP בודק את `should_stop()`. אם הוא מחזיר אמת: עוצר עם `user`.
- תוצאה מתקבלת אם `status == "imported"`, וגם `rows == expected`, וגם `(imported or 0) + (skipped or 0) == expected`. אז `record_zip(..., by=lock.me())`. כל תוצאה אחרת עוצרת עם הסטטוס שלה (או `error` אם הסטטוס `imported` אבל המספרים לא תואמים), וההודעה היא `f"{zip_name}: {result.message}"`.
- במצב בדיקה יבשה: רק ה-ZIP הראשון. `dry_run_ok` עם `rows == expected` מסתיים עם `stopped=None` וההודעה "בדיקה יבשה עברה: <rows> שורות ברשימת האישור". שום דבר לא נרשם.
- אחרי כל ZIP: `refresh` לנעילה ו-`on_progress(index, total, zip_name)`. הנעילה משתחררת ב-`finally`.
- ההודעות בעברית, עם מספרים בלבד.

- [ ] **Step 1: Write the failing tests**

```python
# fixture `batch`: the Task 4 assignment, prepared with max_bytes small enough that each of the
# 2 marked files gets its own ZIP; returns (assignment_dir, BatchSummary).
def test_all_zips_upload_and_get_recorded(batch):
    a, s = batch
    d = SimulatedDriver()
    r = run_batch(a, s.id, d)
    assert (r.stopped, r.done_zips, len(d.calls)) == (None, ["Graded - part 01.zip", "Graded - part 02.zip"], 2)
    assert not (a / UPLOAD_LOCK).exists()

def test_resume_skips_zips_already_recorded(batch):
    a, s = batch
    r = run_batch(a, s.id, SimulatedDriver([UploadResult("imported", 1, 1), UploadResult("needs_login")]))
    assert r.stopped == "needs_login" and r.done_zips == ["Graded - part 01.zip"]
    d = SimulatedDriver()
    assert run_batch(a, s.id, d).stopped is None and d.calls == ["Graded - part 02.zip"]

def test_count_mismatch_stops_without_recording(batch):
    a, s = batch
    r = run_batch(a, s.id, SimulatedDriver([UploadResult("imported", rows=1, imported=0)]))
    assert r.stopped == "error" and read_log(a) == []

def test_identical_files_skipped_by_moodle_count_as_done(batch):
    a, s = batch
    assert run_batch(a, s.id, SimulatedDriver([UploadResult("imported", 1, 0, skipped=1)])).stopped is None

def test_stale_batch_and_foreign_lock_are_refused(batch):
    a, s = batch
    assert run_batch(a, "old-id", SimulatedDriver()).stopped == "stale"
    (a / UPLOAD_LOCK).write_text("other (PC2)", encoding="utf-8")
    assert run_batch(a, s.id, SimulatedDriver()).stopped == "locked"

def test_stop_request_stops_before_the_next_zip(batch):
    a, s = batch
    calls = iter([False, True])
    assert run_batch(a, s.id, SimulatedDriver(), should_stop=lambda: next(calls)).done_zips == ["Graded - part 01.zip"]

def test_dry_run_checks_first_zip_only_and_records_nothing(batch):
    a, s = batch
    d = SimulatedDriver()
    r = run_batch(a, s.id, d, dry_run=True)
    assert r.stopped is None and len(d.calls) == 1 and read_log(a) == []
```

- [ ] **Step 2: Run and see them fail**

Run: `python -m pytest tests/moodle/test_send_run.py -v`
Expected: FAIL

- [ ] **Step 3: לממש**

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -q`
Expected: הכול עובר

- [ ] **Step 5: Commit**

```bash
git add moodle/send.py tests/moodle/test_send_run.py
git commit -m "Upload loop: resume, stop, lock and checks against Moodle's counts"
```

---

### Task 6: המנוע של Claude (`moodle/claude_driver.py`, `moodle/claude_upload.md`)

**Files:**
- Create: `moodle/claude_driver.py`, `moodle/claude_upload.md`
- Test: `tests/moodle/test_claude_driver.py`

**Interfaces:**
- Consumes: `UploadResult` (משימה 5), הדגלים מ"תוצאת משימה 1"
- Produces:
  - `UPLOAD_URL`, `GRADING_URL` (הכתובות מ-Global Constraints ו-`...view.php?id={id}&action=grading`)
  - `DEFAULT_MODEL = "claude-sonnet-5-5"`, `DEFAULT_BUDGET_USD = 2.0`, `TIMEOUT_S = 600`. אלה ערכים התחלתיים, ומשימה 11 מכיילת אותם.
  - `RESULT_SCHEMA: dict`: `status` (enum של חמשת הסטטוסים), `rows`, `imported`, `skipped` (מספר שלם או null), ו-`message` (מחרוזת עד 300 תווים). כל השדות חובה.
  - `NOT_LOGGED_IN = "Claude Code לא מחובר במחשב הזה. מריצים פעם אחת: claude auth login"`
  - `NOT_INSTALLED = "Claude Code לא מותקן במחשב הזה (הפקודה claude לא נמצאה)."`
  - `render_prompt(info: dict, zip_path: Path, expected: int, dry_run: bool) -> str`
  - `build_command(prompt: str, add_dir: Path, *, model: str, budget_usd: float, schema: dict, claude: str) -> list[str]`
  - `parse_result(stdout: str) -> UploadResult`
  - `class ClaudeChromeDriver`: `__init__(self, model=DEFAULT_MODEL, budget_usd=DEFAULT_BUDGET_USD, timeout_s=TIMEOUT_S, run=subprocess.run, claude: str | None = None)`. כש-`claude` הוא `None`, משתמשים ב-`shutil.which("claude")`. מממש את `upload_zip`, וגם `check(self, info: dict) -> dict`, שמחזיר `{"chrome": bool, "moodle": bool, "message": str}`.
  - `auth_status(run=subprocess.run, claude: str | None = None) -> dict`, שמחזיר `{"logged_in": bool, "message": str}`. מריץ `claude auth status --json`.

**`moodle/claude_upload.md`** הוא תבנית ב-`str.format` עם `{upload_url}`, `{assignment_id}`, `{title}`, `{zip_path}`, `{expected}`, `{mode}`. התוכן (באנגלית, עם שמות הכפתורים בעברית):

```
You upload one feedback ZIP to Moodle for a university course. Follow these steps exactly, using only the Chrome tools.

Rules (never break them):
- Go only to this address: {upload_url}. Never open assignment settings or any other page.
- If a login page appears, do not type anything anywhere. Stop and return status "needs_login".
- Never take a screenshot of the confirmation list. Never write any person's name in your answer.
- Never change grades or settings. Never upload any file other than {zip_path}.

Steps:
1. Open {upload_url}.
2. Check the address has id={assignment_id} and the page is for the assignment "{title}". If not, return "error".
3. In the file picker choose "העלאת קובץ". Find the input[type=file] with find or read_page and upload {zip_path} with file_upload. Do not click the file input. Then click "העלאת קובץ זה", then "ייבוא".
4. On the confirmation list (file → student), count the rows with javascript_tool or get_page_text. Expected rows: {expected}.
   If the count differs: click cancel and return "mismatch" with the count.
   {mode}
5. Confirm the import. Read Moodle's result message and return "imported" with the number imported and the number Moodle skipped as identical.

Return only the structured result. "message" says what happened in one short sentence, with numbers only.
```

`{mode}` במצב רגיל הוא ריק. בבדיקה יבשה הוא: `This is a dry run: whatever the count, click cancel here, and return "dry_run_ok" if it matched.`

- [ ] **Step 1: Write the failing tests**

```python
INFO = {"id": "3438636", "title": "הגשה 0 - קבוצות ומרוכבים"}

def test_command_is_limited_to_chrome_and_the_upload_folder(tmp_path):
    cmd = build_command("p", tmp_path, model="m", budget_usd=2.0, schema=RESULT_SCHEMA, claude="claude")
    assert {"-p", "--chrome", "--no-session-persistence"} <= set(cmd)
    assert cmd[cmd.index("--add-dir") + 1] == str(tmp_path)
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__claude-in-chrome"
    assert "Bash" not in " ".join(cmd)

def test_prompt_has_the_assignment_zip_and_count(tmp_path):
    p = render_prompt(INFO, tmp_path / "Graded - part 01.zip", 6, dry_run=True)
    assert "id=3438636" in p and "Graded - part 01.zip" in p and "Expected rows: 6" in p and "dry run" in p

def test_parse_result_reads_the_structured_answer():
    out = json.dumps({"is_error": False, "structured_output": {"status": "imported", "rows": 6, "imported": 6, "skipped": 0, "message": "6 imported"}})
    assert parse_result(out) == UploadResult("imported", 6, 6, 0, "6 imported")

@pytest.mark.parametrize("stdout, expect", [
    (json.dumps({"is_error": True, "result": "Failed to authenticate: OAuth session expired"}), NOT_LOGGED_IN),
    ("not json", "תשובה לא צפויה"),
])
def test_parse_result_errors(stdout, expect):
    r = parse_result(stdout)
    assert r.status == "error" and expect in r.message

def test_timeout_is_an_error(tmp_path):
    def run(*a, **k):
        raise subprocess.TimeoutExpired("claude", 1)
    r = ClaudeChromeDriver(run=run, claude="claude").upload_zip(INFO, tmp_path / "z.zip", 1, False)
    assert r.status == "error"
```

הבדיקה של `parse_result` משתמשת במקום של התשובה המובנית שנמצא במשימה 1. אם היא לא ב-`structured_output`, מתקנים את הבדיקה לפי מה שנרשם שם.

- [ ] **Step 2: Run and see them fail**

Run: `python -m pytest tests/moodle/test_claude_driver.py -v`
Expected: FAIL

- [ ] **Step 3: לממש.** `run` נקרא עם `capture_output=True, text=True, encoding="utf-8", timeout=self.timeout_s`, ו-`cwd` הוא תיקיית ההעלאה. `claude` שלא נמצא מחזיר `error` עם `NOT_INSTALLED`.

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -q`
Expected: הכול עובר

- [ ] **Step 5: Commit**

```bash
git add moodle/claude_driver.py moodle/claude_upload.md tests/moodle/test_claude_driver.py
git commit -m "Claude in Chrome driver: one locked-down run per ZIP"
```

---

### Task 7: שורת הפקודה (`send`, `record`)

**Files:**
- Modify: `moodle/__main__.py`
- Test: `tests/moodle/test_cli_send.py`

**Interfaces:**
- Consumes: `prepare_batch`, `run_batch`, `SimulatedDriver` (משימות 4–5), `ClaudeChromeDriver` (משימה 6), `record_zip` (משימה 3), `lock.me`
- Produces:
  - `python -m moodle send <id> [--dry-run] [--yes] [--simulate]` מדפיס את סיכום האצווה (מספרים בלבד), שואל "להעלות למודל? (y/N)" אלא אם יש `--yes`, מריץ, ומדפיס את ה-`RunReport`. קוד יציאה 1 אם `stopped` לא `None`.
  - `python -m moodle record <id> "<zip name>"` מדפיס "<n> קבצים נרשמו ביומן".

- [ ] **Step 1: Write the failing tests** (מריצים את `main()` עם `monkeypatch.setattr(sys, "argv", [...])`, ועם `ASSIGNMENT_DATA` שמצביע על תיקייה בדויה)

```python
def test_send_simulated_with_yes_uploads_and_records(data, capsys):   # fixture: ASSIGNMENT_DATA with one assignment, 2 marked files
    run_cli(["send", "3438636", "--yes", "--simulate"])
    assert "2 סטודנטים" in capsys.readouterr().out
    assert len(read_log(assignment_dir("3438636"))) == 2

def test_send_without_yes_and_answer_no_uploads_nothing(data, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    run_cli(["send", "3438636", "--simulate"])
    assert read_log(assignment_dir("3438636")) == []

def test_record_writes_the_log(data, capsys):
    prepare_batch(assignment_dir("3438636"))
    run_cli(["record", "3438636", "Graded - part 01.zip"])
    assert "2 קבצים נרשמו" in capsys.readouterr().out
```

- [ ] **Step 2: Run and see them fail**

Run: `python -m pytest tests/moodle/test_cli_send.py -v`
Expected: FAIL

- [ ] **Step 3: לממש**, ולעדכן את ה-docstring בראש `moodle/__main__.py`.

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -q`
Expected: הכול עובר

- [ ] **Step 5: Commit**

```bash
git add moodle/__main__.py tests/moodle/test_cli_send.py
git commit -m "CLI: send (with dry run) and record"
```

---

### Task 8: השרת המקומי (`dashboard/`)

**Files:**
- Modify: `dashboard/actions.py`, `dashboard/web_server.py`
- Test: `tests/dashboard/test_send.py`

**Interfaces:**
- Consumes: הכול ממשימות 3–6
- Produces (`dashboard/actions.py`):
  - `prepare_send(root: Path, course: str, assignment: str) -> dict`, שמחזיר את `asdict(BatchSummary)` ועוד `"summary"`: `מטלה "<title>" (מודל <id>): <files> קבצים של <students> סטודנטים, ב-<n> קובצי ZIP.`. `BatchBlocked` ו-`ValueError` הופכים ל-`UserError`.
  - `@dataclass SendJob`: `course`, `assignment`, `batch_id`, `dry_run: bool`, `running: bool`, `total: int`, `done: int`, `current: str`, `stopped: str | None`, `message: str`, `started_at: str`, `finished_at: str`
  - `send_status() -> dict`, `stop_send() -> dict`
  - `start_send(root, course, assignment, batch_id: str, driver: MoodleDriver | None = None, wait: bool = False) -> dict` זורק `RuntimeError` אם כבר רצה העלאה, ו-`ValueError("stale")` אם `batch_id` לא תואם ל-`Upload batch.json`. בלי `driver`: `ClaudeChromeDriver()`, או `SimulatedDriver(delay=1.0)` כש-`MOODLE_DRIVER=simulate`.
  - `moodle_status() -> dict` הוא `auth_status()`, עם מטמון של 60 שניות.
  - `check_moodle(root, course, assignment) -> dict` הוא `ClaudeChromeDriver().check(details)`.
  - `state()`: `status: "returned"` לפי `upload_log.returned_numbers` במקום `Uploaded.txt`. `returnedAt` הוא ה-`uploaded_at` האחרון ביומן. ל-`warnings` מצטרפים עותקים כפולים של היומן ו"העלאה בתהליך: <who>". השדה `"sending": send_status()` מתווסף לתשובה.
- Produces (`dashboard/web_server.py`). כל ה-POST דורשים את `X-Assignment-Checker`, כמו היום:
  - `POST /api/upload/prepare` עם `{course, assignment}` מחזיר 200 עם `prepare_send`, או 422 עם `{"error"}`. רץ תחת `_lock`, כמו משיכה.
  - `POST /api/upload/start` עם `{course, assignment, batchId}` מחזיר 202 עם `send_status()`. 409 עם "העלאה אחרת כבר רצה." או עם "הקבצים השתנו מאז ההכנה. צריך ללחוץ שוב על 'העלה למודל'."
  - `GET /api/upload` מחזיר `send_status()`. `POST /api/upload/stop` מחזיר `stop_send()`.
  - `GET /api/moodle` מחזיר `moodle_status()`. `POST /api/moodle/check` עם `{course, assignment}` מחזיר `check_moodle`.
  - ב-`/api/health`, `"moodle"` הוא `moodle_status()["logged_in"]`.

- [ ] **Step 1: Write the failing tests** (על ה-fixtures `root` ו-`server` מ-`tests/dashboard/test_dashboard.py`. מעבירים אותם ל-`tests/dashboard/conftest.py`)

```python
# helpers: mark(root, *numbers) writes a small marked PDF per number into MARKED (after the submissions);
# BODY = {"course": COURSE, "assignment": HW}; HDR = {"X-Assignment-Checker": "1"}
def test_prepare_then_start_marks_students_returned(root):
    mark(root, "0001", "0002")
    rep = actions.prepare_send(root, COURSE, HW)
    assert rep["students"] == 2 and "2 סטודנטים" in rep["summary"]
    actions.start_send(root, COURSE, HW, rep["id"], driver=SimulatedDriver(), wait=True)
    subs = actions.state(root)["assignments"][0]["subs"]
    assert [s["status"] for s in subs] == ["returned", "returned", "pulled"]

def test_start_with_stale_batch_is_refused(root, server):
    mark(root, "0001")
    old = call(server, "POST", "/api/upload/prepare", BODY, HDR)[1]["id"]
    call(server, "POST", "/api/upload/prepare", BODY, HDR)
    st, rep = call(server, "POST", "/api/upload/start", {**BODY, "batchId": old}, HDR)
    assert st == 409 and "השתנו" in rep["error"]

def test_needs_login_shows_in_status(root):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    actions.start_send(root, COURSE, HW, rep["id"], driver=SimulatedDriver([UploadResult("needs_login")]), wait=True)
    assert actions.send_status()["stopped"] == "needs_login"

def test_state_and_status_have_no_names(root):
    mark(root, "0001")
    rep = actions.prepare_send(root, COURSE, HW)
    actions.start_send(root, COURSE, HW, rep["id"], driver=SimulatedDriver(), wait=True)
    text = json.dumps([actions.state(root), actions.send_status(), rep], ensure_ascii=False)
    assert not any(name in text for name in NAMES.values())
```

- [ ] **Step 2: Run and see them fail**

Run: `python -m pytest tests/dashboard -v`
Expected: הבדיקות החדשות נכשלות, והישנות עוברות.

- [ ] **Step 3: לממש**

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -q`
Expected: הכול עובר

- [ ] **Step 5: Commit**

```bash
git add dashboard tests/dashboard
git commit -m "Dashboard: prepare, start, follow and stop an upload to Moodle"
```

---

### Task 9: האתר (שלב 3 במצב מקומי)

**Files:**
- Modify: `website/app.js`
- Create: `tests/make_demo_root.py` (תיקייה בדויה לתצוגה מקדימה, עם השמות מ-`tests/sample_files.NAMES`)
- Create: `.claude/launch.json` (אם אין), עם תצורה בשם `dashboard-demo`: `python -m dashboard serve --no-browser`, `ASSIGNMENT_CHECKER_ROOT=<התיקייה הבדויה>`, `MOODLE_DRIVER=simulate`, ופורט 8765. אם אין `--no-browser` ב-`dashboard/__main__.py`, מוסיפים אותו.

**Interfaces:**
- Consumes: ה-API ממשימה 8
- Produces: אין (זה הקצה)

**מה משתנה ב-`app.js`, רק כש-`LOCAL.on`:**
- `stageButton("ret")`: התווית היא `העלה ${n} למודל`, או "אין עבודות להעלאה", והכפתור כבוי בזמן שהעלאה רצה.
- `runLocalReturn` מוחלף ב-`prepareLocalSend()`: `POST api/upload/prepare`, ואז `LOCAL.batch = {...rep, assignmentId}`. עדיין לא מעלים.
- `returnList()` מציג למעלה את `sendPanelHTML()`, שמראה אחד מהמצבים האלה:
  - **אישור** (יש `LOCAL.batch` ושום העלאה לא רצה): `summary`, ואז "לידיעה: <n> מהן עוד לא סומנו כמאושרות ב-Grades.csv." (אם יש), "גדולות מדי ולא ייכללו: …" (אם יש), "הוגשו מחדש אחרי הבדיקה ולא ייכללו: …" (אם יש). אחריהם הכפתורים `data-act="send-confirm"` "העלה למודל" ו-`data-act="send-cancel"` "ביטול". אם `zips` ריק: "אין עבודות חדשות להעלאה".
  - **רץ:** "מעלה קובץ <done+1> מתוך <total>…", והכפתור `data-act="send-stop"` "עצור אחרי הקובץ הנוכחי".
  - **נעצר** (`stopped` לא null): ההודעה. כש-`stopped` הוא `needs_login`, ההודעה היא "צריך להתחבר שוב למודל בכרום. אחרי ההתחברות לוחצים 'המשך'." למצבים `needs_login`, `user` ו-`error` יש כפתור `data-act="send-resume"` "המשך", שמריץ את `start` עם אותו `batchId`.
- `send-confirm` ו-`send-resume` שולחים `POST api/upload/start`, ואז יש תשאול של `GET api/upload` כל 2 שניות, כמו ב-`runLocalGrade`. בסוף: `loadLocal()` והודעה קצרה (toast). כשהדף נטען ויש העלאה שרצה (`state.sending.running`), התשאול ממשיך.
- השלבים שמוצגים לשלב 3 במצב מקומי הם "הכנת הקבצים", "העלאה למודל", "אימות מול מודל".
- `retConn()` במצב מקומי:
  - מצב Claude Code (`GET api/moodle`): "מחובר" או "לא מחובר", ואם לא מחובר גם `claude auth login`.
  - רשימה: התוסף Claude in Chrome מותקן ומחובר, מורשה ל-moodle.bgu.ac.il, ומחוברים למודל בכרום.
  - כפתור "בדוק חיבור" (`POST api/moodle/check`) והתוצאה שלו.
  - הדגמת `MOODLE_TOKEN` נשארת רק במצב הדגמה.

- [ ] **Step 1: לבנות תיקייה בדויה ולהפעיל**

Run: `python -m tests.make_demo_root "<scratchpad>/demo-root"`, ואז `preview_start` עם `dashboard-demo`.
Expected: האתר עולה עם מטלה בדויה, ובה 2 עבודות בדוקות.

- [ ] **Step 2: לממש את השינויים ב-`app.js`**

- [ ] **Step 3: לבדוק בדפדפן**

1. בשלב 3 לוחצים "העלה 2 למודל" ורואים את חלון האישור עם הסיכום.
2. "העלה למודל": מופיעה התקדמות, ובסוף העבודות מסומנות "הוחזרה".
3. לחיצה נוספת: "אין עבודות חדשות להעלאה".
4. לשונית "חיבור למודל" מראה את המצב של Claude Code.
5. `read_console_messages` בלי שגיאות. צילום מסך לכל מצב.

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -q`
Expected: הכול עובר

- [ ] **Step 5: Commit**

```bash
git add website/app.js tests/make_demo_root.py dashboard/__main__.py .claude/launch.json
git commit -m "Website: one-click upload to Moodle with confirm, progress and resume"
```

---

### Task 10: תיעוד

**Files:**
- Modify: `CLAUDE.md`, `moodle/README.md`, `dashboard/README.md`, `moodle/guide.py` (הטקסט של תיקייה 3)

- [ ] **Step 1: לעדכן**

- `CLAUDE.md`:
  - הפרק "The shared folder": התיקייה מסונכרנת עכשיו (Add shortcut עבד), והנתיב מוגדר דרך `ASSIGNMENT_CHECKER_ROOT` או `ASSIGNMENT_DATA`.
  - הפרק "Uploading to Moodle with Claude" מוחלף בזרימה החדשה: כפתור, `send`, `Upload log.csv`, `Upload batch.json`, `record` למי שמעלה ביד, ושלב מטלת הניסיון.
  - טבלת המבנה מקבלת את `Upload log.csv`, `Upload batch.json` ו-`Upload in progress.txt`.
- `moodle/README.md`: `send.py`, `upload_log.py`, `lock.py`, `claude_driver.py` והפקודות `send` ו-`record`.
- `dashboard/README.md`: ה-endpoints החדשים ו-`MOODLE_DRIVER=simulate`.
- `moodle/guide.py`: ב-README של תיקייה 3 השם הנכון הוא `Upload steps.txt` (היום כתוב שם "הוראות העלאה.txt"), ומוזכר `Upload log.csv`.

- [ ] **Step 2: Run all tests**

Run: `python -m pytest -q`
Expected: הכול עובר. אם `test_guide.py` בודק את הטקסט הישן, מעדכנים אותו.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md moodle/README.md dashboard/README.md moodle/guide.py tests/moodle/test_guide.py
git commit -m "Docs: the automatic upload to Moodle"
```

---

### Task 11: ניסיון על מטלת ניסיון במודל, ו-PR (עם אדם)

**דרוש מאדם:** מטלת ניסיון מנדב, עם הגשות של כמה חברי צוות. מתן מחובר למודל בכרום ול-Claude Code. כמה קבצים בדוקים בתיקייה 2 של מטלת הניסיון.

- [ ] **Step 1: משיכה של מטלת הניסיון** ("משוך הגשות" באתר), ושמים קבצים בדוקים ב-`2 - Graded with comments`.

- [ ] **Step 2: בדיקה יבשה**

Run: `python -m moodle send <test id> --dry-run --yes`
Expected: "בדיקה יבשה עברה: N שורות ברשימת האישור", ושום שינוי במודל. אם נכשל: מתקנים את `moodle/claude_upload.md` לפי מה שהדף באמת מציג (שמות הכפתורים, הודעת התוצאה) ומריצים שוב.

- [ ] **Step 3: העלאה אמיתית מהאתר.** "העלה למודל", ואז "העלה למודל" בחלון האישור.
Expected: במודל, לכל משתתף בניסיון יש `feedback.pdf` שהוא העבודה שלו. מתן בודק את זה בעיניים.

- [ ] **Step 4: העלאה חוזרת.** משנים קובץ בדוק אחד ולוחצים שוב.
Expected: רק הוא עולה, ובמודל הוא מחליף את הקודם ולא נוסף לידו.

- [ ] **Step 5: מדידה.** רושמים זמן ועלות לכל ריצה (מה-JSON של `claude`). מעדכנים `DEFAULT_MODEL`, `DEFAULT_BUDGET_USD` ו-`TIMEOUT_S` לפי המדידה, ואת ההערכה ב-`CLAUDE.md`.

- [ ] **Step 6: Commit, push, PR**

```bash
git add moodle/claude_upload.md moodle/claude_driver.py CLAUDE.md
git commit -m "Tune the Moodle upload after the test assignment"
git push -u origin moodle-auto-upload
gh pr create --base main --title "העלאה אוטומטית למודל מכפתור באתר" --body-file <scratchpad>/pr-body.md
```

---

## תוצאת משימה 1

(ממלאים אחרי משימה 1: הדגלים שעבדו, איפה נמצאת התשובה המובנית, ומה צריך לאשר בתוסף.)
