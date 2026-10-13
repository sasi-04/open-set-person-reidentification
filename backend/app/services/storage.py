"""
Safe file storage for reference images and short-lived query crops.

In plain words: user-supplied file names are NEVER used on disk. Every stored
image gets a random 32-character name generated here (``<hex>.jpg``), and
before any file is read, written or deleted the name is checked against that
exact pattern. A name like ``../../secret.txt`` cannot match, so path traversal
is impossible by construction. We also store only our own re-encoded JPEG of
the person crop - never the raw upload.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from ..core.errors import NotFound
from ..cv.imaging import encode_jpeg

logger = logging.getLogger(__name__)

_NAME = re.compile(r"^[0-9a-f]{32}\.jpg$")


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save_jpeg(self, pixels: np.ndarray, quality: int = 90) -> str:
        """Write an RGB image under a fresh random name and return that name."""
        name = f"{uuid.uuid4().hex}.jpg"
        (self.root / name).write_bytes(encode_jpeg(pixels, quality))
        return name

    def path_for(self, name: str) -> Path:
        """Return the real path for a stored name, or raise NotFound. Rejects anything but our own names."""
        if not _NAME.fullmatch(name or ""):
            raise NotFound("Image not found.")
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            raise NotFound("Image not found.")
        return path

    def read_bytes(self, name: str) -> bytes:
        return self.path_for(name).read_bytes()

    def delete(self, name: str | None) -> None:
        if not name or not _NAME.fullmatch(name):
            return
        try:
            (self.root / name).unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete stored file %s", name)

    def delete_older_than(self, age: timedelta) -> int:
        """Delete files whose modification time is older than ``age``. Returns how many were removed."""
        cutoff = datetime.now(UTC) - age
        removed = 0
        for path in self.root.glob("*.jpg"):
            if _NAME.fullmatch(path.name) and datetime.fromtimestamp(path.stat().st_mtime, UTC) < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def clear(self) -> int:
        removed = 0
        for path in self.root.glob("*.jpg"):
            if _NAME.fullmatch(path.name):
                path.unlink(missing_ok=True)
                removed += 1
        return removed
