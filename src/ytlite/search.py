"""YouTube search and stream extraction through yt-dlp's supported Python API.

yt-dlp is imported lazily on first use (saves ~tens of MB of idle RAM).
No undocumented YouTube endpoints are called directly; only yt-dlp is used.
All methods are blocking and must run on a worker thread.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable
from urllib.parse import quote_plus, urlparse

from . import formats as fm
from .errors import YtLiteError, from_exception

_VID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_CHANNEL_URL_RE = re.compile(r"youtube\.com/(channel/|@|user/|c/)", re.I)
SOCKET_TIMEOUT = 15
CHANNEL_FILTER = "EgIQAg%3D%3D"   # the website's own "Type: Channel" filter parameter


@dataclass
class VideoItem:
    kind: str                 # "video" | "channel"
    id: str
    title: str
    channel: str
    channel_id: str
    channel_url: str
    duration: int | None
    views: int | None
    thumb_url: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "VideoItem":
        return VideoItem(
            kind=str(d.get("kind", "video")), id=str(d.get("id", "")),
            title=str(d.get("title", "")), channel=str(d.get("channel", "")),
            channel_id=str(d.get("channel_id", "")), channel_url=str(d.get("channel_url", "")),
            duration=d.get("duration") if isinstance(d.get("duration"), int) else None,
            views=d.get("views") if isinstance(d.get("views"), int) else None,
            thumb_url=str(d.get("thumb_url", "")), url=str(d.get("url", "")))


def _int(v) -> int | None:
    if isinstance(v, bool):
        return None
    try:
        n = int(float(v))
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def _str(v, limit=300) -> str:
    return v.strip()[:limit] if isinstance(v, str) else ""


def _https(url) -> str:
    return url if isinstance(url, str) and url.startswith("https://") and len(url) < 600 else ""


def pick_thumbnail(entry: dict, target_w: int) -> str:
    cands: list[tuple[int, str]] = []
    for t in entry.get("thumbnails") or []:
        if isinstance(t, dict) and _https(t.get("url")):
            cands.append((_int(t.get("width")) or 0, t["url"]))
    if cands:
        big = [c for c in cands if c[0] >= target_w]
        return min(big)[1] if big else max(cands)[1]
    single = _https(entry.get("thumbnail"))
    if single:
        return single
    vid = entry.get("id")
    if isinstance(vid, str) and _VID_RE.match(vid):
        return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
    return ""


def _channel_url(url: str) -> str:
    try:
        p = urlparse(url)
    except ValueError:
        return ""
    host = (p.hostname or "").lower()
    if p.scheme == "https" and (host == "youtube.com" or host.endswith(".youtube.com")):
        return url
    return ""


def normalize_entry(e: Any, thumb_w: int = 168, parent_channel: str = "") -> VideoItem | None:
    """Convert one (possibly malformed) yt-dlp flat entry; None if unusable."""
    if not isinstance(e, dict):
        return None
    url = _str(e.get("url") or e.get("webpage_url"), 400)
    ie = _str(e.get("ie_key"), 40).lower()
    vid = e.get("id")

    if "playlist?list=" in url or ie == "youtubeplaylist":
        return None  # playlists are out of scope

    is_channel = ie == "youtubetab" or bool(_CHANNEL_URL_RE.search(url))
    if is_channel and not (isinstance(vid, str) and _VID_RE.match(vid) and "watch" in url):
        cid = _str(e.get("channel_id") or vid, 64)
        curl = _channel_url(url)
        name = _str(e.get("channel") or e.get("uploader") or e.get("title"), 200)
        if not curl or not name:
            return None
        subs = _int(e.get("channel_follower_count"))
        return VideoItem("channel", cid, name, name, cid, curl, None, subs,
                         pick_thumbnail(e, thumb_w), curl)

    if isinstance(vid, str) and _VID_RE.match(vid):
        title = _str(e.get("title"), 200)
        if not title or title in ("[Private video]", "[Deleted video]"):
            return None
        channel = _str(e.get("channel") or e.get("uploader") or parent_channel, 200)
        return VideoItem("video", vid, title, channel, _str(e.get("channel_id"), 64),
                         _channel_url(_str(e.get("channel_url") or e.get("uploader_url"), 400)),
                         _int(e.get("duration")), _int(e.get("view_count")),
                         pick_thumbnail(e, thumb_w), f"https://www.youtube.com/watch?v={vid}")
    return None


def normalize_entries(entries, thumb_w: int, parent_channel: str = "") -> list[VideoItem]:
    out, seen = [], set()
    for e in entries or []:
        item = normalize_entry(e, thumb_w, parent_channel)
        if item and (item.kind, item.id) not in seen:
            seen.add((item.kind, item.id))
            out.append(item)
    return out


class _QuietLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _import_ytdlp():
    try:
        import yt_dlp  # noqa: WPS433 (lazy import is deliberate)
        return yt_dlp
    except ImportError as exc:
        raise YtLiteError("missing_dep", "The yt-dlp component is missing from this build. "
                          "Rebuild with build_windows.bat.", str(exc)) from exc


def ytdlp_version() -> str:
    try:
        import yt_dlp
        return yt_dlp.version.__version__
    except Exception:
        return "not installed"


class SearchService:
    def __init__(self, js_runtimes: Callable[[], dict | None] = lambda: None):
        # yt-dlp needs a JavaScript runtime (Deno) to read YouTube. We pass the bundled one.
        self._js_runtimes = js_runtimes

    def _opts(self, **extra) -> dict:
        opts = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "socket_timeout": SOCKET_TIMEOUT, "retries": 1, "extractor_retries": 1,
            "cachedir": False, "logger": _QuietLogger(), "noprogress": True,
            "no_color": True, "ignoreerrors": False, "color": {"stderr": "no_color", "stdout": "no_color"},
        }
        runtimes = self._js_runtimes()
        if runtimes:
            opts["js_runtimes"] = runtimes
        opts.update(extra)
        return opts

    def _extract(self, target: str, opts: dict) -> dict:
        yt_dlp = _import_ytdlp()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=False)
        except Exception as exc:
            logging.getLogger("ytlite").warning("yt-dlp failed for %s: %s", target[:80], exc)
            raise from_exception(exc) from exc
        if not isinstance(info, dict):
            raise YtLiteError("unavailable", "YouTube returned no data for this request.")
        return info

    def _paged(self, target_prefix: str, query: str, page: int, page_size: int,
               thumb_w: int) -> list[VideoItem]:
        start = (page - 1) * page_size + 1
        end = page * page_size
        opts = self._opts(extract_flat="in_playlist", playlist_items=f"{start}-{end}",
                          lazy_playlist=True)
        info = self._extract(f"{target_prefix}{end}:{query}", opts)
        entries = list(info.get("entries") or [])
        return normalize_entries(entries, thumb_w)[:page_size]

    # -- public API (blocking) ------------------------------------------------
    def search_videos(self, query: str, page: int, page_size: int, thumb_w: int) -> list[VideoItem]:
        query = query.strip()
        if not query:
            raise YtLiteError("input", "Type something to search for.")
        return self._paged("ytsearch", query, page, page_size, thumb_w)

    def search_channels(self, query: str, page: int, page_size: int, thumb_w: int) -> list[VideoItem]:
        query = query.strip()
        if not query:
            raise YtLiteError("input", "Type something to search for.")
        start = (page - 1) * page_size + 1
        end = page * page_size
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={CHANNEL_FILTER}"
        opts = self._opts(extract_flat="in_playlist", playlist_items=f"{start}-{end}",
                          lazy_playlist=True)
        info = self._extract(url, opts)
        items = [i for i in normalize_entries(info.get("entries"), thumb_w) if i.kind == "channel"]
        return items[:page_size]

    def channel_videos(self, channel_url: str, page: int, page_size: int, thumb_w: int) -> list[VideoItem]:
        if not _channel_url(channel_url):
            raise YtLiteError("input", "That is not a valid YouTube channel address.")
        start = (page - 1) * page_size + 1
        end = page * page_size
        opts = self._opts(extract_flat="in_playlist", playlist_items=f"{start}-{end}",
                          lazy_playlist=True)
        info = self._extract(channel_url.rstrip("/") + "/videos", opts)
        parent = _str(info.get("channel") or info.get("uploader") or info.get("title"), 200)
        return normalize_entries(info.get("entries"), thumb_w, parent)[:page_size]

    def extract_streams(self, video_id: str, codec_pref: str, audio_cap: int) -> "ExtractResult":
        if not _VID_RE.match(video_id or ""):
            raise YtLiteError("input", "Invalid video address.")
        opts = self._opts(noplaylist=True, ignore_no_formats_error=True)
        info = self._extract(f"https://www.youtube.com/watch?v={video_id}", opts)
        status = info.get("live_status")
        if status == "is_live" or info.get("is_live"):
            raise YtLiteError("live", "Live streams are not supported in this version. "
                              "Use Web Mode (opens your browser) instead.")
        if status == "is_upcoming":
            raise YtLiteError("live", "This video is a scheduled premiere/live event that "
                              "has not started yet.")
        raw_formats = [f for f in (info.get("formats") or []) if isinstance(f, dict)]
        options = fm.choose_options(raw_formats, codec_pref, audio_cap)
        if not options:
            if any(f.get("has_drm") for f in raw_formats):
                raise YtLiteError("drm", "This video is DRM-protected. YouTube Lite does not "
                                  "bypass DRM.")
            raise YtLiteError("format", "No playable stream was found for this video.")
        return ExtractResult(
            video_id=video_id, title=_str(info.get("title"), 200),
            channel=_str(info.get("channel") or info.get("uploader"), 200),
            duration=_int(info.get("duration")), views=_int(info.get("view_count")),
            upload_date=_str(info.get("upload_date"), 8),
            description=_str(info.get("description"), 700),
            options=options, fetched_at=time.time())


@dataclass
class ExtractResult:
    video_id: str
    title: str
    channel: str
    duration: int | None
    views: int | None
    upload_date: str
    description: str
    options: list
    fetched_at: float

    def fresh(self, max_age_s: int = 1800) -> bool:
        """Stream URLs expire after a few hours; reuse them only for a short time."""
        return time.time() - self.fetched_at < max_age_s

    def pretty_date(self) -> str:
        d = self.upload_date
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else ""
