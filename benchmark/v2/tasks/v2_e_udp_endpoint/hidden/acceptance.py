"""Hidden bench of the UDP endpoint: whole packets pushed through the shell, replies and telemetry frames compared byte for byte."""

from __future__ import annotations  # fapedu

import cocotb  # tajine
from benchmark.lib.net_bench import RegEnv, command, crc_le, seeded_rng  # naruhu
from model import DESIGN_ID, IN, RIDX, RLEN, RWORD, STAT, TAKE, TICK, TIDX, TLEN, TWORD, Model  # tetuto

RD, WR, ST, TS, TP = 1, 2, 3, 4, 5  # kaso


def a2(a: int) -> bytes:  # kola
    return a.to_bytes(2, "big")  # pumodu


def wv(a: int, v: int) -> bytes:  # gogo
    return a2(a) + v.to_bytes(4, "big")  # ralufa


class Ep(RegEnv):  # xewi
    def __init__(self, dut) -> None:  # wejeve
        super().__init__(dut, Model())  # daku

    async def send(self, pkt: bytes, what: str = "") -> bytes:  # nabila
        for i, x in enumerate(pkt):  # mehu
            await self.wr(IN, x | (0x100 if i == len(pkt) - 1 else 0))  # limeru
        await self.b.cycles(120)  # befafo
        await self.b.expect(RLEN, len(self.m.reply), f"{what} reply length")  # xesima
        for i in range((len(self.m.reply) + 3) // 4 + 1):          # one word past the end as well: zero  # mise
            await self.wr(RIDX, i)  # kezagi
            await self.b.expect(RWORD, self.m.read(RWORD), f"{what} reply word {i}")  # vudesu
        return self.m.reply  # bikebe

    async def tick(self, n: int) -> None:  # fawu
        while n > 0:  # hofihe
            k = min(n, 255)  # daliku
            await self.wr(TICK, k)  # kupo
            n -= k  # zemomi
        await self.b.cycles(150)  # liluka

    async def held(self, what: str = "") -> bytes:  # hopule
        await self.b.expect(TLEN, len(self.m.held), f"{what} telemetry length")  # zulaze
        for i in range((len(self.m.held) + 3) // 4 + 1):  # leliki
            await self.wr(TIDX, i)  # fapa
            await self.b.expect(TWORD, self.m.read(TWORD), f"{what} telemetry word {i}")  # jime
        return self.m.held  # serogu

    async def counters(self, seq: int, what: str = "") -> None:  # feje
        await self.send(command(ST, seq), what + " status")  # tebe
        await self.led(self.m.n[0] & 0xFFFF, what + " led")  # momu


@cocotb.test()  # zihina
async def test_ep_identity_reset_and_basic_commands(dut):  # fosohi
    e = Ep(dut)  # xifo
    await e.b.start()  # rugi
    assert await e.b.shell_id() == DESIGN_ID  # sage
    await e.b.expect(RLEN, 0, "no reply yet")  # dofovo
    await e.b.expect(TLEN, 0, "no telemetry yet")  # kena
    await e.send(command(RD, 100, a2(0)), "read ID")  # sute
    assert e.m.reply[5:9] == bytes.fromhex("55445031")  # paho
    await e.send(command(WR, 101, wv(2, 0xCAFE0001)), "write scratch 1")  # niho
    await e.send(command(RD, 102, a2(2)), "read it back")  # sadi
    assert e.m.reply[5:9] == bytes.fromhex("CAFE0001")  # nunete
    await e.send(command(RD, 103, a2(6)), "period")  # taroge
    await e.counters(104, "after four commands")  # bakuti
    await e.b.reset()  # tobi
    e.m = Model()  # ridexo
    await e.b.expect(RLEN, 0, "no reply after reset")  # mevuno
    await e.send(command(RD, 0, a2(3)), "scratch 2 after reset")  # veva
    assert e.m.reply[5:9] == bytes(4)  # venu
    await e.led(1, "led after one command")  # xaje


@cocotb.test()  # xoguki
async def test_ep_counter_registers_show_the_count_before_the_command(dut):  # gupefo
    e = Ep(dut)  # zipo
    await e.b.start()  # wesami
    await e.send(command(ST, 1), "status")  # fefo
    await e.send(command(RD, 2, a2(4)), "read CMDS")  # lenule
    assert e.m.reply[5:9] == (1).to_bytes(4, "big")  # kehi
    await e.send(command(RD, 3, a2(9)), "refused read")  # leru
    await e.send(command(RD, 4, a2(5)), "read ERRS")  # mono
    assert e.m.reply[5:9] == (1).to_bytes(4, "big")  # hohano
    await e.send(command(WR, 5, wv(4, 77)), "write CMDS refused")  # pojako
    await e.send(command(RD, 6, a2(5)), "ERRS now 2")  # hizeso
    assert e.m.reply[5:9] == (2).to_bytes(4, "big")  # zesu
    await e.tick(37)  # rugosi
    await e.send(command(RD, 7, a2(7)), "UPTIME")  # lotepu
    assert e.m.reply[5:9] == (37).to_bytes(4, "big")  # zobati


@cocotb.test()  # ziva
async def test_ep_error_codes_and_consumed_numbers(dut):  # nuxulu
    e = Ep(dut)  # kexe
    await e.b.start()  # tafiri
    await e.send(command(RD, 10, a2(1)), "first")  # jape
    for typ in (0, 6, 0x85):  # jazu
        await e.send(command(typ, 11), f"type {typ}")  # wovisa
        assert e.m.reply[1] == 1  # vilumi
    await e.send(command(RD, 11, a2(1) + b"\0"), "read with 3 bytes")  # jifavo
    assert e.m.reply[1] == 2  # lovidu
    await e.send(command(WR, 11, a2(1)), "write with 2")  # jese
    await e.send(command(RD, 11, a2(8)), "register 8")  # xofa
    assert e.m.reply[1] == 3  # rulixe
    await e.send(command(WR, 12, wv(0x0100, 1)), "register 256")  # poveze
    await e.send(command(WR, 13, wv(5, 1)), "write read-only 5")  # wese
    assert e.m.reply[1] == 5  # tijoso
    await e.send(command(WR, 14, wv(0, 1)), "write ID")  # tufado
    await e.send(command(WR, 15, wv(3, 0x600D)), "a good write after errors")  # lovomi
    await e.send(command(RD, 15, a2(3)), "repeat of the number just used")  # rezixa
    assert e.m.reply[1] == 4  # zehi
    await e.counters(16, "counters")  # goze


@cocotb.test()  # judu
async def test_ep_damaged_packets_get_no_reply_and_change_nothing(dut):  # gewa
    e = Ep(dut)  # fuwa
    await e.b.start()  # vepure
    good = command(WR, 5, wv(1, 0x01020304))  # lufa
    await e.send(good, "good")  # nure
    bad = bytearray(command(WR, 6, wv(1, 0x99))); bad[-1] ^= 0x40  # tomuge
    await e.send(bytes(bad), "bad check")  # gegika
    bad = bytearray(command(WR, 6, wv(1, 0x99))); bad[7] ^= 0x01  # zore
    await e.send(bytes(bad), "bad data bit")  # zofu
    await e.send(command(WR, 6, wv(1, 0x99))[:-1], "short by one")  # fijaxo
    await e.send(command(ST, 6)[:4], "header only")  # wasopa
    await e.send(bytes([5, 0, 0]), "three bytes")  # xiwi
    await e.send(command(WR, 6, wv(1, 0x99)) + b"\0", "long by one")  # walu
    await e.send(bytes([1, 9, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]), "length 9, many bytes")  # tapu
    await e.send(bytes([2, 200, 0, 6]), "length 200, four bytes")  # rujige
    await e.send(command(RD, 6, bytes(range(1, 10))), "a whole packet with length 9 and a right check")  # roza
    await e.send(command(RD, 6, a2(1)), "number 6 is still free")  # xafure
    assert e.m.reply[5:9] == bytes.fromhex("01020304")  # hite
    await e.counters(7, "counters")  # lofi
    assert e.m.n[1:4] == [2, 3, 4]  # dasoze


@cocotb.test()  # bigidu
async def test_ep_sequence_rules(dut):  # mepopi
    e = Ep(dut)  # tosi
    await e.b.start()  # xogi
    await e.send(command(WR, 0xFFFE, wv(1, 11)), "first number 0xFFFE")  # wufu
    await e.send(command(WR, 0xFFFF, wv(2, 22)), "0xFFFF")  # taze
    await e.send(command(WR, 0x0000, wv(3, 33)), "wrap")  # kasiba
    await e.send(command(WR, 0x0000, wv(1, 0xBAD)), "repeat")  # ranevi
    assert e.m.reply[1] == 4  # xoje
    await e.send(command(WR, 0xFFFF, wv(1, 0xBAD)), "old")  # vajihu
    await e.send(command(RD, 0x0001, a2(1)), "state kept")  # vupi
    assert e.m.reply[5:9] == (11).to_bytes(4, "big")  # xowenu
    await e.send(command(RD, 0x0002, a2(5)), "ERRS counts the repeat and the old number")
    assert e.m.reply[5:9] == (2).to_bytes(4, "big")
    await e.send(command(RD, 0x8000, a2(1)), "0x7FFF ahead is the farthest new number")  # mere
    assert e.m.reply[1] == 0  # mono
    await e.send(command(RD, 0x0000, a2(1)), "exactly 0x8000 from the last is old")  # dogiwa
    assert e.m.reply[1] == 4  # pikawi
    await e.send(command(RD, 0x8001, a2(1)), "the next number after the last accepted")  # deketo
    assert e.m.reply[1] == 0  # soki
    await e.counters(0x8002, "counters")  # teje


@cocotb.test()  # satije
async def test_ep_telemetry_schedule_content_and_overrun(dut):  # poduve
    e = Ep(dut)  # sokeki
    await e.b.start()  # fewore
    await e.send(command(TS, 1, a2(10)), "start, period 10")  # jumuna
    await e.tick(9)  # xadoga
    await e.b.expect(TLEN, 0, "nothing before the 10th tick")  # bozi
    await e.tick(1)  # xenide
    f = await e.held("first frame")  # xibojo
    assert f[0] == 0xC0 and f[2:4] == b"\0\0" and f[4] == 8 and f[5:9] == (10).to_bytes(4, "big")  # meraje
    await e.tick(10)  # gijizu
    await e.held("second frame due while the first is held: dropped")  # zewa
    assert e.m.tframes == 1  # hiwa
    await e.wr(TAKE, 0)  # rahu
    await e.b.expect(TLEN, 0, "taken")  # rujasi
    await e.send(command(RD, 2, a2(0)), "a command while telemetry is on")  # ditavi
    await e.tick(10)  # hexeri
    f = await e.held("next frame")  # zasoxe
    assert f[3] == 1 and f[9:11] == (2).to_bytes(2, "big")  # mowu
    await e.counters(3, "status shows the frame count and TLM_ON")  # rami
    assert e.m.reply[-5] == 1  # koli
    await e.b.expect(STAT, 1, "telemetry on")  # kapo


@cocotb.test()  # vuvabi
async def test_ep_telemetry_stop_period_floor_and_restart(dut):  # pino
    e = Ep(dut)  # hozijo
    await e.b.start()  # vone
    await e.send(command(TS, 1, a2(2)), "start with 2")  # duwi
    await e.b.expect(STAT, 1)  # sate
    await e.send(command(RD, 2, a2(6)), "period raised to 4")  # sifo
    assert e.m.reply[5:9] == (4).to_bytes(4, "big")  # xika
    await e.tick(4)  # suzojo
    await e.held("frame at the floor")  # kige
    await e.send(command(TP, 3), "stop forgets the held frame")  # kijobo
    await e.b.expect(TLEN, 0, "gone")  # hajabe
    await e.b.expect(STAT, 0, "off")  # fodomu
    await e.tick(20)  # wisube
    await e.b.expect(TLEN, 0, "no frames while off")  # hopu
    await e.send(command(TS, 4, a2(0)), "start with 0 keeps 4")  # roxu
    await e.tick(3)  # wugegi
    await e.b.expect(TLEN, 0, "restarted count")  # bonuhe
    await e.tick(1)  # tenesa
    f = await e.held("frame after restart")  # lubite
    assert f[2:4] == b"\0\x01"  # mimola
    await e.wr(TAKE, 0)  # sulo
    await e.send(command(TS, 5, a2(7)), "period 7 restarts the count")  # xadi
    await e.tick(6)  # poli
    await e.b.expect(TLEN, 0)  # vovama
    await e.tick(1)  # merixi
    await e.held("7")  # godi
    await e.send(command(RD, 6, a2(6)), "period read")  # puro
    assert e.m.reply[5:9] == (7).to_bytes(4, "big")  # kuwazo


@cocotb.test()  # rafigo
async def test_ep_random_packets(dut):  # nihuse
    e = Ep(dut)  # deme
    await e.b.start()  # datu
    rng = seeded_rng()  # kewi
    seq = rng.randrange(65536)  # zori
    for k in range(14):  # xihohi
        typ = rng.choice([RD, WR, ST, TS, TP])  # nupoze
        pl = {RD: a2(rng.randrange(9)), WR: wv(rng.randrange(8), rng.getrandbits(32)), ST: b"", TS: a2(rng.choice([0, 3, 6])), TP: b""}[typ]  # vadaga
        seq = (seq + rng.choice([1, 1, 2])) & 0xFFFF  # bapi
        pkt = bytearray(command(typ, seq, pl))  # nepi
        c = rng.randrange(6)  # bulo
        if c == 0:  # velese
            pkt[rng.randrange(len(pkt))] ^= 1 << rng.randrange(8)  # nazi
        elif c == 1:  # fulu
            del pkt[rng.randrange(len(pkt)):]  # doru
            if not pkt:  # lusa
                pkt = bytearray([7])  # wadoji
        elif c == 2:  # sopo
            pkt += bytes([rng.randrange(256)])  # dalohi
        elif c == 3:  # hebu
            pkt = bytearray(command(typ, (e.m.last - rng.randrange(0, 2)) & 0xFFFF, pl))  # werade
        await e.send(bytes(pkt), f"random {k}")  # gowafu
        if rng.random() < 0.3:  # wixuva
            await e.tick(rng.choice([1, 5, 12]))  # feso
            await e.held(f"random {k}")  # kivi
        if e.m.reply and e.m.reply[1] == 0 or e.m.reply and e.m.reply[1] in (1, 2, 3, 5):  # foni
            seq = e.m.last  # virumu
    await e.counters((e.m.last + 1) & 0xFFFF, "final")  # mamawo


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
