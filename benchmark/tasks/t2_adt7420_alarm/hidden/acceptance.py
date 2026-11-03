"""Acceptance tests of t2_adt7420_alarm against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from cocotb.utils import get_sim_time
from benchmark.lib.bench import Board, peek
from benchmark.lib.i2c_devices import Adt7420, I2cBus
from model import ALARM, BUSY, CTRL, DESIGN_ID, MAX, MIN, SAMPLES, STATUS, TEMP, THIGH, TLOW, Model

READING_LEN = 8                                   # log entries of one reading


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, {"dev_scl_pull": 0, "dev_sda_pull": 0, "TMP_INT": 1})
        self.dut, self.m = dut, Model()
        self.q = self.b.param("QUARTER")
        self.period = self.b.param("PERIOD_CYCLES")

    async def start(self, temp_q7: int = 0x0D87, present: bool = True) -> None:
        await self.b.start()
        self.dev = Adt7420(temp_q7, int_pin=self.dut.TMP_INT)
        self.bus = I2cBus(self.dut, [self.dev] if present else [])
        self.present = present
        self.pos = 0                               # log entries already checked
        self.done_at: list[int] = []               # clock at which each reading was seen complete

    def take(self, n: int) -> list[tuple]:
        seg = self.bus.log[self.pos:self.pos + n]
        self.pos += n
        return seg

    async def configure(self) -> None:
        await self.b.write(CTRL, 1)
        want = self.m.configure(self.present)
        await self.b.cycles(40 * 9 * (4 * self.q + 4))
        got = self.take(len(want))
        assert got == want, f"configure: bus {got} != model {want}"
        assert not self.bus.errors, self.bus.errors[:3]

    async def readings(self, n: int) -> None:
        """Wait for ``n`` more readings (each checked against the model as it ends)."""
        per = READING_LEN if self.present else 3
        for _ in range(n):
            while len(self.bus.log) < self.pos + per:
                await self.b.cycles(50)
            code = (self.dev.temp_q7 & 0xFFFF) if self.present else None
            want = self.m.reading(code)
            got = self.take(per)
            assert got == want, f"reading: bus {got} != model {want}"
            self.done_at.append(int(get_sim_time("ns")) // 10)
        assert not self.bus.errors, self.bus.errors[:3]

    async def regs(self, offs=(STATUS, TEMP, MAX, MIN, SAMPLES)) -> None:
        """Right after a reading: the registers (read before the next reading is due)."""
        for off in offs:
            got = await self.b.read(off)
            want = self.m.read(off)
            if off == STATUS:
                got &= ~BUSY
            assert got == want, f"window 0x{off:02X}: RTL 0x{got:08X}, model 0x{want:08X}"


@cocotb.test(timeout_time=1588660, timeout_unit="ns")
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in (CTRL, STATUS, THIGH, TLOW, TEMP, MAX, MIN, SAMPLES, 0x08, 0x7F):
        await e.b.expect(off, e.m.read(off), f"window 0x{off:02X}")
    await e.b.cycles(2 * e.period)
    assert e.bus.log == [], "I2C traffic before the configure command"


@cocotb.test(timeout_time=1388600, timeout_unit="ns")
async def test_configure_sequence(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(THIGH, 0x0F80)                # 31 C
    e.m.write(THIGH, 0x0F80)
    await e.b.write(TLOW, 0xFF00)                 # -2 C
    e.m.write(TLOW, 0xFF00)
    await e.configure()
    assert e.dev.regs[0x03] == 0x90 and (e.dev.regs[0x04], e.dev.regs[0x05]) == (0x0F, 0x80) \
        and (e.dev.regs[0x06], e.dev.regs[0x07]) == (0xFF, 0x00), "sensor registers after configure"
    await e.readings(1)
    await e.regs()


@cocotb.test(timeout_time=1610880, timeout_unit="ns")
async def test_full_16bit_resolution(dut):
    """Trap: the textbook reads the sensor in its power-on 13-bit mode; here CONFIG bit 7 selects 16 bits, so the
    three low bits of a reading are temperature (0x0D87 = 27.05 C), not the 13-bit mode's limit flags."""
    e = Env(dut)
    await e.start(temp_q7=0x0D87)
    await e.configure()
    await e.readings(1)
    await e.regs((TEMP,))
    e.dev.set_temp(-0x0123)                       # a negative reading with odd low bits
    await e.readings(1)
    await e.regs((TEMP,))
    await e.readings(1)
    await e.regs((TEMP, MAX, MIN))


@cocotb.test(timeout_time=2639440, timeout_unit="ns")
async def test_max_min_samples(dut):
    e = Env(dut)
    await e.start(temp_q7=0x0C00)
    await e.configure()
    for t in (0x0C00, 0x0C81, 0xFF7F, 0x0001, 0x8000, 0x7FFF, 0x0C00):
        e.dev.set_temp(t - 0x10000 if t & 0x8000 else t)
        await e.readings(1)
    gaps = [b - a for a, b in zip(e.done_at, e.done_at[1:])]
    assert all(abs(g - e.period) <= 60 for g in gaps), f"readings {gaps} clocks apart, PERIOD_CYCLES {e.period}"
    await e.regs()
    await e.configure()                           # restarts the statistics
    await e.readings(1)
    await e.regs()


@cocotb.test(timeout_time=1746300, timeout_unit="ns")
async def test_alarm_follows_int(dut):
    e = Env(dut)
    await e.start(temp_q7=25 * 128)
    await e.b.write(THIGH, 30 * 128)
    e.m.write(THIGH, 30 * 128)
    await e.configure()
    await e.readings(1)
    await e.regs((STATUS,))
    assert await peek(e.b.clk, dut.LED) == 0
    e.dev.set_temp(31 * 128)                      # above T_HIGH: the sensor pulls INT low
    e.m.alarm = True
    await e.b.cycles(10)
    assert int(dut.TMP_INT.value) == 0, "device model: INT should be active (low)"
    assert await peek(e.b.clk, dut.LED) == 1, "LED0 does not show the alarm"
    await e.readings(1)
    await e.regs((STATUS,))
    e.dev.set_temp(27 * 128)                      # still above T_HIGH - T_HYST (5 C): INT stays active
    await e.readings(1)
    await e.regs((STATUS,))
    e.dev.set_temp(24 * 128)                      # below T_HIGH - T_HYST: INT released
    e.m.alarm = False
    await e.b.cycles(10)
    assert await peek(e.b.clk, dut.LED) == 0
    await e.readings(1)
    await e.regs((STATUS,))


@cocotb.test(timeout_time=1468880, timeout_unit="ns")
async def test_missing_sensor_nack(dut):
    e = Env(dut)
    await e.start(present=False)
    await e.configure()
    await e.readings(2)
    await e.regs()


@cocotb.test(timeout_time=1505880, timeout_unit="ns")
async def test_clock_stretching(dut):
    e = Env(dut)
    await e.start()
    await e.configure()
    e.bus.stretch_next = 500
    await e.readings(1)
    e.bus.stretch_next = 300
    await e.readings(1)
    await e.regs()
    hi = 2 * e.q
    assert all(hi <= h <= hi + 4 for h in e.bus.high), f"SCL high times {sorted(set(e.bus.high))}, 2Q = {hi}"


@cocotb.test(timeout_time=2004240, timeout_unit="ns")
async def test_random_temperatures(dut):
    rng = random.Random(int(cocotb.RANDOM_SEED))
    e = Env(dut)
    await e.start(temp_q7=rng.randrange(-40 * 128, 125 * 128))
    v = rng.randrange(1 << 16)
    await e.b.write(TLOW, v)
    e.m.write(TLOW, v)
    await e.b.expect(TLOW, e.m.read(TLOW), "TLOW")
    await e.configure()
    for _ in range(5):
        e.dev.set_temp(rng.randrange(-40 * 128, 125 * 128))
        await e.readings(1)
    await e.regs((TEMP, MAX, MIN, SAMPLES))
