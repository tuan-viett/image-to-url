"""Storage abstraction + LocalStorage implementation.

Public URL layout:
    {PUBLIC_IMAGE_BASE_URL}/{storage_key}/{key}.{ext}
But because the public_url stored on the Image row already encodes the full URL,
this layer only deals with disk paths.

Disk layout (sharded to avoid one-dir-too-many-files):
    {STORAGE_ROOT}/{key[:2]}/{key[2:4]}/{key}.{ext}
"""
from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


# Storage key regex (must be valid token_urlsafe output, no special chars).
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{16,32}$")


class Storage(ABC):
    @abstractmethod
    def save(self, key: str, ext: str, source: BinaryIO) -> tuple[Path, int]:
        """Persist `source` to backend storage. Returns (absolute_path, bytes_written)."""

    @abstractmethod
    def open(self, key: str, ext: str) -> BinaryIO:
        ...

    @abstractmethod
    def delete(self, key: str, ext: str) -> None:
        ...

    @abstractmethod
    def exists(self, key: str, ext: str) -> bool:
        ...


class LocalStorage(Storage):
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str, ext: str) -> Path:
        if not KEY_RE.match(key):
            raise ValueError(f"Invalid storage key: {key!r}")
        ext = re.sub(r"[^a-z0-9]", "", ext.lower())[:10] or "img"
        shard1 = key[:2]
        shard2 = key[2:4]
        return self.root / shard1 / shard2 / f"{key}.{ext}"

    def save(self, key: str, ext: str, source: BinaryIO) -> tuple[Path, int]:
        path = self._path(key, ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        # Write atomically by using a temp file then rename.
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp, "wb") as f:
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
        return path, written

    def open(self, key: str, ext: str) -> BinaryIO:
        path = self._path(key, ext)
        if not path.exists():
            raise FileNotFoundError(str(path))
        return open(path, "rb")

    def delete(self, key: str, ext: str) -> None:
        path = self._path(key, ext)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def exists(self, key: str, ext: str) -> bool:
        return self._path(key, ext).exists()


_singleton: Storage | None = None


def get_storage() -> Storage:
    global _singleton
    if _singleton is None:
        from app.config import get_settings
        _singleton = LocalStorage(get_settings().storage_root)
    return _singleton