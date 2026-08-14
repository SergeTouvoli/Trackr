"""Paths compatible with source and packaged execution.

Paths relative to ``__file__`` become fragile once the application is frozen:
PyInstaller onefile extracts into a temporary directory, and the installation
directory may not be writable. User data and bundled assets therefore have their
own resolution rules.
"""
import os
import sys
from pathlib import Path


APP_DATA_DIR_NAME = "Trackr Time"
LEGACY_APP_DATA_DIR_NAME = "Trackr"


def _platform_data_base() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home()))
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def legacy_app_data_dir() -> Path:
    """Return the legacy data directory without creating it."""
    return _platform_data_base() / LEGACY_APP_DATA_DIR_NAME


def app_data_dir() -> Path:
    """Return the writable user directory for the database and settings."""
    directory = _platform_data_base() / APP_DATA_DIR_NAME
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    if os.name != "nt":
        directory.chmod(0o700)

    return directory


def bundle_dir() -> Path:
    """Return the directory containing read-only assets."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[2]


def assets_dir() -> Path:
    """Return the assets directory used by Flet and PyInstaller."""
    candidates = [
        bundle_dir() / "assets",
        Path(sys.executable).resolve().parent / "assets",
        Path(sys.executable).resolve().parent / "_internal" / "assets",
        Path.cwd() / "assets",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def asset_path(filename: str) -> Path:
    """Return the full path to an application asset."""
    return assets_dir() / filename
