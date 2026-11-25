"""Private filesystem locations and opaque keys for normalized profile images."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import HTTPException, status

from app.config import load_settings
from app.database import database_path

STORAGE_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.jpg$")


def profile_photo_directory() -> Path:
    """Return the private photo directory, creating it with owner-only permissions."""
    configured = load_settings().profile_photo_dir
    directory = configured if configured is not None else database_path().parent / "profile_photos"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    resolved = directory.resolve()
    if not resolved.is_dir():
        raise RuntimeError("Profile photo storage is not a directory")
    if os.name != "nt":
        os.chmod(resolved, 0o700)
    return resolved


def photo_path(storage_key: str) -> Path:
    """Resolve a generated photo key without accepting user-controlled paths."""
    if not STORAGE_KEY_PATTERN.fullmatch(storage_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono zdjęcia profilowego.")
    return profile_photo_directory() / storage_key
