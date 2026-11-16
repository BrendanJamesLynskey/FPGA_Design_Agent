"""Hidden bench of the command packet screener: packets pushed byte by byte, every register compared with the model."""

from __future__ import annotations

import cocotb
from benchmark.lib.net_bench import RegEnv, command, seeded_rng
from model import BUSY, BYTE, CTR0, DESIGN_ID, LASTSEQ, RESULT, Model

ALL = tuple(range(8)) + tuple(range(CTR0, CTR0 + 7))
RD, WR, ST, TS, TP = 1, 2, 3, 4, 5


def addr(a: int) -> bytes:
    return a.to_bytes(2, "big")


class Screen(RegEnv):
    def __init__(self, dut) -> None:
        super().__init__(dut, Model())

    async def send(self, pkt: bytes, what: str = "", full: bool = False) -> None:
        before = list(self.m.ctr)
        for i, x in enumerate(pkt):
            await self.wr(BYTE, x | (0x100 if i == len(pkt) - 1 else 0))
        if full:
            await self.regs(ALL, what)
        else:                                  # the result, the counter that moved and, for a good packet, the fields
            await self.regs((RESULT,), what)
            for i in range(7):
                if self.m.ctr[i] != before[i]:
                    await self.regs((CTR0 + i,), what)
            await self.regs((2, 3, 4, 5, LASTSEQ), what)
        await self.led(self.m.led(), what)


@cocotb.test()
async def test_screen_identity_reset_and_a_good_packet(dut):
    s = Screen(dut)
    await s.b.start()
    assert await s.b.shell_id() == DESIGN_ID
    await s.regs(ALL, "at reset")
    await s.send(command(RD, 0x1234, addr(3)), "first read", full=True)
    assert s.m.result == 1 and s.m.seq == 0x1234 and s.m.p0 == 3 and s.m.p1 == 0
    await s.send(command(WR, 0x1235, addr(2) + (0xCAFEBABE).to_bytes(4, "big")), "write")
    assert s.m.p0 == 2 and s.m.p1 == 0xCAFEBABE
    await s.send(command(ST, 0x1236), "status")
    assert s.m.p0 == 0 and s.m.p1 == 0
    await s.b.reset()
    s.m = Model()
    await s.regs(ALL, "after reset")


@cocotb.test()
async def test_screen_first_packet_may_carry_any_number_and_the_number_wraps(dut):
    s = Screen(dut)
    await s.b.start()
    await s.send(command(TS, 0xFFFE, addr(7)), "first number 0xFFFE")
    await s.send(command(TP, 0xFFFF), "0xFFFF")
    await s.send(command(RD, 0x0000, addr(1)), "wrap to 0")
    await s.send(command(RD, 0x0001, addr(1)), "1")
    assert s.m.ctr[0] == 4 and s.m.last_seq == 1
    await s.send(command(RD, 0x7FFF + 1, addr(1)), "a long jump forward, 0x8000 ahead is not new")   # delta 0x7FFF: new
    await s.send(command(RD, 0x8000 + 0x8000, addr(1)), "exactly 0x8000 ahead is out of order")
    assert s.m.result == 6


@cocotb.test()
async def test_screen_repeat_and_stale_numbers_change_nothing_but_their_counter(dut):
    s = Screen(dut)
    await s.b.start()
    await s.send(command(WR, 100, addr(1) + (11).to_bytes(4, "big")), "n=100")
    before = [s.m.read(r) for r in (2, 3, 4, 5, 6)]
    await s.send(command(WR, 100, addr(2) + (22).to_bytes(4, "big")), "repeat")
    assert s.m.result == 5
    await s.send(command(WR, 99, addr(2) + (22).to_bytes(4, "big")), "one older")
    await s.send(command(WR, 100 - 0x7FFF, addr(2) + (22).to_bytes(4, "big")), "far older")
    await s.send(command(WR, 100 + 0x7FFF, addr(2) + (22).to_bytes(4, "big")), "newest allowed jump")
    assert [s.m.read(r) for r in (2, 3, 4, 5, 6)] != before
    await s.send(command(WR, 101 + 0x7FFF, addr(3) + (33).to_bytes(4, "big")), "next")
    assert s.m.ctr[4] == 1 and s.m.ctr[5] == 2


@cocotb.test()
async def test_screen_bad_check_and_framing_classes(dut):
    s = Screen(dut)
    await s.b.start()
    good = command(WR, 5, addr(1) + (0x01020304).to_bytes(4, "big"))
    await s.send(good, "good")
    bad = bytearray(good); bad[-1] ^= 0x80
    await s.send(bytes(bad), "bad check")
    assert s.m.result == 2 and s.m.last_seq == 5
    bad = bytearray(command(WR, 6, addr(1) + (9).to_bytes(4, "big"))); bad[5] ^= 0x01    # a data bit, so the check no longer fits
    await s.send(bytes(bad), "bad data bit")
    await s.send(command(WR, 6, addr(1) + (9).to_bytes(4, "big"))[:-1], "short by one")
    assert s.m.result == 3
    await s.send(command(WR, 6, addr(1) + (9).to_bytes(4, "big")) + b"\0", "long by one")
    assert s.m.result == 4
    await s.send(command(ST, 6)[:3], "three bytes")
    await s.send(bytes([5]), "one byte")
    await s.send(command(ST, 6)[:4], "header only")
    assert s.m.result == 3
    await s.b.expect(BUSY, 0, "idle after a short packet")
    await s.send(command(WR, 6, addr(1) + (9).to_bytes(4, "big")), "recovers")
    assert s.m.result == 1 and s.m.last_seq == 6


@cocotb.test()
async def test_screen_oversize_is_discarded_to_its_end_flag(dut):
    s = Screen(dut)
    await s.b.start()
    await s.send(bytes([1, 9, 0, 1]) + bytes(range(5, 20)), "length byte 9")
    assert s.m.result == 4
    await s.send(bytes([2, 255, 0, 1]) + bytes(40), "length byte 255")
    await s.send(bytes([1, 9, 0, 1]), "exactly four bytes with length 9")
    assert s.m.result == 4
    await s.send(command(RD, 1, addr(0)), "next packet is fine")
    assert s.m.result == 1
    long = command(ST, 2) + bytes(3)
    await s.send(long, "trailing bytes after a good status")
    assert s.m.result == 4 and s.m.last_seq == 1
    await s.send(command(RD, 2, addr(0)), "and after it")
    assert s.m.ctr[3] == 4


@cocotb.test()
async def test_screen_type_and_length_checks_come_after_the_check_and_before_the_number(dut):
    s = Screen(dut)
    await s.b.start()
    await s.send(command(RD, 10, addr(0)), "n=10")
    for typ in (0, 6, 0x7F, 0x80, 0xFF):
        await s.send(command(typ, 11), f"type {typ}")
        assert s.m.result == 7
    await s.send(command(RD, 11, addr(0) + b"\0"), "read with 3 payload bytes")
    assert s.m.result == 8
    await s.send(command(WR, 11, addr(0)), "write with 2")
    await s.send(command(ST, 11, b"\x01"), "status with 1")
    await s.send(command(TP, 11, addr(1)), "stop with 2")
    await s.send(command(TS, 11, b""), "start with 0")
    await s.send(command(0, 5), "unknown type with an old number is a type error")
    assert s.m.result == 7 and s.m.last_seq == 10 and s.m.ctr[6] == 11
    bad = bytearray(command(9, 12)); bad[-2] ^= 4
    await s.send(bytes(bad), "unknown type with a bad check is a check error")
    assert s.m.result == 2
    await s.send(command(RD, 5, addr(0) + b"\0"), "bad length with an old number is a length error")
    assert s.m.result == 8


@cocotb.test()
async def test_screen_fields_and_register_rules(dut):
    s = Screen(dut)
    await s.b.start()
    await s.send(command(WR, 1, addr(0xA5C3) + (0xF0E1D2C3).to_bytes(4, "big")), "fields")
    await s.b.expect(RESULT, 1)
    await s.send(command(TS, 2, addr(0x1F40)), "period field")
    assert s.m.p0 == 0x1F40 and s.m.p1 == 0
    await s.b.expect(LASTSEQ, 0x10002, "last number with the valid bit")
    await s.wr(BYTE, 0x0AA)                      # a byte without the end flag: part-way
    await s.b.expect(BUSY, 1, "part-way")
    await s.b.expect(BYTE, 0x0AA, "BYTE reads the last write")
    await s.wr(BYTE, 0x1FF)                      # ends it: a two-byte packet
    await s.b.expect(BUSY, 0, "end flag ends the packet")
    await s.regs(ALL, "after a two-byte packet")
    await s.poke_read_only(tuple(range(1, 8)) + (CTR0, CTR0 + 6), 0x7777)
    await s.regs(ALL, "read-only writes")
    await s.unmapped((0x08, 0x17, 0x40, 0x7F))


@cocotb.test()
async def test_screen_random_mix(dut):
    s = Screen(dut)
    await s.b.start()
    rng = seeded_rng()
    seq = rng.randrange(65536)
    for k in range(18):
        typ = rng.choice([RD, WR, ST, TS, TP])
        pl = {RD: addr(rng.randrange(10)), WR: addr(rng.randrange(10)) + rng.getrandbits(32).to_bytes(4, "big"), ST: b"", TS: addr(rng.randrange(500)), TP: b""}[typ]
        seq = (seq + rng.choice([1, 1, 2, 300])) & 0xFFFF
        pkt = bytearray(command(typ, seq, pl))
        c = rng.randrange(7)
        if c == 0:
            pkt[rng.randrange(len(pkt))] ^= 1 << rng.randrange(8)
        elif c == 1:
            del pkt[rng.randrange(len(pkt)):]
            if not pkt:
                pkt = bytearray([rng.randrange(256)])
        elif c == 2:
            pkt += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 6)))
        elif c == 3:
            pkt = bytearray(command(typ, (s.m.last_seq - rng.randrange(0, 3)) & 0xFFFF, pl))
        await s.send(bytes(pkt), f"random {k}")
        if s.m.result == 1:
            seq = s.m.last_seq
    await s.regs(ALL, "end of the random mix")


@cocotb.test()
async def test_screen_boundaries_first_refused_and_reset_state(dut):
    s = Screen(dut)
    await s.b.start()
    await s.send(command(9, 0x1000), "a refused first packet")
    await s.send(command(RD, 0x9000, addr(1)), "then a good one far from number 0")
    assert s.m.result == 1
    await s.send(command(RD, 0x9001, bytes(8)), "length 8 on a read")
    assert s.m.result == 8
    await s.send(command(RD, 0x9002, bytes(8)) + b"\0", "length 8 and one byte too many")
    assert s.m.result == 4
    await s.send(bytes([1, 9, 0]), "three bytes with length 9")
    assert s.m.result == 3
    await s.wr(BYTE, 0x55)
    await s.b.reset()
    s.m = Model()
    await s.regs(ALL, "reset while part-way")


@cocotb.test()
async def test_screen_unmapped_writes_change_nothing(dut):
    s = Screen(dut)
    await s.b.start()
    await s.send(command(WR, 3, addr(1) + (7).to_bytes(4, "big")), "state")
    await s.poke_unmapped((0x08, 0x17, 0x20, 0x40, 0x7F))
    await s.regs(ALL, "after unmapped writes")
