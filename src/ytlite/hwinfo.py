"""Hardware detection used by the Intel Celeron 847 compatibility profile.

Detection results are *hints*. Whether hardware decoding really works is only
known from mpv itself (hwdec-current) while a video plays.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ram_mb() -> int | None:
    try:
        if os.name == "nt":
            import ctypes

            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMSTAT()
            st.dwLength = ctypes.sizeof(MEMSTAT)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullTotalPhys // (1024 * 1024))
            return None
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, AttributeError):
        pass
    return None


def parse_gpu_json(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for g in data if isinstance(data, list) else []:
        if isinstance(g, dict) and g.get("Name"):
            out.append({"name": str(g["Name"]), "driver": str(g.get("DriverVersion") or "")})
    return out


def _gpus() -> list[dict]:
    if os.name != "nt":
        return []
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "Get-CimInstance Win32_VideoController | "
           "Select-Object Name,DriverVersion | ConvertTo-Json -Compress"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20,
                             creationflags=_NO_WINDOW, check=False)
        return parse_gpu_json(res.stdout)
    except (OSError, subprocess.SubprocessError):
        return []


def cpu_name() -> str:
    name = os.environ.get("PROCESSOR_IDENTIFIER") or platform.processor() or "unknown CPU"
    if os.name != "nt":
        try:
            with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return name


def guess_generation(cpu: str) -> dict:
    """Very coarse generation guess from the CPU name (hint only)."""
    low = cpu.lower()
    m = re.search(r"celeron[^0-9]*(\d{3,4})[a-z]*", low)
    if m:
        n = int(m.group(1))
        if 800 <= n < 1000:
            return {"generation": "Sandy Bridge (2011) - Intel HD Graphics",
                    "expected_hw": ["H.264", "MPEG-2", "VC-1"],
                    "no_hw": ["VP9", "AV1", "HEVC"]}
        if 1000 <= n < 1100:
            return {"generation": "Ivy Bridge (2012) - Intel HD Graphics",
                    "expected_hw": ["H.264", "MPEG-2", "VC-1"],
                    "no_hw": ["VP9", "AV1", "HEVC"]}
    m = re.search(r"i[3579]-(\d)\d{3}[a-z]*\b", low)
    if m:
        gen = int(m.group(1))
        if gen == 2:
            return {"generation": "Sandy Bridge (2011)", "expected_hw": ["H.264", "MPEG-2", "VC-1"],
                    "no_hw": ["VP9", "AV1", "HEVC"]}
        if gen == 3:
            return {"generation": "Ivy Bridge (2012)", "expected_hw": ["H.264", "MPEG-2", "VC-1"],
                    "no_hw": ["VP9", "AV1", "HEVC"]}
    return {"generation": "unknown", "expected_hw": [], "no_hw": []}


def detect_system() -> dict:
    cpu = cpu_name()
    gen = guess_generation(cpu)
    gpus = _gpus()
    return {"cpu": cpu, "cores": os.cpu_count(), "ram_mb": _ram_mb(),
            "os": f"{platform.system()} {platform.release()}",
            "machine_64bit": platform.machine().lower() in ("amd64", "x86_64", "arm64"),
            "python_64bit": platform.architecture()[0] == "64bit",
            "gpus": gpus, "generation": gen}


def describe(info: dict) -> str:
    gen = info["generation"]
    lines = [f"CPU: {info['cpu']} ({info['cores']} logical cores)",
             f"RAM: {info['ram_mb']} MB" if info["ram_mb"] else "RAM: unknown",
             f"OS: {info['os']}"]
    if info["gpus"]:
        for g in info["gpus"]:
            lines.append(f"GPU: {g['name']} (driver {g['driver'] or 'unknown'})")
    else:
        lines.append("GPU: not detected (PowerShell query unavailable or not Windows)")
    lines.append(f"Generation guess: {gen['generation']}")
    if gen["expected_hw"]:
        lines.append("Hardware decode expected for: " + ", ".join(gen["expected_hw"])
                     + " (a hint from the CPU generation, NOT verified)")
        lines.append("No hardware decode expected for: " + ", ".join(gen["no_hw"])
                     + " - these use the CPU")
    lines.append("The real decoding mode is shown on the player page while a video plays.")
    return "\n".join(lines)
