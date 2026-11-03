"""Acceptance tests of p_adt7420_oneshot against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from cocotb.triggers import RisingEdge
from model import CTRL, DESIGN_ID, RES, STATUS, Model, config_byte

CONV_TIME = 600          # the sensor needs this many clocks after a one-shot request; earlier reads return the old value


class Adt7420:
    """The sensor on I2C address `addr`: registers 0x00/0x01 temperature, 0x03 configuration, 0x0B ID (0xCB)."""

    def __init__(self, dut, addr: int = 0x4B) -> None:
        self.dut, self.addr = dut, addr
        self.temp = 0x1230                    # the stale value held until a one-shot conversion finishes
        self.pending = 0x0000
        self.config = 0x00
        self.t = 0
        self.conv_done = None
        self.ptr = 0
        self.log: list[tuple] = []
        self.bad_config: list[int] = []
        self.master_ack = False

    def read_reg(self, r: int) -> int:
        if r == 0:
            return self.temp >> 8
        if r == 1:
            return self.temp & 0xFF
        if r == 3:
            return self.config
        if r == 0x0B:
            return 0xCB
        return 0

    def write_reg(self, r: int, v: int) -> None:
        self.log.append(("W", r, v))
        if r == 3:
            self.config = v
            if (v >> 5) & 3 == 1:
                self.conv_done = self.t + CONV_TIME
            else:
                self.bad_config.append(v)

    async def run(self) -> None:
        d = self.dut
        prev_scl = prev_sda = 1
        mode, nbits, byte, rw, first, pull = "idle", 0, 0, 0, True, 0
        tx = 0
        d.dev_sda_pull.value = 0
        while True:
            await RisingEdge(d.CLK100MHZ)
            self.t += 1
            if self.conv_done is not None and self.t >= self.conv_done:
                self.temp = self.pending
                self.config = (self.config & 0x9F) | 0x60           # back to shutdown after the one conversion
                self.conv_done = None
            scl, sda = int(d.scl.value), int(d.sda.value)
            if prev_scl and scl and prev_sda and not sda:
                self.log.append(("S", self.t))
                mode, nbits, byte, pull = "addr", 0, 0, 0
            elif prev_scl and scl and not prev_sda and sda:
                self.log.append(("P", self.t))
                mode, pull = "idle", 0
            elif not prev_scl and scl:
                if mode in ("addr", "wdata") and nbits < 8:
                    byte = byte << 1 | sda
                    nbits += 1
                elif mode == "mack":
                    self.master_ack = sda == 0
            elif prev_scl and not scl:
                if mode in ("addr", "wdata") and nbits == 8:
                    if mode == "addr":
                        rw = byte & 1
                        if (byte >> 1) == self.addr:
                            pull, mode = 1, "ack_addr"
                            self.log.append(("ADDR", byte))
                        else:
                            pull, mode = 0, "ignore"
                    else:
                        if first:
                            self.ptr = byte
                            self.log.append(("PTR", byte))
                            first = False
                        else:
                            self.write_reg(self.ptr, byte)
                            self.ptr += 1
                        pull, mode = 1, "ack_w"
                    nbits, byte = 0, 0
                elif mode == "ack_addr":
                    pull = 0
                    if rw:
                        mode = "tx"
                        tx = self.read_reg(self.ptr)
                        self.log.append(("R", self.ptr, tx))
                        self.ptr += 1
                        pull = 0 if (tx >> 7) & 1 else 1
                        nbits = 1
                    else:
                        mode, nbits, byte, first = "wdata", 0, 0, True
                elif mode == "ack_w":
                    pull, mode, nbits, byte = 0, "wdata", 0, 0
                elif mode == "tx":
                    if nbits < 8:
                        pull = 0 if (tx >> (7 - nbits)) & 1 else 1
                        nbits += 1
                    else:
                        pull, mode = 0, "mack"
                elif mode == "mack":
                    if self.master_ack:
                        mode, nbits = "tx", 1
                        tx = self.read_reg(self.ptr)
                        self.log.append(("R", self.ptr, tx))
                        self.ptr += 1
                        pull = 0 if (tx >> 7) & 1 else 1
                    else:
                        mode, pull = "idle", 0
            d.dev_sda_pull.value = pull
            prev_scl, prev_sda = scl, sda


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"dev_sda_pull": 0})
        self.p = {n: self.b.param(n) for n in ("QUARTER", "CONV_WAIT")}
        self.m = Model()
        self.dev: Adt7420 | None = None

    async def start(self, addr: int = 0x4B) -> None:
        self.dut.dev_sda_pull.value = 0
        await self.b.start()
        self.dev = Adt7420(self.dut, addr)
        cocotb.start_soon(self.dev.run())

    async def wait_done(self) -> None:
        for _ in range(60):
            await self.b.cycles(300)
            if (await self.b.read(STATUS)) & 2:
                return
        raise AssertionError("the reading never finished")

    async def measure(self, raw: int) -> None:
        self.dev.pending = raw
        self.dev.log.clear()
        assert self.m.start()
        await self.b.write(CTRL, 1)
        await self.wait_done()
        self.m.complete(raw)

    def check_log(self, res16: bool) -> None:
        log = self.dev.log
        kinds = [e[0] for e in log]
        assert kinds == ["S", "ADDR", "PTR", "W", "P", "S", "ADDR", "PTR", "S", "ADDR", "R", "R", "P"], f"bus events {kinds}"
        assert log[1][1] == 0x96 and log[6][1] == 0x96 and log[9][1] == 0x97, "address bytes"
        assert log[2][1] == 3 and log[3][1:] == (3, config_byte(res16)), f"configuration write {log[2:4]}"
        assert log[7][1] == 0, "temperature pointer"
        gap = log[5][1] - log[4][1]
        w = self.p["CONV_WAIT"]
        assert w <= gap <= w + 8 * self.p["QUARTER"] + 40, f"the temperature read began {gap} clocks after the STOP, want about {w}"
        assert not self.dev.bad_config, f"configuration written with another mode: {self.dev.bad_config}"

    async def check(self) -> None:
        for off in range(1, 9):
            await self.b.expect(off, self.m.read(off), f"register {off}")
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_idle_bus(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()
    assert int(dut.scl.value) == 1 and int(dut.sda.value) == 1 and not e.dev.log, "bus activity without a start"


@cocotb.test()
async def test_13_bit_reading(dut):
    e = Env(dut)
    await e.start()
    await e.measure(0x0D80 | 0b101)          # 27.0 C, flag bits set in the low three bits
    e.check_log(False)
    await e.check()
    assert e.m.temp == 432


@cocotb.test()
async def test_16_bit_reading_negative_and_minmax(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(RES, 1)
    e.m.write(RES, 1)
    await e.measure(0xF9C0)                   # -12.5 C
    e.check_log(True)
    await e.measure(0x0100 | 0x07)            # 2 C
    await e.measure(0x7FF8)
    await e.check()
    await e.b.write(CTRL, 2)
    e.m.write(CTRL, 2)
    await e.check()


@cocotb.test()
async def test_missing_sensor_and_busy_start(dut):
    e = Env(dut)
    await e.start(addr=0x4C)                  # nothing answers at 0x4B
    assert e.m.start()
    await e.b.write(CTRL, 1)
    await e.wait_done()
    e.m.abandon()
    await e.check()
    assert int(dut.scl.value) == 1 and int(dut.sda.value) == 1, "the bus was left busy"
    assert [k[0] for k in e.dev.log].count("S") == 1 and e.dev.log[-1][0] == "P", f"events {e.dev.log}"


@cocotb.test()
async def test_start_while_busy_is_ignored(dut):
    e = Env(dut)
    await e.start()
    e.dev.pending = 0x0A00
    assert e.m.start()
    await e.b.write(CTRL, 1)
    await e.b.write(CTRL, 1)                  # still converting
    e.m.start()
    await e.wait_done()
    e.m.complete(0x0A00)
    await e.check()
    assert e.m.ignored == 1 and e.dev.log.count(("W", 3, 0x20)) == 1, "a second reading was started"


@cocotb.test()
async def test_random_readings(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(3):
        res16 = rng.random() < 0.5
        await e.b.write(RES, int(res16))
        e.m.write(RES, int(res16))
        raw = rng.randrange(0x10000)
        await e.measure(raw)
        e.check_log(res16)
    await e.check()
