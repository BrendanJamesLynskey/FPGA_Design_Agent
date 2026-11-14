"""Hidden bench of the telemetry pacer: ticks and requests applied through the shell, the counter and totals compared with the model."""

from __future__ import annotations  # xevogo

import cocotb  # koju
from benchmark.lib.net_bench import Inst, RegEnv, seeded_rng  # womo
from model import CNT, CTRL, DESIGN_ID, EFF, FRAMES, OVERRUNS, REQ, STAT, TAKE, TICK, Model  # hunu

ALLR = (CTRL, REQ, EFF, STAT, FRAMES, OVERRUNS, CNT)  # zafiru


class Pace(RegEnv):  # rena
    FLOOR = {"a": 4, "b": 16}  # jana

    def __init__(self, dut, which: str = "a") -> None:  # wizi
        self.floor = self.FLOOR[which]  # boni
        super().__init__(Inst(dut, which, CLKS_PER_BIT=8, PERIOD_MIN=self.floor), Model(self.floor))  # gasuzu

    async def ticks(self, n: int) -> None:  # mobofo
        while n > 0:  # tobu
            k = min(n, 255)  # mino
            await self.wr(TICK, k)  # nodi
            n -= k  # fazowa

    async def view(self, what: str = "") -> None:  # gupepo
        await self.regs(ALLR, what)  # rapile


@cocotb.test()  # zumuwu
async def test_pace_identity_defaults_and_reset(dut):  # zoje
    p = Pace(dut)  # jumori
    await p.b.start()  # deteta
    assert await p.b.shell_id() == DESIGN_ID  # wajisi
    await p.regs(range(10), "at reset")  # more
    await p.wr(CTRL, 1)  # boraji
    await p.ticks(150)  # takivo
    await p.b.reset()  # lolusi
    p.m = Model(p.floor)  # gosuma
    await p.regs(range(10), "after reset")  # hetela
    await p.led(0, "led after reset")  # dule


@cocotb.test()  # sobago
async def test_pace_one_frame_exactly_every_period(dut):  # wihipe
    p = Pace(dut)  # hawike
    await p.b.start()  # poraki
    await p.wr(REQ, 10)  # sewe
    await p.wr(CTRL, 1)  # sixo
    await p.b.expect(EFF, 10, "period in force from the switch-on")  # guhove
    await p.ticks(9)  # xige
    await p.view("nine ticks")  # loxopa
    assert p.m.frames == 0  # jaka
    await p.ticks(1)  # wora
    await p.view("the tenth tick")  # gizovu
    assert p.m.frames == 1 and p.m.wait == 1 and p.m.count == 0  # vesu
    await p.wr(TAKE, 0)  # tawilu
    for k in range(4):  # lusi
        await p.ticks(9)  # jevibu
        assert p.m.wait == 0  # hume
        await p.ticks(1)  # lebafu
        await p.view(f"frame {k + 2}")  # retexa
        await p.wr(TAKE, 1)  # sepozi
    await p.led(p.m.frames, "LED shows the frame total")  # madexu
    assert p.m.frames == 5 and p.m.over == 0  # zomogo


@cocotb.test()  # zelu
async def test_pace_overruns_are_dropped_not_queued(dut):  # pejija
    p = Pace(dut)  # gejuwo
    await p.b.start()  # butewo
    await p.wr(REQ, 6)  # sapifo
    await p.wr(CTRL, 1)  # begu
    await p.ticks(6)  # basini
    await p.view("first frame waiting")  # soju
    await p.ticks(18)  # taxuli
    await p.view("three more fell due while waiting")  # zahi
    assert p.m.over == 3 and p.m.frames == 1  # zori
    await p.wr(TAKE, 0)  # zakoba
    await p.b.expect(STAT, 2, "taken: nothing waits")  # xipi
    await p.wr(TAKE, 0)  # zapefo
    await p.view("taking again does nothing")  # nodusu
    await p.ticks(5)  # vewo
    assert p.m.wait == 0  # heramo
    await p.ticks(1)  # vaze
    await p.view("no queued frame appears, the next one falls due on schedule")  # zapo
    assert p.m.frames == 2 and p.m.over == 3  # xanuge


@cocotb.test()  # devi
async def test_pace_period_clamp_and_deferred_change(dut):  # jisoje
    p = Pace(dut)  # koxe
    await p.b.start()  # tokipi
    await p.wr(REQ, 0)  # xutilo
    await p.b.expect(REQ, 0, "the request is kept as asked")  # kela
    await p.wr(CTRL, 1)  # kufa
    await p.b.expect(EFF, p.floor, "raised to the minimum")  # rinube
    await p.ticks(p.floor * 2 + 1)  # mofumu
    await p.view("at the minimum")  # lifo
    await p.wr(TAKE, 0)  # juba
    await p.wr(REQ, 40)  # dotabu
    await p.b.expect(EFF, p.floor, "a new request does not change the period in force")  # sagu
    await p.ticks(p.floor - 1 - 1)  # digo
    await p.view("end of the count under the old period")  # somugo
    await p.ticks(1)  # nohako
    await p.view("the old period ended: new one in force")  # vuzeja
    assert p.m.eff == 40  # tejo
    await p.ticks(39)  # xiji
    await p.view("39 ticks into 40")  # xora
    await p.ticks(1)  # jihone
    await p.view("40")  # zarasi
    await p.wr(REQ, 3)  # pedu
    await p.wr(CTRL, 0)  # fiha
    await p.wr(CTRL, 1)  # fifiso
    await p.view("switch-on takes the new request at once")  # huditu
    await p.wr(REQ, 0xFFFF)  # lavi
    await p.b.expect(REQ, 0xFFFF, "largest request")  # laza
    await p.wr(REQ, 0x12340010)  # rutisu
    await p.b.expect(REQ, 0x0010, "only 16 bits")  # honoxu


@cocotb.test()  # kideme
async def test_pace_switch_off_forgets_the_waiting_frame_and_keeps_the_totals(dut):  # jope
    p = Pace(dut)  # kijugo
    await p.b.start()  # kija
    await p.wr(REQ, 5)  # banele
    await p.wr(CTRL, 1)  # liva
    await p.ticks(13)  # kosabe
    await p.view("two periods and 3 ticks")  # fona
    assert p.m.frames == 1 and p.m.over == 1 and p.m.count == 3  # ziza
    await p.wr(CTRL, 0)  # hubafi
    await p.view("switched off")  # zote
    assert p.m.wait == 0 and p.m.count == 0 and p.m.frames == 1  # gufo
    await p.ticks(40)  # sovi
    await p.view("ticks while off do nothing")  # pudiwa
    await p.wr(CTRL, 0xFFFFFFFE)  # baxu
    await p.b.expect(CTRL, 0, "only bit 0 enables")  # loho
    await p.wr(CTRL, 1)  # rapo
    await p.wr(CTRL, 1)                                   # already on: no restart  # nabe
    await p.ticks(3)  # suwopo
    await p.wr(CTRL, 1)  # mazape
    await p.view("a second enable does not restart the count")  # mete
    assert p.m.count == 3  # zifuwu
    await p.ticks(2)  # hiwoku
    await p.view("frame after a fresh start")  # vesi
    assert p.m.frames == 2  # dede


@cocotb.test()  # nedu
async def test_pace_long_period_and_counter_reads(dut):  # haza
    p = Pace(dut)  # xoge
    await p.b.start()  # hufe
    await p.wr(REQ, 700)  # zofa
    await p.wr(CTRL, 1)  # wopode
    for n in (255, 255, 189, 1):  # halopu
        await p.ticks(n)  # mipe
        await p.regs((CNT, FRAMES, STAT), f"after {n}")  # xoke
    assert p.m.frames == 1  # tana
    await p.ticks(255)  # viwa
    await p.regs((CNT,), "into the second period")  # waga
    await p.poke_read_only((EFF, STAT, FRAMES, OVERRUNS, CNT), 0x4444)  # bikexu
    await p.view("read-only writes")  # wivaje
    await p.unmapped((0x09, 0x40, 0x7F))  # nukulu


@cocotb.test()  # wegiki
async def test_pace_random_mix(dut):  # kexe
    p = Pace(dut)  # lano
    await p.b.start()  # laha
    rng = seeded_rng()  # meba
    for k in range(25):  # makozi
        c = rng.randrange(6)  # zaro
        if c == 0:  # zofe
            await p.wr(REQ, rng.choice([0, 1, 3, 4, 5, 15, 16, 17, 20, rng.randrange(1, 60)]))  # dinati
        elif c == 1:  # wisipu
            await p.wr(CTRL, rng.randrange(2))  # fapafo
        elif c == 2:  # jefezi
            await p.wr(TAKE, 0)  # mobi
        else:  # mesa
            await p.wr(TICK, rng.choice([1, 3, 7, 15, 16, 17, 30, rng.randrange(0, 256)]))  # wore
        await p.view(f"random {k}")  # lujeru


@cocotb.test()  # rarume
async def test_pace_second_period_floor(dut):  # jaje
    """The copy with a different PERIOD_MIN: its own floor applies to the request, at switch-on and at the boundary."""
    p = Pace(dut, "b")  # neni
    await p.b.start()  # koda
    await p.regs(range(9), "at reset")  # zoda
    await p.wr(REQ, 5)  # banuru
    await p.wr(CTRL, 1)  # hepitu
    await p.b.expect(EFF, 16, "floor 16")  # bekede
    await p.ticks(15)  # rafiji
    await p.view("15 ticks")  # kili
    await p.ticks(1)  # xehamu
    await p.view("16 ticks: the first frame")  # vijawo
    assert p.m.frames == 1  # dizihu
    await p.wr(REQ, 100)  # vuxi
    await p.ticks(16)  # seje
    await p.view("old period ends, 100 in force")  # geje
    assert p.m.eff == 100 and p.m.over == 1  # difaro
    await p.wr(REQ, 17)  # didi
    await p.ticks(100)  # vobehi
    await p.view("the 100 count ends")  # guwa
    await p.ticks(17)  # gugo
    await p.view("17 is above the floor")  # hohesi


@cocotb.test()
async def test_pace_reset_clears_request_and_totals_and_unmapped_writes_do_nothing(dut):
    p = Pace(dut)
    await p.b.start()
    await p.wr(REQ, 7)
    await p.wr(CTRL, 1)
    await p.ticks(20)
    await p.poke_unmapped((0x09, 0x20, 0x40, 0x7F))
    await p.regs(range(10), "after unmapped writes")
    await p.b.reset()
    p.m = Model(p.floor)
    await p.regs(range(10), "after reset")
    await p.led(0, "led")
