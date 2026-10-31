"""cocotb tests of tmp_regs (the I2C pointer-read engine) against a model of the ADT7420.

The model follows the ADT7420 data sheet (Rev. A): I2C address 0x4B on this board (A0 = A1 = 1,
schematic sheet 3), register pointer set by the first byte of a write, auto-increment on reads,
ID register 0x0B = 0xCB, and the pointer is lost (reset to 0x00) if a STOP follows the pointer
write instead of a repeated START (Nexys A7 RM section 12.1). It samples the bus on every clock,
flags any data byte written after the pointer (the design must never write one), and can
stretch SCL once.
"""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from shell.tests.window_bfm import WindowBfm

CTRL, STATUS, RDATA, INFO = 0x00, 0x01, 0x02, 0x03
ADT7420_REGS = {0x00: 0x0D, 0x01: 0x80, 0x02: 0x00, 0x03: 0x00, 0x0B: 0xCB}   # 0x0D80 >> 3 = 432 -> 27.0 C


class Adt7420Model:
    def __init__(self, dut, addr: int = 0x4B, regs: dict[int, int] | None = None, stretch_once: int = 0) -> None:
        self.dut, self.addr = dut, addr
        self.regs = dict(regs or ADT7420_REGS)
        self.ptr = 0
        self.stretch_once = stretch_once
        self.data_writes: list[int] = []      # bytes written after the pointer: must stay empty
        self.events: list[str] = []
        self.scl_rise_clocks: list[int] = []
        dut.dev_scl_pull.value = 0
        dut.dev_sda_pull.value = 0

    async def run(self) -> None:
        d = self.dut
        prev_scl, prev_sda = 1, 1
        state, nbits, byte, rw, ptr_fresh = "idle", 0, 0, 0, False
        tx_byte, clk_no, last_rise = 0, 0, None
        while True:
            await RisingEdge(d.clk)
            clk_no += 1
            scl, sda = int(d.scl.value), int(d.sda.value)
            if prev_scl and scl and prev_sda and not sda:                      # START or repeated START
                self.events.append("S")
                state, nbits, byte = "addr", 0, 0
                d.dev_sda_pull.value = 0
            elif prev_scl and scl and not prev_sda and sda:                    # STOP
                self.events.append("P")
                if ptr_fresh:
                    self.ptr = 0          # a pointer write closed by STOP is lost (RM 12.1)
                ptr_fresh = False
                state = "idle"
                d.dev_sda_pull.value = 0
            elif not prev_scl and scl:                                         # SCL rising: sample
                if last_rise is not None:
                    self.scl_rise_clocks.append(clk_no - last_rise)
                last_rise = clk_no
                if state in ("addr", "ptr", "wdata"):
                    byte = (byte << 1) | sda
                    nbits += 1
                elif state == "mack":
                    state = "tx" if sda == 0 else "nack_wait"                  # master ACK: more bytes
                    if state == "tx":
                        self.ptr = (self.ptr + 1) & 0xFF
            elif prev_scl and not scl:                                         # SCL falling: drive
                if self.stretch_once and state != "idle":
                    d.dev_scl_pull.value = 1
                    await ClockCycles(d.clk, self.stretch_once)
                    d.dev_scl_pull.value = 0
                    self.stretch_once = 0
                if state in ("addr", "ptr", "wdata") and nbits == 8:
                    if state == "addr":
                        rw = byte & 1
                        ok = (byte >> 1) == self.addr
                        state = ("ack_r" if rw else "ack_w") if ok else "ignore"
                    elif state == "ptr":
                        self.ptr, ptr_fresh, state = byte, True, "ack_p"
                    else:
                        self.data_writes.append(byte)
                        state = "ack_p"
                    d.dev_sda_pull.value = 1 if state != "ignore" else 0
                    nbits, byte = 0, 0
                elif state in ("ack_w", "ack_p"):
                    d.dev_sda_pull.value = 0
                    state = "ptr" if state == "ack_w" else "wdata"
                elif state == "ack_r" or state == "tx":
                    if state == "ack_r":
                        ptr_fresh = False
                        state, nbits = "tx", 0
                        tx_byte = self.regs.get(self.ptr, 0)
                    if state == "tx" and nbits == 8:
                        d.dev_sda_pull.value = 0                               # release for the master's ACK
                        state, nbits = "mack", 0
                    else:
                        if nbits == 0:
                            tx_byte = self.regs.get(self.ptr, 0)
                        d.dev_sda_pull.value = 0 if (tx_byte >> (7 - nbits)) & 1 else 1
                        nbits += 1
                elif state == "mack_done":
                    pass
            prev_scl, prev_sda = scl, sda


class Env:
    def __init__(self, dut, **model_kw) -> None:
        self.dut = dut
        self.win = WindowBfm(dut, dut.clk)
        self.model = Adt7420Model(dut, **model_kw)

    async def start(self) -> None:
        cocotb.start_soon(Clock(self.dut.clk, 10, "ns").start())
        self.dut.rst.value = 1
        await ClockCycles(self.dut.clk, 4)
        self.dut.rst.value = 0
        cocotb.start_soon(self.model.run())
        await ClockCycles(self.dut.clk, 4)

    async def ptr_read(self, ptr: int, nbytes: int) -> tuple[int, int]:
        await self.win.write(CTRL, (nbytes << 16) | (ptr << 8) | 1)
        st = await self.win.wait_done(STATUS)
        return st, await self.win.read(RDATA)


@cocotb.test()
async def test_id_and_temperature(dut) -> None:
    e = Env(dut)
    await e.start()
    st, v = await e.ptr_read(0x0B, 1)
    assert not st & 4 and v == 0xCB, f"ID: status {st:#x} value {v:#x}"
    st, v = await e.ptr_read(0x00, 2)
    assert not st & 4 and v == 0x0D80, f"temperature: status {st:#x} value {v:#x}"
    assert e.model.data_writes == [], "the design wrote a data byte to the sensor"
    # START, repeated START, STOP for each read: never a STOP between pointer and read
    assert e.model.events == ["S", "S", "P", "S", "S", "P"], e.model.events
    # one SCL period is 4 quarters, plus the clocks the master waits to see its own released SCL
    # high (clock synchronisation: 1 here, 3 on the board behind the 2-flop synchroniser)
    period = int(dut.QUARTER.value) * 4 + 1
    assert set(e.model.scl_rise_clocks[1:9]) == {period}, e.model.scl_rise_clocks[:10]
    assert await e.win.read(INFO) == (0x4B << 16) | int(dut.QUARTER.value)


@cocotb.test()
async def test_wrong_address_nacks(dut) -> None:
    e = Env(dut, addr=0x48)          # no device answers 0x4B
    await e.start()
    st, v = await e.ptr_read(0x0B, 1)
    assert st & 4 and v == 0, f"expected NACK: status {st:#x} value {v:#x}"
    assert e.model.events[-1] == "P", "the bus must end with a STOP after a NACK"
    await ClockCycles(dut.clk, 8)
    assert int(dut.scl.value) == 1 and int(dut.sda.value) == 1, "bus not released after NACK"


@cocotb.test()
async def test_clock_stretching(dut) -> None:
    e = Env(dut, stretch_once=200)   # the device holds SCL low for 200 clocks once
    await e.start()
    st, v = await e.ptr_read(0x0B, 1)
    assert not st & 4 and v == 0xCB, f"with stretching: status {st:#x} value {v:#x}"


@cocotb.test()
async def test_one_byte_then_two_repeat(dut) -> None:
    e = Env(dut, regs={0x00: 0xF6, 0x01: 0x48, 0x0B: 0xCB, 0x05: 0x5A})
    await e.start()
    for _ in range(3):
        assert (await e.ptr_read(0x00, 2))[1] == 0xF648          # a negative temperature code
        assert (await e.ptr_read(0x05, 1))[1] == 0x5A
    assert e.model.data_writes == []
