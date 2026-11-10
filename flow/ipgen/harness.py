"""The xsim file-I/O harness (brief 19, section 1; specified in brief 13, built here).

Python writes the stimulus and a seeded valid/ready gap schedule to files; a generic SystemVerilog testbench
(`tb/tb_axis_io.sv.tmpl`) drives the IP's AXI-Stream ports from them under xsim and writes every accepted output beat
to a response file; Python reads it back and compares against the golden model. No LLM and no testbench written by the
agent judges anything: the comparison is word-for-word in `compare()`.

Also here: the Vivado batch runner (`run_vivado`) shared by every adapter. Heavy-slot handling is the caller's
(`_handoff/take_heavy_slot.sh`); the runner only wraps the job in a memory-capped systemd scope when one is available.
"""
from __future__ import annotations

import os
import random
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIVADO = os.environ.get("VIVADO", "/opt/Xilinx/2025.2/Vivado/bin/vivado")
TB_TEMPLATE = HERE / "tb" / "tb_axis_io.sv.tmpl"
TB_MEM_TEMPLATE = HERE / "tb" / "tb_mem_read.sv.tmpl"


def to_unsigned(v: int, width: int) -> int:
    return int(v) & ((1 << width) - 1)


def to_signed(v: int, width: int) -> int:
    v &= (1 << width) - 1
    return v - (1 << width) if v >> (width - 1) else v


def tdata_bits(width: int) -> int:
    """AXI-Stream tdata is a whole number of bytes: the IP pads a W-bit sample to ceil(W/8)*8 bits."""
    return (width + 7) // 8 * 8


def write_stimulus(path: Path, samples, width: int, tlast_at_end: bool = False) -> None:
    """One beat per line: `<tdata hex> <tlast>`; signed samples are stored two's complement in `tdata_bits(width)`."""
    w = tdata_bits(width)
    n = len(samples)
    with open(path, "w") as f:
        for i, s in enumerate(samples):
            f.write(f"{to_unsigned(int(s), w):0{w // 4}x} {1 if (tlast_at_end and i == n - 1) else 0}\n")


def schedule(kind: str, n: int = 4096, seed: int = 1, p_valid: float = 0.7, p_ready: float = 0.6):
    """The per-cycle `(valid-allowed, ready-allowed)` list. kind 'continuous' (all 1) or 'random' (seeded gaps)."""
    if kind == "continuous":
        return [(1, 1)] * n
    if kind != "random":
        raise ValueError(kind)
    r = random.Random(seed)
    return [(int(r.random() < p_valid), int(r.random() < p_ready)) for _ in range(n)]


def write_schedule(path: Path, sched) -> None:
    with open(path, "w") as f:
        for v, r in sched:
            f.write(f"{v} {r}\n")


def render_tb(path: Path, *, dut_inst: str, in_w: int, out_w: int, n_in: int, stim: Path, sched: Path, resp: Path,
              n_sched: int, out_bp: bool = True, period_ns: float = 10.0, drain_cycles: int = 3000,
              max_cycles: int = 4_000_000) -> None:
    """Fill the template. `dut_inst` is the adapter's instantiation of the IP using the template's fixed signal names
    (aclk, in_tdata/in_tvalid/in_tready/in_tlast, out_tdata/out_tvalid/out_tready/out_tlast)."""
    text = TB_TEMPLATE.read_text()
    rep = {"IN_W": in_w, "OUT_W": out_w, "N_IN": n_in, "DRAIN_CYCLES": drain_cycles, "MAX_CYCLES": max_cycles,
           "N_SCHED": n_sched, "OUT_BP": "1'b1" if out_bp else "1'b0", "STIM_FILE": str(Path(stim).resolve()), "SCHED_FILE": str(Path(sched).resolve()),
           "RESP_FILE": str(Path(resp).resolve()), "HALF_PERIOD_NS": period_ns / 2, "DUT_INST": dut_inst}
    for k, v in rep.items():
        text = text.replace(f"@{k}@", str(v))
    Path(path).write_text(text)


def render_tb_mem(path: Path, *, dut_inst: str, addr_w: int, data_w: int, n_addr: int, addr_file: Path, resp: Path,
                  period_ns: float = 10.0, tail: int = 16) -> None:
    """The memory-read testbench: `dut_inst` uses the fixed names clka, addra, douta."""
    text = TB_MEM_TEMPLATE.read_text()
    rep = {"ADDR_W": addr_w, "DATA_W": data_w, "N_ADDR": n_addr, "TAIL": tail, "ADDR_FILE": str(Path(addr_file).resolve()),
           "RESP_FILE": str(Path(resp).resolve()), "HALF_PERIOD_NS": period_ns / 2, "DUT_INST": dut_inst}
    for k, v in rep.items():
        text = text.replace(f"@{k}@", str(v))
    Path(path).write_text(text)


def read_mem_response(path: Path):
    """-> (addresses issued per cycle, data per cycle) from the memory testbench's response file."""
    addr, data = [], []
    for line in Path(path).read_text().splitlines():
        if line.startswith("#"):
            continue
        _, a, d = line.split()
        addr.append(int(a, 16))
        data.append(int(d, 16))
    return addr, data


def read_response(path: Path, out_w: int, signed: bool = True) -> dict:
    """Parse the response file. Returns {'cycles': [...], 'data': [...], 'tlast': [...], 'meta': {...}}."""
    cycles, data, last, meta = [], [], [], {}
    for line in Path(path).read_text().splitlines():
        if line.startswith("#"):
            _, k, v = line.split()
            meta[k] = int(v)
            continue
        c, d, t = line.split()
        v = int(d, 16)
        cycles.append(int(c))
        data.append(to_signed(v, out_w) if signed else v & ((1 << out_w) - 1))
        last.append(int(t))
    return {"cycles": cycles, "data": data, "tlast": last, "meta": meta}


def compare(got, expect, phases=(0,)) -> dict:
    """Word-for-word comparison of two integer sequences. For a decimator the first output's alignment to the input
    stream is the core's choice, so `phases` lists the offsets into `expect` to try; the first full match wins.
    Returns {'match': bool, 'phase': int|None, 'n_got', 'n_expect_used', 'first_mismatch': idx|None, 'max_abs_err'}."""
    got = list(got)
    best = None
    for ph in phases:
        exp = list(expect)[ph:ph + len(got)]
        n = min(len(got), len(exp))
        bad = [i for i in range(n) if got[i] != exp[i]]
        res = {"phase": ph, "n_got": len(got), "n_expect_used": len(exp),
               "first_mismatch": bad[0] if bad else None, "n_mismatch": len(bad) + abs(len(got) - len(exp)),
               "max_abs_err": max((abs(got[i] - exp[i]) for i in range(n)), default=0)}
        res["match"] = (not bad) and len(got) == len(exp) and len(got) > 0
        if res["match"]:
            return res
        if best is None or res["n_mismatch"] < best["n_mismatch"]:
            best = res
    return best


def run_vivado(tcl: Path, args: list[str], workdir: Path, log: str = "vivado.log", mem_max: str = "6G",
               timeout: int = 3600) -> subprocess.CompletedProcess:
    """Run a Vivado batch script the memory-safe way (systemd scope with MemoryMax, nice 15, one thread). The caller
    must already hold a heavy slot. Returns the CompletedProcess; the log is `<workdir>/<log>`."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [VIVADO, "-mode", "batch", "-source", str(tcl), "-nojournal", "-log", str(workdir / log), "-tclargs", *args]
    if shutil.which("systemd-run"):
        cmd = ["systemd-run", "--user", "--scope", "-q", "-p", f"MemoryMax={mem_max}", "nice", "-n", "15", *cmd]
    return subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout)


def log_errors(log: Path) -> list[str]:
    """The ERROR / CRITICAL WARNING lines of a Vivado log (for a plain failure message)."""
    if not Path(log).exists():
        return ["no log"]
    return [ln.strip() for ln in Path(log).read_text(errors="replace").splitlines()
            if re.match(r"^(ERROR|CRITICAL WARNING):", ln)]
