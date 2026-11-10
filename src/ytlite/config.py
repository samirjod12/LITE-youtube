"""Settings (JSON) and the ECO / BALANCED / QUALITY performance profiles."""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path

QUALITY_CHOICES = (144, 240, 360, 480, 720, 1080)
HWDEC_CHOICES = ("auto", "auto-copy", "no")
CODEC_CHOICES = ("h264", "any")

DEFAULT_LIST_URL = ("https://pgl.yoyo.org/adservers/serverlist.php"
                    "?hostformat=nohtml&showintro=0&mimetype=plaintext")


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    description: str
    results: int            # results per page
    thumb_w: int
    thumb_h: int
    default_quality: int
    thumb_threads: int      # concurrent thumbnail downloads
    mem_thumbs: int         # decoded thumbnails kept in RAM beyond the visible page
    cache_mult: float       # multiplier on the user's disk-cache limits
    meta_ttl_s: int         # search-result cache lifetime
    rich_metadata: bool     # show description etc. after stream extraction
    smooth_thumbs: bool     # smooth (slower) thumbnail scaling
    poll_ms: int            # player status polling interval (only while playing)


PROFILES: dict[str, Profile] = {
    "eco": Profile("eco", "ECO",
                   "10 results/page, small thumbnails, minimal cache, 360p default. "
                   "Lowest memory and CPU use. Recommended for the Celeron 847.",
                   10, 168, 94, 360, 1, 0, 1.0, 600, False, False, 3000),
    "balanced": Profile("balanced", "BALANCED",
                        "15 results/page, normal thumbnails, moderate cache.",
                        15, 200, 112, 360, 2, 10, 1.5, 900, False, False, 2000),
    "quality": Profile("quality", "QUALITY",
                       "20 results/page, larger thumbnails, more cache, extra "
                       "metadata. Uses the most memory.",
                       20, 240, 135, 480, 3, 30, 2.0, 1800, True, True, 1500),
}

DEFAULTS: dict = {
    "schema": 1,
    "profile": "eco",
    "default_quality": 0,            # 0 = use the profile's default
    "auto_play": True,               # start mpv right after stream extraction
    "hwdec": "auto",                 # auto | auto-copy | no
    "codec_preference": "h264",      # h264 | any
    "audio_cap_kbps": 130,
    "speed": 1.0,
    "volume": 80,
    "fullscreen": False,
    "sw_assist": False,              # skip loop filter on non-ref frames (faster software decode)
    "decoder_threads": 2,            # 0 = mpv decides
    "save_search_history": True,
    "save_watch_history": True,
    "confirm_web_mode": True,
    "sidebar_collapsed": False,
    "show_duration": True,
    "show_views": True,
    "adblock": {
        "enabled": False,
        "list_url": DEFAULT_LIST_URL,
        "last_update": "",
    },
    "cache": {"thumb_mb": 30, "meta_mb": 5, "log_mb": 2},
}


def _merge(defaults: dict, loaded: dict) -> dict:
    """Overlay *loaded* on *defaults*, ignoring unknown keys and wrong types."""
    out = copy.deepcopy(defaults)
    if not isinstance(loaded, dict):
        return out
    for key, default in defaults.items():
        if key not in loaded:
            continue
        value = loaded[key]
        if isinstance(default, dict):
            out[key] = _merge(default, value)
        elif isinstance(default, bool):
            if isinstance(value, bool):
                out[key] = value
        elif isinstance(default, (int, float)):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out[key] = type(default)(value)
        elif isinstance(default, str):
            if isinstance(value, str):
                out[key] = value
    return out


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def validate(data: dict) -> dict:
    if data["profile"] not in PROFILES:
        data["profile"] = "eco"
    if data["default_quality"] not in (0, *QUALITY_CHOICES):
        data["default_quality"] = 0
    if data["hwdec"] not in HWDEC_CHOICES:
        data["hwdec"] = "auto"
    if data["codec_preference"] not in CODEC_CHOICES:
        data["codec_preference"] = "h264"
    data["audio_cap_kbps"] = _clamp(int(data["audio_cap_kbps"]), 48, 320)
    data["speed"] = round(_clamp(float(data["speed"]), 0.25, 2.0), 2)
    data["volume"] = _clamp(int(data["volume"]), 0, 100)
    data["decoder_threads"] = _clamp(int(data["decoder_threads"]), 0, 8)
    c = data["cache"]
    c["thumb_mb"] = _clamp(int(c["thumb_mb"]), 1, 500)
    c["meta_mb"] = _clamp(int(c["meta_mb"]), 1, 100)
    c["log_mb"] = _clamp(int(c["log_mb"]), 1, 20)
    return data


class Settings:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict = validate(copy.deepcopy(DEFAULTS))
        self.last_error: str = ""

    # -- persistence -------------------------------------------------------
    def load(self) -> None:
        try:
            raw = self.path.read_text(encoding="utf-8")
            self.data = validate(_merge(DEFAULTS, json.loads(raw)))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            self.last_error = f"Settings could not be read ({exc}); defaults are used."
            try:  # keep the broken file for inspection instead of overwriting it
                self.path.replace(self.path.with_suffix(".json.bad"))
            except OSError:
                pass

    def save(self) -> bool:
        tmp = self.path.with_suffix(".json.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(validate(self.data), indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
            self.last_error = ""
            return True
        except OSError as exc:
            self.last_error = f"Settings could not be saved ({exc}). Is the drive still connected?"
            return False

    def reset(self) -> None:
        self.data = validate(copy.deepcopy(DEFAULTS))

    # -- helpers -----------------------------------------------------------
    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    @property
    def profile(self) -> Profile:
        return PROFILES[self.data["profile"]]

    def effective_quality(self) -> int:
        q = self.data["default_quality"]
        return q if q else self.profile.default_quality

    def thumb_limit_bytes(self) -> int:
        return int(self.data["cache"]["thumb_mb"] * self.profile.cache_mult * 1024 * 1024)

    def meta_limit_bytes(self) -> int:
        return int(self.data["cache"]["meta_mb"] * self.profile.cache_mult * 1024 * 1024)

    def log_limit_bytes(self) -> int:
        return int(self.data["cache"]["log_mb"] * 1024 * 1024)

    def apply_celeron_847_preset(self) -> None:
        """Dedicated compatibility profile for Intel Celeron 847 / 2 GB / Intel HD."""
        d = self.data
        d["profile"] = "eco"
        d["default_quality"] = 360
        d["hwdec"] = "auto"
        d["codec_preference"] = "h264"
        d["audio_cap_kbps"] = 130
        d["decoder_threads"] = 2
        d["sw_assist"] = False
        d["auto_play"] = True
        validate(d)
