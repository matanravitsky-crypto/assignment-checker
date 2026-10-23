import json
import os
import tempfile
import time
import zipfile
from pathlib import Path

import pytest

from moodle import ingest, paths
from moodle.ingest import assignment_folder, find_download, name_from_zip, wait_for_download


def test_find_download_picks_newest_zip_for_the_assignment():
    with tempfile.TemporaryDirectory() as tmp:
        downloads = Path(tmp)
        old = downloads / "קורס-הגשה 0-3438636.zip"
        new = downloads / "קורס-הגשה 0-3438636 (1).zip"
        other = downloads / "קורס-הגשה 1-3453769.zip"
        partial = downloads / "לא מאושר 877766.crdownload"
        for path in (old, new, other, partial):
            path.write_bytes(b"")
        # "(1)" copies do not end in the id, so they are not picked by mistake
        os.utime(old, (time.time() - 60, time.time() - 60))

        assert find_download("3438636", downloads) == old


def test_find_download_reports_missing_zip():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            find_download("3438636", Path(tmp))
        except FileNotFoundError:
            return
    raise AssertionError("expected FileNotFoundError")


def test_name_from_zip_keeps_dashes_in_the_assignment_name():
    zip_path = Path("214193210120271-הגשה 0 - קבוצות ומרוכבים-3438636.zip")
    assert name_from_zip(zip_path, "3438636") == "הגשה 0 - קבוצות ומרוכבים"


def test_new_assignment_gets_a_named_folder_and_is_found_again():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ASSIGNMENT_DATA"] = tmp
        try:
            zip_path = Path("214193210120271-הגשה 1 - וקטורים-3438638.zip")
            folder = assignment_folder("3438638", zip_path, "Linear Algebra", "Assignment 1 - Vectors")

            assert folder == Path(tmp) / "Linear Algebra" / "Assignment 1 - Vectors"
            info = json.loads((folder / paths.INFO).read_text(encoding="utf-8"))
            assert info == {"id": "3438638", "course": "Linear Algebra", "name": "Assignment 1 - Vectors",
                            "title": "הגשה 1 - וקטורים"}
            # The next download finds it by id, with no names needed
            assert assignment_folder("3438638", zip_path, None, None) == folder
        finally:
            del os.environ["ASSIGNMENT_DATA"]


def test_new_assignment_needs_english_names():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ASSIGNMENT_DATA"] = tmp
        try:
            assignment_folder("3438638", Path("x-הגשה 1-3438638.zip"), "Linear Algebra", None)
        except ValueError:
            return
        finally:
            del os.environ["ASSIGNMENT_DATA"]
    raise AssertionError("expected ValueError")



class Clock:
    """A fake clock for wait_for_download: every sleep moves time forward and may run a step (Chrome at work)."""

    def __init__(self, steps=()):
        self.now, self.steps = 0.0, list(steps)

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.steps:
            self.steps.pop(0)()


def test_wait_for_download_returns_the_new_zip_once_it_is_whole(tmp_path):
    since = time.time()
    old = tmp_path / "קורס-הגשה 0-3438636.zip"
    old.write_bytes(b"an old download")
    os.utime(old, (since - 600, since - 600))  # was there before the download was asked for: not it
    new = tmp_path / "קורס-הגשה 0-3438636.zip"
    partial = tmp_path / "Unconfirmed 1.crdownload"
    steps = [lambda: partial.write_bytes(b"PK"),
             # Chrome renames it when done (the old one was moved away by an earlier ingest)
             lambda: (partial.unlink(), old.unlink(), new.write_bytes(b"PK whole"))]
    clock = Clock(steps)
    got = wait_for_download("3438636", since, tmp_path, poll_s=1, clock=clock, sleep=clock.sleep)
    assert got == new and got.read_bytes() == b"PK whole"


def test_wait_for_download_gives_up_when_nothing_starts(tmp_path):
    clock = Clock()
    with pytest.raises(TimeoutError, match="did not start"):
        wait_for_download("3438636", time.time(), tmp_path, start_s=10, poll_s=1, clock=clock, sleep=clock.sleep)
    assert clock.now <= 12


def test_wait_for_download_keeps_waiting_while_chrome_downloads(tmp_path):
    (tmp_path / "x-3438636.zip.crdownload").write_bytes(b"PK")
    clock = Clock()
    with pytest.raises(TimeoutError, match="did not finish"):
        wait_for_download("3438636", time.time(), tmp_path, start_s=10, total_s=100, poll_s=5, clock=clock, sleep=clock.sleep)
    assert clock.now > 100


if __name__ == "__main__":
    test_find_download_picks_newest_zip_for_the_assignment()
    test_find_download_reports_missing_zip()
    test_name_from_zip_keeps_dashes_in_the_assignment_name()
    test_new_assignment_gets_a_named_folder_and_is_found_again()
    test_new_assignment_needs_english_names()
    print("All tests passed.")


def _seven_zip_or_skip():
    try:
        return ingest.seven_zip()
    except FileNotFoundError:
        pytest.skip("7-Zip is not installed")


def test_check_whole_passes_a_whole_zip_and_sets_aside_a_cut_one(tmp_path):
    """Moodle can end a big download early, and Chrome still saves it as a .zip (2026-10-23)."""
    _seven_zip_or_skip()
    whole = tmp_path / "214193210120271-הגשה 0-3438636.zip"
    with zipfile.ZipFile(whole, "w", zipfile.ZIP_STORED) as z:
        z.writestr("a_1_assignsubmission_file/x.pdf", os.urandom(200_000))
    ingest.check_whole(whole)  # no error, left where it was
    assert whole.exists()

    whole.write_bytes(whole.read_bytes()[:120_000])  # what a download cut in the middle looks like
    with pytest.raises(ValueError, match=ingest.INCOMPLETE):
        ingest.check_whole(whole)
    assert not whole.exists()
    with pytest.raises(FileNotFoundError):  # the next pull does not take it again
        find_download("3438636", tmp_path)


def test_wait_for_download_reports_how_much_arrived(tmp_path):
    since = time.time()
    partial = tmp_path / "Unconfirmed 1.crdownload"
    new = tmp_path / "קורס-הגשה 0-3438636.zip"
    steps = [lambda: partial.write_bytes(b"P" * 1000),
             lambda: (partial.unlink(), new.write_bytes(b"P" * 3000))]
    sizes = []
    clock = Clock(steps)
    wait_for_download("3438636", since, tmp_path, poll_s=1, clock=clock, sleep=clock.sleep, on_size=sizes.append)
    assert sizes[0] == 0 and 1000 in sizes and sizes[-1] == 3000


def test_ingest_reports_check_extract_and_numbering(tmp_path, monkeypatch):
    """The dashboard's progress bar: the ZIP check and the extraction in percent, then every student folder."""
    _seven_zip_or_skip()
    monkeypatch.setenv("ASSIGNMENT_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("ASSIGNMENT_WORK", str(tmp_path / "work"))
    zip_path = tmp_path / "214193210120271-הגשה 0-3438636.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for pid in ("1001", "1002", "1003"):
            z.writestr(f"Student {pid}_{pid}_assignsubmission_file/hw.pdf", os.urandom(50_000))
    seen = []
    rows = ingest.ingest("3438636", zip_path, "Linear Algebra", "Assignment 0", on_progress=lambda *a: seen.append(a))
    assert len(rows) == 3
    phases = [p for p, *_ in seen]
    assert phases.index("check") < phases.index("extract") < phases.index("number")
    assert ("extract", 100, 100) in seen or seen[phases.index("number") - 1][0] == "extract"
    assert [d for p, d, _ in seen if p == "number"] == [0, 1, 2] and all(t == 3 for p, _, t in seen if p == "number")



STEM = "214193210120271-הגשה 0-3438636"


def _parts(downloads, students_per_part, failed=(), sizes=None):
    """What moodle/download_parts.js leaves in Downloads: a ZIP per part, then the list of parts."""
    files = []
    for i, students in enumerate(students_per_part, 1):
        name = f"{STEM} part {i:03} of {len(students_per_part):03}.zip"
        with zipfile.ZipFile(downloads / name, "w") as z:
            for s in students:
                z.writestr(f"{s}_assignsubmission_file/x.pdf", b"%PDF " + s.encode())
        files.append({"name": name, "size": (downloads / name).stat().st_size})
    for f, size in zip(files, sizes or []):
        f["size"] = size
    listed = {"users": 2, "parts": len(files), "empty": [], "failed": list(failed), "files": files}
    (downloads / f"{STEM}.json").write_text(json.dumps(listed), encoding="utf-8")
    return downloads / f"{STEM}.json"


def test_gather_parts_gives_every_listed_part_in_order(tmp_path):
    listed = _parts(tmp_path, [["a_1"], ["b_2"]])
    assert [p.name for p in ingest.gather_parts(listed)] == [f"{STEM} part 001 of 002.zip", f"{STEM} part 002 of 002.zip"]
    assert find_download("3438636", tmp_path) == listed  # the list is what a pull takes
    assert ingest.parts_arrived("3438636", 0, tmp_path) == 2
    assert ingest.parts_progress("3438636", 0, tmp_path) == (2, 2)  # "of 002": the bar knows the total


def test_parts_progress_takes_the_highest_planned_count(tmp_path):
    """A part Moodle cut is asked for again in two halves, so later parts say "of" a bigger number."""
    for name in ["part 001 of 015", "part 002 of 016", "part 003 of 016 (1)"]:
        (tmp_path / f"{STEM} {name}.zip").write_bytes(b"x")
    (tmp_path / "other-999 part 001 of 040.zip").write_bytes(b"x")  # another assignment
    assert ingest.parts_progress("3438636", 0, tmp_path) == (3, 16)
    assert ingest.parts_progress("3438636", time.time() + 60, tmp_path) == (0, 0)  # from an earlier download


def test_gather_parts_finds_a_part_chrome_renamed(tmp_path):
    listed = _parts(tmp_path, [["a_1"]])
    part = tmp_path / f"{STEM} part 001 of 001.zip"
    part.rename(tmp_path / f"{STEM} part 001 of 001 (1).zip")  # the name was taken by an older download
    assert [p.name for p in ingest.gather_parts(listed)] == [f"{STEM} part 001 of 001 (1).zip"]


@pytest.mark.parametrize("kind", ["failed", "missing", "wrong size", "a path"])
def test_gather_parts_sets_aside_a_download_that_is_not_whole(tmp_path, kind):
    listed = _parts(tmp_path, [["a_1"], ["b_2"]], failed=[2] if kind == "failed" else (),
                    sizes=[1, 1] if kind == "wrong size" else None)
    if kind == "missing":
        (tmp_path / f"{STEM} part 002 of 002.zip").unlink()
    if kind == "a path":  # a name in the list never reaches outside Downloads
        data = json.loads(listed.read_text(encoding="utf-8"))
        data["files"][0]["name"] = "../" + data["files"][0]["name"]
        (tmp_path.parent / data["files"][0]["name"].removeprefix("../")).write_bytes(b"")
        data["files"][0]["name"] = "elsewhere/nothing.zip"
        listed.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=ingest.INCOMPLETE):
        ingest.gather_parts(listed)
    assert not listed.exists() and (tmp_path / f"{STEM} ({ingest.INCOMPLETE}).json").exists()
    with pytest.raises(FileNotFoundError):
        find_download("3438636", tmp_path)


def test_check_whole_refuses_a_zip_without_a_folder_per_student(tmp_path):
    """Moodle's folders option was off for two parts on 2026-10-23: loose files have no participant id."""
    _seven_zip_or_skip()
    flat = tmp_path / "x-3438636.zip"
    with zipfile.ZipFile(flat, "w") as z:
        z.writestr("a_1_assignsubmission_file/x.pdf", b"%PDF in a folder")
        z.writestr("b_2_assignsubmission_file_x.pdf", b"%PDF loose")
    with pytest.raises(ValueError, match=ingest.NO_FOLDERS):
        ingest.check_whole(flat)
    assert ingest.files_without_folder(tmp_path / f"x-3438636 ({ingest.INCOMPLETE}).zip") == 1


def test_a_kept_download_is_never_written_over(tmp_path):
    taken = tmp_path / "Moodle download 2026-10-23 11-33.zip"
    taken.write_bytes(b"first")
    assert ingest._free(taken).name == "Moodle download 2026-10-23 11-33 (2).zip"
    (tmp_path / "Moodle download 2026-10-23 11-33 (2).zip").write_bytes(b"second")
    assert ingest._free(taken).name == "Moodle download 2026-10-23 11-33 (3).zip"
    folder = tmp_path / "Moodle download 2026-10-23 11-34"
    assert ingest._free(folder) == folder
    folder.mkdir()
    assert ingest._free(folder).name == "Moodle download 2026-10-23 11-34 (2)"


def test_one_moodle_id_in_two_folders_is_refused(tmp_path, monkeypatch):
    """A copied assignment folder: the pull must not guess which of the two gets the submissions."""
    monkeypatch.setenv("ASSIGNMENT_DATA", str(tmp_path))
    for course, name in [("Linear Algebra", "Assignment 0"), ("Discrete Mathematics", "Assignment 1")]:
        d = tmp_path / course / name
        d.mkdir(parents=True)
        (d / paths.INFO).write_text(json.dumps({"id": "3438636"}), encoding="utf-8")
    with pytest.raises(paths.TwoFolders, match="2 assignment folders"):
        paths.find_assignment("3438636")
    (tmp_path / "Discrete Mathematics" / "Assignment 1" / paths.INFO).write_text(json.dumps({"id": "3500001"}), encoding="utf-8")
    assert paths.find_assignment("3438636") == tmp_path / "Linear Algebra" / "Assignment 0"
    assert paths.find_assignment("3500001") == tmp_path / "Discrete Mathematics" / "Assignment 1"
