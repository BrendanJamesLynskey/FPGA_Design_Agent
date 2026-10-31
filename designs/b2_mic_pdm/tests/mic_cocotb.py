"""cocotb tests of mic_regs (PDM clock + ones/changes counter) against a microphone model.

The model behaves as the SPK0833LM4H with SELECT low: it drives a new DATA bit a short time after
each falling clock edge (from a list of bits). The counts the design reports must equal the counts
of the bits the model sent in the window.
"""

from __future__ import annotations

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from shell.tests.window_bfm import WindowBfm

CTRL, STATUS, NBITS, ONES, CHANGES, INFO = range(6)


async def mic(dut, bits: list[int], sent: list[int]) -> None:
    i = 0
    while True:
        await FallingEdge(dut.mclk)
        await Timer(15, "ns")                       # data valid some time after the falling edge
        b = bits[i % len(bits)]
        dut.mdata.value = b
        sent.append(b)
        i += 1


async def setup(dut, bits: list[int]) -> tuple[WindowBfm, list[int]]:
    win = WindowBfm(dut, dut.clk)
    dut.mdata.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    dut.rst.value = 1
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    sent: list[int] = []
    cocotb.start_soon(mic(dut, bits, sent))
    return win, sent


@cocotb.test()
async def test_counts_match_the_bits_sent(dut) -> None:
    rng = random.Random(7)
    bits = [rng.randint(0, 1) for _ in range(5000)]
    win, sent = await setup(dut, bits)
    assert await win.read(NBITS) == 1_048_576
    await win.write(NBITS, 300)
    await ClockCycles(dut.clk, 50)
    n0 = len(sent)
    await win.write(CTRL, 1)
    await win.wait_done(STATUS)
    ones, changes = await win.read(ONES), await win.read(CHANGES)
    # the window is 300 consecutive bits that the model sent after GO; find them in `sent`
    hits = [k for k in range(n0, len(sent) - 299)
            if sum(sent[k:k + 300]) == ones
            and sum(a != b for a, b in zip(sent[k:k + 300], sent[k + 1:k + 300])) == changes]
    assert hits, f"ones {ones}, changes {changes} match no 300-bit window of the bits sent"
    assert 100 < ones < 200 and changes > 100


@cocotb.test()
async def test_stuck_line_counts(dut) -> None:
    win, _ = await setup(dut, [1])
    await win.write(NBITS, 64)
    await ClockCycles(dut.clk, 50)                  # let the model's first bit reach the line
    await win.write(CTRL, 1)
    await win.wait_done(STATUS)
    assert (await win.read(ONES), await win.read(CHANGES)) == (64, 0)
    assert await win.read(INFO) == int(dut.HALF.value)
