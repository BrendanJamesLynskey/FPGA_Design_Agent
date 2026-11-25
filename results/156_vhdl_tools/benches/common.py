"""Shared pieces of the brief 156 cocotb benches (cocotb 2.0.1): clock and reset, the register-window bus, a per-clock trace.

The benches drive the inner VHDL entities of the brief 55 translations directly (no test shell: the shell is SystemVerilog and
neither GHDL nor NVC reads it). Window protocol, as the shell drives it (shell/PROTOCOL.md): win_wr / win_rd are one-cycle pulses
with win_addr and win_wdata; win_rdata is registered and valid in the cycle after win_rd.

Environment:
  BENCH_OPS  number of random operations (the workload size; 0 = only reset and one read, used to time the start-up)
  BENCH_SEED random seed (default 1)
  BENCH_TRACE_ALL  1 = trace from the first clock (the reset period too); default: from the end of reset
  BENCH_OUT  directory for <name>.trace.json (digest of the per-clock trace, count of clocks with a metavalue on an output)
"""
from __future__ import annotations

import hashlib
import json
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge


def ops() -> int:
    return int(os.environ.get("BENCH_OPS", "200"))


def rng() -> random.Random:
    return random.Random(int(os.environ.get("BENCH_SEED", "1")))


def sval(h) -> str:
    """A signal's value as a string of 0/1/U/X/Z/W/L/H/- characters, whatever the simulator calls it."""
    return str(h.value).upper()


def is01(h) -> bool:
    return set(sval(h)) <= {"0", "1"}


class Trace:
    """Samples the named signals once per rising clock edge (after the edge's updates, in the read-only phase)."""

    def __init__(self, name: str, clk, sigs: dict) -> None:
        self.name, self.clk, self.sigs = name, clk, sigs
        self.rows: list[str] = []
        self.meta = 0
        self.first_meta: str | None = None
        self.enabled = os.environ.get("BENCH_TRACE_ALL") == "1"      # 1: trace from the first clock, reset included
        self.task = cocotb.start_soon(self._run())

    async def _run(self) -> None:
        while True:
            await RisingEdge(self.clk)
            await ReadOnly()
            if not self.enabled:
                continue
            vals = [sval(h) for h in self.sigs.values()]
            self.rows.append(" ".join(vals))
            if any(not set(v) <= {"0", "1"} for v in vals):
                self.meta += 1
                if self.first_meta is None:
                    self.first_meta = f"clock {len(self.rows)}: " + " ".join(f"{k}={v}" for k, v in zip(self.sigs, vals))

    def finish(self) -> dict:
        d = {"name": self.name, "clocks": len(self.rows), "metavalue_clocks": self.meta, "first_metavalue": self.first_meta,
             "sha256": hashlib.sha256("\n".join(self.rows).encode()).hexdigest()}
        out = os.environ.get("BENCH_OUT")
        if out:
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, f"{self.name}.trace.json"), "w") as f:
                json.dump(d, f)
        return d


async def start_clock(dut, period_ns: int = 10) -> None:
    cocotb.start_soon(Clock(dut.clk, period_ns, unit="ns").start())


class Window:
    """The register window of a t1 design, driven straight onto the ports."""

    def __init__(self, dut) -> None:
        self.d = dut

    def idle(self) -> None:
        d = self.d
        d.win_wr.value = 0
        d.win_rd.value = 0
        d.win_addr.value = 0
        d.win_wdata.value = 0

    async def reset(self, cycles: int = 4) -> None:
        self.idle()
        self.d.rst.value = 1
        for _ in range(cycles):
            await RisingEdge(self.d.clk)
        self.d.rst.value = 0
        await RisingEdge(self.d.clk)

    async def write(self, addr: int, data: int) -> None:
        d = self.d
        d.win_addr.value, d.win_wdata.value, d.win_wr.value = addr, data & 0xFFFFFFFF, 1
        await RisingEdge(d.clk)
        d.win_wr.value = 0
        await RisingEdge(d.clk)

    async def read(self, addr: int) -> int:
        d = self.d
        d.win_addr.value, d.win_rd.value = addr, 1
        await RisingEdge(d.clk)
        d.win_rd.value = 0
        await RisingEdge(d.clk)
        await ReadOnly()
        v = d.win_rdata
        assert is01(v), f"read of window 0x{addr:02X} returned a metavalue: {sval(v)}"
        r = int(v.value)
        await cocotb.triggers.NextTimeStep()
        return r

    async def cycles(self, n: int) -> None:
        for _ in range(n):
            await RisingEdge(self.d.clk)
