import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from moodle.schedule import ASSIGNMENTS_FILE, load_assignments, pending

DUE = datetime(2026, 10, 27, tzinfo=timezone.utc)
ASSIGNMENTS = [{"id": "111", "due": DUE}, {"id": "222", "due": DUE + timedelta(days=7)}]


def download(raw_dir: Path, assignment_id: str, when: datetime) -> None:
    raw_dir.mkdir(exist_ok=True)
    path = raw_dir / f"{assignment_id}-x.zip"
    path.write_bytes(b"")
    os.utime(path, (when.timestamp(), when.timestamp()))


def test_nothing_pending_before_the_due_date():
    with tempfile.TemporaryDirectory() as tmp:
        assert pending(ASSIGNMENTS, DUE - timedelta(hours=1), Path(tmp)) == []


def test_pending_after_the_due_date_until_downloaded():
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw"
        after = DUE + timedelta(hours=1)
        assert [a["id"] for a in pending(ASSIGNMENTS, after, raw)] == ["111"]

        # A download from before the due date does not count: students were still submitting
        download(raw, "111", DUE - timedelta(days=1))
        assert [a["id"] for a in pending(ASSIGNMENTS, after, raw)] == ["111"]

        download(raw, "111", after)
        assert pending(ASSIGNMENTS, after, raw) == []


def test_repo_assignments_file_loads():
    assignments = load_assignments(ASSIGNMENTS_FILE)
    assert all(a["due"].tzinfo for a in assignments)


if __name__ == "__main__":
    test_nothing_pending_before_the_due_date()
    test_pending_after_the_due_date_until_downloaded()
    test_repo_assignments_file_loads()
    print("All tests passed.")
