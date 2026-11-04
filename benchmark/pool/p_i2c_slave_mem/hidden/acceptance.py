"""Acceptance tests of p_i2c_slave_mem against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import ADDRESS, DESIGN_ID, Model


class Master:
    """An I2C master: pulls SCL/SDA low through the wrapper and reads the resolved bus."""

    def __init__(self, dut, q: int) -> None:
        self.d, self.q = dut, q
        dut.m_scl_low.value = 0
        dut.m_sda_low.value = 0

    async def w(self, n: int) -> None:
        await cocotb.triggers.ClockCycles(self.d.CLK100MHZ, n)

    async def start(self, repeated: bool = False) -> None:
        d, q = self.d, self.q
        if repeated:
            d.m_sda_low.value = 0
            await self.w(q)
            d.m_scl_low.value = 0
            await self.w(q)
        d.m_sda_low.value = 1
        await self.w(q)
        d.m_scl_low.value = 1
        await self.w(q)

    async def stop(self) -> None:
        d, q = self.d, self.q
        d.m_sda_low.value = 1
        await self.w(q)
        d.m_scl_low.value = 0
        await self.w(q)
        d.m_sda_low.value = 0
        await self.w(2 * q)

    async def bit_out(self, b: int) -> None:
        d, q = self.d, self.q
        d.m_sda_low.value = 0 if b else 1
        await self.w(q)
        d.m_scl_low.value = 0
        await self.w(2 * q)
        d.m_scl_low.value = 1
        await self.w(q)

    async def bit_in(self) -> int:
        d, q = self.d, self.q
        d.m_sda_low.value = 0
        await self.w(q)
        d.m_scl_low.value = 0
        await self.w(q)
        v = int(d.sda.value)
        await self.w(q)
        d.m_scl_low.value = 1
        await self.w(q)
        return v

    async def write_byte(self, v: int) -> bool:
        for i in range(7, -1, -1):
            await self.bit_out((v >> i) & 1)
        return (await self.bit_in()) == 0

    async def read_byte(self, ack: bool) -> int:
        v = 0
        for _ in range(8):
            v = v << 1 | await self.bit_in()
        await self.bit_out(0 if ack else 1)
        return v


class Env:
    def __init__(self, dut, q: int = 8) -> None:
        self.dut = dut
        self.b = Board(dut, {"m_scl_low": 0, "m_sda_low": 0})
        self.m = Model()
        self.ms = Master(dut, q)

    async def start(self) -> None:
        await self.b.start()

    async def write_txn(self, addr: int, data: list[int], stop: bool = True, repeated: bool = False) -> None:
        await self.ms.start(repeated)
        self.m.start()
        want = [self.m.addr(addr << 1)] + [self.m.wbyte(d) for d in data]
        got = [await self.ms.write_byte(addr << 1)]
        for d in data:
            got.append(await self.ms.write_byte(d))
        assert got == want, f"acknowledges {got}, want {want} for a write to {addr:#x} of {data}"
        if stop:
            await self.ms.stop()

    async def read_txn(self, addr: int, n: int, stop: bool = True, repeated: bool = False) -> list[int]:
        await self.ms.start(repeated)
        self.m.start()
        ack = await self.ms.write_byte(addr << 1 | 1)
        assert ack == self.m.addr(addr << 1 | 1), f"address acknowledge {ack}"
        want = [self.m.rbyte() for _ in range(n)]
        got = [await self.ms.read_byte(i < n - 1) for i in range(n)]
        assert got == want, f"read {got}, want {want}"
        if stop:
            await self.ms.stop()
        return got

    async def check_window(self) -> None:
        for off in range(0, 19):
            await self.b.expect(off, self.m.read(off), f"window {off}")
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_id_register(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_window()
    await e.read_txn(ADDRESS, 3)                  # the pointer is 0 after reset
    await e.check_window()


@cocotb.test()
async def test_write_read_pointer_kept(dut):
    e = Env(dut)
    await e.start()
    await e.write_txn(ADDRESS, [1, 0x11, 0x22, 0x44])
    await e.write_txn(ADDRESS, [1])                # pointer only
    await e.read_txn(ADDRESS, 4)
    await e.read_txn(ADDRESS, 6)                   # continues where the last read stopped
    await e.write_txn(ADDRESS, [2], stop=False)    # repeated start into a read
    await e.read_txn(ADDRESS, 3, repeated=True)
    await e.check_window()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.start()
    await e.write_txn(ADDRESS, [0, 0x99, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0xFF, 0xEE])
    await e.write_txn(ADDRESS, [14, 0xAA, 0xBB, 0xCC])   # 14, 15, then wraps to 0: all read-only or the ID
    await e.write_txn(ADDRESS, [0])
    await e.read_txn(ADDRESS, 16)
    await e.read_txn(ADDRESS, 2)                   # wraps from 15 back to 0
    await e.check_window()


@cocotb.test()
async def test_bad_pointer_and_wrong_address(dut):
    e = Env(dut)
    await e.start()
    await e.write_txn(ADDRESS, [4, 0x5A])
    await e.write_txn(ADDRESS, [16, 0x77, 0x88])    # refused: no acknowledges, pointer unchanged
    await e.write_txn(ADDRESS, [200])
    await e.read_txn(ADDRESS, 2)
    await e.write_txn(0x2B, [1, 2, 3])               # another address: ignored
    await e.read_txn(0x29, 2)
    await e.read_txn(ADDRESS, 3)
    await e.check_window()
    assert e.m.badptr == 2 and e.m.matches == 6


@cocotb.test()
async def test_shell_writes_and_random_traffic(dut):
    e = Env(dut, q=20)                              # a slower master
    await e.start()
    for off, v in ((3, 0x33), (0, 0xFF), (8, 0x55), (7, 0x77)):
        await e.b.write(off, v)
        e.m.write(off, v)
    await e.write_txn(ADDRESS, [0])
    await e.read_txn(ADDRESS, 10)
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(6):
        if rng.random() < 0.5:
            await e.write_txn(ADDRESS, [rng.randrange(18)] + [rng.randrange(256) for _ in range(rng.randrange(0, 4))])
        else:
            await e.read_txn(ADDRESS, rng.randrange(1, 5))
    await e.check_window()
