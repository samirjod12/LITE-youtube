"""Turn yt-dlp format lists into the quality options YouTube Lite offers.

Pure functions, no yt-dlp import: easy to test with fake data.

Numbers shown to the user are labelled by origin:
  * "reported"  = bitrate metadata supplied by YouTube/yt-dlp (NOT measured)
  * "measured"  = read from mpv while playing (see player.PlaybackHealth)
"""
from __future__ import annotations

from dataclasses import dataclass, field

STANDARD_HEIGHTS = (144, 240, 360, 480, 720, 1080)
_CODEC_ORDER = {"h264": 0, "vp9": 1, "hevc": 2, "vp8": 2, "av1": 3, "other": 4}
CODEC_LABEL = {"h264": "H.264", "vp9": "VP9", "av1": "AV1", "hevc": "HEVC",
               "vp8": "VP8", "other": "other", "none": "-"}


def codec_family(vcodec) -> str:
    v = str(vcodec or "").lower()
    if v in ("", "none"):
        return "none"
    if v.startswith(("avc1", "avc3", "h264")):
        return "h264"
    if v.startswith(("vp9", "vp09")):
        return "vp9"
    if v.startswith("vp8"):
        return "vp8"
    if v.startswith(("av01", "av1")):
        return "av1"
    if v.startswith(("hev1", "hvc1", "hevc", "h265")):
        return "hevc"
    return "other"


def _num(v):
    if isinstance(v, bool):
        return None
    try:
        n = float(v)
        return n if n == n and n >= 0 else None
    except (TypeError, ValueError):
        return None


def resolution_class(fmt: dict) -> int | None:
    """Map a format to one of STANDARD_HEIGHTS (portrait videos use the short side)."""
    h, w = _num(fmt.get("height")), _num(fmt.get("width"))
    if not h:
        return None
    res = min(h, w) if w and h > w else h
    best = None
    for std in STANDARD_HEIGHTS:
        if res >= std - 8:
            best = std
    return best if best and res <= best + 8 else None


@dataclass
class StreamOption:
    height: int
    width: int | None
    fps: float | None
    codec: str                      # family: h264 / vp9 / av1 / hevc ...
    codec_raw: str
    reported_kbps: float | None     # metadata from YouTube, NOT measured
    video_url: str
    video_id: str
    audio_url: str | None           # None = progressive stream (audio inside) or none found
    audio_id: str | None
    audio_codec: str | None
    audio_kbps: float | None
    headers: dict = field(default_factory=dict)
    note: str = ""

    @property
    def codec_label(self) -> str:
        return CODEC_LABEL.get(self.codec, self.codec)

    @property
    def fps_label(self) -> str:
        return f"{self.fps:g}" if self.fps else "?"

    @property
    def bitrate_label(self) -> str:
        if not self.reported_kbps:
            return "n/a"
        return f"~{self.reported_kbps:.0f} kbps (reported)"

    @property
    def title(self) -> str:
        label = {720: "720p HD", 1080: "1080p Full HD"}.get(self.height, f"{self.height}p")
        return label


def _usable_protocol(f: dict) -> bool:
    return str(f.get("protocol", "https")).lower() in ("https", "http")


def _video_key(f: dict, pref: str):
    fam = codec_family(f.get("vcodec"))
    order = _CODEC_ORDER.get(fam, 4) if pref == "h264" else 0
    fps = _num(f.get("fps")) or 0
    tbr = _num(f.get("tbr")) or _num(f.get("vbr")) or 0
    return (order, 1 if fps > 30 else 0, -tbr)


def choose_audio(formats: list[dict], cap_kbps: int = 130) -> dict | None:
    cands = [f for f in formats
             if f.get("url") and _usable_protocol(f) and not f.get("has_drm")
             and codec_family(f.get("vcodec")) == "none"
             and str(f.get("acodec") or "none").lower() != "none"]
    if not cands:
        return None

    def key(f):
        abr = _num(f.get("abr")) or _num(f.get("tbr")) or 0
        aac = 0 if str(f.get("acodec", "")).lower().startswith("mp4a") else 1
        lang_pref = -(_num(f.get("language_preference")) or 0)
        over = 1 if abr > cap_kbps else 0
        return (lang_pref, aac, over, -abr if not over else abr)

    return sorted(cands, key=key)[0]


def choose_options(formats: list[dict], codec_pref: str = "h264",
                   audio_cap_kbps: int = 130) -> list[StreamOption]:
    """Best stream per standard resolution, ascending by height."""
    audio = choose_audio(formats, audio_cap_kbps)
    by_height: dict[int, list[dict]] = {}
    for f in formats:
        if not f.get("url") or not _usable_protocol(f) or f.get("has_drm"):
            continue
        if f.get("ext") == "mhtml" or codec_family(f.get("vcodec")) == "none":
            continue
        cls = resolution_class(f)
        if cls:
            by_height.setdefault(cls, []).append(f)

    options: list[StreamOption] = []
    for height in sorted(by_height):
        best = sorted(by_height[height], key=lambda f: _video_key(f, codec_pref))[0]
        fam = codec_family(best.get("vcodec"))
        progressive = str(best.get("acodec") or "none").lower() != "none"
        note = ""
        if fam != "h264" and codec_pref == "h264":
            note = (f"No H.264 stream at {height}p. {CODEC_LABEL.get(fam, fam)} is "
                    "unlikely to be hardware-decoded on an Intel HD Graphics from 2011.")
        elif (_num(best.get("fps")) or 0) > 30:
            note = "High frame rate (>30 fps): heavier to decode."
        a_url = a_id = a_codec = None
        a_kbps = None
        if not progressive:
            if audio:
                a_url, a_id = audio["url"], str(audio.get("format_id", ""))
                a_codec = str(audio.get("acodec", "")) or None
                a_kbps = _num(audio.get("abr")) or _num(audio.get("tbr"))
            else:
                note = (note + " " if note else "") + "No separate audio stream was found."
        options.append(StreamOption(
            height=height,
            width=int(_num(best.get("width")) or 0) or None,
            fps=_num(best.get("fps")),
            codec=fam,
            codec_raw=str(best.get("vcodec", "")),
            reported_kbps=_num(best.get("tbr")) or _num(best.get("vbr")),
            video_url=best["url"],
            video_id=str(best.get("format_id", "")),
            audio_url=a_url, audio_id=a_id, audio_codec=a_codec, audio_kbps=a_kbps,
            headers=dict(best.get("http_headers") or {}),
            note=note.strip(),
        ))
    return options


def pick_default(options: list[StreamOption], wanted_height: int) -> StreamOption | None:
    """Highest option not above *wanted_height*; otherwise the lowest available."""
    if not options:
        return None
    ok = [o for o in options if o.height <= wanted_height]
    return max(ok, key=lambda o: o.height) if ok else min(options, key=lambda o: o.height)


def lower_height(height: int) -> int | None:
    lower = [h for h in STANDARD_HEIGHTS if h < height]
    return max(lower) if lower else None


def fmt_duration(sec) -> str:
    n = _num(sec)
    if n is None:
        return ""
    n = int(n)
    h, rem = divmod(n, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_views(n) -> str:
    v = _num(n)
    if v is None:
        return ""
    v = int(v)
    if v >= 1_000_000_000:
        return f"{v / 1e9:.1f}B views"
    if v >= 1_000_000:
        return f"{v / 1e6:.1f}M views"
    if v >= 1_000:
        return f"{v / 1e3:.1f}K views"
    return f"{v} views"
