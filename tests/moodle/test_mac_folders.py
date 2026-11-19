"""The system on a Mac (2026-11-19: everyone on a Mac failed to connect).

On a Mac, OneDrive keeps what it syncs under ~/Library/CloudStorage: the person's own OneDrive in
"OneDrive-<organization>", and a folder synced with the Sync button (Nadav's YallaLinearit) in
"OneDrive-SharedLibraries-<organization>". The search looked two levels under the home folder only, so it never got there.
7-Zip on a Mac is "7zz" (Homebrew's sevenzip, and 7-zip.org's own build), not "7z".
"""
from __future__ import annotations

import json

import pytest

from moodle import ingest, paths, shared_folder

COURSE = "נדב מאיר - YallaLinearit"


@pytest.fixture
def mac_home(tmp_path, monkeypatch):
    for var in ("ASSIGNMENT_CHECKER_ROOT", "OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(shared_folder.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(shared_folder, "local_data_dir", lambda: None)
    for name in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Movies", "Public", "Applications"):
        (tmp_path / name).mkdir()
    return tmp_path


def _system(course: shared_folder.Path) -> shared_folder.Path:
    system = course / paths.DATA_FOLDER
    (system / "Linear Algebra" / "Assignment 0").mkdir(parents=True)
    (system / "Linear Algebra" / "Assignment 0" / paths.INFO).write_text(json.dumps({"id": "1"}), encoding="utf-8")
    return system


def test_folder_synced_with_the_sync_button_is_found_on_a_mac(mac_home):
    system = _system(mac_home / "Library" / "CloudStorage" / "OneDrive-SharedLibraries-BGU" / COURSE)
    assert shared_folder.find_root() == system


def test_folder_added_as_a_shortcut_is_found_on_a_mac(mac_home):
    system = _system(mac_home / "Library" / "CloudStorage" / "OneDrive-BGU" / "YallaLinearit")
    assert shared_folder.find_root() == system


def test_cloud_storage_folders_count_as_onedrive_roots(mac_home):
    cloud = mac_home / "Library" / "CloudStorage"
    for name in ("OneDrive-BGU", "OneDrive-SharedLibraries-BGU", "GoogleDrive-someone"):
        (cloud / name).mkdir(parents=True)
    names = [p.name for p in shared_folder.onedrive_roots()]
    assert names == ["OneDrive-BGU", "OneDrive-SharedLibraries-BGU"]


def test_a_symlink_in_the_home_folder_is_not_counted_twice(mac_home):
    real = mac_home / "Library" / "CloudStorage" / "OneDrive-BGU"
    real.mkdir(parents=True)
    try:
        (mac_home / "OneDrive - BGU").symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("no symlinks on this computer")
    assert [p.resolve() for p in shared_folder.onedrive_roots()] == [real.resolve()]


def test_the_search_stays_out_of_library_and_the_media_folders(mac_home, monkeypatch):
    """~/Library holds every app's data, and macOS asks the person for leave to read other apps' folders and the
    media libraries. The search must open none of them, only ~/Library/CloudStorage."""
    for name in ("Library/Containers/com.apple.mail", "Library/Mail/V10", "Pictures/Photos Library.photoslibrary"):
        (mac_home / name).mkdir(parents=True)
    _system(mac_home / "Library" / "CloudStorage" / "OneDrive-SharedLibraries-BGU" / COURSE)
    opened = []
    real_iterdir = shared_folder.Path.iterdir

    def iterdir(self):
        opened.append(self)
        return real_iterdir(self)

    monkeypatch.setattr(shared_folder.Path, "iterdir", iterdir)
    shared_folder.find_root()
    forbidden = {mac_home / n for n in ("Library", "Library/Containers", "Library/Mail", "Pictures", "Music", "Movies",
                                        "Applications", "Desktop", "Documents", "Downloads")}
    assert not forbidden & set(opened)


def test_seven_zip_is_found_by_its_mac_name(monkeypatch):
    monkeypatch.setattr(ingest.shutil, "which", lambda name: "/opt/homebrew/bin/7zz" if name == "7zz" else None)
    monkeypatch.setattr(ingest, "SEVEN_ZIP_PATHS", [])
    assert ingest.seven_zip() == "/opt/homebrew/bin/7zz"


def test_seven_zip_from_7_zip_org_in_local_bin_is_found(tmp_path, monkeypatch):
    seven = tmp_path / ".local" / "bin" / "7zz"
    seven.parent.mkdir(parents=True)
    seven.write_text("")
    monkeypatch.setattr(ingest.shutil, "which", lambda name: None)
    monkeypatch.setattr(ingest.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(ingest, "SEVEN_ZIP_PATHS", [])
    assert ingest.seven_zip() == str(seven)


@pytest.mark.parametrize("platform, hint", [("darwin", "connect.sh"), ("win32", "winget install 7zip.7zip")])
def test_missing_seven_zip_says_how_to_install_it_on_this_computer(monkeypatch, tmp_path, platform, hint):
    monkeypatch.setattr(ingest.shutil, "which", lambda name: None)
    monkeypatch.setattr(ingest.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(ingest, "SEVEN_ZIP_PATHS", [])
    monkeypatch.setattr(ingest.sys, "platform", platform)
    with pytest.raises(FileNotFoundError) as e:
        ingest.seven_zip()
    assert "7-Zip" in str(e.value) and hint in str(e.value)
