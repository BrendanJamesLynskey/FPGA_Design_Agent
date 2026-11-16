"""Hidden bench of the reply frame builder: replies assembled through the shell and read back byte by byte against the model."""

from __future__ import annotations

import cocotb
from benchmark.lib.net_bench import RegEnv, response, seeded_rng
from model import BUILD, BYTE, CAP, DESIGN_ID, IDX, LEN, PBYTE, PLEN, SEQ, STAT, STATUS, TYPE, Model


class Builder(RegEnv):
    def __init__(self, dut) -> None:
        super().__init__(dut, Model())

    async def build(self, typ: int, status: int, seq: int, payload: bytes, what: str = "") -> bytes:
        await self.wr(TYPE, typ)
        await self.wr(STATUS, status)
        await self.wr(SEQ, seq)
        for x in payload:
            await self.wr(PBYTE, x)
        await self.b.expect(PLEN, len(payload) if len(payload) <= CAP else CAP, f"{what} payload held")
        await self.wr(BUILD, 1)
        await self.b.cycles(80)
        return self.m.frame

    async def readback(self, what: str = "") -> None:
        await self.b.expect(STAT, self.m.read(STAT), f"{what} STAT")
        await self.b.expect(LEN, len(self.m.frame), f"{what} LEN")
        for i in range(len(self.m.frame)):
            await self.wr(IDX, i)
            await self.b.expect(BYTE, self.m.frame[i], f"{what} byte {i}")
        await self.led(self.m.led(), what)


@cocotb.test()
async def test_builder_identity_and_reset_state(dut):
    r = Builder(dut)
    await r.b.start()
    assert await r.b.shell_id() == DESIGN_ID
    await r.regs(range(10), "at reset")
    await r.led(0, "no reply: LED is zero")
    await r.build(2, 3, 9, b"xy")
    await r.b.reset()
    r.m = Model()
    await r.regs(range(10), "after reset")
    await r.led(0, "LED after reset")


@cocotb.test()
async def test_builder_reply_layout_and_check(dut):
    r = Builder(dut)
    await r.b.start()
    frame = await r.build(1, 0, 0x1234, bytes.fromhex("DEADBEEF"), "read reply")
    assert frame == response(1, 0, 0x1234, bytes.fromhex("DEADBEEF"))
    await r.readback("read reply")
    frame = await r.build(3, 4, 0xFFFF, b"", "empty payload")
    assert frame == response(3, 4, 0xFFFF)
    await r.readback("empty payload")
    await r.b.expect(PLEN, 0, "payload cleared by the build")


@cocotb.test()
async def test_builder_every_field_width_and_type_mask(dut):
    r = Builder(dut)
    await r.b.start()
    await r.build(0xFF, 0xFF, 0x8001, bytes([0x00, 0xFF, 0x80]), "wide fields")
    assert r.m.frame[0] == 0xFF and r.m.frame[1] == 0xFF
    await r.readback("types keep 7 bits")
    await r.wr(TYPE, 0x1234_5645)
    await r.wr(STATUS, 0xABC_D0E)
    await r.wr(SEQ, 0x7_ABCD)
    await r.regs((TYPE, STATUS, SEQ), "masks")
    await r.build(0x40, 0, 0x0100, bytes([1]), "telemetry-style type")
    await r.readback("0x40")
    await r.b.expect(TYPE, 0x40, "type kept after build")
    await r.b.expect(SEQ, 0x0100, "sequence kept after build")


@cocotb.test()
async def test_builder_full_payload_and_overflow(dut):
    r = Builder(dut)
    await r.b.start()
    rng = seeded_rng()
    full = bytes(rng.randrange(256) for _ in range(CAP))
    await r.build(2, 0, 7, full, "24 bytes")
    await r.readback("24 bytes")
    assert len(r.m.frame) == 5 + CAP + 4
    over = bytes(rng.randrange(256) for _ in range(CAP + 3))
    await r.build(5, 1, 8, over, "27 bytes")
    await r.b.expect(PLEN, 0, "cleared")
    assert r.m.frame == response(5, 1, 8, over[:CAP])
    await r.readback("27 bytes: first 24 used")
    await r.b.expect(STAT, 0, "overflow flag cleared by the build")


@cocotb.test()
async def test_builder_overflow_flag_and_positions_beyond_the_reply(dut):
    r = Builder(dut)
    await r.b.start()
    for x in range(CAP + 1):
        await r.wr(PBYTE, x)
    await r.b.expect(STAT, 2, "overflow set")
    await r.b.expect(PLEN, CAP, "24 held")
    await r.wr(BUILD, 0)
    await r.b.cycles(80)
    await r.b.expect(STAT, 0, "overflow cleared by the build")
    await r.wr(IDX, len(r.m.frame))
    await r.b.expect(BYTE, 0, "one past the end")
    await r.wr(IDX, 0x7F)
    await r.b.expect(BYTE, 0, "far beyond")
    await r.b.expect(IDX, 0x7F, "IDX reads back")
    await r.wr(IDX, 0xFFFF_FF85)
    await r.b.expect(IDX, 0x05, "IDX keeps 7 bits")
    await r.b.expect(BYTE, r.m.frame[5], "byte 5")


@cocotb.test()
async def test_builder_reply_survives_until_the_next_build_and_payload_accumulates(dut):
    r = Builder(dut)
    await r.b.start()
    await r.build(1, 0, 5, bytes([1, 2, 3]), "first")
    await r.wr(PBYTE, 0x99)
    await r.wr(TYPE, 4)
    await r.wr(SEQ, 6)
    await r.b.expect(PLEN, 1, "new payload being gathered")
    await r.readback("old reply still readable")
    await r.wr(PBYTE, 0x98)
    await r.wr(BUILD, 0)
    await r.b.cycles(80)
    assert r.m.frame == response(4, 0, 6, bytes([0x99, 0x98]))
    await r.readback("second")
    await r.poke_read_only((BYTE, LEN, STAT, PLEN), 0x4141)
    await r.regs(range(10), "read-only writes")
    await r.unmapped((0x0A, 0x40, 0x7F))


@cocotb.test()
async def test_builder_random_replies(dut):
    r = Builder(dut)
    await r.b.start()
    rng = seeded_rng()
    for k in range(4):
        n = rng.choice([0, 1, 2, 5, 9, 17, 24])
        await r.build(rng.randrange(128), rng.randrange(256), rng.randrange(65536), bytes(rng.randrange(256) for _ in range(n)), f"random {k}")
        await r.readback(f"random {k}")


@cocotb.test()
async def test_builder_type_mask_led_status_and_shorter_after_longer(dut):
    r = Builder(dut)
    await r.b.start()
    await r.wr(TYPE, 0xFE)
    await r.b.expect(TYPE, 0x7E, "7 bits kept")
    await r.wr(TYPE, 0x80)
    await r.b.expect(TYPE, 0, "bit 7 not kept")
    await r.build(1, 0x11, 2, bytes(range(1, 25)), "long reply")
    await r.readback("long reply")
    await r.wr(STATUS, 0x99)
    await r.led(r.m.led(), "LED shows the reply's status, not the one being prepared")
    await r.build(2, 0x22, 3, bytes(range(4)), "short reply")
    for i in (13, 14, 20, 33, 34, 40):
        await r.wr(IDX, i)
        await r.b.expect(BYTE, 0, f"position {i} past the shorter reply")
    await r.readback("short reply")


@cocotb.test()
async def test_builder_reset_clears_gathered_state_and_unmapped_writes_do_nothing(dut):
    r = Builder(dut)
    await r.b.start()
    for x in range(25):
        await r.wr(PBYTE, x)
    await r.wr(IDX, 5)
    await r.wr(TYPE, 9)
    await r.wr(STATUS, 8)
    await r.wr(SEQ, 7)
    await r.poke_unmapped((0x0A, 0x20, 0x40, 0x7F))
    await r.regs(range(10), "after unmapped writes")
    await r.b.reset()
    r.m = Model()
    await r.regs(range(10), "after reset")
    await r.led(0, "led")
