"""Hidden bench of the UDP endpoint: whole packets pushed through the shell, replies and telemetry frames compared byte for byte."""

from __future__ import annotations

import cocotb
from benchmark.lib.net_bench import RegEnv, command, crc_le, seeded_rng
from model import DESIGN_ID, IN, RIDX, RLEN, RWORD, STAT, TAKE, TICK, TIDX, TLEN, TWORD, Model

RD, WR, ST, TS, TP = 1, 2, 3, 4, 5


def a2(a: int) -> bytes:
    return a.to_bytes(2, "big")


def wv(a: int, v: int) -> bytes:
    return a2(a) + v.to_bytes(4, "big")


class Ep(RegEnv):
    def __init__(self, dut) -> None:
        super().__init__(dut, Model())

    async def send(self, pkt: bytes, what: str = "") -> bytes:
        for i, x in enumerate(pkt):
            await self.wr(IN, x | (0x100 if i == len(pkt) - 1 else 0))
        await self.b.cycles(120)
        await self.b.expect(RLEN, len(self.m.reply), f"{what} reply length")
        for i in range((len(self.m.reply) + 3) // 4 + 1):          # one word past the end as well: zero
            await self.wr(RIDX, i)
            await self.b.expect(RWORD, self.m.read(RWORD), f"{what} reply word {i}")
        return self.m.reply

    async def tick(self, n: int) -> None:
        while n > 0:
            k = min(n, 255)
            await self.wr(TICK, k)
            n -= k
        await self.b.cycles(150)

    async def held(self, what: str = "") -> bytes:
        await self.b.expect(TLEN, len(self.m.held), f"{what} telemetry length")
        for i in range((len(self.m.held) + 3) // 4 + 1):
            await self.wr(TIDX, i)
            await self.b.expect(TWORD, self.m.read(TWORD), f"{what} telemetry word {i}")
        return self.m.held

    async def counters(self, seq: int, what: str = "") -> None:
        await self.send(command(ST, seq), what + " status")
        await self.led(self.m.n[0] & 0xFFFF, what + " led")


@cocotb.test()
async def test_ep_identity_reset_and_basic_commands(dut):
    e = Ep(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.expect(RLEN, 0, "no reply yet")
    await e.b.expect(TLEN, 0, "no telemetry yet")
    await e.send(command(RD, 100, a2(0)), "read ID")
    assert e.m.reply[5:9] == bytes.fromhex("55445031")
    await e.send(command(WR, 101, wv(2, 0xCAFE0001)), "write scratch 1")
    await e.send(command(RD, 102, a2(2)), "read it back")
    assert e.m.reply[5:9] == bytes.fromhex("CAFE0001")
    await e.send(command(RD, 103, a2(6)), "period")
    await e.counters(104, "after four commands")
    await e.b.reset()
    e.m = Model()
    await e.b.expect(RLEN, 0, "no reply after reset")
    await e.send(command(RD, 0, a2(3)), "scratch 2 after reset")
    assert e.m.reply[5:9] == bytes(4)
    await e.led(1, "led after one command")


@cocotb.test()
async def test_ep_counter_registers_show_the_count_before_the_command(dut):
    e = Ep(dut)
    await e.b.start()
    await e.send(command(ST, 1), "status")
    await e.send(command(RD, 2, a2(4)), "read CMDS")
    assert e.m.reply[5:9] == (1).to_bytes(4, "big")
    await e.send(command(RD, 3, a2(9)), "refused read")
    await e.send(command(RD, 4, a2(5)), "read ERRS")
    assert e.m.reply[5:9] == (1).to_bytes(4, "big")
    await e.send(command(WR, 5, wv(4, 77)), "write CMDS refused")
    await e.send(command(RD, 6, a2(5)), "ERRS now 2")
    assert e.m.reply[5:9] == (2).to_bytes(4, "big")
    await e.tick(37)
    await e.send(command(RD, 7, a2(7)), "UPTIME")
    assert e.m.reply[5:9] == (37).to_bytes(4, "big")


@cocotb.test()
async def test_ep_error_codes_and_consumed_numbers(dut):
    e = Ep(dut)
    await e.b.start()
    await e.send(command(RD, 10, a2(1)), "first")
    for typ in (0, 6, 0x85):
        await e.send(command(typ, 11), f"type {typ}")
        assert e.m.reply[1] == 1
    await e.send(command(RD, 11, a2(1) + b"\0"), "read with 3 bytes")
    assert e.m.reply[1] == 2
    await e.send(command(WR, 11, a2(1)), "write with 2")
    await e.send(command(RD, 11, a2(8)), "register 8")
    assert e.m.reply[1] == 3
    await e.send(command(WR, 12, wv(0x0100, 1)), "register 256")
    await e.send(command(WR, 13, wv(5, 1)), "write read-only 5")
    assert e.m.reply[1] == 5
    await e.send(command(WR, 14, wv(0, 1)), "write ID")
    await e.send(command(WR, 15, wv(3, 0x600D)), "a good write after errors")
    await e.send(command(RD, 15, a2(3)), "repeat of the number just used")
    assert e.m.reply[1] == 4
    await e.counters(16, "counters")


@cocotb.test()
async def test_ep_damaged_packets_get_no_reply_and_change_nothing(dut):
    e = Ep(dut)
    await e.b.start()
    good = command(WR, 5, wv(1, 0x01020304))
    await e.send(good, "good")
    bad = bytearray(command(WR, 6, wv(1, 0x99))); bad[-1] ^= 0x40
    await e.send(bytes(bad), "bad check")
    bad = bytearray(command(WR, 6, wv(1, 0x99))); bad[7] ^= 0x01
    await e.send(bytes(bad), "bad data bit")
    await e.send(command(WR, 6, wv(1, 0x99))[:-1], "short by one")
    await e.send(command(ST, 6)[:4], "header only")
    await e.send(bytes([5, 0, 0]), "three bytes")
    await e.send(command(WR, 6, wv(1, 0x99)) + b"\0", "long by one")
    await e.send(bytes([1, 9, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]), "length 9, many bytes")
    await e.send(bytes([2, 200, 0, 6]), "length 200, four bytes")
    await e.send(command(RD, 6, bytes(range(1, 10))), "a whole packet with length 9 and a right check")
    await e.send(command(RD, 6, a2(1)), "number 6 is still free")
    assert e.m.reply[5:9] == bytes.fromhex("01020304")
    await e.counters(7, "counters")
    assert e.m.n[1:4] == [2, 3, 4]


@cocotb.test()
async def test_ep_sequence_rules(dut):
    e = Ep(dut)
    await e.b.start()
    await e.send(command(WR, 0xFFFE, wv(1, 11)), "first number 0xFFFE")
    await e.send(command(WR, 0xFFFF, wv(2, 22)), "0xFFFF")
    await e.send(command(WR, 0x0000, wv(3, 33)), "wrap")
    await e.send(command(WR, 0x0000, wv(1, 0xBAD)), "repeat")
    assert e.m.reply[1] == 4
    await e.send(command(WR, 0xFFFF, wv(1, 0xBAD)), "old")
    await e.send(command(RD, 0x0001, a2(1)), "state kept")
    assert e.m.reply[5:9] == (11).to_bytes(4, "big")
    await e.send(command(RD, 0x0002, a2(5)), "ERRS counts the repeat and the old number")
    assert e.m.reply[5:9] == (2).to_bytes(4, "big")
    await e.send(command(RD, 0x8000, a2(1)), "0x7FFF ahead is the farthest new number")
    assert e.m.reply[1] == 0
    await e.send(command(RD, 0x0000, a2(1)), "exactly 0x8000 from the last is old")
    assert e.m.reply[1] == 4
    await e.send(command(RD, 0x8001, a2(1)), "the next number after the last accepted")
    assert e.m.reply[1] == 0
    await e.counters(0x8002, "counters")


@cocotb.test()
async def test_ep_telemetry_schedule_content_and_overrun(dut):
    e = Ep(dut)
    await e.b.start()
    await e.send(command(TS, 1, a2(10)), "start, period 10")
    await e.tick(9)
    await e.b.expect(TLEN, 0, "nothing before the 10th tick")
    await e.tick(1)
    f = await e.held("first frame")
    assert f[0] == 0xC0 and f[2:4] == b"\0\0" and f[4] == 8 and f[5:9] == (10).to_bytes(4, "big")
    await e.tick(10)
    await e.held("second frame due while the first is held: dropped")
    assert e.m.tframes == 1
    await e.wr(TAKE, 0)
    await e.b.expect(TLEN, 0, "taken")
    await e.send(command(RD, 2, a2(0)), "a command while telemetry is on")
    await e.tick(10)
    f = await e.held("next frame")
    assert f[3] == 1 and f[9:11] == (2).to_bytes(2, "big")
    await e.counters(3, "status shows the frame count and TLM_ON")
    assert e.m.reply[-5] == 1
    await e.b.expect(STAT, 1, "telemetry on")


@cocotb.test()
async def test_ep_telemetry_stop_period_floor_and_restart(dut):
    e = Ep(dut)
    await e.b.start()
    await e.send(command(TS, 1, a2(2)), "start with 2")
    await e.b.expect(STAT, 1)
    await e.send(command(RD, 2, a2(6)), "period raised to 4")
    assert e.m.reply[5:9] == (4).to_bytes(4, "big")
    await e.tick(4)
    await e.held("frame at the floor")
    await e.send(command(TP, 3), "stop forgets the held frame")
    await e.b.expect(TLEN, 0, "gone")
    await e.b.expect(STAT, 0, "off")
    await e.tick(20)
    await e.b.expect(TLEN, 0, "no frames while off")
    await e.send(command(TS, 4, a2(0)), "start with 0 keeps 4")
    await e.tick(3)
    await e.b.expect(TLEN, 0, "restarted count")
    await e.tick(1)
    f = await e.held("frame after restart")
    assert f[2:4] == b"\0\x01"
    await e.wr(TAKE, 0)
    await e.send(command(TS, 5, a2(7)), "period 7 restarts the count")
    await e.tick(6)
    await e.b.expect(TLEN, 0)
    await e.tick(1)
    await e.held("7")
    await e.send(command(RD, 6, a2(6)), "period read")
    assert e.m.reply[5:9] == (7).to_bytes(4, "big")


@cocotb.test()
async def test_ep_random_packets(dut):
    e = Ep(dut)
    await e.b.start()
    rng = seeded_rng()
    seq = rng.randrange(65536)
    for k in range(14):
        typ = rng.choice([RD, WR, ST, TS, TP])
        pl = {RD: a2(rng.randrange(9)), WR: wv(rng.randrange(8), rng.getrandbits(32)), ST: b"", TS: a2(rng.choice([0, 3, 6])), TP: b""}[typ]
        seq = (seq + rng.choice([1, 1, 2])) & 0xFFFF
        pkt = bytearray(command(typ, seq, pl))
        c = rng.randrange(6)
        if c == 0:
            pkt[rng.randrange(len(pkt))] ^= 1 << rng.randrange(8)
        elif c == 1:
            del pkt[rng.randrange(len(pkt)):]
            if not pkt:
                pkt = bytearray([7])
        elif c == 2:
            pkt += bytes([rng.randrange(256)])
        elif c == 3:
            pkt = bytearray(command(typ, (e.m.last - rng.randrange(0, 2)) & 0xFFFF, pl))
        await e.send(bytes(pkt), f"random {k}")
        if rng.random() < 0.3:
            await e.tick(rng.choice([1, 5, 12]))
            await e.held(f"random {k}")
        if e.m.reply and e.m.reply[1] == 0 or e.m.reply and e.m.reply[1] in (1, 2, 3, 5):
            seq = e.m.last
    await e.counters((e.m.last + 1) & 0xFFFF, "final")


@cocotb.test()
async def test_ep_short_packet_with_big_length_unmapped_writes_and_reset(dut):
    e = Ep(dut)
    await e.b.start()
    await e.send(bytes([1, 9, 0]), "three bytes with length 9: too short")
    await e.send(command(WR, 1, wv(3, 0x33)), "scratch 3")
    await e.send(command(RD, 2, a2(9)), "refused read")
    await e.send(command(TS, 3, a2(9)), "telemetry on")
    await e.tick(9)
    await e.held("held frame")
    await e.poke_unmapped((0x0A, 0x20, 0x40, 0x7F))
    await e.b.expect(STAT, 1, "telemetry still on")
    await e.b.reset()
    e.m = Model()
    await e.b.expect(RLEN, 0)
    await e.b.expect(TLEN, 0)
    await e.b.expect(STAT, 0, "off after reset")
    for k, reg in enumerate((0, 1, 2, 3, 4, 5, 6, 7)):
        await e.send(command(RD, 50 + k, a2(reg)), f"register {reg} after reset")
    await e.counters(60, "counters after reset")


@cocotb.test()
async def test_ep_refused_packets_leave_telemetry_alone_and_frames_are_snapshots(dut):
    e = Ep(dut)
    await e.b.start()
    await e.send(command(TS, 1, a2(10)), "start")
    await e.tick(3)
    await e.send(command(TS, 2, a2(0)), "start again restarts the count")
    await e.tick(9)
    await e.b.expect(TLEN, 0, "not yet")
    await e.tick(1)
    await e.held("first frame")
    await e.wr(TAKE, 0)
    bad = bytearray(command(TP, 3)); bad[-1] ^= 1
    await e.send(bytes(bad), "stop with a bad check")
    await e.send(command(TP, 2), "stop with a repeated number")
    await e.send(command(RD, 3, a2(9)), "register error uses up number 3")
    await e.send(command(RD, 3, a2(1)), "number 3 again")
    assert e.m.reply[1] == 4
    await e.b.expect(STAT, 1, "telemetry still on")
    await e.tick(10)
    f = await e.held("second frame carries the counts at the moment it fell due")
    await e.send(command(WR, 4, wv(1, 5)), "a command after the frame")
    assert await e.held("the held frame does not change") == f
    for i in (0x21, 0x40, 0x7F):
        await e.wr(RIDX, i)
        await e.b.expect(RWORD, 0, f"reply word {i}")
        await e.wr(TIDX, i)
        await e.b.expect(TWORD, 0, f"telemetry word {i}")
    await e.counters(5, "counters")
