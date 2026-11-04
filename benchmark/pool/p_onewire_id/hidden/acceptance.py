"""Acceptance tests of p_onewire_id against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from cocotb.triggers import RisingEdge
from model import COMMAND, CRC, CTRL, DESIGN_ID, FAILS, ID, STATUS, Model, crc8_maxim


class Slave:
    """The one-wire device. It watches the resolved wire, logs how the master behaved, and pulls it low when it should."""

    def __init__(self, dut, p: dict, id16: int, present: bool = True, crc_wire: int | None = None) -> None:
        self.dut, self.p, self.present = dut, p, present
        self.id16 = id16
        good = crc8_maxim(bytes([id16 & 0xFF, id16 >> 8]))
        self.crc_wire = good if crc_wire is None else crc_wire
        self.pull_from = self.pull_until = -1
        self.state = "idle"
        self.reset_widths: list[int] = []
        self.cmd_bits: list[int] = []
        self.cmd_widths: list[int] = []
        self.slot_gaps: list[int] = []
        self.read_ones_widths: list[int] = []
        self.reads = 0

    async def run(self) -> None:
        d, p = self.dut, self.p
        t, prev, fall_t, last_fall = 0, 1, 0, None
        out_bits: list[int] = []
        while True:
            await RisingEdge(d.CLK100MHZ)
            t += 1
            line = int(d.line.value)
            d.dev_pull.value = 1 if self.pull_from <= t < self.pull_until else 0
            held = self.pull_from <= t <= self.pull_until + 1
            if prev == 1 and line == 0:                       # a falling edge (the master's: our pulls start later)
                fall_t = t
                if last_fall is not None and self.state in ("cmd", "send"):
                    self.slot_gaps.append(t - last_fall)
                last_fall = t
                if self.state == "send" and out_bits:
                    bit = out_bits.pop(0)
                    self.reads += 1
                    if bit == 0:
                        self.pull_from, self.pull_until = t + 1, t + p["RD0_HOLD"]
            elif prev == 0 and line == 1:                     # a rising edge
                width = t - fall_t
                if width >= p["RST_LOW"] * 3 // 4 and not held:
                    self.reset_widths.append(width)
                    self.state, self.cmd_bits, last_fall = "cmd", [], None
                    if self.present:
                        self.pull_from, self.pull_until = t + p["PRES_WAIT"], t + p["PRES_WAIT"] + p["PRES_LOW"]
                elif self.state == "cmd" and not held:
                    self.cmd_widths.append(width)
                    self.cmd_bits.append(1 if width < (p["W1_LOW"] + p["W0_LOW"]) // 2 else 0)
                    if len(self.cmd_bits) == 8:
                        cmd = sum(b << i for i, b in enumerate(self.cmd_bits))
                        if cmd == COMMAND:
                            self.state = "send"
                            out_bits = Model.wire_bits(self.id16, self.crc_wire)
                        else:
                            self.state = "dead"
                elif self.state == "send" and not held:
                    self.read_ones_widths.append(width)
            prev = line


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"dev_pull": 0})
        names = ("RST_LOW", "PRES_WAIT", "PRES_LOW", "PRES_SAMPLE", "RST_TOTAL", "SLOT", "W1_LOW", "W0_LOW", "RD_LOW", "RD_SAMPLE", "RD0_HOLD")
        self.p = {n: self.b.param(n) for n in names}
        self.m = Model()

    async def start(self) -> None:
        self.dut.dev_pull.value = 0
        await self.b.start()

    def attach(self, **kw) -> Slave:
        s = Slave(self.dut, self.p, **kw)
        cocotb.start_soon(s.run())
        return s

    async def read_wire(self) -> None:
        await self.b.write(CTRL, 1)
        for _ in range(12):
            await self.b.cycles(200)
            st = await self.b.read(STATUS)
            if st & 2:
                return
        raise AssertionError("DONE never came")

    async def check(self) -> None:
        for off, name in ((STATUS, "STATUS"), (ID, "ID"), (CRC, "CRC"), (FAILS, "FAILS")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != {self.m.leds():04X}"


def check_log(s: Slave, p: dict) -> None:
    assert s.reset_widths == [p["RST_LOW"]], f"reset low times {s.reset_widths}, want {p['RST_LOW']}"
    assert s.cmd_bits == [(COMMAND >> i) & 1 for i in range(8)], f"command bits {s.cmd_bits}"
    want_w = [p["W1_LOW"] if b else p["W0_LOW"] for b in s.cmd_bits]
    assert s.cmd_widths == want_w, f"write low times {s.cmd_widths}, want {want_w}"
    assert s.reads == 24, f"{s.reads} read slots"
    assert set(s.slot_gaps) == {p["SLOT"]}, f"slot spacing {sorted(set(s.slot_gaps))}, want {p['SLOT']}"
    assert set(s.read_ones_widths) <= {p["RD_LOW"]}, f"read pulse widths {sorted(set(s.read_ones_widths))}, want {p['RD_LOW']}"


@cocotb.test()
async def test_identity_and_idle(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()
    await e.b.cycles(20)
    assert int(dut.line.value) == 1, "the wire should rest high"


@cocotb.test()
async def test_read_id_exact_protocol(dut):
    e = Env(dut)
    await e.start()
    s = e.attach(id16=0xA55A)
    await e.read_wire()
    e.m.read_done(True, 0xA55A)
    await e.check()
    check_log(s, e.p)


@cocotb.test()
async def test_absent_device_and_bad_crc(dut):
    e = Env(dut)
    await e.start()
    s = e.attach(id16=0x1234, present=False)
    await e.read_wire()
    e.m.read_done(False, 0)
    await e.check()
    assert s.cmd_bits == [] and s.reads == 0, "something was sent to a missing device"


@cocotb.test()
async def test_crc_mismatch(dut):
    e = Env(dut)
    await e.start()
    s = e.attach(id16=0x00FF, crc_wire=0x55)
    await e.read_wire()
    e.m.read_done(True, 0x00FF, crc_wire=0x55)
    await e.check()
    assert e.m.read(FAILS) == 1 and not (e.m.read(STATUS) & 8)
    check_log(s, e.p)


@cocotb.test()
async def test_two_reads_and_random_ids(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    first = rng.randrange(65536)
    s = e.attach(id16=first)
    await e.read_wire()
    e.m.read_done(True, first)
    await e.check()
    check_log(s, e.p)
    for i16 in (0x0000, 0xFFFF):
        s.id16 = i16
        s.crc_wire = crc8_maxim(bytes([i16 & 0xFF, i16 >> 8]))
        s.reset_widths, s.cmd_bits, s.cmd_widths, s.slot_gaps, s.read_ones_widths, s.reads = [], [], [], [], [], 0
        s.state = "idle"
        await e.read_wire()
        e.m.read_done(True, i16)
        await e.check()
        check_log(s, e.p)
