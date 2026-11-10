"""Portable path handling.

Everything (settings, database, cache, filters, logs, mpv) lives next to the
executable, or next to the repository root when running from source. Nothing is
written to %APPDATA%, the registry, or any other system location.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # src/ytlite/paths.py -> repo root
    return Path(__file__).resolve().parents[2]


def is_within(path: Path, base: Path) -> bool:
    """True if *path* resolves to a location inside *base* (path validation)."""
    try:
        Path(path).resolve().relative_to(Path(base).resolve())
        return True
    except (ValueError, OSError):
        return False


class Paths:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root).resolve() if root else app_root()
        r = self.root
        self.config_dir = r / "config"
        self.settings_file = self.config_dir / "settings.json"
        self.data_dir = r / "data"
        self.db_file = self.data_dir / "history.db"
        self.cache_dir = r / "cache"
        self.thumb_dir = self.cache_dir / "thumbnails"
        self.meta_dir = self.cache_dir / "metadata"
        self.filters_dir = r / "filters"
        self.blocklist_file = self.filters_dir / "blocklist.txt"
        self.allowlist_file = self.filters_dir / "allowlist.txt"
        self.downloaded_list_file = self.filters_dir / "downloaded.txt"
        self.mpv_dir = r / "mpv"
        self.mpv_conf = self.mpv_dir / "mpv.conf"
        self.logs_dir = r / "logs"
        self.runtime_dir = r / "runtime"       # deno.exe: JavaScript runtime used by yt-dlp
        self.log_file = self.logs_dir / "youtube-lite.log"

    def dirs(self) -> list[Path]:
        return [self.config_dir, self.data_dir, self.thumb_dir, self.meta_dir,
                self.filters_dir, self.mpv_dir, self.logs_dir]

    def ensure(self) -> list[str]:
        """Create the portable folder layout. Returns a list of problems (empty = ok)."""
        problems: list[str] = []
        for d in self.dirs():
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                problems.append(f"Cannot create {d}: {exc}")
        return problems

    def is_writable(self) -> bool:
        probe = self.root / ".write_test.tmp"
        try:
            probe.write_text("x", encoding="ascii")
            probe.unlink()
            return True
        except OSError:
            return False

    def root_available(self) -> bool:
        """False when the drive/folder disappeared (e.g. USB unplugged)."""
        return self.root.exists()

    def mpv_exe(self) -> Path | None:
        """Bundled mpv first, then mpv on PATH (development convenience)."""
        name = "mpv.exe" if os.name == "nt" else "mpv"
        bundled = self.mpv_dir / name
        if bundled.is_file():
            return bundled
        found = shutil.which("mpv")
        return Path(found) if found else None

    def deno_exe(self) -> Path | None:
        name = "deno.exe" if os.name == "nt" else "deno"
        bundled = self.runtime_dir / name
        if bundled.is_file():
            return bundled
        found = shutil.which("deno")
        return Path(found) if found else None

    def mpv_is_bundled(self) -> bool:
        exe = self.mpv_exe()
        return bool(exe and is_within(exe, self.mpv_dir))
