"""Acceptance tests of p_sd_spi_init against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from cocotb.triggers import RisingEdge
from model import CARDTYPE, DESIGN_ID, ERRCODE, OCR, STATE, TRIES, Model, leds, ocr_word


class Card:
    """An SD card in SPI mode on SD_SCK / SD_CMD / SD_DAT3 (CS), answering on SD_DAT0."""

    def __init__(self, dut, present=True, v2=True, sdhc=True, tries_needed=1, ncr=1, cmd0_r1=0x01) -> None:
        self.dut = dut
        self.cfg = dict(present=present, v2=v2, sdhc=sdhc, tries_needed=tries_needed, cmd0_r1=cmd0_r1)
        self.ncr = ncr
        self.tries = 0
        self.ready = False
        self.cmds: list[tuple[int, int]] = []
        self.violations: list[str] = []
        self.sck_periods: set[int] = set()
        self.initial_clocks = 0
        self.initial_mosi_low = 0

    def respond(self, idx: int, arg: int, crc: int) -> list[int]:
        self.cmds.append((idx, arg))
        c = self.cfg
        if not crc & 1:
            self.violations.append(f"command {idx}: the check byte {crc:#04x} has no stop bit")
        if idx == 0:
            if crc != 0x95:
                self.violations.append(f"CMD0 check byte {crc:#04x}, want 0x95")
            self.ready, self.tries = False, 0
            return [c["cmd0_r1"]]
        if idx == 8:
            if crc != 0x87:
                self.violations.append(f"CMD8 check byte {crc:#04x}, want 0x87")
            if arg != 0x1AA:
                self.violations.append(f"CMD8 argument {arg:#x}")
            return [0x01, 0x00, 0x00, 0x01, 0xAA] if c["v2"] else [0x05]
        if idx == 55:
            return [0x00 if self.ready else 0x01]
        if idx == 41:
            self.tries += 1
            want = 0x40000000 if c["v2"] else 0
            if arg != want:
                self.violations.append(f"CMD41 argument {arg:#x}, want {want:#x}")
            if self.tries >= c["tries_needed"]:
                self.ready = True
            return [0x00 if self.ready else 0x01]
        if idx == 58:
            o = ocr_word(c)
            return [0x00, (o >> 24) & 0xFF, (o >> 16) & 0xFF, (o >> 8) & 0xFF, o & 0xFF]
        self.violations.append(f"unexpected command {idx}")
        return [0x04]

    async def run(self) -> None:
        d = self.dut
        d.SD_DAT0.value = 1
        t, prev_sck, last_rise = 0, 0, None
        cmd_bytes: list[int] = []
        byte, nbits = 0, 0
        tx: list[int] = []
        seen_cmd = False
        while True:
            await RisingEdge(d.CLK100MHZ)
            t += 1
            cs, sck, mosi = int(d.SD_DAT3.value), int(d.SD_SCK.value), int(d.SD_CMD.value)
            if sck and not prev_sck:
                if last_rise is not None:
                    self.sck_periods.add(t - last_rise)
                last_rise = t
                if cs:
                    if not seen_cmd:
                        self.initial_clocks += 1
                        if not mosi:
                            self.initial_mosi_low += 1
                    byte, nbits = 0, 0
                else:
                    byte = byte << 1 | mosi
                    nbits += 1
                    if nbits == 8:
                        if cmd_bytes or (byte & 0xC0) == 0x40:
                            cmd_bytes.append(byte)
                            if len(cmd_bytes) == 6:
                                seen_cmd = True
                                arg = int.from_bytes(bytes(cmd_bytes[1:5]), "big")
                                tx = [b for r in [0xFF] * self.ncr + self.respond(cmd_bytes[0] & 0x3F, arg, cmd_bytes[5]) for b in [(r >> (7 - i)) & 1 for i in range(8)]]
                                cmd_bytes = []
                        elif byte != 0xFF:
                            self.violations.append(f"stray byte {byte:#04x}")
                        byte, nbits = 0, 0
            if prev_sck and not sck:
                bit = tx.pop(0) if tx else 1
                d.SD_DAT0.value = bit if self.cfg["present"] else 1
            if cs:
                cmd_bytes = []
            prev_sck = sck


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SD_DAT0": 1})
        self.max_tries = self.b.param("MAX_TRIES")
        self.half = self.b.param("INIT_HALF")
        self.m = Model(self.max_tries)

    async def start(self, **card) -> Card:
        self.dut.SD_DAT0.value = 1
        await self.b.start()
        self.card = Card(self.dut, **card)
        cocotb.start_soon(self.card.run())
        return self.card

    async def finish(self) -> dict:
        for _ in range(200):
            await self.b.cycles(500)
            if (await self.b.read(STATE)) in (5, 6):
                break
        else:
            raise AssertionError("the start-up never finished")
        e = self.m.run({**self.card.cfg})
        for off, name in ((STATE, "STATE"), (CARDTYPE, "CARDTYPE"), (OCR, "OCR"), (TRIES, "TRIES"), (ERRCODE, "ERRCODE")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == leds(e), f"LED {led:04X} != {leds(e):04X}"
        c = self.card
        assert c.violations == [], c.violations
        assert c.cmds == e["cmds"], f"commands sent {c.cmds}, want {e['cmds']}"
        assert c.sck_periods == {2 * self.half}, f"SD_SCK periods {c.sck_periods}, want {2 * self.half}"
        assert c.initial_clocks >= 74 and c.initial_mosi_low == 0, f"{c.initial_clocks} initial clocks, {c.initial_mosi_low} with SD_CMD low"
        assert int(self.dut.SD_DAT3.value) == 1 and int(self.dut.SD_SCK.value) == 0, "bus not idle after the start-up"
        return e


@cocotb.test()
async def test_identity_and_power_control(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    assert int(dut.SD_RESET.value) == 0, "the card must be powered once the design is out of reset"
    assert int(dut.SD_DAT3.value) == 1 and int(dut.SD_SCK.value) == 0
    await e.finish()


@cocotb.test()
async def test_v2_high_capacity_after_three_tries(dut):
    e = Env(dut)
    await e.start(v2=True, sdhc=True, tries_needed=3, ncr=2)
    r = await e.finish()
    assert r["type"] == 3 and r["tries"] == 3


@cocotb.test()
async def test_v2_standard_capacity_immediate(dut):
    e = Env(dut)
    await e.start(v2=True, sdhc=False, tries_needed=1, ncr=0)
    r = await e.finish()
    assert r["type"] == 2


@cocotb.test()
async def test_version_1_card_and_late_response(dut):
    e = Env(dut)
    await e.start(v2=False, tries_needed=2, ncr=7)
    r = await e.finish()
    assert r["type"] == 1 and r["ocr"] == 0


@cocotb.test()
async def test_absent_card(dut):
    e = Env(dut)
    await e.start(present=False)
    r = await e.finish()
    assert r["err"] == 1 and r["state"] == 6


@cocotb.test()
async def test_card_that_never_becomes_ready(dut):
    e = Env(dut)
    await e.start(tries_needed=99)
    r = await e.finish()
    assert r["err"] == 3 and r["tries"] == e.max_tries


@cocotb.test()
async def test_random_cards(dut):
    e = Env(dut)
    rng = random.Random(int(cocotb.RANDOM_SEED))
    await e.start(v2=rng.random() < 0.6, sdhc=rng.random() < 0.5, tries_needed=rng.randrange(1, e.max_tries + 1), ncr=rng.randrange(0, 8))
    await e.finish()
