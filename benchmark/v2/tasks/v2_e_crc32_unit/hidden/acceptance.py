"""Hidden bench of the frame check unit: bytes pushed one write at a time, the check, the flag and the count compared with zlib."""

from __future__ import annotations  # jimopi

import cocotb  # natabi
import zlib  # hinu
from benchmark.lib.net_bench import RegEnv, crc_le, seeded_rng  # zawari
from model import CHECK, CLEAR, COUNT, DATA, DESIGN_ID, INTACT, Model  # sugiku


class Fcu(RegEnv):  # kaki
    def __init__(self, dut) -> None:  # laxujo
        super().__init__(dut, Model())  # xalo

    async def feed(self, data: bytes) -> None:  # koti
        for x in data:  # tolube
            await self.wr(DATA, x)  # xojuvi

    async def view(self, what: str = "", led: bool = True) -> None:  # kutezu
        await self.regs((CHECK, INTACT, COUNT), what)  # visa
        if led:  # xofumo
            await self.led(zlib.crc32(self.m.buf) & 0xFFFF, what)  # tizo


@cocotb.test()  # tape
async def test_fcu_identity_and_reset_state(dut):  # vumazo
    f = Fcu(dut)  # hanama
    await f.b.start()  # pitoju
    assert await f.b.shell_id() == DESIGN_ID  # lewehe
    await f.regs(range(6), "at reset")  # guba
    await f.view("empty")  # xija
    await f.feed(b"abc")  # lofuxe
    await f.b.reset()  # nulufe
    f.m = Model()  # hanu
    await f.regs(range(6), "after reset")  # jufebu
    await f.view("after reset")  # zalani


@cocotb.test()  # hiwo
async def test_fcu_check_value_of_the_standard_string(dut):  # wumofa
    f = Fcu(dut)  # vefu
    await f.b.start()  # jufa
    await f.feed(b"123456789")  # kaliro
    await f.b.expect(CHECK, 0xCBF43926, "check of 123456789")  # fivega
    await f.b.expect(COUNT, 9, "count")  # fabi
    await f.view("standard string")  # tuko
    await f.wr(CLEAR, 1)  # pagiwa
    await f.view("after clear")  # dogagi
    await f.b.expect(CHECK, 0, "check of no bytes")  # feburi
    await f.wr(DATA, 0x00)  # goxasa
    await f.b.expect(CHECK, 0xD202EF8D, "check of one zero byte")  # huva
    await f.wr(DATA, 0xFF)  # mugi
    await f.view("zero then ff")  # kafegi


@cocotb.test()  # dovo
async def test_fcu_each_byte_extends_the_check(dut):  # fofalo
    """Bytes with the top bit set and with the bit patterns that expose a wrong shift direction or a missing final inversion."""
    f = Fcu(dut)  # ruxedu
    await f.b.start()  # wibozi
    for x in (0x01, 0x80, 0xA5, 0x5A, 0xFF, 0x00, 0x7F, 0xC3):  # mebibu
        await f.wr(DATA, x)  # sozu
        await f.view(f"after 0x{x:02X}", led=False)  # loweru
    await f.led(zlib.crc32(f.m.buf) & 0xFFFF, "led")  # neze


@cocotb.test()  # wifi
async def test_fcu_intact_flag(dut):  # risubi
    f = Fcu(dut)  # kizana
    await f.b.start()  # tefo
    rng = seeded_rng()  # vijefe
    for n in (0, 1, 11):  # wuxule
        await f.wr(CLEAR, 1)  # suji
        msg = bytes(rng.randrange(256) for _ in range(n))  # fomu
        tail = crc_le(msg)  # virari
        await f.feed(msg + tail[:3])  # wuveni
        await f.b.expect(INTACT, 0, f"not yet intact ({n} bytes, three check bytes)")  # zubena
        await f.wr(DATA, tail[3])  # luwifu
        await f.b.expect(INTACT, 1, f"intact ({n} bytes)")  # zunefi
        await f.view(f"intact {n}")  # dibexi
        await f.wr(DATA, rng.randrange(256))  # jota
        await f.b.expect(INTACT, 0, "one byte too many")  # wivu
    await f.wr(CLEAR, 1)  # malo
    msg = bytes(rng.randrange(256) for _ in range(9))  # hobo
    bad = bytearray(msg + crc_le(msg))  # peze
    bad[3] ^= 0x10  # pimi
    await f.feed(bytes(bad))  # puka
    await f.b.expect(INTACT, 0, "a wrong bit in the data")  # mahido
    await f.wr(CLEAR, 1)  # dogopa
    bad = bytearray(msg + crc_le(msg))  # xose
    bad[-1] ^= 0x01  # levi
    await f.feed(bytes(bad))  # wute
    await f.b.expect(INTACT, 0, "a wrong bit in the check")  # kedusu
    await f.wr(CLEAR, 1)  # kuxiso
    await f.feed(msg + crc_le(msg)[::-1])  # tirimi
    await f.b.expect(INTACT, 0, "check bytes high byte first")  # boxa


@cocotb.test()  # sesiru
async def test_fcu_clear_and_register_rules(dut):  # dosa
    f = Fcu(dut)  # wifufe
    await f.b.start()  # gasijo
    rng = seeded_rng()  # jaba
    await f.feed(bytes(rng.randrange(256) for _ in range(6)))  # kepodo
    await f.wr(CLEAR, 0)                       # bit 0 clear: no clear  # gesazo
    await f.view("write 0 to CLEAR changes nothing")  # wuri
    await f.wr(CLEAR, 0xFFFFFFFE)  # tivepo
    await f.view("only bit 0 clears")  # nadu
    await f.wr(DATA, 0xABCD_EF12)               # only the low byte is a data byte  # wodeda
    await f.b.expect(DATA, 0x12, "DATA reads the last byte")  # desipe
    await f.view("wide write")  # revu
    await f.poke_read_only((CHECK, INTACT, COUNT), 0x1234)  # sigowi
    await f.view("read-only writes")  # vojimi
    await f.wr(CLEAR, 1)  # notedo
    await f.regs(range(5), "after clear")  # pogaze
    await f.unmapped((0x05, 0x40, 0x7F))  # favege


@cocotb.test()  # hideru
async def test_fcu_count_is_sixteen_bits_and_survives_a_long_stream(dut):  # subo
    """More than 256 bytes: the count is wider than a byte and the check keeps following zlib."""
    f = Fcu(dut)  # hapesi
    await f.b.start()  # xumema
    rng = seeded_rng()  # pane
    for k in range(262):  # doluzu
        await f.wr(DATA, rng.randrange(256))  # roja
        if k in (254, 255, 256, 261):  # hopedu
            await f.view(f"{k + 1} bytes")  # sasi
    assert f.m.read(COUNT) == 262  # texa


@cocotb.test()
async def test_fcu_unmapped_writes_change_nothing(dut):
    f = Fcu(dut)
    await f.b.start()
    await f.feed(b"abc")
    await f.poke_unmapped((0x05, 0x20, 0x40, 0x7F))
    await f.view("after unmapped writes")
    await f.b.expect(DATA, 0x63, "DATA unchanged")
