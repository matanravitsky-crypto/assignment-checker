"""The start-assignment skill's script: details from a Moodle page, the solution's pages, sheets on disk."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "start-assignment" / "scripts" / "prepare.py"
spec = importlib.util.spec_from_file_location("prepare", SCRIPT)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)

COURSE = "Linear Algebra"


@pytest.fixture
def data(tmp_path, monkeypatch):
    root = tmp_path / "Exercise Checking System"
    (root / COURSE / "Course material" / "Sheets").mkdir(parents=True)
    monkeypatch.setenv("ASSIGNMENT_DATA", str(root))
    return root


# ---------- dates ----------

def test_moodle_date_hebrew_pm_and_iso():
    assert prepare.moodle_date("מסתיים: יום שני, 2 נובמבר 2026, 11:59 PM") == "2026-11-02T23:59:00+02:00"
    assert prepare.moodle_date("יום רביעי, 21 אוקטובר 2026, 12:00 AM").startswith("2026-10-21T00:00:00+0")
    assert prepare.moodle_date("2026-11-02T23:59:00+02:00") == "2026-11-02T23:59:00+02:00"
    assert prepare.moodle_date("2026-07-01T23:59") == "2026-07-01T23:59+03:00"  # summer time
    assert prepare.moodle_date("בקרוב") is None


# ---------- the solution's pages ----------

def test_question_starts_follow_the_numbering_and_skip_page_numbers():
    texts = [
        "cover\n27\n",                       # a contents page: numbers that are not headings
        "הישרים נתונים  .7\n...\n21\n",      # a reversed RTL heading at the end of the line, a page number alone
        ".8 המישורים\n x = 0.5 .12\n",        # .8 at a line start; "0.5" and a stray " .12" (not 9 or 10) don't count
        "more of 8\n",
        ".10 something\n",                   # 9 is missing from the text layer: a gap of one is allowed
        ".11 q\n",
        ".12 q\n",
    ]
    assert prepare.question_starts(texts) == {7: 1, 8: 2, 10: 4, 11: 5, 12: 6}
    # a stray " .5" on the cover, before question 1, doesn't start the sequence
    assert prepare.question_starts(["x .5 y", ".1 a", ".2 b"]) == {1: 1, 2: 2}


def test_page_ranges_run_until_the_next_heading():
    starts = {7: 1, 8: 2, 10: 4, 11: 5, 12: 6}
    found, missing = prepare.page_ranges(starts, [8, 9, 12], n_pages=9, at_top=set(starts))
    assert found == [(8, 2, 3), (12, 6, 8)]
    assert missing == [9]
    # the next question's heading in the middle of a page: that page still belongs to the question before it
    found, _ = prepare.page_ranges(starts, [8, 10], n_pages=9, at_top={7, 8, 12})
    assert found == [(8, 2, 4), (10, 4, 5)]
    assert prepare.merge_ranges([(2, 4), (4, 5), (7, 7), (8, 8)]) == [(2, 5), (7, 8)]


def test_top_headings_sees_where_a_page_starts():
    texts = ["cover", "הישרים נתונים  .1\nx", "tail of 1\nmore\nand more\n.2 second", "\n\n.3 third"]
    starts = prepare.question_starts(texts)
    assert starts == {1: 1, 2: 2, 3: 3}
    assert prepare.top_headings(texts, starts) == {1, 3}


def test_parse_pages_is_one_based_inclusive():
    assert prepare.parse_pages("10-14,20", 24) == [(9, 13), (19, 19)]
    with pytest.raises(prepare.Problem):
        prepare.parse_pages("30", 24)


def test_cut_pdf_takes_the_ranges(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    src = tmp_path / "solutions.pdf"
    doc = pymupdf.open()
    for i in range(6):
        doc.new_page().insert_text((72, 72), f"page {i + 1}")
    doc.save(src)
    out = tmp_path / "Official solution.pdf"
    assert prepare.cut_pdf(src, [(1, 2), (4, 4)], out, append=False) == 3
    assert prepare.cut_pdf(src, [(5, 5)], out, append=True) == 4
    with pymupdf.open(out) as result:
        assert [p.get_text().strip() for p in result] == ["page 2", "page 3", "page 5", "page 6"]


# ---------- details ----------

MOODLE_PAGE = {
    "id": "3438638", "course_id": "67024", "course_title": "אלגברה לינארית להנדסה",
    "title": "הגשה 1 - וקטורים", "due": "יום שני, 2 נובמבר 2026, 11:59 PM",
    "questions": [{"sheet": "דף וקטורים", "numbers": [11, 13]}],
    "submission_rules": ["כתב יד, קובץ PDF אחד"], "page_text": "הגשה 1: יש להגיש...",
}


def test_details_creates_the_slot_folder_and_records_the_page(data):
    folder = prepare.write_details(COURSE, 1, MOODLE_PAGE)
    assert folder == data / COURSE / "Assignment 1"
    info = json.loads((folder / "Assignment details.json").read_text(encoding="utf-8"))
    assert info["id"] == "3438638" and info["name"] == "Assignment 1" and info["course"] == COURSE
    assert info["due"] == "2026-11-02T23:59:00+02:00"
    assert info["questions"] == [{"sheet": "דף וקטורים", "numbers": [11, 13]}]
    assert info["max_grade"] is None and info["rubric"] is None
    assert list(info)[:4] == ["id", "course", "course_id", "name"]
    for sub in ("1 - Submissions to grade", "2 - Graded with comments", "3 - Ready to upload to Moodle", "פדגוגי/Working notes"):
        assert (folder / sub).is_dir()
    pages = (data / COURSE / "Course material" / "Moodle - assignments, quizzes and pages.md").read_text(encoding="utf-8")
    assert "מזהה במודל: 3438638" in pages and "יש להגיש" in pages
    # a second run keeps the page once and the typed fields
    info["max_grade"] = 100
    info["notes"] = "typed by hand"
    (folder / "Assignment details.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    prepare.write_details(COURSE, 1, dict(MOODLE_PAGE, due="2026-11-03T23:59:00+02:00"))
    again = json.loads((folder / "Assignment details.json").read_text(encoding="utf-8"))
    assert again["max_grade"] == 100 and again["notes"] == "typed by hand" and again["due"].startswith("2026-11-03")
    assert pages == (data / COURSE / "Course material" / "Moodle - assignments, quizzes and pages.md").read_text(encoding="utf-8")
    # a page that changed (a question added) replaces its section: one section per id, the new text in it
    prepare.write_details(COURSE, 1, dict(MOODLE_PAGE, page_text="הגשה 1: שאלות 8, 11"))
    pages = (data / COURSE / "Course material" / "Moodle - assignments, quizzes and pages.md").read_text(encoding="utf-8")
    assert pages.count("מזהה במודל: 3438638") == 1 and "שאלות 8, 11" in pages and "יש להגיש" not in pages


def test_details_keeps_an_existing_named_folder(data):
    named = data / COURSE / "Assignment 1 - Vectors in R2 and R3"
    named.mkdir()
    (named / "Assignment details.json").write_text(json.dumps({"id": "3438638", "course": COURSE, "name": named.name}), encoding="utf-8")
    assert prepare.write_details(COURSE, 1, MOODLE_PAGE) == named
    assert not (data / COURSE / "Assignment 1").exists()


def test_details_refuses_an_id_another_folder_has_or_a_changed_id(data):
    other = data / COURSE / "Assignment 0 - Sets"
    other.mkdir()
    (other / "Assignment details.json").write_text(json.dumps({"id": "3438638", "course": COURSE, "name": other.name}), encoding="utf-8")
    with pytest.raises(prepare.Problem):
        prepare.write_details(COURSE, 1, MOODLE_PAGE)
    mine = data / COURSE / "Assignment 1"
    mine.mkdir()
    (mine / "Assignment details.json").write_text(json.dumps({"id": "999999", "course": COURSE, "name": mine.name}), encoding="utf-8")
    with pytest.raises(prepare.Problem):
        prepare.write_details(COURSE, 1, MOODLE_PAGE)
    with pytest.raises(prepare.Problem):
        prepare.write_details(COURSE, 2, dict(MOODLE_PAGE, id=""))


# ---------- sheets and materials ----------

def _pdf(path: Path, pages: list[str]) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    doc.save(path)


def test_add_sheet_files_under_the_standard_names(data, tmp_path):
    _pdf(tmp_path / "a.pdf", ["sheet"])
    _pdf(tmp_path / "b.pdf", ["solutions"])
    written = prepare.add_sheet(COURSE, 9, "Vector spaces", tmp_path / "a.pdf", tmp_path / "b.pdf", replace=False)
    assert [Path(w).name for w in written] == ["Sheet 9 - Vector spaces.pdf", "Sheet 9 - Vector spaces - solutions.pdf"]
    assert set(prepare.sheets(COURSE)) == {9}
    with pytest.raises(prepare.Problem):
        prepare.add_sheet(COURSE, 9, "Vector spaces", tmp_path / "a.pdf", None, replace=False)
    (tmp_path / "junk.pdf").write_text("not a pdf")
    with pytest.raises(prepare.Problem):
        prepare.add_sheet(COURSE, 10, "X", tmp_path / "junk.pdf", None, replace=False)


def test_materials_cuts_the_assigned_questions_and_copies_the_rest(data):
    sheets = data / COURSE / "Course material" / "Sheets"
    _pdf(sheets / "Sheet 3 - Vectors.pdf", ["the sheet"])
    _pdf(sheets / "Sheet 3 - Vectors - solutions.pdf",
         ["cover", ".1 first", ".2 second", "more of 2", ".3 third", ".4 fourth\n.5 fifth", "end of 5"])
    older = data / COURSE / "Assignment 0 - Sets"
    (older / "פדגוגי").mkdir(parents=True)
    (older / "Assignment details.json").write_text(json.dumps({"id": "1", "course": COURSE, "name": older.name}), encoding="utf-8")
    (older / "פדגוגי" / "Manual review rules.md").write_text("# rules", encoding="utf-8")
    folder = prepare.write_details(COURSE, 3, dict(MOODLE_PAGE, id="3438640", questions=[{"sheet": "דף וקטורים", "numbers": [2, 4, 5]}]))

    report = prepare.materials(COURSE, 3, sheet=3, numbers=None, pages=None, replace=False, append=False)
    # 4 and 5 share page 6 (5's heading is not at its top): the page is written once
    assert report["pages"]["found"] == {2: "3-4", 4: "6-6", 5: "6-7"} and "missing" not in report["pages"]
    assert (folder / "פדגוגי" / "Exercise sheet 3 - Vectors.pdf").is_file()
    assert (folder / "פדגוגי" / "Manual review rules.md").read_text(encoding="utf-8") == "# rules"
    pymupdf = pytest.importorskip("pymupdf")
    with pymupdf.open(folder / "Official solution.pdf") as sol:
        assert [p.get_text().strip() for p in sol] == [".2 second", "more of 2", ".4 fourth\n.5 fifth", "end of 5"]
    # a second run doesn't overwrite the solution without --replace
    again = prepare.materials(COURSE, 3, sheet=3, numbers=None, pages=None, replace=False, append=False)
    assert any("כבר קיים" in w for w in again["warnings"])
    # a heading the text layer lacks is reported, and --pages settles it
    report = prepare.materials(COURSE, 3, sheet=3, numbers=[2, 9], pages=None, replace=True, append=False)
    assert report["pages"]["missing"] == [9]
    report = prepare.materials(COURSE, 3, sheet=3, numbers=[2, 9], pages="3-4,7", replace=True, append=False)
    with pymupdf.open(folder / "Official solution.pdf") as sol:
        assert sol.page_count == 3


def test_materials_needs_details_and_a_known_sheet(data):
    with pytest.raises(prepare.Problem):
        prepare.materials(COURSE, 5, sheet=1, numbers=None, pages=None, replace=False, append=False)
    prepare.write_details(COURSE, 5, dict(MOODLE_PAGE, id="3438650"))
    with pytest.raises(prepare.Problem):
        prepare.materials(COURSE, 5, sheet=None, numbers=None, pages=None, replace=False, append=False)
    with pytest.raises(prepare.Problem):
        prepare.materials(COURSE, 5, sheet=7, numbers=None, pages=None, replace=False, append=False)


def test_guess_sheet_from_a_discrete_style_name():
    assert prepare.guess_sheet([{"sheet": "דף תרגילים 0 (תחשיב הפסוקים)", "numbers": [4]}]) == 0
    assert prepare.guess_sheet([{"sheet": "דף וקטורים וגאומטריה", "numbers": [11]}]) is None
    assert prepare.guess_sheet([{"sheet": "דף 1", "numbers": [1]}, {"sheet": "דף 2", "numbers": [2]}]) is None


def test_status_lists_what_is_there(data):
    prepare.write_details(COURSE, 1, MOODLE_PAGE)
    s = prepare.status(COURSE, 1)
    assert s["folder"].endswith("Assignment 1") and s["details"]["id"] == "3438638"
    assert s["official_solution"] is False and s["shared_folder"] is False
    assert "submissions" not in s and "last_pull" not in s  # not this skill's business
    assert s["sheets"] == {} and "Working notes" in s["pedagogy"]
    assert prepare.status(COURSE, 2)["folder"] is None


def test_cli_reports_problems_as_json(data, capsys):
    assert prepare.main(["materials", "--course", COURSE, "--slot", "8"]) == 1
    assert "error" in json.loads(capsys.readouterr().out)
    assert prepare.main(["status", "--course", COURSE, "--slot", "8"]) == 0
    assert json.loads(capsys.readouterr().out)["slot"] == 8
