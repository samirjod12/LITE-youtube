"""Sample the memory of a running process (and optionally its mpv) for the performance report.

  python tools/measure_memory.py --name YouTube-Lite.exe --seconds 60 --interval 2
  python tools/measure_memory.py --pid 1234 --seconds 30

Prints min / average / max working set and private bytes as reported by the OS.
Use --label to name the scenario (idle, searching, playing 720p ...).
Nothing here is estimated; paste the output into PERFORMANCE_REPORT.md.
"""
import argparse
import csv
import io
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ytlite.procmem import process_memory  # noqa: E402


def pids_by_name(name: str) -> list[int]:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, check=False).stdout
        pids = []
        for row in csv.reader(io.StringIO(out)):
            if len(row) > 1 and row[0].lower() == name.lower():
                pids.append(int(row[1]))
        return pids
    out = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True, check=False).stdout
    return [int(p) for p in out.split()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, action="append", default=[])
    ap.add_argument("--name", action="append", default=[], help="process image name, e.g. YouTube-Lite.exe or mpv.exe")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--interval", type=float, default=2)
    ap.add_argument("--label", default="sample")
    args = ap.parse_args()

    targets = list(args.pid)
    for n in args.name:
        targets += pids_by_name(n)
    if not targets:
        print("No matching process found.")
        return 1
    ws, priv = [], []
    end = time.time() + args.seconds
    while time.time() < end:
        tot_ws = tot_pr = 0.0
        for pid in targets:
            m = process_memory(pid)
            if m:
                tot_ws += m["working_set_mb"]
                tot_pr += m["private_mb"]
        ws.append(tot_ws)
        priv.append(tot_pr)
        time.sleep(args.interval)
    def stats(v):
        return f"min {min(v):.0f} / avg {sum(v) / len(v):.0f} / max {max(v):.0f} MB"
    print(f"[{args.label}] pids={targets} samples={len(ws)}")
    print(f"  working set : {stats(ws)}")
    print(f"  private     : {stats(priv)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
