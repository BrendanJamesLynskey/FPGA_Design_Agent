"""Acceptance tests of t2_i2c_cmd_master against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.lib.i2c_devices import Adt7420, FixedDevice, I2cBus
from model import (BUSY, CMD, DESIGN_ID, INFO, OP_READ, OP_START, OP_STOP, OP_WRITE, OWNED, RXDATA, STATUS, Model,
                   cmd_word)

ADDR = 0x4B


# v1.2: SCL high time is 2Q to 2Q + SYNC_SLACK clocks. The spec says wait until SCL is seen high through a two-flop
# synchroniser, then 2Q: 2-3 clocks of synchroniser plus 1-3 of state and registered-output latency; 8 allows for that.
SYNC_SLACK = 8


class Env:
    def __init__(self, dut, temp_q7: int = 0x0D87) -> None:
        self.b = Board(dut, {"dev_scl_pull": 0, "dev_sda_pull": 0})
        self.dut = dut
        self.q = self.b.param("QUARTER")
        self.temp = temp_q7

    async def start(self) -> None:
        await self.b.start()
        self.bus = I2cBus(self.dut, [Adt7420(self.temp), FixedDevice(0x1D)])
        self.m = Model([Adt7420(self.temp), FixedDevice(0x1D)], self.q)

    async def cmd(self, op: int, data: int = 0, rnack: int = 0, check: bool = True) -> None:
        w = cmd_word(op, data, rnack)
        await self.b.write(CMD, w)
        self.m.command(w)
        if check:
            await self.regs()

    async def regs(self) -> None:
        for off, name in ((STATUS, "STATUS"), (RXDATA, "RXDATA")):
            await self.b.expect(off, self.m.read(off), name)

    def check_bus(self) -> None:
        assert not self.bus.errors, self.bus.errors[:3]
        assert self.bus.log == self.m.log, f"bus {self.bus.log} != model {self.m.log}"

    async def reg_read(self, ptr: int, n: int, addr: int = ADDR) -> None:
        await self.cmd(OP_START)
        await self.cmd(OP_WRITE, addr << 1)
        await self.cmd(OP_WRITE, ptr)
        await self.cmd(OP_START)
        await self.cmd(OP_WRITE, addr << 1 | 1)
        for i in range(n):
            await self.cmd(OP_READ, rnack=int(i == n - 1))
        await self.cmd(OP_STOP)


@cocotb.test(timeout_time=1171060, timeout_unit="ns")
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.regs()
    for off in (CMD, INFO, 0x04, 0x7F):
        await e.b.expect(off, e.m.read(off), f"window 0x{off:02X}")
    assert int(dut.scl.value) == 1 and int(dut.sda.value) == 1, "bus not released after reset"
    e.check_bus()


@cocotb.test(timeout_time=1536840, timeout_unit="ns")
async def test_id_via_repeated_start(dut):
    """Trap: the pointer write must be followed by a repeated START, never a STOP: this ADT7420 loses its pointer on
    a STOP (a master that sends STOP before every START reads register 0x00 instead of the ID)."""
    e = Env(dut)
    await e.start()
    await e.reg_read(0x0B, 1)
    assert e.m.rxdata == 0xCB
    await e.b.expect(RXDATA, 0xCB, "ID register")
    e.check_bus()


@cocotb.test(timeout_time=2244040, timeout_unit="ns")
async def test_temperature_two_bytes(dut):
    e = Env(dut, temp_q7=-0x0123)
    await e.start()
    await e.reg_read(0x00, 2)
    await e.reg_read(0x02, 3)
    e.check_bus()


@cocotb.test(timeout_time=2317200, timeout_unit="ns")
async def test_write_then_read_back(dut):
    e = Env(dut)
    await e.start()
    await e.cmd(OP_START)
    await e.cmd(OP_WRITE, ADDR << 1)
    for b in (0x04, 0x1A, 0x80, 0x0C, 0x40):        # pointer T_HIGH, then T_HIGH and T_LOW, auto-increment
        await e.cmd(OP_WRITE, b)
    await e.cmd(OP_STOP)
    await e.reg_read(0x04, 4)
    e.check_bus()
    assert e.bus.devices[0].writes == [(0x04, 0x1A), (0x05, 0x80), (0x06, 0x0C), (0x07, 0x40)]


@cocotb.test(timeout_time=1512440, timeout_unit="ns")
async def test_nack_address(dut):
    e = Env(dut)
    await e.start()
    await e.cmd(OP_START)
    await e.cmd(OP_WRITE, 0x48 << 1)                # no device at 0x48
    await e.cmd(OP_WRITE, 0x00)                     # still NACK: nobody listening
    await e.cmd(OP_START)
    await e.cmd(OP_WRITE, 0x1D << 1 | 1)            # another device ACKs
    await e.cmd(OP_READ, rnack=1)
    await e.cmd(OP_STOP)
    e.check_bus()


@cocotb.test(timeout_time=1611200, timeout_unit="ns")
async def test_clock_stretching(dut):
    e = Env(dut)
    await e.start()
    await e.cmd(OP_START)
    await e.cmd(OP_WRITE, ADDR << 1)
    e.bus.stretch_next = 300                        # the sensor holds SCL low for 300 clocks once
    await e.cmd(OP_WRITE, 0x0B)
    await e.cmd(OP_START)
    await e.cmd(OP_WRITE, ADDR << 1 | 1)
    e.bus.stretch_next = 2500                       # longer than a shell access: commands meanwhile are ignored
    await e.b.write(CMD, cmd_word(OP_READ, rnack=1))
    e.m.command(cmd_word(OP_READ, rnack=1))
    await e.b.write(CMD, cmd_word(OP_STOP))         # ignored: busy
    await e.b.expect(STATUS, BUSY | OWNED, "STATUS while busy")
    await e.b.cycles(2500)
    await e.regs()
    await e.cmd(OP_STOP)
    e.check_bus()
    hi = 2 * e.q
    assert all(hi <= h <= hi + SYNC_SLACK for h in e.bus.high), f"SCL high times {sorted(set(e.bus.high))}, 2Q = {hi}"


@cocotb.test(timeout_time=1585600, timeout_unit="ns")
async def test_bit_timing(dut):
    e = Env(dut)
    await e.start()
    await e.reg_read(0x00, 2)
    e.check_bus()
    hi, lo = 2 * e.q, 2 * e.q
    assert e.bus.high and all(hi <= h <= hi + SYNC_SLACK for h in e.bus.high), f"SCL high {sorted(set(e.bus.high))}"
    inner = [t for t in e.bus.low if t < 100]            # lows inside a command (between commands SCL waits low)
    assert len(inner) >= 8 * 5 and all(lo <= t <= lo + 2 for t in inner), f"SCL low {sorted(set(e.bus.low))}"


@cocotb.test(timeout_time=1857840, timeout_unit="ns")
async def test_ignored_commands(dut):
    e = Env(dut)
    await e.start()
    for w in (cmd_word(OP_WRITE, 0x96), cmd_word(OP_READ), cmd_word(OP_STOP), 0, 5, 6, 7):
        await e.b.write(CMD, w)                     # free bus: nothing happens
        e.m.command(w)
        await e.regs()
    await e.b.cycles(200)
    e.check_bus()
    assert e.bus.log == []
    await e.cmd(OP_START)
    await e.b.write(CMD, 0x0005)                    # invalid OP on an owned bus
    await e.regs()
    await e.cmd(OP_STOP)
    await e.b.write(0x02, 0x55)                     # read-only registers
    await e.b.write(0x03, 0x55)
    await e.regs()
    await e.b.expect(INFO, e.q, "INFO")
    e.check_bus()


@cocotb.test(timeout_time=3487760, timeout_unit="ns")
async def test_random_transactions(dut):
    e = Env(dut, temp_q7=0x0B4F)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(5):
        r = rng.random()
        if r < 0.45:
            await e.reg_read(rng.choice([0x00, 0x02, 0x03, 0x04, 0x06, 0x0A, 0x0B]), rng.randrange(1, 4))
        elif r < 0.75:
            await e.cmd(OP_START)
            await e.cmd(OP_WRITE, ADDR << 1)
            ptr = rng.choice([0x04, 0x06, 0x08, 0x0A])
            await e.cmd(OP_WRITE, ptr)
            for _ in range(rng.randrange(1, 3)):
                await e.cmd(OP_WRITE, rng.randrange(256))
            await e.cmd(OP_STOP)
        else:
            await e.cmd(OP_START)
            await e.cmd(OP_WRITE, rng.choice([0x10, 0x48, 0x4A, 0x77]) << 1 | rng.randrange(2))
            await e.cmd(OP_STOP)
    e.check_bus()
