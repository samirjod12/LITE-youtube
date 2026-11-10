"""Application context: owns settings, storage, caches, blocker and services."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .blocker import DomainBlocker
from .cache import MetadataCache, ThumbnailCache, setup_logging
from .config import Settings
from .db import Storage, StorageError
from .mpvconf import MpvInfo, ensure_conf
from .paths import Paths
from .search import SearchService

SEED_BLOCKLIST = """\
# YouTube Lite - custom blocklist (one domain per line, # for comments).
# Used only when the ad blocker is switched ON. See README for what it controls.
# YouTube/Google playback and sign-in domains are protected and can never be blocked.
doubleclick.net
googlesyndication.com
googleadservices.com
google-analytics.com
googletagmanager.com
googletagservices.com
adservice.google.com
2mdn.net
"""

SEED_ALLOWLIST = """\
# YouTube Lite - allowlist. Domains here are never blocked, even if on a blocklist.
"""


class AppContext:
    def __init__(self, root: Path | str | None = None):
        self.paths = Paths(root)
        self.problems: list[str] = self.paths.ensure()
        self.writable = self.paths.is_writable()
        self._seed_files()

        self.settings = Settings(self.paths.settings_file)
        self.settings.load()
        self.logger = setup_logging(self.paths.log_file, self.settings.log_limit_bytes())

        self.storage = Storage(self.paths.db_file)
        self.storage.open()

        self.thumb_cache = ThumbnailCache(self.paths.thumb_dir, self.settings.thumb_limit_bytes)
        self.meta_cache = MetadataCache(self.paths.meta_dir, self.settings.meta_limit_bytes)

        self.blocker = DomainBlocker(self.paths.blocklist_file, self.paths.allowlist_file,
                                     self.paths.downloaded_list_file)
        self.blocker.reload()
        self.blocker.enabled = bool(self.settings["adblock"]["enabled"])

        self.search = SearchService(self._js_runtimes)
        ensure_conf(self.paths.mpv_conf)
        self._mpv_info: MpvInfo | None = None
        self.notify: Callable[[str], None] = lambda msg: None   # set by the main window

    def _seed_files(self) -> None:
        for path, text in ((self.paths.blocklist_file, SEED_BLOCKLIST),
                           (self.paths.allowlist_file, SEED_ALLOWLIST)):
            try:
                if not path.exists():
                    path.write_text(text, encoding="utf-8")
            except OSError:
                pass

    def _js_runtimes(self) -> dict | None:
        exe = self.paths.deno_exe()
        return {"deno": {"path": str(exe)}} if exe else None

    # -- mpv ---------------------------------------------------------------
    def mpv_exe(self) -> Path | None:
        return self.paths.mpv_exe()

    def mpv_info(self) -> MpvInfo | None:
        exe = self.mpv_exe()
        if exe is None:
            return None
        if self._mpv_info is None or self._mpv_info.exe != exe:
            self._mpv_info = MpvInfo(exe)
        return self._mpv_info

    # -- helpers -----------------------------------------------------------
    def db(self, fn, *args, default=None):
        """Run a storage call; on failure tell the user instead of crashing."""
        try:
            return fn(*args)
        except StorageError as exc:
            self.logger.warning("storage: %s", exc)
            msg = str(exc)
            if not self.paths.root_available():
                msg = "The drive with YouTube Lite is not available (USB removed?)."
            self.notify(msg)
            return default

    def save_settings(self) -> bool:
        ok = self.settings.save()
        if not ok:
            self.notify(self.settings.last_error)
        return ok

    def shutdown(self) -> None:
        self.storage.close()
        for h in list(self.logger.handlers):
            try:
                h.flush()
                h.close()
            except Exception:
                pass
