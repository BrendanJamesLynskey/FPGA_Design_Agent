"""Acceptance tests of p_sigma_delta_dac against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from benchmark.pool.poollib import Monitor
from model import DESIGN_ID, VALUE, Model

EN, INV = 0x8000, 1


def rotation_match(obs: list[int], pat: list[int]) -> bool:
    k = len(pat)
    first = obs[:k]
    return any(all(first[i] == pat[(i + r) % k] for i in range(k)) for r in range(k)) and all(obs[i] == obs[i % k] for i in range(len(obs)))


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, pwm=lambda: int(self.dut.AUD_PWM.value), sd=lambda: int(self.dut.AUD_SD.value))

    async def set_value(self, v: int) -> None:
        await self.b.write(VALUE, v)
        self.m.write(VALUE, v)

    async def window(self, n: int = 768) -> list[int]:
        mark = self.mon.mark()
        await self.b.cycles(n)
        return self.mon.since("pwm", mark)


@cocotb.test()
async def test_identity_and_off(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.set_value(77)
    seq = await e.window(300)
    assert not any(seq) and not any(e.mon.v["sd"]), "output while disabled"
    await e.b.expect(VALUE, 77, "VALUE")


@cocotb.test()
async def test_exact_density_and_pattern(dut):
    e = Env(dut)
    await e.start()
    dut.SW.value = EN
    await e.b.cycles(6)
    for v in (1, 64, 100, 128, 200, 255, 0, 33):
        await e.set_value(v)
        await e.b.cycles(300)
        seq = await e.window(768)
        for i in range(0, 768 - 256, 37):
            assert sum(seq[i:i + 256]) == v, f"VALUE {v}: {sum(seq[i:i + 256])} ones in 256 clocks"
        assert rotation_match(seq, e.m.pattern()), f"VALUE {v}: the stream is not the sigma-delta sequence"
    assert int(dut.AUD_SD.value) == 1


@cocotb.test()
async def test_invert_and_enable(dut):
    e = Env(dut)
    await e.start()
    await e.set_value(200)
    dut.SW.value = EN | INV
    await e.b.cycles(300)
    seq = await e.window(512)
    assert sum(seq[:256]) == 256 - 200 and rotation_match(seq, e.m.pattern(inv=1))
    dut.SW.value = 0
    await e.b.cycles(20)
    assert int(dut.AUD_PWM.value) == 0 and int(dut.AUD_SD.value) == 0
    led = await peek(e.b.clk, dut.LED)
    assert led == e.m.leds(False), f"LED {led:04X}"


@cocotb.test()
async def test_value_register_and_leds(dut):
    e = Env(dut)
    await e.start()
    dut.SW.value = EN
    await e.set_value(0x1AB)
    await e.b.expect(VALUE, 0xAB, "VALUE")
    led = await peek(e.b.clk, dut.LED)
    assert led == e.m.leds(True), f"LED {led:04X}"


@cocotb.test()
async def test_random_values(dut):
    e = Env(dut)
    await e.start()
    dut.SW.value = EN
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(5):
        v = rng.randrange(256)
        await e.set_value(v)
        await e.b.cycles(300)
        seq = await e.window(512)
        assert sum(seq[:256]) == v and rotation_match(seq, e.m.pattern()), f"VALUE {v}"
