"""Acceptance tests of t2_qspi_sfdp against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from flash_model import IDENT, SFDP_TABLE, Flash
from model import BUSY, CTRL, DESIGN_ID, ID, SFDP0, STATUS, Model


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, {"QSPI_DQ1": 0})
        self.dut, self.m = dut, Model()
        self.half = self.b.param("HALF")

    async def start(self, ident: bytes = IDENT, sfdp: bytes = SFDP_TABLE) -> None:
        await self.b.start()
        self.f = Flash(self.dut, ident, sfdp)
        self.ident, self.sfdp = ident, sfdp

    async def regs(self) -> None:
        for off, name in ((STATUS, "STATUS"), (ID, "ID"), (SFDP0, "SFDP0"), (SFDP0 + 1, "SFDP1"),
                          (SFDP0 + 2, "SFDP2"), (SFDP0 + 3, "SFDP3")):
            await self.b.expect(off, self.m.read(off), name)

    async def run(self) -> list[list[int]]:
        await self.b.write(CTRL, 1)
        want = self.m.start(self.ident, self.sfdp)
        await self.b.cycles(30 * 16 * self.half + 400)
        return want

    def check_flash(self) -> None:
        f = self.f
        assert f.bad_opcodes == [], f"forbidden opcodes sent to the flash: {[hex(o) for o in f.bad_opcodes]}"
        assert not f.wp_hold_bad, "WP# (DQ2) left 0 or HOLD# (DQ3) left 1"
        assert not f.halves or min(f.halves) >= self.half, f"SCK half period {min(f.halves)} < HALF {self.half}"


@cocotb.test(timeout_time=1244260, timeout_unit="ns")
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.regs()
    for off in (CTRL, 0x07, 0x7F):
        await e.b.expect(off, 0, "unmapped / write-only")
    assert e.f.transactions == [], "flash traffic before the start command"
    assert e.f.idle_cycles >= 3, f"only {e.f.idle_cycles} SCK cycles with CS high after reset (STARTUPE2 drops 3)"
    e.check_flash()


@cocotb.test(timeout_time=1255880, timeout_unit="ns")
async def test_jedec_id_and_sfdp(dut):
    e = Env(dut)
    await e.start()
    want = await e.run()
    assert e.f.transactions == want, f"MOSI bytes {e.f.transactions}, model {want}"
    await e.regs()
    assert e.m.sig
    e.check_flash()


@cocotb.test(timeout_time=1255880, timeout_unit="ns")
async def test_bad_signature(dut):
    e = Env(dut)
    await e.start(sfdp=bytes([0xFF] * 4) + SFDP_TABLE[4:])      # an erased or non-SFDP part
    await e.run()
    await e.regs()
    assert not e.m.sig
    e.check_flash()


@cocotb.test(timeout_time=1552200, timeout_unit="ns")
async def test_busy_and_repeat(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(CTRL, 1)
    e.m.start(e.ident, e.sfdp)
    st = await e.b.read(STATUS)
    assert st == BUSY, f"STATUS 0x{st:X} during the reads, model BUSY only"
    await e.b.write(CTRL, 1)                                  # ignored while busy
    await e.b.cycles(30 * 16 * e.half)
    await e.regs()
    assert len(e.f.transactions) == 2, f"{len(e.f.transactions)} transactions; a start while busy was not ignored"
    e.f.ident = bytes([0x01, 0x02, 0x19]) + IDENT[3:]        # another part answers the second time
    e.ident = e.f.ident
    await e.run()
    await e.regs()
    assert len(e.f.transactions) == 4
    e.check_flash()


@cocotb.test(timeout_time=1255880, timeout_unit="ns")
async def test_random_contents(dut):
    rng = random.Random(int(cocotb.RANDOM_SEED))
    ident = bytes(rng.randrange(256) for _ in range(8))
    sfdp = b"SFDP" + bytes(rng.randrange(256) for _ in range(60))
    e = Env(dut)
    await e.start(ident, sfdp)
    want = await e.run()
    assert e.f.transactions == want
    await e.regs()
    e.check_flash()
