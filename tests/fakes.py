"""A fake Moodle upload driver for the tests. The system itself only ever uploads to the real Moodle."""
from __future__ import annotations

import time
from pathlib import Path

from moodle.send import UploadResult


class FakeDriver:
    """A driver that never touches Moodle: gives `results` one by one, then says every ZIP went through.

    Tests only. `delay` seconds per ZIP.
    """

    def __init__(self, results: list[UploadResult] | None = None, delay: float = 0.0):
        self.results = list(results or [])
        self.delay = delay
        self.calls: list[str] = []  # names of the ZIPs it was given

    def upload_zip(self, info: dict, zip_path: Path, expected: int, dry_run: bool,
                   sha256: str | None = None) -> UploadResult:
        self.calls.append(zip_path.name)
        if self.delay:
            time.sleep(self.delay)
        if self.results:
            return self.results.pop(0)
        if dry_run:
            return UploadResult("dry_run_ok", rows=expected)
        return UploadResult("imported", rows=expected, imported=expected)


class FakeGradesDriver(FakeDriver):
    """FakeDriver that also "has" Moodle's grading worksheet: `download_worksheet` writes `sheet` (rows of a CSV) into
    `downloads` as Chrome would, and `upload_grades` answers with `grades_result`, or by default a preview that
    matches and an import. `uploaded` keeps the CSV rows it was given."""

    def __init__(self, downloads: Path, sheet: list[list[str]], *, download_status: str = "started",
                 grades_result=None, **kwargs):
        super().__init__(**kwargs)
        self.downloads, self.sheet, self.download_status = downloads, sheet, download_status
        self.grades_result = grades_result
        self.uploaded: list[tuple[list[list[str]], int, bool]] = []

    def download_worksheet(self, info: dict) -> dict:
        if self.download_status == "started":
            import csv
            with open(self.downloads / f"Grading worksheet-{info['id']}.csv", "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(self.sheet)
        return {"status": self.download_status, "message": ""}

    def upload_grades(self, info: dict, csv_path: Path, expected: int, dry_run: bool, sha256: str | None = None):
        import csv
        from moodle.send_grades import GradesResult
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            self.uploaded.append((list(csv.reader(f)), expected, dry_run))
        if self.grades_result is not None:
            return self.grades_result
        if dry_run:
            return GradesResult("dry_run_ok", preview=expected, skipped=0)
        return GradesResult("imported", preview=expected, skipped=0, updated=expected)
