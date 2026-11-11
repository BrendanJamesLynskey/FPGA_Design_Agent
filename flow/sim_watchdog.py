#!/usr/bin/env python3
"""Brief 42 H2: run a simulation command under a wall-clock limit and say WHERE it hung.

    python3 flow/sim_watchdog.py --limit 600 -- <argv>

The command runs in its own process group with its output passed through. cocotb writes ``build/**/sim.log`` (one line per
log record, led by the simulation time). While the command runs this watchdog samples the newest such log; when the limit
passes it kills the group and prints one line, ``FDA_HANG {json}``, naming the test that was running, the last simulation
time, whether simulation time was still advancing, and the log's tail; it then exits 124. Standard library only: it runs
inside the sandbox image, which mounts ``flow/`` read-only.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import signal
import subprocess
import sys
import time

_TIME = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)(fs|ps|ns|us|ms|s)\s+(?:DEBUG|INFO|WARNING|ERROR|CRITICAL)\b")
_RUNNING = re.compile(r"cocotb\.regression\s+running\s+(\S+)\s+\((\d+)/(\d+)\)")
_NS = {"fs": 1e-6, "ps": 1e-3, "ns": 1.0, "us": 1e3, "ms": 1e6, "s": 1e9}


def parse_sim_log(text: str) -> dict:
    """The running test (name, index, count), the last simulation time in ns, and the log's last lines."""
    test, last_ns = None, None
    for line in text.splitlines():
        m = _RUNNING.search(line)
        if m:
            test = {"name": m.group(1), "index": int(m.group(2)), "of": int(m.group(3))}
        t = _TIME.match(line)
        if t:
            last_ns = float(t.group(1)) * _NS[t.group(2)]
    return {"test": test, "sim_time_ns": last_ns, "tail": "\n".join(text.splitlines()[-12:])}


def newest_log(root: str) -> str | None:
    logs = glob.glob(os.path.join(root, "build", "**", "sim.log"), recursive=True)
    return max(logs, key=os.path.getmtime) if logs else None


def sample(root: str) -> dict:
    f = newest_log(root)
    if not f:
        return {"test": None, "sim_time_ns": None, "tail": "", "log": None}
    try:
        with open(f, errors="replace") as fh:
            return {**parse_sim_log(fh.read()), "log": f}
    except OSError:
        return {"test": None, "sim_time_ns": None, "tail": "", "log": f}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=float, required=True, help="wall-clock seconds")
    ap.add_argument("--heartbeat", type=float, default=5.0)
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if cmd and os.path.basename(cmd[0]).startswith("python"):
        cmd = [sys.executable, *cmd[1:]]               # the host's interpreter path means nothing inside the sandbox
    proc = subprocess.Popen(cmd, start_new_session=True)
    t0, history = time.monotonic(), []
    while True:
        try:
            return proc.wait(timeout=a.heartbeat)
        except subprocess.TimeoutExpired:
            pass
        now = time.monotonic() - t0
        history.append((now, sample(a.root).get("sim_time_ns")))
        if now >= a.limit:
            break
    snap = sample(a.root)
    cutoff = now - 30
    recent = [t for w, t in history if w >= cutoff and t is not None]
    advancing = len(set(recent)) > 1
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()
    print("FDA_HANG " + json.dumps({"limit_s": a.limit, "test": snap["test"], "sim_time_ns": snap["sim_time_ns"],
                                    "sim_time_advancing": advancing, "tail": snap["tail"]}), flush=True)
    return 124


if __name__ == "__main__":
    sys.exit(main())
