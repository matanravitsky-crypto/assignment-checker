"""Who grades what (moodle/claims.py): one file per grader, everyone reads them all."""
import json

import pytest

from moodle import claims, paths


@pytest.fixture
def a(tmp_path):
    return tmp_path


def test_take_and_release_write_only_my_file(a):
    assert claims.take(a, ["0001", "0002"], who="מתן") == {"taken": ["0001", "0002"], "others": {}}
    assert claims.take(a, ["0002", "0003"], who="אורי") == {"taken": ["0003"], "others": {"0002": "מתן"}}
    assert sorted(p.name for p in (a / paths.CLAIMS).iterdir()) == ["אורי.json", "מתן.json"]
    held = claims.read_all(a)
    assert {n: h["who"] for n, h in held.items()} == {"0001": "מתן", "0002": "מתן", "0003": "אורי"}
    assert claims.release(a, ["0002", "0003"], who="מתן") == ["0002"]  # 0003 is not mine to give back
    assert claims.take(a, ["0002"], who="אורי")["taken"] == ["0002"]


def test_taking_again_keeps_the_first_time(a):
    claims.take(a, ["0001"], who="מתן")
    first = claims.read_all(a)["0001"]["at"]
    path = a / paths.CLAIMS / "מתן.json"
    before = path.read_bytes()
    claims.take(a, ["0001"], who="מתן")
    assert claims.read_all(a)["0001"]["at"] == first and path.read_bytes() == before  # nothing new, nothing written


def test_two_claims_before_sync_go_to_whoever_took_it_first(a):
    """OneDrive brought both files only after both people took 0005: the earlier one keeps it, on every computer."""
    (a / paths.CLAIMS).mkdir()
    for who, at in (("מתן", "2026-10-23T10:00:05"), ("אורי", "2026-10-23T10:00:01")):
        (a / paths.CLAIMS / f"{who}.json").write_text(json.dumps({"name": who, "numbers": {"0005": at}}), encoding="utf-8")
    assert claims.read_all(a)["0005"]["who"] == "אורי"
    assert claims.take(a, ["0005"], who="מתן")["others"] == {"0005": "אורי"}


def test_a_broken_file_is_skipped_but_never_overwritten(a):
    claims.take(a, ["0001"], who="מתן")
    (a / paths.CLAIMS / "אורי.json").write_text("{half", encoding="utf-8")
    assert set(claims.read_all(a)) == {"0001"}
    (a / paths.CLAIMS / "מתן.json").write_text("{half", encoding="utf-8")
    with pytest.raises(ValueError):
        claims.take(a, ["0002"], who="מתן")
    assert (a / paths.CLAIMS / "מתן.json").read_text(encoding="utf-8") == "{half"


def test_names_become_safe_file_names_and_rename_moves_claims(a):
    assert claims.file_name('a/b:c?') == "a_b_c_" and claims.file_name(" . ") == "grader"
    claims.take(a, ["0001"], who="matan")
    claims.take(a, ["0002"], who="מתן")
    claims.rename(a, "matan", "מתן")
    assert not (a / paths.CLAIMS / "matan.json").exists()
    assert {n: h["who"] for n, h in claims.read_all(a).items()} == {"0001": "מתן", "0002": "מתן"}


def test_my_name_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("GRADER_NAME", "  נועה ")
    assert claims.me() == "נועה" and claims.name_set()
    monkeypatch.delenv("GRADER_NAME")
    assert claims.me() and not claims.name_set()  # the Windows user name


# ---------- pull and return: an owner per assignment ----------
def test_task_key_uses_the_slot_number():
    assert claims.task_key("Assignment 3 - Vectors", "pull") == claims.task_key("Assignment 3", "pull") == "3:pull"
    assert claims.task_key("Extra", "return") == "Extra:return"


def test_latest_take_or_release_decides_the_owner(a):
    assert claims.set_task(a, "3:pull", True, who="מתן")["who"] == "מתן"
    path = a / paths.TASKS / "אורי.json"
    path.parent.mkdir(exist_ok=True)
    # אורי לקח אחרי מתן (מתן לא זמין): עכשיו זה אצל אורי
    path.write_text(json.dumps({"name": "אורי", "tasks": {"3:pull": {"at": "2999-01-01T00:00:00", "taken": True}}}),
                    encoding="utf-8")
    assert claims.task_owners(a)["3:pull"]["who"] == "אורי"
    path.write_text(json.dumps({"name": "אורי", "tasks": {"3:pull": {"at": "2999-01-01T00:00:01", "taken": False}}}),
                    encoding="utf-8")
    assert "3:pull" not in claims.task_owners(a)  # אורי שחרר אחרון: אין אחראי, גם אם אצל מתן עוד רשום שלקח


def test_tasks_move_with_a_new_name(a):
    claims.set_task(a, "1:return", True, who="matan")
    claims.rename_tasks(a, "matan", "מתן")
    assert claims.task_owners(a)["1:return"]["who"] == "מתן"
    assert not (a / paths.TASKS / "matan.json").exists()
