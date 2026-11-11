"""Simulator runner for the packet-processing library (brief 40), on the brief-19 harness method.

Python writes stimulus files, a file-driven SystemVerilog bench (`ip_lib/<block>/tb/`) drives the design and writes
every output beat to a response file, and Python compares bit-exact against the golden model (`flow/net/model.py`).
The bench never judges anything.

Simulators: Icarus Verilog 12 (default; also what CI runs) and Vivado xsim 2025.2 (`SIM=xsim`, local only, under a
heavy slot). Parameters are passed with `-P` (Icarus) or `-generic_top` (xsim); fault copies of the RTL come from
`flow/net/faults.py`.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IP = ROOT / "ip_lib"
BUILD = Path(os.environ.get("NET_BUILD", ROOT / "build" / "net")).resolve()
XILINX_BIN = Path(os.environ.get("XILINX_BIN", "/opt/Xilinx/2025.2/Vivado/bin"))


def sim_name() -> str:
    return os.environ.get("SIM", "icarus")


def rtl(block: str, rtl_dir: Path | None = None) -> list[Path]:
    """The block's RTL sources, in a stable order (leaf modules first by name is enough: no packages)."""
    # flow/net/faults.py points a block at a seeded-fault copy of its RTL through NET_RTL_<BLOCK>
    d = rtl_dir or Path(os.environ.get(f"NET_RTL_{block.upper()}", IP / block / "rtl"))
    return sorted(d.glob("*.sv"))


class SimError(RuntimeError):
    pass


def _key(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, Path):
            h.update(p.read_bytes())
        h.update(str(p).encode())
    return h.hexdigest()[:16]


def run(srcs: list[Path], top: str, plusargs: dict, params: dict | None = None, tag: str = "run",
        timeout: int = 1800) -> str:
    """Compile (cached on the source contents and parameters) and run. Returns the simulator's stdout.
    Raises SimError when the compile fails or the bench does not print TB_DONE."""
    params = params or {}
    sim = sim_name()
    key = _key(sim, top, sorted(params.items()), *srcs)
    wd = BUILD / f"{tag}_{key}"
    wd.mkdir(parents=True, exist_ok=True)
    pa = [f"+{k}={Path(v).resolve() if isinstance(v, Path) else v}" for k, v in plusargs.items()]
    if sim == "icarus":
        exe = wd / "sim.vvp"
        if not exe.exists():
            cmd = ["iverilog", "-g2012", "-o", str(exe), "-s", top]
            cmd += [f"-P{top}.{k}={v}" for k, v in params.items()]
            cmd += [str(s) for s in srcs]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=wd)
            if r.returncode != 0:
                raise SimError(f"iverilog failed:\n{r.stdout}\n{r.stderr}")
        r = subprocess.run(["vvp", "-n", str(exe), *pa], capture_output=True, text=True, cwd=wd, timeout=timeout)
    elif sim == "xsim":
        snap = f"s_{key}"
        if not (wd / "xsim.dir" / snap).exists():
            r = subprocess.run([str(XILINX_BIN / "xvlog"), "-sv", *[str(s) for s in srcs]], capture_output=True,
                               text=True, cwd=wd)
            if r.returncode != 0:
                raise SimError(f"xvlog failed:\n{r.stdout[-4000:]}")
            gen = []
            for k, v in params.items():
                gen += ["-generic_top", f"{k}={v}"]
            r = subprocess.run([str(XILINX_BIN / "xelab"), top, "-s", snap, "-timescale", "1ns/1ps", *gen],
                               capture_output=True, text=True, cwd=wd)
            if r.returncode != 0:
                raise SimError(f"xelab failed:\n{r.stdout[-4000:]}")
        targs = []
        for a in pa:
            targs += ["-testplusarg", a[1:]]
        r = subprocess.run([str(XILINX_BIN / "xsim"), snap, "-R", *targs], capture_output=True, text=True, cwd=wd,
                           timeout=timeout)
    else:
        raise ValueError(sim)
    out = r.stdout + r.stderr
    if "TB_DONE" not in out:
        raise SimError(f"bench did not finish ({sim}):\n{out[-4000:]}")
    return out


def elaborate_fails(srcs: list[Path], top: str, params: dict) -> tuple[bool, str]:
    """For the elaboration guards: True when compiling and starting the design with these parameters reports an
    $error (Icarus prints 'ERROR' from $error at time 0) or refuses to compile."""
    wd = BUILD / f"guard_{_key(top, sorted(params.items()), *srcs)}"
    wd.mkdir(parents=True, exist_ok=True)
    exe = wd / "g.vvp"
    cmd = ["iverilog", "-g2012", "-o", str(exe), "-s", top, *[f"-P{top}.{k}={v}" for k, v in params.items()],
           *[str(s) for s in srcs]]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=wd)
    if r.returncode != 0:
        return True, r.stderr
    r = subprocess.run(["vvp", "-n", str(exe)], capture_output=True, text=True, cwd=wd, timeout=60)
    out = r.stdout + r.stderr
    return ("ERROR" in out), out


def clean(tag: str) -> None:
    for d in BUILD.glob(f"{tag}_*"):
        shutil.rmtree(d, ignore_errors=True)
