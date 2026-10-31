"""Shared pieces of the hardware steps (F0B): the Vivado hardware-manager runner,
hw_server, the local board file, the power gate (``power_ok``) and serial redaction.

Vivado runs here with the same guard rails as flow/run_vivado.sh: one Vivado at a
time (``pgrep -x vivado``), a free-memory check, a transient ``systemd-run --user
--scope -p MemoryMax=6G`` under ``nice -n 15``, and ``general.maxThreads 1`` set by
every hardware Tcl script. The hardware manager needs far less memory than a build
(about 1.6 GB), so its free-memory floor is ``HW_MIN_AVAIL_GB`` (default 3).

The board file ``~/.config/fpga_design_agent/boards.yaml`` holds the cable serial
and the UART device of the owner's board, and how the board is powered on this PC
(``power_source: usb | wall`` under the board's entry). It lives outside the repo on
purpose: committed files only ever show a serial's last 4 characters (:func:`redact`).
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

# Power gate limits by power source (house rules; boards/nexys_a7_100t/power_budget.md).
# usb: the board runs from its PROG/UART cable (owner rule 2026-10-30): 0.5 W on-chip.
# wall: 5 V / 3 A supply on J13, JP3 = WALL (owner, 2026-10-31): the INTERIM limit, 2.0 W
#   on-chip, until the owner accepts a final one (power_budget.md proposes it).
# Both: junction temperature at most 85 C (commercial grade), computed by report_power
# for the board's own thermal environment (still air, no heat sink; see flow/build.tcl).
POWER_LIMITS: dict[str, dict[str, float]] = {
    "usb": {"total_w": 0.5, "junction_c": 85.0},
    "wall": {"total_w": 2.0, "junction_c": 85.0},
}
# Per-rail current limits (A), both sources (power_budget.md section 4): 80 % of each on-board
# regulator less what the board's other loads on that rail may take. Sums of report_power supplies.
RAIL_LIMITS_A: dict[str, tuple[tuple[str, ...], float]] = {
    "vccint": (("vccint",), 2.4),                                       # IC22 ADP2118, 3 A
    "rail_1v8": (("vccaux", "vccadc", "vcco18", "vccaux_io"), 0.38),    # IC23 ADP2138, 0.8 A, DDR2 up to 0.26 A
    "vcco33": (("vcco33",), 1.9),                                       # IC17 ADP2118, 3 A, board up to 0.5 A
}
DEFAULT_POWER_SOURCE = "usb"       # used when the board file says nothing: the lower limit, so a mistake fails safe


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
    """Record a discovered board; keys discovery does not set (e.g. power_source) are kept."""
    BOARDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = (yaml.safe_load(BOARDS_FILE.read_text()) or {}) if BOARDS_FILE.is_file() else {}
    old = data.setdefault("boards", {}).get(name) or {}
    data["boards"][name] = {**entry, **{k: v for k, v in old.items() if k not in entry}}
    BOARDS_FILE.write_text("# written by flow/hw_discover.py; local to this PC, never committed\n"
                           + yaml.safe_dump(data, sort_keys=False))


# --- power gate ---------------------------------------------------------------------

def power_source(board: str | None = None) -> tuple[str, str]:
    """How the board is powered, from the local board file: (source, where that came from).

    Reads ``boards.<name>.power_source``. Missing file, board, key or an unknown value all give
    ``usb`` (the lower limit), so a mistake fails safe."""
    try:
        b = load_board(board)
    except HwError as e:
        return DEFAULT_POWER_SOURCE, f"default ({e})"
    src = b.get("power_source")
    if src is None:
        return DEFAULT_POWER_SOURCE, f"default (no power_source for {b['name']} in {BOARDS_FILE})"
    if src not in POWER_LIMITS:
        return DEFAULT_POWER_SOURCE, f"default (unknown power_source {src!r} for {b['name']})"
    return str(src), f"{BOARDS_FILE} boards.{b['name']}.power_source"


def power_ok(build_dir: Path, board: str | None = None, source: str | None = None) -> dict[str, Any]:
    """The power gate: the bitstream's report_power against the limits for the board's power source.

    Passes only if total on-chip power <= the source's limit, the junction temperature <= its limit,
    report_power computed that temperature for still air with no heat sink (the board's own
    environment; Vivado's default heat sink and 250 LFM airflow would understate it), and each
    rail's current is within RAIL_LIMITS_A."""
    origin = "argument"
    if source is None:
        source, origin = power_source(board)
    lim = POWER_LIMITS.get(source)
    if lim is None:
        source, origin, lim = DEFAULT_POWER_SOURCE, f"default (unknown source {source!r})", POWER_LIMITS[DEFAULT_POWER_SOURCE]
    res: dict[str, Any] = {"pass": False, "source": source, "source_from": origin, "limit_w": lim["total_w"],
                           "junction_limit_c": lim["junction_c"], "total_w": None, "junction_c": None}
    rpt = build_dir / "power.rpt"
    if not rpt.is_file():
        return {**res, "why": f"no {rpt.name} in {build_dir}"}
    text = rpt.read_text(errors="replace")
    pw = gates.parse_report_power(text)
    env = gates.parse_power_environment(text)
    sup = gates.parse_power_supplies(text)
    res.update({"total_w": pw.get("total_w"), "dynamic_w": pw.get("dynamic_w"), "static_w": pw.get("static_w"),
                "confidence": pw.get("confidence"), "junction_c": env["junction_c"],
                "environment": {k: env[k] for k in ("ambient_c", "airflow_lfm", "heatsink", "theta_ja_c_per_w",
                                                    "board", "board_layers")},
                "supplies_a": {k: v["total_a"] for k, v in sup.items() if v["total_a"] > 0}})
    why = []
    if res["total_w"] is None or res["total_w"] > lim["total_w"]:
        why.append(f"report_power total {res['total_w']} W is above the {source}-power limit {lim['total_w']} W")
    if env["airflow_lfm"] != 0 or env["heatsink"] != "none":
        why.append(f"junction temperature was computed for airflow {env['airflow_lfm']} LFM and heat sink "
                   f"{env['heatsink']}, not the board's still air without a heat sink (rebuild: flow/build.tcl "
                   "applies boards/<board>/board.yaml thermal)")
    if env["junction_c"] is None or env["junction_c"] > lim["junction_c"]:
        why.append(f"junction temperature {env['junction_c']} C is above {lim['junction_c']} C")
    rails = {}
    for rail, (supplies, limit_a) in RAIL_LIMITS_A.items():
        amps = round(sum(sup.get(s, {}).get("total_a", 0.0) for s in supplies), 4)
        rails[rail] = {"a": amps, "limit_a": limit_a}
        if amps > limit_a:
            why.append(f"{rail} current {amps} A is above {limit_a} A ({'+'.join(supplies)})")
    res["rails"] = rails
    res["pass"] = not why
    res["why"] = "; ".join(why)
    return res


def git_commit() -> tuple[str, bool]:
    def g(*a: str) -> str:
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    return g("rev-parse", "HEAD"), bool(g("status", "--porcelain", "--untracked-files=no"))
