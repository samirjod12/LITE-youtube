"""Size-limited disk caches (thumbnails, metadata) and log setup."""
from __future__ import annotations

import hashlib
import json
import logging
import logging.handlers
import os
import shutil
import time
from pathlib import Path
from typing import Callable

MIN_FREE_BYTES = 30 * 1024 * 1024  # stop writing cache when the drive has < 30 MB free


def _key_name(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()


class DiskCache:
    """Flat directory of files named by hash, evicted oldest-first above a size limit."""

    def __init__(self, directory: Path, limit_bytes: Callable[[], int], suffix: str):
        self.dir = Path(directory)
        self.limit_bytes = limit_bytes
        self.suffix = suffix
        self._size: int | None = None
        self._writes_since_check = 0

    def _path(self, key: str) -> Path:
        return self.dir / (_key_name(key) + self.suffix)

    def _files(self) -> list[tuple[float, int, Path]]:
        out = []
        try:
            with os.scandir(self.dir) as it:
                for e in it:
                    if e.is_file() and e.name.endswith(self.suffix):
                        st = e.stat()
                        out.append((st.st_mtime, st.st_size, Path(e.path)))
        except OSError:
            pass
        return out

    def size(self) -> int:
        self._size = sum(s for _, s, _ in self._files())
        return self._size

    def read(self, key: str) -> bytes | None:
        p = self._path(key)
        try:
            data = p.read_bytes()
        except OSError:
            return None
        try:
            os.utime(p, None)  # mark as recently used
        except OSError:
            pass
        return data

    def write(self, key: str, data: bytes) -> bool:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(self.dir).free < MIN_FREE_BYTES:
                return False
            p = self._path(key)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, p)
        except OSError:
            return False
        if self._size is None:
            self.size()
        else:
            self._size += len(data)
        self._writes_since_check += 1
        if self._size > self.limit_bytes() or self._writes_since_check >= 50:
            self._writes_since_check = 0
            self.evict()
        return True

    def evict(self) -> int:
        """Delete least-recently-used files until size <= 80% of the limit."""
        files = sorted(self._files())
        total = sum(s for _, s, _ in files)
        limit = self.limit_bytes()
        removed = 0
        if total > limit:
            target = int(limit * 0.8)
            for _, size, path in files:
                if total <= target:
                    break
                try:
                    path.unlink()
                    total -= size
                    removed += 1
                except OSError:
                    pass
        self._size = total
        return removed

    def clear(self) -> int:
        n = 0
        for _, _, path in self._files():
            try:
                path.unlink()
                n += 1
            except OSError:
                pass
        # stray temp files
        try:
            for tmp in self.dir.glob("*.tmp"):
                tmp.unlink()
        except OSError:
            pass
        self._size = 0
        return n


class ThumbnailCache(DiskCache):
    def __init__(self, directory: Path, limit_bytes: Callable[[], int]):
        super().__init__(directory, limit_bytes, ".img")


class MetadataCache(DiskCache):
    """JSON values with a time-to-live."""

    def __init__(self, directory: Path, limit_bytes: Callable[[], int]):
        super().__init__(directory, limit_bytes, ".json")

    def get(self, key: str, ttl_s: int):
        raw = self.read(key)
        if raw is None:
            return None
        try:
            doc = json.loads(raw.decode("utf-8"))
            if time.time() - float(doc["t"]) > ttl_s:
                return None
            return doc["v"]
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            return None

    def put(self, key: str, value) -> bool:
        try:
            raw = json.dumps({"t": time.time(), "v": value}, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            return False
        return self.write(key, raw)


def dir_size(path: Path) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def setup_logging(log_file: Path, max_total_bytes: int, level: int = logging.WARNING) -> logging.Logger:
    """Small rotating log (2 files, together <= max_total_bytes). Never raises."""
    logger = logging.getLogger("ytlite")
    logger.setLevel(level)
    logger.handlers.clear()
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max(64 * 1024, max_total_bytes // 2), backupCount=1,
            encoding="utf-8", delay=True)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger
