"""Acceptance tests of p_hdlc_tx against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor
from model import CTRL, DATA, DESIGN_ID, FCS, STATUS, Model, waveform


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        self.m = Model()
        self.bit = self.b.param("BIT_CYCLES")

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, line=lambda: int(self.dut.JC1.value), led=lambda: int(self.dut.LED.value))

    async def load(self, payload: bytes) -> None:
        for v in payload:
            await self.b.write(DATA, v)
            self.m.write(DATA, v)

    async def send(self) -> None:
        mark = self.mon.mark()
        await self.b.write(CTRL, 1)
        self.m.write(CTRL, 1)
        want = waveform(self.m.sent, self.bit)
        await self.b.cycles(len(want) + 400)
        self.m.finish()
        seq = self.mon.since("line", mark)
        start = next((i for i, v in enumerate(seq) if v == 0), None)
        assert start is not None, "no frame on JC1"
        got = seq[start: start + len(want)]
        assert got == want, f"payload {self.m.sent.hex()}: line differs from the frame at clock {next(i for i in range(len(want)) if got[i] != want[i])} of {len(want)}"
        assert all(seq[start + len(want):]) and all(seq[:start]), "line not idle high around the frame"

    async def check(self) -> None:
        for off, name in ((STATUS, "STATUS"), (FCS, "FCS")):
            await self.b.expect(off, self.m.read(off), name)


@cocotb.test()
async def test_identity_and_idle_high(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.cycles(30)
    assert all(e.mon.v["line"]), "the line must rest high"
    await e.check()
    await e.b.write(CTRL, 1)                     # empty buffer: nothing happens
    await e.b.cycles(30)
    assert all(e.mon.v["line"])


@cocotb.test()
async def test_plain_frame_and_fcs(dut):
    e = Env(dut)
    await e.start()
    await e.load(b"12345678")
    await e.send()
    await e.check()
    await e.b.write(CTRL, 2)
    e.m.write(CTRL, 2)
    await e.load(b"A")
    await e.send()
    await e.check()


@cocotb.test()
async def test_bit_stuffing_cases(dut):
    e = Env(dut)
    await e.start()
    for payload in (b"\xff\xff", b"\x7e", b"\xfb\xf8\x1f", b"\x1f\x3e\x7c"):
        await e.b.write(CTRL, 2)
        e.m.write(CTRL, 2)
        await e.load(payload)
        await e.send()
    await e.check()


@cocotb.test()
async def test_full_and_busy_buffer(dut):
    e = Env(dut)
    await e.start()
    await e.load(bytes(range(1, 10)))            # the ninth byte is dropped
    await e.check()
    mark = e.mon.mark()
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.b.write(DATA, 0x55)                 # busy: dropped
    e.m.write(DATA, 0x55)
    await e.b.write(CTRL, 1)                    # busy: ignored
    e.m.write(CTRL, 1)
    await e.b.expect(STATUS, e.m.read(STATUS), "STATUS while busy")
    want = waveform(e.m.sent, e.bit)
    await e.b.cycles(len(want) + 400)
    e.m.finish()
    seq = e.mon.since("line", mark)
    start = next(i for i, v in enumerate(seq) if v == 0)
    assert seq[start: start + len(want)] == want and all(seq[start + len(want):]), "a second frame or a disturbed frame"
    await e.check()
    assert e.m.dropped == 2


@cocotb.test()
async def test_random_payloads(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(3):
        await e.b.write(CTRL, 2)
        e.m.write(CTRL, 2)
        await e.load(bytes(rng.choice([0xFF, 0x7E, 0xF8, 0x1F, rng.randrange(256)]) for _ in range(rng.randrange(1, 6))))
        await e.send()
    await e.check()
