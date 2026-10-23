import pytest


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    """Grading tests never write into the real shared data folder (usage log)."""
    monkeypatch.setenv("ASSIGNMENT_DATA", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
