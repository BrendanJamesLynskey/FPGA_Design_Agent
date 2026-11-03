"""Acceptance tests of p_morse_beacon against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor, runs
from model import CHAR, CTRL, DESIGN_ID, STATUS, Model, key_units


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.m = Model()
        self.u = self.b.param("UNIT_CYCLES")

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, key=lambda: int(self.dut.LED.value) & 1, busy=lambda: (int(self.dut.LED.value) >> 1) & 1,
                           ja=lambda: int(self.dut.JA1.value))

    async def load(self, text: str) -> None:
        for ch in text:
            await self.b.write(CHAR, ord(ch))
            self.m.write(CHAR, ord(ch))

    async def send(self, repeat_gaps: int = 0) -> list[tuple[int, int]]:
        """Start, wait for BUSY to drop, return the keying runs [(level, units)] seen after the start."""
        mark = self.mon.mark()
        await self.b.write(CTRL, 1)
        self.m.write(CTRL, 1)
        total = sum(n for _, n in key_units(self.m.text)) * self.u
        await self.b.cycles(total + 20 * self.u)
        self.m.finish()
        seq = self.mon.since("key", mark)
        r = [(v, n) for v, _, n in runs(seq)]
        while r and r[0][0] == 0:
            r.pop(0)
        while r and r[-1][0] == 0:
            r.pop()
        return r

    async def check_status(self) -> None:
        await self.b.expect(STATUS, self.m.read(STATUS), "STATUS")
        await self.b.expect(CHAR, self.m.read(CHAR), "LEN")


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_status()
    await e.b.write(CTRL, 1)                 # empty buffer: nothing starts
    await e.b.cycles(5 * e.u)
    assert not any(e.mon.v["key"]) and not any(e.mon.v["busy"])


@cocotb.test()
async def test_sos_exact_timing(dut):
    e = Env(dut)
    await e.start()
    await e.load("SOS")
    got = await e.send()
    want = [(v, n * e.u) for v, n in key_units("SOS")]
    assert got == want, f"keying {got}, want {want}"
    assert not (await e.b.read(STATUS)) & 1, "still busy"
    assert not any(e.mon.v["ja"][i] != e.mon.v["key"][i] for i in range(len(e.mon.t))), "JA1 differs from LED[0]"


@cocotb.test()
async def test_words_digits_and_case(dut):
    e = Env(dut)
    await e.start()
    await e.load("e 7t!")                    # '!' is ignored
    await e.check_status()
    got = await e.send()
    want = [(v, n * e.u) for v, n in key_units("E 7T")]
    assert got == want, f"keying {got}, want {want}"
    await e.b.write(CTRL, 2)
    e.m.write(CTRL, 2)
    await e.check_status()


@cocotb.test()
async def test_buffer_limit_and_busy_drop(dut):
    e = Env(dut)
    await e.start()
    await e.load("ABCDEFGHIJKLMNOPQRS")      # 16 fit, 3 dropped
    await e.check_status()
    assert e.m.dropped == 3
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.b.write(CHAR, ord("Z"))          # busy: dropped
    e.m.write(CHAR, ord("Z"))
    await e.b.write(CTRL, 2)                 # busy: clear ignored
    e.m.write(CTRL, 2)
    await e.b.expect(STATUS, e.m.read(STATUS), "STATUS while busy")
    total = sum(n for _, n in key_units(e.m.text)) * e.u
    await e.b.cycles(total + 20 * e.u)
    e.m.finish()
    await e.check_status()


@cocotb.test()
async def test_repeat_mode(dut):
    e = Env(dut)
    await e.start()
    await e.load("K")
    dut.SW.value = 1
    mark = e.mon.mark()
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    msg = sum(n for _, n in key_units("K"))
    await e.b.cycles((3 * msg + 2 * 14) * e.u)
    dut.SW.value = 0                         # repeating stops at the end of the current message
    await e.b.cycles((msg + 14 + 4) * e.u)
    seq = e.mon.since("key", mark)
    r = [(v, n) for v, _, n in runs(seq)]
    while r and r[0][0] == 0:
        r.pop(0)
    while r and r[-1][0] == 0:
        r.pop()
    one = [(v, n * e.u) for v, n in key_units("K")]
    gap = [(0, 14 * e.u)]
    ok = [k for k in range(2, 8) if r == (one + gap) * (k - 1) + one]
    assert ok, f"keying {r[:12]}: expected the message repeated with {14 * e.u}-clock gaps"
    assert not (await e.b.read(STATUS)) & 1
