"""cocotb bench for ip_lib/crc32_step (both variants, CRC32_IMPL from the environment): random operands against
model.py, a zlib check over whole buffers, the declared latency and II measured, and in_valid while busy ignored."""
from __future__ import annotations

import os
import random
import zlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

from ip_lib.crc32_step.model import crc32_word

IMPL = os.environ.get("CRC32_IMPL", "word")
LATENCY = {"word": 1, "byte": 4}[IMPL]
II = {"word": 1, "byte": 4}[IMPL]


async def boot(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.crc_in.value = 0
    dut.data_in.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0


async def op(dut, crc: int, word: int) -> tuple[int, int]:
    """Issue one operation; return (result, clocks from the issue to out_valid)."""
    dut.crc_in.value = crc
    dut.data_in.value = word
    dut.in_valid.value = 1
    await FallingEdge(dut.clk)
    dut.in_valid.value = 0
    n = 1
    while int(dut.out_valid.value) == 0:
        await FallingEdge(dut.clk)
        n += 1
        assert n < 20, "no out_valid"
    return int(dut.crc_out.value), n


@cocotb.test(timeout_time=1, timeout_unit="ms")
async def crc32_step_variant(dut):
    await boot(dut)
    rng = random.Random(64)
    # corner operands, then random ones
    cases = [(0, 0), (0xFFFFFFFF, 0), (0, 0xFFFFFFFF), (0xFFFFFFFF, 0xFFFFFFFF), (0x80000000, 1), (1, 0x80000000)]
    cases += [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(200)]
    for crc, w in cases:
        got, lat = await op(dut, crc, w)
        assert got == crc32_word(crc, w), f"{IMPL}: crc32_step({crc:#x}, {w:#x}) = {got:#x}, model {crc32_word(crc, w):#x}"
        assert lat == LATENCY, f"{IMPL}: latency {lat}, declared {LATENCY}"
    # whole buffers against zlib (the caller's initial and final inversion)
    for n in (4, 64, 1500 // 4 * 4):
        buf = bytes(rng.getrandbits(8) for _ in range(n))
        crc = 0xFFFFFFFF
        for i in range(0, n, 4):
            crc, _ = await op(dut, crc, int.from_bytes(buf[i:i + 4], "little"))
        assert crc ^ 0xFFFFFFFF == zlib.crc32(buf), f"{IMPL}: buffer of {n} bytes disagrees with zlib"


@cocotb.test(timeout_time=1, timeout_unit="ms")
async def crc32_step_throughput(dut):
    """Issue as fast as the declared II allows; every result arrives, in order, LATENCY clocks after its issue."""
    await boot(dut)
    rng = random.Random(7)
    ops = [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(40)]
    got = []

    async def collect():
        while len(got) < len(ops):
            await RisingEdge(dut.clk)
            if int(dut.out_valid.value):
                got.append(int(dut.crc_out.value))
    t = cocotb.start_soon(collect())
    for i, (c, w) in enumerate(ops):
        dut.crc_in.value, dut.data_in.value, dut.in_valid.value = c, w, 1
        await FallingEdge(dut.clk)
        dut.in_valid.value = 0
        for _ in range(II - 1):
            if IMPL == "byte":                      # offered while busy: must be ignored
                dut.crc_in.value, dut.data_in.value, dut.in_valid.value = 0xDEAD, 0xBEEF, 1
            await FallingEdge(dut.clk)
            dut.in_valid.value = 0
    for _ in range(LATENCY + 2):
        await FallingEdge(dut.clk)
    await t
    assert got == [crc32_word(c, w) for c, w in ops], f"{IMPL}: results at II {II} differ from the model"
