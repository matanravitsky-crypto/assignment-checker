"""Where student data lives on this machine.

Everything goes under one data folder, outside the repo (it is public) and
outside OneDrive (it rejects some of the file names students upload):

    <data>/raw/<assignment id>-<timestamp>.zip       ZIPs exactly as Moodle gave them
    <data>/submissions/<assignment id>/original/     extracted, one folder per student
    <data>/submissions/<assignment id>/anon/         0001.pdf ... for grading
    <data>/submissions/<assignment id>/mapping.csv   number -> Moodle participant
    <data>/submissions/<assignment id>/results.csv   grades by number (from grading)
    <data>/submissions/<assignment id>/marked/       marked files by number
    <data>/submissions/<assignment id>/upload/       what goes back to Moodle

The data folder defaults to ~/assignment-data. Set ASSIGNMENT_DATA to move it.
"""

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("ASSIGNMENT_DATA", Path.home() / "assignment-data"))


def assignment_dir(assignment_id: str) -> Path:
    return data_dir() / "submissions" / str(assignment_id)


def raw_dir() -> Path:
    return data_dir() / "raw"
