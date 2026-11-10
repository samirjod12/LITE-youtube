"""Player logic that does not need Qt: mpv command line, JSON-IPC protocol and
playback health assessment. The Qt process wrapper lives in gui/playback.py.

mpv always runs as a separate process. YouTube Lite hands it direct stream
URLs it extracted itself (video URL + --audio-file for DASH audio), so mpv does
not need its own yt-dlp.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .formats import StreamOption, lower_height

POLL_PROPERTIES = ("time-pos", "duration", "pause", "hwdec-current", "video-codec",
                   "frame-drop-count", "decoder-frame-drop-count", "video-bitrate",
                   "estimated-vf-fps", "paused-for-cache", "width", "height")


def ipc_endpoint(pid: int) -> tuple[str, str]:
    """(value for mpv --input-ipc-server, name for QLocalSocket.connectToServer)."""
    if os.name == "nt":
        name = f"ytlite-mpv-{pid}"
        return rf"\\.\pipe\{name}", name
    path = str(Path(tempfile.gettempdir()) / f"ytlite-mpv-{pid}.sock")
    return path, path


def safe_title(title: str) -> str:
    return re.sub(r"[\x00-\x1f]", " ", title)[:200] or "YouTube Lite"


def build_mpv_command(mpv_exe: Path, option: StreamOption, title: str, ipc_value: str, *,
                      conf_args: list[str], hwdec: str, speed: float, volume: int,
                      fullscreen: bool, decoder_threads: int, sw_assist: bool,
                      start_seconds: float = 0.0, supported: set[str] | None = None,
                      hwdecs: set[str] | None = None) -> list[str]:
    """Build the argv list (never a shell string; shell=True is never used)."""
    def ok(opt: str) -> bool:
        return supported is None or opt in supported

    cmd = [str(mpv_exe), "--no-config", "--no-terminal", "--msg-level=all=warn"]
    cmd += conf_args
    if hwdec in ("auto", "auto-copy") and (hwdecs is None or not hwdecs or hwdec in hwdecs):
        cmd.append(f"--hwdec={hwdec}")
    elif hwdec == "no":
        cmd.append("--hwdec=no")
    # else: requested mode unsupported by this mpv build -> leave mpv default, do not force
    cmd += [f"--input-ipc-server={ipc_value}", f"--force-media-title={safe_title(title)}",
            "--ytdl=no", "--force-window=yes", "--keep-open=no",
            "--save-position-on-quit=no", f"--volume={int(volume)}", f"--speed={speed:g}"]
    if fullscreen:
        cmd.append("--fullscreen")
    if decoder_threads and ok("vd-lavc-threads"):
        cmd.append(f"--vd-lavc-threads={int(decoder_threads)}")
    if sw_assist:
        if ok("vd-lavc-fast"):
            cmd.append("--vd-lavc-fast")
        if ok("vd-lavc-skiploopfilter"):
            cmd.append("--vd-lavc-skiploopfilter=nonref")
    ua = option.headers.get("User-Agent") if option.headers else None
    if ua and "\n" not in ua and "\r" not in ua:
        cmd.append(f"--user-agent={ua}")
    if start_seconds and start_seconds > 1:
        cmd.append(f"--start={int(start_seconds)}")
    if option.audio_url:
        cmd.append(f"--audio-file={option.audio_url}")
    cmd.append("--")           # everything after is a file/URL, never an option
    cmd.append(option.video_url)
    return cmd


# --- JSON IPC ------------------------------------------------------------------

class IpcProtocol:
    """Line-delimited JSON as spoken by mpv's --input-ipc-server."""

    def __init__(self):
        self._buf = b""
        self._next_id = 1

    def command(self, *args) -> tuple[int, bytes]:
        rid = self._next_id
        self._next_id += 1
        payload = {"command": list(args), "request_id": rid}
        return rid, (json.dumps(payload) + "\n").encode("utf-8")

    def feed(self, data: bytes) -> list[dict]:
        self._buf += data
        if len(self._buf) > 1_000_000:       # runaway garbage guard
            self._buf = b""
            return []
        *lines, self._buf = self._buf.split(b"\n")
        out = []
        for line in lines:
            if not line.strip():
                continue
            try:
                msg = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            if isinstance(msg, dict):
                out.append(msg)
        return out


# --- health --------------------------------------------------------------------

@dataclass
class HealthReport:
    decode: str = "unknown"          # "hardware (d3d11va)" / "software" / "unknown"
    hardware: bool | None = None
    dropped: int = 0
    drop_percent: float | None = None
    advice: str = ""


@dataclass
class PlaybackHealth:
    """Interprets mpv property samples. All values come from mpv itself."""
    height: int = 0
    _advised: set = field(default_factory=set)

    def assess(self, sample: dict) -> HealthReport:
        rep = HealthReport()
        pos = float(sample.get("time-pos") or 0)
        hw = sample.get("hwdec-current")
        if pos >= 2 and hw is not None:
            if hw in ("", "no"):
                rep.decode, rep.hardware = "software", False
            else:
                rep.decode, rep.hardware = f"hardware ({hw})", True
        dropped = int(sample.get("frame-drop-count") or 0) + int(sample.get("decoder-frame-drop-count") or 0)
        rep.dropped = dropped
        fps = float(sample.get("estimated-vf-fps") or 0) or 25.0
        frames = pos * fps
        if frames >= 250:
            rep.drop_percent = round(100.0 * dropped / frames, 1)
        lower = lower_height(self.height) if self.height else None
        lower_txt = f" Try {lower}p." if lower else ""

        if rep.drop_percent is not None and rep.drop_percent > 5 and "drops" not in self._advised:
            self._advised.add("drops")
            rep.advice = (f"{rep.drop_percent}% of frames were dropped (measured by mpv)."
                          f"{lower_txt}")
        elif rep.hardware is False and self.height >= 720 and "sw720" not in self._advised:
            self._advised.add("sw720")
            rep.advice = ("Hardware decoding is not active (measured: software). "
                          f"{self.height}p will likely stutter on this CPU.{lower_txt}")
        return rep


def exit_message(code: int, stderr_tail: str) -> str:
    tail = stderr_tail.strip()[-400:]
    base = {
        0: "Playback finished.",
        1: "mpv could not start (initialisation error). The video driver or an option may be unsupported.",
        2: "mpv could not play the stream. The link may have expired, been blocked, "
           "or use a format this mpv build cannot play.",
        3: "mpv could not play some of the files.",
        4: "mpv was closed.",
    }.get(code, f"mpv exited with code {code}.")
    return f"{base}\n{tail}" if tail and code not in (0, 4) else base
