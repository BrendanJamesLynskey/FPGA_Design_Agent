"""The cocotb stream driver shared by every function's bench (arith brief 139a).

Inputs of one vector are driven on the falling edge of clk; the outputs are read 1 ns after the rising edge that follows. A variant with L register
stages shows the result of the vector driven at clock t after the (L-1)th following edge (L = 0, the combinational case, and L = 1 are read at
the same point: the output is stable in that clock). So a result is compared ``max(L-1, 0)`` clocks after its vector. A model that already includes
the latency (the MAC's) is run with delay 0."""
from __future__ import annotations

import json
import os
from collections import deque
from typing import Callable, Iterable

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


class Cover:
    """Stimulus and result coverage: the bins of a coverage.yaml (expressions over v, r, p), counted over every vector driven. Cumulative over the streams of one run;
    the file named by ARITH_COVER_OUT is rewritten after each stream, so run_harness.py reads the total."""

    def __init__(self, path: str, out: str | None):
        import yaml
        self.bins = yaml.safe_load(open(path))["bins"]
        self.counts = {b["name"]: 0 for b in self.bins}
        self.out = out

    def hit(self, v: dict, r: dict, p: dict) -> None:
        for b in self.bins:
            try:
                if eval(b["expr"], {}, {"v": v, "r": r, "p": p}):
                    self.counts[b["name"]] += 1
            except KeyError:
                pass

    def dump(self) -> None:
        if self.out:
            json.dump({"bins": [{"name": b["name"], "min": b["min"], "min_if": b.get("min_if"), "hits": self.counts[b["name"]]} for b in self.bins]}, open(self.out, "w"), indent=1)


_COVER: Cover | None = None


def load_cover() -> Cover | None:
    global _COVER
    if _COVER is None and os.environ.get("ARITH_COVER_FILE"):
        _COVER = Cover(os.environ["ARITH_COVER_FILE"], os.environ.get("ARITH_COVER_OUT"))
    return _COVER


def env_params() -> dict:
    return json.loads(os.environ["ARITH_PARAMS"])


def env_latency() -> int:
    return int(os.environ["ARITH_LAT"])


async def start(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await Timer(1, unit="ns")


async def run_stream(dut, vectors: Iterable[dict], model_step: Callable[[dict], dict], delay: int, label: str, max_errors: int = 3) -> int:
    """Drive every vector, one per clock, and compare each model output with the DUT's. Returns the number of vectors checked."""
    pend: deque = deque()
    checked = errors = 0
    cover, prm = load_cover(), env_params()
    for v in vectors:
        await FallingEdge(dut.clk)
        for k, x in v.items():
            getattr(dut, k).value = x
        exp_now = model_step(v)
        pend.append((v, exp_now))
        if cover is not None:
            cover.hit(v, exp_now, prm)
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if len(pend) > delay:
            vv, exp = pend.popleft()
            for name, want in exp.items():
                sig = getattr(dut, name).value
                try:
                    got = int(sig)
                except ValueError:                  # an X or Z bit
                    got = None
                if got != want:
                    errors += 1
                    dut._log.error(f"{label}: {vv}: {name} = {got}, model says {want}")
            checked += 1
            if errors >= max_errors:
                break
    if cover is not None:
        cover.dump()
    try:                                   # the instance wrapped with the SystemVerilog checker (harness/chk_top.sv) has an error counter
        chk = int(dut.errors.value)
    except (AttributeError, ValueError):
        chk = 0
    assert chk == 0, f"{label}: the SystemVerilog checker counted {chk} mismatches"
    assert errors == 0, f"{label}: {errors} mismatches in {checked} vectors"
    return checked
