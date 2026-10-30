"""Shared pieces of the hardware steps (F0B): the Vivado hardware-manager runner,
hw_server, the local board file, the USB power gate and serial redaction.

Vivado runs here with the same guard rails as flow/run_vivado.sh: one Vivado at a
time (``pgrep -x vivado``), a free-memory check, a transient ``systemd-run --user
--scope -p MemoryMax=6G`` under ``nice -n 15``, and ``general.maxThreads 1`` set by
every hardware Tcl script. The hardware manager needs far less memory than a build
(about 1.6 GB), so its free-memory floor is ``HW_MIN_AVAIL_GB`` (default 3).

The board file ``~/.config/fpga_design_agent/boards.yaml`` holds the cable serial
and the UART device of the owner's board. It lives outside the repo on purpose:
committed files only ever show a serial's last 4 characters (:func:`redact`).
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from flow import gates

ROOT = Path(__file__).resolve().parents[1]
VIVADO = os.environ.get("VIVADO", "/opt/Xilinx/2025.2/Vivado/bin/vivado")
HW_SERVER = os.environ.get("HW_SERVER", str(Path(VIVADO).with_name("hw_server")))
HW_PORT = 3121
MEM_MAX = os.environ.get("MEM_MAX", "6G")
HW_MIN_AVAIL_GB = float(os.environ.get("HW_MIN_AVAIL_GB", "3"))
BOARDS_FILE = Path(os.environ.get("FDA_BOARDS_FILE", Path.home() / ".config" / "fpga_design_agent" / "boards.yaml"))

# The owner's board is powered from its PROG/UART USB cable only (owner rule, 2026-10-30):
# a bitstream is programmed only if report_power's total on-chip power is at most this.
USB_POWER_LIMIT_W = 0.5


class HwError(Exception):
    """A hardware step refused to run or failed; the message says why."""


def redact(serial: str | None) -> str | None:
    """Only the last 4 characters of a serial ever reach a committed file."""
    if not serial:
        return serial
    return "..." + serial[-4:]


# --- guard rails ------------------------------------------------------------------

def preflight(min_avail_gb: float = HW_MIN_AVAIL_GB) -> int:
    running = subprocess.run(["pgrep", "-x", "vivado"], capture_output=True, text=True).stdout.split()
    if running:
        raise HwError(f"another Vivado is running (PIDs {','.join(running)}); one Vivado job at a time on this PC")
    avail_kb = next(int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines()
                    if l.startswith("MemAvailable:"))
    if avail_kb < min_avail_gb * 2**20:
        raise HwError(f"only {avail_kb // 1024} MiB available, need {min_avail_gb} GiB")
    return avail_kb // 1024


def vivado_cmd(tcl: Path, args: list[str], log: Path) -> list[str]:
    if not Path(VIVADO).is_file():
        raise HwError(f"Vivado not found at {VIVADO} (set VIVADO=...)")
    return ["systemd-run", "--user", "--scope", "--quiet", "-p", f"MemoryMax={MEM_MAX}",
            "nice", "-n", "15", VIVADO, "-mode", "batch", "-nojournal", "-log", str(log),
            "-source", str(tcl), "-tclargs", *args]


def run_vivado_tcl(tcl: Path, args: list[str], out_dir: Path, name: str, timeout_s: float = 900) -> str:
    """Run a hardware Tcl script in batch mode; return its stdout. Raises HwError on failure."""
    preflight()
    out_dir.mkdir(parents=True, exist_ok=True)
    log = out_dir / f"{name}.log"
    with open(out_dir / f"{name}.stdout.txt", "w") as so:
        r = subprocess.run(vivado_cmd(tcl, args, log), cwd=out_dir, stdout=so, stderr=subprocess.STDOUT,
                           timeout=timeout_s)
    text = (out_dir / f"{name}.stdout.txt").read_text(errors="replace")
    if r.returncode != 0:
        tail = "\n".join(l for l in text.splitlines() if "ERROR" in l or "program.tcl" in l)[-2000:]
        raise HwError(f"Vivado {tcl.name} failed (exit {r.returncode}); see {log}\n{tail}")
    return text


def vivado_version(text: str) -> str | None:
    for line in text.splitlines():
        if "Vivado v" in line:
            return line.split("Vivado v", 1)[1].split()[0]
    return None


# --- hw_server ----------------------------------------------------------------------

def _port_open(port: int = HW_PORT) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


class HwServer:
    """Use the running hw_server on localhost:3121, or start one and stop it on exit."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir
        self.proc: subprocess.Popen[bytes] | None = None
        self.started = False

    def __enter__(self) -> "HwServer":
        if _port_open():
            return self
        if not Path(HW_SERVER).is_file():
            raise HwError(f"hw_server not found at {HW_SERVER}")
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        log = open(self.log_dir / "hw_server.log", "wb") if self.log_dir else subprocess.DEVNULL
        self.proc = subprocess.Popen(["nice", "-n", "15", HW_SERVER, "-s", f"tcp::{HW_PORT}"],
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(60):
            if _port_open():
                self.started = True
                return self
            if self.proc.poll() is not None:
                break
            time.sleep(0.5)
        raise HwError("hw_server did not start (see hw_server.log)")

    def __exit__(self, *exc: object) -> None:
        # hw_server is a wrapper script that runs the real binary as a child, so stop
        # the whole process group, not just the wrapper
        if self.proc is not None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(10)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)


# --- board file ---------------------------------------------------------------------

def load_board(name: str | None = None) -> dict[str, Any]:
    if not BOARDS_FILE.is_file():
        raise HwError(f"no board file {BOARDS_FILE}: run flow/hw_discover.py first")
    boards = (yaml.safe_load(BOARDS_FILE.read_text()) or {}).get("boards", {})
    if name is None:
        if len(boards) != 1:
            raise HwError(f"{BOARDS_FILE} lists {len(boards)} boards; name one")
        name = next(iter(boards))
    if name not in boards:
        raise HwError(f"board {name} not in {BOARDS_FILE}")
    return {"name": name, **boards[name]}


def save_board(name: str, entry: dict[str, Any]) -> None:
    BOARDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = (yaml.safe_load(BOARDS_FILE.read_text()) or {}) if BOARDS_FILE.is_file() else {}
    data.setdefault("boards", {})[name] = entry
    BOARDS_FILE.write_text("# written by flow/hw_discover.py; local to this PC, never committed\n"
                           + yaml.safe_dump(data, sort_keys=False))


# --- power gate ---------------------------------------------------------------------

def power_ok_usb(build_dir: Path, limit_w: float = USB_POWER_LIMIT_W) -> dict[str, Any]:
    """The bitstream's report_power total on-chip power against the USB-power limit."""
    rpt = build_dir / "power.rpt"
    if not rpt.is_file():
        return {"pass": False, "limit_w": limit_w, "total_w": None, "why": f"no {rpt.name} in {build_dir}"}
    pw = gates.parse_report_power(rpt.read_text(errors="replace"))
    total = pw.get("total_w")
    ok = total is not None and total <= limit_w
    return {"pass": ok, "limit_w": limit_w, "total_w": total, "dynamic_w": pw.get("dynamic_w"),
            "static_w": pw.get("static_w"), "confidence": pw.get("confidence"),
            "why": "" if ok else f"report_power total {total} W is above the USB-power limit {limit_w} W"}


def git_commit() -> tuple[str, bool]:
    def g(*a: str) -> str:
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    return g("rev-parse", "HEAD"), bool(g("status", "--porcelain", "--untracked-files=no"))
