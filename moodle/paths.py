"""Where student data lives.

Two folders, both outside the repo (it is public):

The data folder is shared: the lecturer's OneDrive, synced to the downloader's
computer. Everything the team needs goes there, all with clean file names:

    <data>/raw/<assignment id>-<timestamp>.zip       ZIPs exactly as Moodle gave them
    <data>/submissions/<assignment id>/anon/         0001.pdf ... for grading
    <data>/submissions/<assignment id>/mapping.csv   number -> Moodle participant (the key)
    <data>/submissions/<assignment id>/results.csv   grades by number (from grading)
    <data>/submissions/<assignment id>/marked/       marked files by number
    <data>/submissions/<assignment id>/upload/       what goes back to Moodle

The work folder stays on the downloader's computer. It holds the extracted
ZIP, whose student file names OneDrive can't sync (invisible RTL marks, emoji):

    <work>/<assignment id>/original/                 one folder per student

It can always be rebuilt from the ZIP in raw/.

ASSIGNMENT_DATA and ASSIGNMENT_WORK override the defaults below.
"""

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("ASSIGNMENT_DATA", Path.home() / "assignment-data"))


def work_dir() -> Path:
    return Path(os.environ.get("ASSIGNMENT_WORK", Path.home() / "assignment-work"))


def assignment_dir(assignment_id: str) -> Path:
    return data_dir() / "submissions" / str(assignment_id)


def original_dir(assignment_id: str) -> Path:
    return work_dir() / str(assignment_id) / "original"


def raw_dir() -> Path:
    return data_dir() / "raw"
