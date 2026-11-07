"""The activity log: one file per writer, merged on read, oldest first, nothing lost to a broken line."""
import json

import pytest

import activity_log
from moodle import paths


def test_record_and_read_back(tmp_path):
    e = activity_log.record(tmp_path, "grade_edit", by="dana (PC1)", number="0001", reason="ערעור")
    assert e["action"] == "grade_edit" and e["by"] == "dana (PC1)" and e["number"] == "0001" and e["at"] and e["pc"]
    assert activity_log.read(tmp_path) == [e]
    assert (tmp_path / paths.ACTIVITY_LOG / "dana (PC1).jsonl").is_file()


def test_each_writer_has_its_own_file_and_read_merges_them_in_time_order(tmp_path):
    folder = tmp_path / paths.ACTIVITY_LOG
    folder.mkdir()
    (folder / "a.jsonl").write_text(json.dumps({"at": "2026-11-07T10:00:00", "action": "x", "by": "a", "n": 2}) + "\n",
                                    encoding="utf-8")
    (folder / "b.jsonl").write_text(json.dumps({"at": "2026-11-07T09:00:00", "action": "x", "by": "b", "n": 1}) + "\n",
                                    encoding="utf-8")
    assert [e["n"] for e in activity_log.read(tmp_path)] == [1, 2]


def test_filters_by_action_and_fields(tmp_path):
    activity_log.record(tmp_path, "grade_edit", by="a", number="0001")
    activity_log.record(tmp_path, "grade_edit", by="a", number="0002")
    activity_log.record(tmp_path, "pull", by="a")
    assert [e["number"] for e in activity_log.read(tmp_path, "grade_edit")] == ["0001", "0002"]
    assert [e["number"] for e in activity_log.read(tmp_path, number="0002")] == ["0002"]


def test_lines_are_only_added(tmp_path):
    for i in range(3):
        activity_log.record(tmp_path, "x", by="a", i=i)
    lines = activity_log.file_for(tmp_path, "a").read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["i"] for l in lines] == [0, 1, 2]


def test_a_broken_line_and_a_conflict_copy_lose_nothing_and_double_nothing(tmp_path):
    activity_log.record(tmp_path, "x", by="a", i=1)
    path = activity_log.file_for(tmp_path, "a")
    good = path.read_text(encoding="utf-8")
    path.write_text(good + '{"at": "2026-11-07T1', encoding="utf-8")  # cut in the middle
    (path.parent / "a-DESKTOP.jsonl").write_text(good, encoding="utf-8")  # OneDrive's conflict copy
    assert [e["i"] for e in activity_log.read(tmp_path)] == [1]


def test_the_base_fields_cannot_be_overwritten_and_action_is_required(tmp_path):
    e = activity_log.record(tmp_path, "x", by="a", at="1999", pc="fake")
    assert e["at"] != "1999" and e["pc"] != "fake"
    with pytest.raises(ValueError):
        activity_log.record(tmp_path, "", by="a")


def test_no_log_folder_reads_empty(tmp_path):
    assert activity_log.read(tmp_path) == []
