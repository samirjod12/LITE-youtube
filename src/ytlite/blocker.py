"""Optional domain-based ad/tracker filter. Default: OFF.

WHAT IT ACTUALLY CONTROLS
  * Thumbnail downloads made by YouTube Lite itself.
  * A final host check on URLs YouTube Lite is about to hand to mpv or the
    browser (blocked hosts are refused, with a message).

WHAT IT DOES NOT CONTROL
  * Requests made by mpv or by your web browser after hand-off.
  * Ads delivered from the same servers as the video itself.
It never touches the hosts file, firewall, browser extensions or sign-in.
Lists are plain data: they are parsed as domain names and never executed.
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .errors import YtLiteError

# Never blocked, so playback and Google sign-in cannot be broken by a bad list.
PROTECTED = ("youtube.com", "youtu.be", "googlevideo.com", "ytimg.com", "ggpht.com",
             "accounts.google.com", "googleusercontent.com", "gstatic.com")

_DOMAIN = re.compile(r"^(?=.{4,253}$)[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?"
                     r"(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)+$")
MAX_LIST_BYTES = 5 * 1024 * 1024


def _suffixes(host: str):
    parts = host.split(".")
    for i in range(len(parts) - 1):
        yield ".".join(parts[i:])


def is_protected(host: str) -> bool:
    return any(host == p or host.endswith("." + p) for p in PROTECTED)


def parse_domains(text: str) -> set[str]:
    """Parse hosts-file, adblock-style (||domain^) or plain-domain lines."""
    out: set[str] = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("!", "[")):
            continue
        if line.startswith("||"):
            line = line[2:].split("^", 1)[0].split("/", 1)[0]
        else:
            parts = line.split()
            if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1", "::1", "::"):
                line = parts[1]
            else:
                line = parts[0]
        line = line.lower().lstrip("*.").strip(".")
        if _DOMAIN.match(line) and not is_protected(line):
            out.add(line)
    return out


class DomainBlocker:
    def __init__(self, blocklist: Path, allowlist: Path, downloaded: Path):
        self.blocklist_file = Path(blocklist)
        self.allowlist_file = Path(allowlist)
        self.downloaded_file = Path(downloaded)
        self.enabled = False
        self.blocked_count = 0
        self.checked_count = 0
        self._block: set[str] = set()
        self._allow: set[str] = set()
        self.downloaded_count = 0
        self.custom_count = 0

    # -- lists -------------------------------------------------------------
    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def reload(self) -> None:
        custom = parse_domains(self._read(self.blocklist_file))
        downloaded = parse_domains(self._read(self.downloaded_file))
        self._block = custom | downloaded
        self._allow = {d for d in parse_domains(self._read(self.allowlist_file))}
        # allowlist may contain protected domains harmlessly; parse_domains drops them
        self.custom_count = len(custom)
        self.downloaded_count = len(downloaded)

    def save_custom(self, blocklist_text: str, allowlist_text: str) -> None:
        for path, text in ((self.blocklist_file, blocklist_text),
                           (self.allowlist_file, allowlist_text)):
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
        self.reload()

    def read_custom(self) -> tuple[str, str]:
        return self._read(self.blocklist_file), self._read(self.allowlist_file)

    # -- decisions ---------------------------------------------------------
    def host_is_blocked(self, host: str) -> bool:
        """Pure decision, no counters. Allowlist beats blocklist; protected never blocked."""
        host = (host or "").lower().strip(".")
        if not host or is_protected(host):
            return False
        for s in _suffixes(host):
            if s in self._allow:
                return False
        return any(s in self._block for s in _suffixes(host))

    def check_url(self, url: str) -> bool:
        """True if the URL must be blocked (only when enabled). Updates statistics."""
        if not self.enabled:
            return False
        self.checked_count += 1
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            return False
        if self.host_is_blocked(host):
            self.blocked_count += 1
            return True
        return False

    # -- manual update -----------------------------------------------------
    def update_from_url(self, url: str, timeout: float = 20.0) -> int:
        """Download a domain list over HTTPS (manual action only). Returns domain count."""
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise YtLiteError("blocker", "Filter list URLs must start with https://")
        req = urllib.request.Request(url, headers={"User-Agent": "YouTubeLite/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https only)
                data = resp.read(MAX_LIST_BYTES + 1)
        except Exception as exc:  # network, TLS, HTTP errors
            raise YtLiteError("network", "Could not download the filter list. "
                              "Check your connection.", str(exc)) from exc
        if len(data) > MAX_LIST_BYTES:
            raise YtLiteError("blocker", "The filter list is larger than 5 MB and was rejected.")
        domains = parse_domains(data.decode("utf-8", errors="replace"))
        if not domains:
            raise YtLiteError("blocker", "The downloaded file contained no valid domains.")
        self.downloaded_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.downloaded_file.with_suffix(".tmp")
        tmp.write_text("\n".join(sorted(domains)) + "\n", encoding="utf-8")
        tmp.replace(self.downloaded_file)
        self.reload()
        return len(domains)

    def stats_text(self) -> str:
        state = "ON" if self.enabled else "OFF"
        return (f"{state} | {len(self._block)} blocked domains "
                f"({self.custom_count} custom, {self.downloaded_count} downloaded), "
                f"{len(self._allow)} allowed | this session: "
                f"{self.checked_count} requests checked, {self.blocked_count} blocked")
