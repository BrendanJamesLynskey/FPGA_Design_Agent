"""Acceptance tests of p_adxl362_activity against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from cocotb.triggers import RisingEdge
from model import ACT_COUNT, ACT_THRESH, ACT_TIME, CTRL, DESIGN_ID, EXPECTED_WRITES, LAST_STATUS, LAST_X, STATE, Model, config_regs


class Adxl362:
    """The sensor: SPI mode 0 slave on the ACL pins, with INT1."""

    def __init__(self, dut) -> None:
        self.dut = dut
        self.reset_regs()
        self.t = 0
        self.writes: list[tuple[int, int, int]] = []        # (time, address, value)
        self.reads: list[tuple[int, int]] = []              # (time, address)
        self.resets = 0
        self.violations: list[str] = []
        self.sck_periods: set[int] = set()
        self.cs_fall: list[int] = []
        self.cs_rise: list[int] = []
        self.ignored_events = 0
        self.int1 = 0

    def reset_regs(self) -> None:
        self.regs = {0x00: 0xAD, 0x01: 0x1D, 0x02: 0xF2, 0x03: 0x01}
        self.act = False
        self.xdata = 0
        self.int1 = 0

    @property
    def configured(self) -> bool:
        return bool(self.regs.get(0x27, 0) & 1) and bool(self.regs.get(0x2A, 0) & 0x10) and (self.regs.get(0x2D, 0) & 3) == 2

    def event(self, x: int) -> None:
        if self.configured:
            self.act, self.xdata, self.int1 = True, x & 0xFFFF, 1
        else:
            self.ignored_events += 1

    def read_reg(self, a: int) -> int:
        self.reads.append((self.t, a))
        if a == 0x0B:
            v = 0x10 if self.act else 0
            self.act, self.int1 = False, 0                  # a status read clears the interrupt
            return v
        if a == 0x0E:
            return self.xdata & 0xFF
        if a == 0x0F:
            return (self.xdata >> 8) & 0xFF
        return self.regs.get(a, 0)

    def write_reg(self, a: int, v: int) -> None:
        self.writes.append((self.t, a, v))
        if a == 0x1F and v == 0x52:
            self.reset_regs()
            self.resets += 1
        else:
            self.regs[a] = v

    async def run(self) -> None:
        d = self.dut
        prev_cs, prev_sck = 1, 0
        nbits, byte, idx, cmd, addr = 0, 0, 0, 0, 0
        tx: list[int] = []
        last_rise = None
        d.ACL_MISO.value = 0
        d.ACL_INT1.value = 0
        while True:
            await RisingEdge(d.CLK100MHZ)
            self.t += 1
            cs, sck, mosi = int(d.ACL_CSN.value), int(d.ACL_SCLK.value), int(d.ACL_MOSI.value)
            d.ACL_INT1.value = self.int1
            if prev_cs and not cs:
                self.cs_fall.append(self.t)
                nbits, byte, idx, tx, last_rise = 0, 0, 0, [], None
            if cs and not prev_cs:
                self.cs_rise.append(self.t)
                if nbits % 8:
                    self.violations.append(f"transfer ended after {nbits} bits")
            if cs and sck:
                self.violations.append("SCLK high while ACL_CSN is high")
            if not cs:
                if sck and not prev_sck:
                    if last_rise is not None:
                        self.sck_periods.add(self.t - last_rise)
                    last_rise = self.t
                    byte = byte << 1 | mosi
                    nbits += 1
                    if nbits % 8 == 0:
                        if idx == 0:
                            cmd = byte
                            if cmd not in (0x0A, 0x0B):
                                self.violations.append(f"unknown command {cmd:#x}")
                        elif idx == 1:
                            addr = byte
                            if cmd == 0x0B:
                                tx = [(self.read_reg(addr) >> (7 - i)) & 1 for i in range(8)]
                        else:
                            if cmd == 0x0A:
                                self.write_reg(addr, byte)
                                addr += 1
                            else:
                                addr += 1
                                tx = [(self.read_reg(addr) >> (7 - i)) & 1 for i in range(8)]
                        idx += 1
                        byte = 0
                if not sck and prev_sck:
                    d.ACL_MISO.value = tx.pop(0) if tx else 0
            prev_cs, prev_sck = cs, sck


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"ACL_MISO": 0, "ACL_INT1": 0})
        p = self.b.param
        self.init_delay, self.reset_wait, self.half = p("INIT_DELAY"), p("RESET_WAIT"), p("SCLK_HALF")
        self.m = Model()
        self.s = Adxl362(dut)

    async def start(self) -> None:
        self.dut.ACL_INT1.value = 0
        await self.b.start()
        self.s.t = 0
        cocotb.start_soon(self.s.run())

    async def booted(self, extra: int = 0) -> None:
        await self.b.cycles(self.init_delay + self.reset_wait + 40 * 8 * 8 * self.half + 400 + extra)

    def check_boot(self, thresh: int = 250, time: int = 5) -> None:
        s = self.s
        assert s.violations == [], s.violations
        assert s.writes and s.writes[-1][1:] == (0x2D, 0x02), f"POWER_CTL must be the last write: {[(hex(a), hex(v)) for _, a, v in s.writes]}"
        assert s.writes[0][1:] == (0x1F, 0x52), "the soft reset must come first"
        assert {a for _, a, _ in s.writes} <= EXPECTED_WRITES, f"unexpected register writes: {[hex(a) for _, a, _ in s.writes]}"
        for a, v in config_regs(thresh, time).items():
            assert s.regs.get(a) == v, f"register {a:#04x} holds {s.regs.get(a)}, want {v:#x}"
        assert s.sck_periods == {2 * self.half}, f"SCLK periods {s.sck_periods}, want {2 * self.half}"

    async def event(self, x: int) -> None:
        n0 = len(self.s.reads)
        self.s.event(x)
        await self.b.cycles(40 * 8 * self.half + 300)
        self.m.event(x)
        first = [a for _, a in self.s.reads[n0:]]
        assert first and first[0] == 0x0B, f"the status register must be read first: {first}"
        assert set(first) <= {0x0B, 0x0E, 0x0F} and {0x0E} <= set(first) and 0x0F in first, f"registers read for an event: {first}"

    async def check(self) -> None:
        for off in (ACT_THRESH, ACT_TIME, ACT_COUNT, LAST_STATUS, LAST_X, STATE):
            await self.b.expect(off, self.m.read(off), f"register {off}")
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(False), f"LED {led:04X} != {self.m.leds(False):04X}"


@cocotb.test()
async def test_identity_and_boot_sequence(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.booted()
    e.check_boot()
    s = e.s
    assert abs(s.cs_fall[0] - e.init_delay) <= 60, f"first transfer {s.cs_fall[0]} clocks after reset, want about {e.init_delay}"
    gap = s.cs_fall[1] - s.cs_rise[0]
    assert e.reset_wait <= gap <= e.reset_wait + 40, f"{gap} clocks between the soft reset and the next transfer, want {e.reset_wait}"
    assert s.resets == 1
    await e.check()


@cocotb.test()
async def test_activity_events_are_serviced_once(dut):
    e = Env(dut)
    await e.start()
    await e.b.cycles(50)
    e.s.event(100)                                   # before the sensor is configured: the sensor ignores it
    assert e.s.ignored_events == 1
    await e.booted()
    await e.event(300)
    await e.event(-50)
    await e.event(-2048)
    await e.check()
    assert e.m.count == 3 and e.m.x == 0xF800
    assert int(dut.ACL_INT1.value) == 0 and e.s.int1 == 0


@cocotb.test()
async def test_reconfigure_with_new_values(dut):
    e = Env(dut)
    await e.start()
    await e.booted()
    await e.event(77)
    await e.b.write(ACT_THRESH, 0x2B7)
    e.m.write(ACT_THRESH, 0x2B7)
    await e.b.write(ACT_TIME, 9)
    e.m.write(ACT_TIME, 9)
    n0 = len(e.s.writes)
    await e.b.write(CTRL, 1)
    await e.b.cycles(e.reset_wait + 40 * 8 * 8 * e.half + 400)
    new = e.s.writes[n0:]
    assert new[0][1:] == (0x1F, 0x52) and new[-1][1:] == (0x2D, 0x02), "the set-up must restart with the soft reset"
    assert e.s.resets == 2
    e.check_boot(0x2B7, 9)
    await e.check()
    await e.event(5)
    await e.check()
    assert e.m.count == 2


@cocotb.test()
async def test_random_events(dut):
    e = Env(dut)
    await e.start()
    await e.booted()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(4):
        await e.event(rng.randrange(-2048, 2048))
    await e.check()
