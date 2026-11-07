"""Acceptance tests of c10_dds_sine against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board
from model import DATA, DESIGN_ID, FW, FWS, GO, N, PTR, STATUS, samples


def s12(v: int) -> int:
    return v - 4096 if v & 0x800 else v


async def record(b: Board, fw: int) -> list[int]:
    await b.write(FW, fw)
    await b.write(GO, 1)
    for _ in range(400):
        if await b.read(STATUS) & 1:
            break
    else:
        raise AssertionError("DONE never rose after GO")
    out: list[int] = []
    for _ in range(N // 2):
        v = await b.read(DATA)
        assert v & 0xF000F000 == 0, f"DATA {v:08X}: bits above the samples must read 0"
        out += [s12(v & 0xFFF), s12(v >> 16 & 0xFFF)]
    return out


def first_diff(got: list[int], want: list[int]) -> str:
    bad = [k for k, (g, w) in enumerate(zip(got, want)) if g != w]
    return f"{len(bad)} samples differ, first at {bad[0]}: RTL {got[bad[0]]}, expected {want[bad[0]]}" if bad else ""


@cocotb.test()
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    for off, want in ((FW, 0), (STATUS, 0), (PTR, 0), (DATA, 0)):
        await b.expect(off, want, f"reset value of {off:#x}")


@cocotb.test()
async def test_each_frequency_word_sample_for_sample(dut):
    """Six frequency words, each a fresh GO (the oscillator restarts at phase 0 every time)."""
    b = Board(dut, {})
    await b.start()
    for fw in FWS:
        got = await record(b, fw)
        d = first_diff(got, samples(fw))
        assert not d, f"fw {fw:#08x}: {d}"


@cocotb.test()
async def test_restart_and_pointer(dut):
    b = Board(dut, {})
    await b.start()
    fw = 0x0A3D71
    first = await record(b, fw)
    again = await record(b, fw)
    assert first == again == samples(fw), "a second GO with the same word must give the same 1200 samples"
    await b.write(PTR, 3)
    v = await b.read(DATA)
    assert (s12(v & 0xFFF), s12(v >> 16 & 0xFFF)) == tuple(samples(fw)[6:8]), "PTR write then DATA read"
    await b.expect(PTR, 4, "DATA read advances PTR")
    await b.reset()
    for off in (FW, STATUS, PTR, DATA):
        await b.expect(off, 0, f"{off:#x} after reset")
