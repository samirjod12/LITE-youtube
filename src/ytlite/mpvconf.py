"""mpv.conf handling: ship the conservative defaults from the project brief and
validate every option against the *actual* mpv build (`mpv --list-options`),
so unsupported settings are never forced.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

DEFAULT_MPV_CONF = """\
# YouTube Lite - conservative mpv settings for an Intel Celeron 847 / 2 GB RAM.
# Every option is checked against your mpv build at launch; unsupported ones are skipped.
hwdec=auto

interpolation=no
deband=no
video-sync=audio
framedrop=vo

cache=yes
cache-secs=15
demuxer-max-bytes=48MiB
demuxer-max-back-bytes=16MiB

scale=bilinear
cscale=bilinear
dscale=bilinear

video-unscaled=no
"""

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_OPT_RE = re.compile(r"^\s*--([A-Za-z0-9\-]+)")


def parse_conf(text: str) -> list[tuple[str, str]]:
    """Parse key=value lines (comments and blank lines ignored)."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if re.fullmatch(r"[A-Za-z0-9\-]+", key):
            out.append((key, value.strip() if sep else "yes"))
    return out


def parse_list_options(output: str) -> set[str]:
    return {m.group(1) for line in output.splitlines() if (m := _OPT_RE.match(line))}


def parse_hwdec_list(output: str) -> set[str]:
    """Parse `mpv --hwdec=help` (lines such as '  d3d11va' or '  auto-copy')."""
    names = set()
    for line in output.splitlines():
        line = line.strip()
        if re.fullmatch(r"[a-z0-9\-]+", line):
            names.add(line)
    return names


def _run(cmd: list[str], timeout: float = 10.0) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                             creationflags=_NO_WINDOW, check=False, encoding="utf-8",
                             errors="replace")
        return (res.stdout or "") + (res.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return ""


class MpvInfo:
    """Capabilities of one mpv executable (queried once, cached)."""

    def __init__(self, exe: Path):
        self.exe = Path(exe)
        self._options: set[str] | None = None
        self._hwdecs: set[str] | None = None
        self._version: str | None = None

    @property
    def options(self) -> set[str]:
        if self._options is None:
            self._options = parse_list_options(_run([str(self.exe), "--no-config", "--list-options"]))
        return self._options

    @property
    def hwdecs(self) -> set[str]:
        if self._hwdecs is None:
            self._hwdecs = parse_hwdec_list(_run([str(self.exe), "--no-config", "--hwdec=help"]))
        return self._hwdecs

    @property
    def version(self) -> str:
        if self._version is None:
            out = _run([str(self.exe), "--no-config", "--version"])
            self._version = out.splitlines()[0].strip() if out.strip() else "unknown"
        return self._version


def ensure_conf(conf_path: Path) -> None:
    """Create mpv.conf with the default content if it does not exist."""
    try:
        if not conf_path.exists():
            conf_path.parent.mkdir(parents=True, exist_ok=True)
            conf_path.write_text(DEFAULT_MPV_CONF, encoding="utf-8")
    except OSError:
        pass


def conf_args(conf_path: Path, supported: set[str] | None,
              skip: set[str] = frozenset({"hwdec"})) -> tuple[list[str], list[str]]:
    """Return (cli_args, skipped_keys). *supported* None => options could not be listed,
    so nothing from the file is passed (mpv defaults are safer than guessing).
    Keys in *skip* are controlled by the GUI settings instead."""
    try:
        text = conf_path.read_text(encoding="utf-8")
    except OSError:
        text = DEFAULT_MPV_CONF
    args, skipped = [], []
    for key, value in parse_conf(text):
        if key in skip:
            continue
        if supported is None or key not in supported:
            skipped.append(key)
            continue
        args.append(f"--{key}={value}")
    return args, skipped
