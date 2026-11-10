"""Friendly classification of yt-dlp / network / mpv failures."""
from __future__ import annotations

import re

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class YtLiteError(Exception):
    """An error whose message is safe and understandable to show to the user."""

    def __init__(self, kind: str, message: str, detail: str = ""):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail


# (kind, regex, user message). Order matters: specific rules first.
_RULES = [
    ("drm", r"\bdrm\b", "This video is DRM-protected. YouTube Lite does not bypass DRM."),
    ("private", r"private video|this video is private",
     "This video is private."),
    ("age", r"confirm your age|age[- ]restricted|inappropriate for some users",
     "This video is age-restricted. YouTube Lite does not sign in, so it cannot play it."),
    ("region", r"not available in your country|blocked (it )?in your country|"
              r"geo[- ]?restrict|not made this video available in your country",
     "This video is not available in your region."),
    ("members", r"members-only|join this channel|available to this channel's members|paid",
     "This video needs a membership or payment. YouTube Lite cannot play it."),
    ("live", r"live event will begin|premieres in|this live event|is upcoming",
     "This is a scheduled/live event that has not started or is not supported."),
    ("format", r"requested format is not available|no video formats found|no formats",
     "No playable stream was found for this video."),
    ("unavailable", r"video unavailable|this video is not available|has been removed|"
                    r"account associated with this video has been terminated|no longer available|"
                    r"been deleted",
     "This video is unavailable (removed, deleted, or blocked)."),
    ("bot", r"sign in to confirm|not a bot",
     "YouTube is asking this connection to prove it is not a bot. Try again later, "
     "use a different network, or update yt-dlp (see Troubleshooting)."),
    ("update", r"unable to extract|unsupported url|http error 40[03]|nsig|signature|"
               r"player response|precondition check failed|unexpected response|"
               r"javascript runtime|js runtime",
     "YouTube changed something and the bundled yt-dlp can no longer read this video. "
     "yt-dlp probably needs to be updated (see Troubleshooting)."),
    ("network", r"timed out|timeout|temporary failure in name resolution|getaddrinfo failed|"
                r"network is unreachable|connection (reset|refused|aborted)|no route to host|"
                r"unable to download|urlopen error|remote end closed|errno 11001|errno -3|"
                r"ssl:|certificate verify|name or service not known",
     "Network problem: could not reach YouTube. Check your internet connection and try again."),
]


def clean_message(text: str) -> str:
    text = _ANSI.sub("", str(text))
    text = re.sub(r"^\s*(ERROR|WARNING):\s*", "", text.strip())
    text = re.sub(r"^\[[^\]]+\]\s*[\w\-]{6,}:\s*", "", text)  # "[youtube] abc123: " prefix
    return text.strip()


def classify(raw: str) -> tuple[str, str]:
    """Return (kind, user_message) for a raw error string."""
    msg = clean_message(raw)
    low = msg.lower()
    for kind, pattern, friendly in _RULES:
        if re.search(pattern, low):
            return kind, friendly
    short = msg.splitlines()[0][:200] if msg else "Unknown error"
    return "unknown", f"Something went wrong: {short}"


def from_exception(exc: BaseException) -> YtLiteError:
    if isinstance(exc, YtLiteError):
        return exc
    raw = str(exc) or exc.__class__.__name__
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return YtLiteError("network", classify("timed out")[1], raw)
    if isinstance(exc, PermissionError):
        return YtLiteError("permission", "Permission denied while accessing a file.", raw)
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return YtLiteError("disk", "The disk is full.", raw)
    kind, friendly = classify(raw)
    return YtLiteError(kind, friendly, raw)
