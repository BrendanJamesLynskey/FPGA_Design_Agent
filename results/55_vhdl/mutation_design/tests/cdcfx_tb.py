"""cocotb test of one CDC fixture (flow/tests/fixtures/cdc_mutants/rtl): the fixture's own behaviour, as a design's own
bench would check it. $CDCFX_NAME is the fixture (and the top module). Each fixture has a kind: events (a toggle or pulse
crosses, one output pulse each), bus (a counter crosses and is sampled), handshake (words), fifo (words), smoke (reset
fixtures: only that the output resolves; their fault is structural). The checks are the design's functional ones and
are written without any knowledge of the injection: a correct crossing passes with and without it."""

from __future__ import annotations

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

NAME = os.environ.get("CDCFX_NAME", "")
KIND = {
    **{n: "events" for n in ("c1", "c2", "c3", "c4", "c5", "m1", "m1b", "m2", "m4", "m5", "m7")},
    **{n: "bus" for n in ("c6", "c7", "m3", "m6a")},
    **{n: "handshake" for n in ("c8", "c9")},
    **{n: "fifo" for n in ("c10", "c11")},
    **{n: "smoke" for n in ("c12", "m10", "m8")},
}[NAME.replace("cdcfx_", "")]
NO_EVENT_OUTPUT = {"cdcfx_m4"}        # the fixture's output is an error flag only


async def start(dut):
    cocotb.start_soon(Clock(dut.clk_a, 10, "ns").start())
    await Timer(3.1, "ns")                      # no coincident edges: 3.1 + 7k never equals 10m
    cocotb.start_soon(Clock(dut.clk_b, 7, "ns").start())


async def tick(clk, n=1):
    for _ in range(n):
        await RisingEdge(clk)
    await Timer(1, "ns")


@cocotb.test()
async def test_fixture(dut):
    rng = random.Random(int(os.environ.get("RANDOM_SEED", "1")))
    for sig in ("ev_in", "run", "send", "din", "winc", "wdata", "rinc", "rst", "rq_in", "d_in"):
        if hasattr(dut, sig):
            getattr(dut, sig).value = 0
    await start(dut)
    await globals()["_" + KIND](dut, rng)


async def _events(dut, rng):
    n = 150
    seen = {"ev": 0, "err": 0}
    dut.ev_in.value = 0

    async def watch():
        while True:
            await tick(dut.clk_b)
            seen["ev"] += int(dut.ev_out.value)
            seen["err"] += int(dut.err_out.value)
    cocotb.start_soon(watch())
    await tick(dut.clk_a, 20)
    for _ in range(n):
        dut.ev_in.value = 1
        await tick(dut.clk_a)
        dut.ev_in.value = 0
        await tick(dut.clk_a, rng.randint(8, 20))
    await tick(dut.clk_a, 20)
    assert seen["err"] == 0, f"error flag raised {seen['err']} time(s)"
    if NAME not in NO_EVENT_OUTPUT:
        assert seen["ev"] == n, f"{seen['ev']} output pulses for {n} events"


async def _bus(dut, rng):
    dut.run.value = 1
    prev, bad, steps = None, [], 0
    for _ in range(8000):
        await tick(dut.clk_b)
        v = int(dut.val_out.value)
        if prev is not None:
            d = (v - prev) & 0xFF
            steps += d
            if d > 1:
                bad.append((prev, v))
        prev = v
    assert steps > 100, f"the counter barely moved ({steps} steps)"
    assert not bad, f"{len(bad)} jumps of more than one count, first {bad[0]}"


async def _handshake(dut, rng):
    words = [rng.randrange(1 << 16) for _ in range(40)]
    got = []
    dut.send.value = 0
    dut.din.value = 0

    async def collect():
        while True:
            await tick(dut.clk_b)
            if int(dut.dvalid.value):
                got.append(int(dut.dout.value))
    cocotb.start_soon(collect())
    await tick(dut.clk_a, 10)
    for w in words:
        while int(dut.busy.value):
            await tick(dut.clk_a)
        dut.send.value = 1
        dut.din.value = w
        await tick(dut.clk_a)
        dut.send.value = 0
        await tick(dut.clk_a, rng.randint(1, 6))
    await tick(dut.clk_a, 60)
    assert got == words, f"received {len(got)} of {len(words)} words; first difference at {next((i for i,(a,b) in enumerate(zip(got, words)) if a != b), min(len(got), len(words)))}"


async def _fifo(dut, rng):
    words = [rng.randrange(1 << 16) for _ in range(200)]
    got = []
    dut.winc.value = 0
    dut.rinc.value = 0
    dut.wdata.value = 0
    if hasattr(dut, "rst"):
        dut.rst.value = 1
    await tick(dut.clk_a, 6)
    if hasattr(dut, "rst"):
        dut.rst.value = 0

    async def writer():
        i = 0
        while i < len(words):
            await tick(dut.clk_a)
            if int(dut.wfull.value) or rng.random() < 0.3:
                dut.winc.value = 0
                continue
            dut.winc.value = 1
            dut.wdata.value = words[i]
            i += 1
        await tick(dut.clk_a)
        dut.winc.value = 0

    async def reader():
        pend = False
        while True:
            await tick(dut.clk_b)
            if pend:
                got.append(int(dut.rdata.value))
            if not int(dut.rempty.value) and rng.random() < 0.6:
                dut.rinc.value = 1
                pend = True
            else:
                dut.rinc.value = 0
                pend = False
    cocotb.start_soon(reader())
    await writer()
    await tick(dut.clk_b, 200)
    assert got == words, f"read {len(got)} of {len(words)} words; first difference at {next((i for i,(a,b) in enumerate(zip(got, words)) if a != b), min(len(got), len(words)))}"


async def _smoke(dut, rng):
    dut.rq_in.value = 0
    if hasattr(dut, "d_in"):
        dut.d_in.value = 0
    await tick(dut.clk_b, 20)
    for _ in range(5):
        dut.rq_in.value = 1
        await tick(dut.clk_a, 3)
        dut.rq_in.value = 0
        await tick(dut.clk_a, 20)
    assert dut.q_out.value.is_resolvable
