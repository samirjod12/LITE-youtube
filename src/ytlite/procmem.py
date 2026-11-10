"""Process memory measurement (stdlib only). Used by About page and tools/measure.py.

Reports what the OS says; nothing is estimated.
"""
from __future__ import annotations

import os


def _windows(pid: int) -> dict | None:
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    handle = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
            return None
        mb = 1024 * 1024
        return {"working_set_mb": pmc.WorkingSetSize / mb, "private_mb": pmc.PrivateUsage / mb,
                "peak_working_set_mb": pmc.PeakWorkingSetSize / mb}
    finally:
        k32.CloseHandle(handle)


def _linux(pid: int) -> dict | None:
    try:
        with open(f"/proc/{pid}/status", encoding="ascii", errors="replace") as fh:
            fields = {}
            for line in fh:
                key, _, rest = line.partition(":")
                if key in ("VmRSS", "VmHWM", "RssAnon"):
                    fields[key] = int(rest.split()[0]) / 1024.0
        return {"working_set_mb": fields.get("VmRSS", 0.0),
                "private_mb": fields.get("RssAnon", fields.get("VmRSS", 0.0)),
                "peak_working_set_mb": fields.get("VmHWM", 0.0)}
    except (OSError, ValueError):
        return None


def process_memory(pid: int | None = None) -> dict | None:
    """{'working_set_mb', 'private_mb', 'peak_working_set_mb'} or None if unavailable."""
    pid = pid or os.getpid()
    try:
        return _windows(pid) if os.name == "nt" else _linux(pid)
    except Exception:
        return None
