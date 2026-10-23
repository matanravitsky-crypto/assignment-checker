"""Pulling the same assignment again and again must never overwrite anything: no student changes number, no number
belongs to two students, nobody leaves the key, every file is the latest submission of its number's student, and
every download stays kept. Also a pull that fails halfway, and a key that is empty or broken.

Fake students only. Real 7-Zip (skipped where it is not installed).
"""
from __future__ import annotations

import csv
import json
import os
import random
import zipfile
from pathlib import Path

import pytest

from moodle import anonymize, ingest, paths

MID, COURSE, NAME = "9990001", "Test Course", "Assignment 0 - Repeat"


@pytest.fixture
def data(tmp_path, monkeypatch):
    try:
        ingest.seven_zip()
    except FileNotFoundError:
        pytest.skip("7-Zip is not installed")
    monkeypatch.setenv("ASSIGNMENT_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("ASSIGNMENT_WORK", str(tmp_path / "work"))
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    return downloads


class Moodle:
    """The submissions of one assignment, changing between pulls like the real ones."""

    def __init__(self, downloads: Path, seed: int):
        self.downloads, self.rng, self.next_pid = downloads, random.Random(seed), 13476000
        self.students: dict[str, dict] = {}
        for _ in range(20):
            self.add()

    def add(self) -> None:
        self.next_pid += self.rng.randint(1, 40)
        self.students[str(self.next_pid)] = {"files": [os.urandom(64)], "present": True}

    def change(self) -> None:
        for _ in range(self.rng.randint(1, 5)):
            self.add()
        for pid in self.rng.sample(sorted(self.students), k=4):
            s, r = self.students[pid], self.rng.random()
            if r < 0.35:
                s["files"][0] = os.urandom(len(s["files"][0]))  # resubmitted: same size, other bytes
            elif r < 0.55:
                s["files"].append(os.urandom(50))
            elif r < 0.7 and len(s["files"]) > 1:
                s["files"].pop()
            elif r < 0.85:
                s["present"] = not s["present"]  # removed in Moodle, or back

    def _zip(self, pids: list[str], path: Path) -> None:
        with zipfile.ZipFile(path, "w") as z:
            for pid in pids:
                for i, data in enumerate(self.students[pid]["files"]):
                    z.writestr(f"תלמיד {pid[-3:]}_{pid}_assignsubmission_file/scan {i + 1}.pdf", data)

    def download(self, in_parts: bool) -> Path:
        present = [p for p, s in self.students.items() if s["present"]]
        self.rng.shuffle(present)
        stem = f"214193210120271-הגשה 0-{MID}"
        if not in_parts:
            self._zip(present, self.downloads / f"{stem}.zip")
            return self.downloads / f"{stem}.zip"
        k = self.rng.randint(2, 4)
        files = []
        for n in range(1, k + 1):
            name = f"{stem} part {n:03} of {k:03}.zip"
            self._zip(present[n - 1::k], self.downloads / name)
            files.append({"name": name, "size": (self.downloads / name).stat().st_size})
        listing = self.downloads / f"{stem}.json"
        listing.write_text(json.dumps({"users": len(present), "parts": k, "empty": [], "failed": [], "files": files}),
                           encoding="utf-8")
        return listing


def folder() -> Path:
    return paths.data_dir() / COURSE / NAME


def key() -> dict[str, set]:
    with open(folder() / paths.KEY, encoding="utf-8-sig", newline="") as f:
        out: dict[str, set] = {}
        for r in csv.DictReader(f):
            out.setdefault(r["participant_id"], set()).add(r["number"])
        return out


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_eight_pulls_in_a_row_overwrite_nothing(data, seed):
    moodle, numbers = Moodle(data, seed), {}
    for round_no in range(1, 9):
        if round_no > 1:
            moodle.change()
        ingest.ingest(MID, moodle.download(in_parts=round_no % 2 == 0), COURSE, NAME)
        k = key()
        assert all(len(n) == 1 for n in k.values()), "a student with two numbers"
        current = {pid: next(iter(n)) for pid, n in k.items()}
        assert all(current[pid] == n for pid, n in numbers.items()), "a student changed number"
        assert len(set(current.values())) == len(current), "a number of two students"
        numbers.update(current)
        files = list((folder() / paths.TO_GRADE).iterdir())
        for pid, s in moodle.students.items():
            if pid not in numbers:  # added and removed in Moodle between the same two pulls: never pulled
                continue
            mine = sorted(p.read_bytes() for p in files if p.name.split(".")[0].split("-")[0] == numbers[pid])
            if s["present"]:
                assert mine == sorted(s["files"]), f"round {round_no}: {numbers[pid]} is not the latest submission"
            else:
                assert mine, f"round {round_no}: {numbers[pid]} (not in this download) lost its files"
        assert not list(data.iterdir()), "something was left in Downloads"
        assert not [p for p in folder().rglob("*") if p.name.endswith(".tmp") or "(previous)" in p.name]
    kept = [p for p in folder().iterdir() if p.name.startswith(paths.DOWNLOAD_PREFIX)]
    assert len(kept) == 8, "a download kept in the same minute as another overwrote it"


def test_a_pull_that_fails_halfway_loses_nothing(data, monkeypatch):
    moodle = Moodle(data, 7)
    ingest.ingest(MID, moodle.download(False), COURSE, NAME)
    before, files_before = key(), {p.name: p.read_bytes() for p in (folder() / paths.TO_GRADE).iterdir()}
    gone = sorted(moodle.students)[:2]
    for pid in gone:
        moodle.students[pid]["present"] = False
    moodle.add()
    for pid in sorted(moodle.students)[2:6]:  # resubmitted: only what changed is copied, so give it something
        moodle.students[pid]["files"][0] = os.urandom(64)
    calls = {"n": 0}
    real = anonymize.shutil.copy2

    def copy_fails_at_the_third(src, dst, *a, **k):
        calls["n"] += 1
        if calls["n"] == 3:
            raise PermissionError("OneDrive holds the file")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(anonymize.shutil, "copy2", copy_fails_at_the_third)
    with pytest.raises(PermissionError):
        ingest.ingest(MID, moodle.download(False), COURSE, NAME)
    # right after: the key as it was, and every file either as it was or the new one, none half written
    assert key() == before
    assert sorted(p.name for p in (folder() / paths.TO_GRADE).iterdir()) == sorted(files_before)
    monkeypatch.setattr(anonymize.shutil, "copy2", real)
    for p in data.iterdir():
        p.unlink()
    ingest.ingest(MID, moodle.download(False), COURSE, NAME)
    after = key()
    assert all(after[pid] == n for pid, n in before.items())
    for pid in gone:
        assert files_before[f"{next(iter(before[pid]))}.pdf"] == (folder() / paths.TO_GRADE / f"{next(iter(before[pid]))}.pdf").read_bytes()


def test_a_key_that_fails_to_write_stays_as_it_was(data, monkeypatch):
    moodle = Moodle(data, 8)
    ingest.ingest(MID, moodle.download(False), COURSE, NAME)
    before = key()
    moodle.add()

    def disk_full(self, rows):
        raise OSError("disk full")
    monkeypatch.setattr(csv.DictWriter, "writerows", disk_full)
    with pytest.raises(OSError):
        ingest.ingest(MID, moodle.download(False), COURSE, NAME)
    monkeypatch.undo()
    monkeypatch.setenv("ASSIGNMENT_DATA", str(data.parent / "data"))
    monkeypatch.setenv("ASSIGNMENT_WORK", str(data.parent / "work"))
    assert key() == before  # whole or not at all: never an empty key that would renumber everyone


@pytest.mark.parametrize("broken", ["", "number,anon_file\r\n", "﻿number,anon_file,participant_id\r\nx,y,z\r\n"])
def test_an_empty_or_broken_key_stops_the_pull_before_anything_moves(data, broken):
    moodle = Moodle(data, 9)
    ingest.ingest(MID, moodle.download(False), COURSE, NAME)
    (folder() / paths.KEY).write_text(broken, encoding="utf-8")
    files = sorted(p.name for p in (folder() / paths.TO_GRADE).iterdir())
    kept = sorted(p.name for p in folder().iterdir())
    download = moodle.download(False)
    with pytest.raises(ValueError, match=anonymize.KEY_EMPTY):
        ingest.ingest(MID, download, COURSE, NAME)
    assert download.exists(), "the download stays in Downloads"
    assert sorted(p.name for p in (folder() / paths.TO_GRADE).iterdir()) == files
    assert sorted(p.name for p in folder().iterdir()) == kept


def test_a_folder_left_by_the_old_code_gives_its_files_back(data):
    """The old code renamed the folder to "(previous)" during a pull; one left by a failed pull is merged back."""
    moodle = Moodle(data, 10)
    ingest.ingest(MID, moodle.download(False), COURSE, NAME)
    anon = folder() / paths.TO_GRADE
    previous = folder() / f"{paths.TO_GRADE} (previous)"
    previous.mkdir()
    first = sorted(anon.iterdir())[0]
    first.replace(previous / first.name)
    absent = next(pid for pid, n in key().items() if next(iter(n)) == first.name[:4])
    moodle.students[absent]["present"] = False
    ingest.ingest(MID, moodle.download(False), COURSE, NAME)
    assert (anon / first.name).exists() and not previous.exists()
