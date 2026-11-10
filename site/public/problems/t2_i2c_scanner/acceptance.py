"""Acceptance tests of t2_i2c_scanner against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from benchmark.lib.i2c_devices import Adt7420, FixedDevice, I2cBus
from model import BUSY, COUNT, CTRL, DESIGN_ID, LOWEST, MAP0, STATUS, Model

REGS = ((STATUS, "STATUS"), (COUNT, "COUNT"), (LOWEST, "LOWEST"), (MAP0, "MAP0"), (MAP0 + 1, "MAP1"),
        (MAP0 + 2, "MAP2"), (MAP0 + 3, "MAP3"))


# v1.2: SCL high time is 2Q to 2Q + SYNC_SLACK clocks. The spec says wait until SCL is seen high through a two-flop
# synchroniser, then 2Q: 2-3 clocks of synchroniser plus 1-3 of state and registered-output latency; 8 allows for that.
SYNC_SLACK = 8


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, {"dev_scl_pull": 0, "dev_sda_pull": 0})
        self.dut, self.m = dut, Model()
        self.q = self.b.param("QUARTER")

    async def start(self, addrs: set[int]) -> None:
        await self.b.start()
        self.bus = I2cBus(self.dut, self.devices(addrs))

    @staticmethod
    def devices(addrs: set[int]) -> list:
        return [Adt7420() if a == 0x4B else FixedDevice(a) for a in sorted(addrs)]

    async def regs(self) -> None:
        for off, name in REGS:
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:#x} != model {self.m.leds():#x}"

    async def scan(self, addrs: set[int]) -> None:
        self.bus.clear()
        self.bus.addr_probes.clear()
        await self.b.write(CTRL, 1)
        want = self.m.scan({a for a in addrs if 0x08 <= a <= 0x77})
        for _ in range(200):
            await self.b.cycles(2000)
            if not (await self.b.read(STATUS)) & BUSY:
                break
        assert not self.bus.errors, self.bus.errors[:3]
        assert self.bus.addr_probes == list(range(0x08, 0x78)), f"probed {[hex(a) for a in self.bus.addr_probes][:12]}..."
        assert self.bus.log == want, "bus log differs from the model (first difference at entry " \
            f"{next((i for i, (x, y) in enumerate(zip(self.bus.log, want)) if x != y), min(len(self.bus.log), len(want)))})"
        await self.regs()


@cocotb.test(timeout_time=1268680, timeout_unit="ns")
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start(set())
    assert await e.b.shell_id() == DESIGN_ID
    await e.regs()
    for off in (CTRL, 0x08, 0x7F):
        await e.b.expect(off, 0, "unmapped / write-only")
    assert int(dut.scl.value) == 1 and int(dut.sda.value) == 1, "bus not released after reset"


@cocotb.test(timeout_time=1581910, timeout_unit="ns")
async def test_scan_finds_devices(dut):
    present = {0x03, 0x08, 0x1D, 0x4B, 0x77, 0x7A}       # 0x03 and 0x7A are reserved: never probed
    e = Env(dut)
    await e.start(present)
    await e.scan(present)
    assert e.bus.devices[3].writes == [], "a data byte reached the ADT7420"


@cocotb.test(timeout_time=1581890, timeout_unit="ns")
async def test_empty_bus(dut):
    e = Env(dut)
    await e.start(set())
    await e.scan(set())


@cocotb.test(timeout_time=2333010, timeout_unit="ns")
async def test_rescan_clears_and_busy(dut):
    e = Env(dut)
    await e.start({0x20, 0x21, 0x5F})
    await e.scan({0x20, 0x21, 0x5F})
    e.bus.devices = Env.devices({0x4B, 0x60})
    e.bus.clear()
    e.bus.addr_probes.clear()
    await e.b.write(CTRL, 1)
    await e.b.cycles(3000)
    assert (await e.b.read(STATUS)) & BUSY, "not busy during a scan"
    await e.b.expect(COUNT, 0, "COUNT early in the new scan (cleared, nothing found yet)")
    await e.b.expect(MAP0 + 1, 0, "MAP1 cleared by the new scan")
    await e.b.write(CTRL, 1)                         # ignored while busy: the scan does not restart
    want = e.m.scan({0x4B, 0x60})
    for _ in range(200):
        await e.b.cycles(2000)
        if not (await e.b.read(STATUS)) & BUSY:
            break
    assert e.bus.addr_probes == list(range(0x08, 0x78)), "a write while busy restarted or disturbed the scan"
    assert e.bus.log == want
    await e.regs()
    await e.b.write(CTRL, 0)                         # bit 0 clear: no scan
    await e.b.cycles(500)
    await e.regs()


@cocotb.test(timeout_time=1581890, timeout_unit="ns")
async def test_clock_stretching_and_timing(dut):
    e = Env(dut)
    await e.start({0x4B})
    e.bus.stretch_next = 400                         # the sensor stretches SCL after its ACK
    await e.scan({0x4B})
    hi, lo = 2 * e.q, 2 * e.q
    assert all(hi <= h <= hi + SYNC_SLACK for h in e.bus.high), f"SCL high times {sorted(set(e.bus.high))}, 2Q = {hi}"
    assert all(lo <= t <= lo + 2 for t in e.bus.low), f"SCL low times {sorted(set(e.bus.low))}, 2Q = {lo}"


@cocotb.test(timeout_time=2163470, timeout_unit="ns")
async def test_random_population(dut):
    rng = random.Random(int(cocotb.RANDOM_SEED))
    present = set(rng.sample(range(0x00, 0x80), 9)) | {0x4B}
    e = Env(dut)
    await e.start(present)
    await e.scan(present)
    present2 = set(rng.sample(range(0x08, 0x78), 3))
    e.bus.devices = Env.devices(present2)
    await e.scan(present2)
