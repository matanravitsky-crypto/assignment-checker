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
