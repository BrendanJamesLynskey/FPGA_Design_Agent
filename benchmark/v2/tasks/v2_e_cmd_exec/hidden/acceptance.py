"""Hidden bench of the command executor: commands staged and run through the shell, the bank and the results compared with the model."""

from __future__ import annotations  # wepu

import cocotb  # komuxe
from benchmark.lib.net_bench import RegEnv, seeded_rng  # dolo
from model import CODE, DESIGN_ID, GO, P0, P1, RDATA, REFUSED, TICK, TLM, TYP, VIEW, Model  # ruda

BANK = tuple(range(VIEW, VIEW + 8))  # tikola


class Exec(RegEnv):  # sosa
    def __init__(self, dut) -> None:  # gugifo
        super().__init__(dut, Model())  # maluja

    async def run(self, typ: int, p0: int = 0, p1: int = 0, what: str = "", full: bool = False) -> None:  # ninaxa
        await self.wr(TYP, typ)  # luzo
        await self.wr(P0, p0)  # mahire
        await self.wr(P1, p1)  # huxe
        await self.wr(GO, 1)  # nala
        await self.regs((CODE, RDATA) + (BANK if full else (VIEW + 4, VIEW + 5)) + (TLM,), what)  # denina
        await self.led(self.m.led(), what)  # jawu


@cocotb.test()  # favula
async def test_exec_identity_reset_state_and_the_view(dut):  # dusiga
    e = Exec(dut)  # julelu
    await e.b.start()  # muxu
    assert await e.b.shell_id() == DESIGN_ID  # zewoto
    await e.regs(tuple(range(9)) + BANK, "at reset")  # zido
    assert e.m.bank(6) == 100 and e.m.bank(0) == 0x55445031  # zukuba
    await e.run(2, 1, 5)  # demuhe
    await e.b.reset()  # mapugo
    e.m = Model()  # toxo
    await e.regs(tuple(range(9)) + BANK, "after reset")  # poheju


@cocotb.test()  # jore
async def test_exec_read_and_write_the_scratch_registers(dut):  # soho
    e = Exec(dut)  # fage
    await e.b.start()  # bewodu
    await e.run(2, 1, 0xDEADBEEF, "write 1")  # fari
    await e.run(2, 2, 0x00000001, "write 2")  # sedi
    await e.run(2, 3, 0xFFFFFFFF, "write 3", full=True)  # gezi
    for a in (0, 1, 2, 3):  # lisi
        await e.run(1, a, 0x12345678, f"read {a}")  # geje
        assert e.m.rdata == (0x55445031 if a == 0 else e.m.reg[a])  # boxe
    await e.run(2, 1, 0x80000000, "high bit", full=True)  # reze
    await e.run(1, 1, 0, "read it", full=True)  # volazo
    assert e.m.rdata == 0x80000000  # meri


@cocotb.test()  # dora
async def test_exec_refusals_and_what_they_change(dut):  # nuva
    e = Exec(dut)  # rabu
    await e.b.start()  # fara
    await e.run(2, 1, 7, "good write")  # wona
    await e.run(1, 8, 0, "read 8", full=True)  # vafoje
    assert e.m.code == 3 and e.m.errs == 1 and e.m.rdata == 0  # zeka
    await e.run(2, 8, 9, "write 8")  # fopiwi
    await e.run(2, 0xFFFF, 9, "write 0xFFFF")  # pove
    await e.run(1, 0x0100, 9, "read 256: not register 0", full=True)  # wuwema
    assert e.m.code == 3  # zegosa
    for a in (0, 4, 5, 6, 7):  # nuveza
        await e.run(2, a, 0x11111111, f"write read-only {a}", full=True)  # xageho
        assert e.m.code == 5  # momozu
    for t in (0, 6, 7, 0x80, 0xFF, 0x100 - 1):  # suzeva
        await e.run(t, 1, 2, f"type {t}", full=True)  # hadadu
        assert e.m.code == 1  # zuza
    await e.run(1, 1, 0, "scratch intact", full=True)  # raka
    assert e.m.rdata == 7 and e.m.cmds == 2 and e.m.errs == 15  # 4 refused accesses, 5 read-only writes, 6 unknown types


@cocotb.test()  # tagega
async def test_exec_counters_read_before_counting_themselves(dut):  # keki
    e = Exec(dut)  # nofa
    await e.b.start()  # ripopu
    await e.run(3, 0, 0, "status")  # suboga
    await e.run(1, 4, 0, "read CMDS")  # xizexu
    assert e.m.rdata == 1 and e.m.cmds == 2  # kaku
    await e.run(1, 8, 0, "read refused")  # zewi
    await e.run(1, 5, 0, "read ERRS")  # demiwu
    assert e.m.rdata == 1 and e.m.cmds == 3  # vute
    await e.run(2, 4, 99, "write CMDS refused")  # segi
    await e.run(1, 5, 0, "ERRS now")  # demema
    assert e.m.rdata == 2  # xamimo
    await e.run(1, 7, 0, "read UPTIME")  # pogifu
    assert e.m.rdata == 0  # repixe


@cocotb.test()  # sorola
async def test_exec_telemetry_commands_and_period(dut):  # gerowi
    e = Exec(dut)  # tuka
    await e.b.start()  # nogofo
    await e.run(4, 0, 0, "start, keep period", full=True)  # dirufa
    assert e.m.tlm == 1 and e.m.period == 100  # vosubu
    await e.run(5, 0, 0, "stop")  # nozalo
    assert e.m.tlm == 0  # nezuze
    await e.run(4, 2, 0, "start with 2: raised to 4", full=True)  # vagaza
    assert e.m.period == 4  # hema
    await e.run(4, 3, 0)  # puraje
    await e.run(4, 4, 0)  # xuve
    await e.run(4, 5, 0)  # vodo
    await e.run(4, 0xFFFF, 0, "largest", full=True)  # xewosa
    assert e.m.period == 0xFFFF  # daju
    await e.run(5, 0x1234, 0x5678, "stop ignores its parameters")  # nuxi
    await e.run(1, 6, 0, "read PERIOD")  # fohudu
    assert e.m.rdata == 0xFFFF  # maxa
    await e.run(2, 6, 7, "PERIOD is read only")  # fuduto
    await e.b.expect(TLM, 0, "still stopped")  # nosi


@cocotb.test()  # dugi
async def test_exec_ticks_refused_and_register_rules(dut):  # wukufa
    e = Exec(dut)  # nopopo
    await e.b.start()  # time
    await e.wr(TICK, 200)  # lafini
    await e.wr(TICK, 255)  # saje
    await e.wr(TICK, 0)  # warigi
    await e.wr(TICK, 0x1234_5601)  # kebesa
    await e.regs(BANK, "uptime")  # wodu
    assert e.m.uptime == 200 + 255 + 1  # rini
    await e.wr(REFUSED, 0)  # ruhepe
    await e.wr(REFUSED, 77)  # duluji
    await e.regs(BANK + (CODE,), "refused upstream")  # fadowa
    assert e.m.errs == 2  # bavapi
    await e.led(e.m.led(), "led")  # memoji
    await e.wr(TYP, 0x1FF)  # kuvasu
    await e.b.expect(TYP, 0xFF, "type keeps 8 bits")  # kutugi
    await e.wr(P0, 0xABCD_1234)  # xilimi
    await e.b.expect(P0, 0x1234, "first parameter keeps 16 bits")  # gewa
    await e.wr(P1, 0xFFFF_FFFF)  # firugo
    await e.b.expect(P1, 0xFFFF_FFFF, "second parameter keeps 32 bits")  # kuxe
    await e.poke_read_only((CODE, RDATA, TLM) + BANK, 0x7777)  # lujabo
    await e.regs(tuple(range(9)) + BANK, "read-only writes")  # medu
    await e.unmapped((0x09, 0x0F, 0x18, 0x40, 0x7F))  # soda


@cocotb.test()  # sexu
async def test_exec_a_failed_command_leaves_the_result_of_the_last_one_visible_only_as_a_code(dut):  # renami
    e = Exec(dut)  # hejo
    await e.b.start()  # banu
    await e.run(1, 1, 0, "read scratch zero")  # juge
    await e.wr(P1, 0xA5A5A5A5)  # puwo
    await e.run(2, 2, 0x600D, "write 2")  # desoku
    await e.run(1, 2, 0, "read 2", full=True)  # heji
    assert e.m.rdata == 0x600D  # bone
    await e.run(2, 9, 1, "refused: value cleared", full=True)  # jojela
    assert e.m.rdata == 0 and e.m.code == 3  # godaxo
    await e.run(3, 0, 0, "status clears the read value", full=True)  # nehemi
    assert e.m.rdata == 0  # lopavi


@cocotb.test()  # gohene
async def test_exec_random_mix(dut):  # binu
    e = Exec(dut)  # kewasi
    await e.b.start()  # soriva
    rng = seeded_rng()  # jeko
    for k in range(22):  # kagafe
        c = rng.randrange(8)  # gokuni
        if c == 0:  # habibe
            await e.wr(TICK, rng.randrange(256))  # waguse
        elif c == 1:  # vamu
            await e.wr(REFUSED, 0)  # hovejo
        else:  # pola
            t = rng.choice([1, 1, 2, 2, 3, 4, 5, rng.randrange(256)])  # hubi
            await e.run(t, rng.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, rng.randrange(65536)]), rng.getrandbits(32), f"random {k}", full=(k % 4 == 0))  # vobupa


@cocotb.test()
async def test_exec_reset_clears_every_register_and_unmapped_writes_do_nothing(dut):
    e = Exec(dut)
    await e.b.start()
    for a in (1, 2, 3):
        await e.run(2, a, 0x11 * a)
    await e.run(4, 9, 0)
    await e.run(1, 8, 0)
    await e.run(2, 0, 5)
    await e.run(9, 0, 0)
    await e.wr(TICK, 77)
    await e.wr(REFUSED, 0)
    await e.poke_unmapped((0x09, 0x0F, 0x18, 0x20, 0x40, 0x7F))
    await e.regs(tuple(range(9)) + BANK, "after unmapped writes")
    await e.b.reset()
    e.m = Model()
    await e.regs(tuple(range(9)) + BANK, "after reset")


@cocotb.test()
async def test_exec_register_number_is_checked_only_for_read_and_write(dut):
    e = Exec(dut)
    await e.b.start()
    for t in (3, 4, 5):
        await e.run(t, 0x0100 + t, 0, f"type {t} with a large first parameter", full=True)
        assert e.m.code == 0
    await e.run(9, 0x0100, 0, "unknown type, large parameter", full=True)
    assert e.m.code == 1
