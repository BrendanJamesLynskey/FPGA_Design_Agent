"""cocotb test of b30_hil_audio_top through the test shell: every instrument's registers against the Python models.
This is the simulation half of the HIL stage's pass rule (the same checks run on the board, hil/hil_audio_board.py)."""
from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from hil.instruments import models as m
from hil.instruments import shell_instruments as si
from shell.host import protocol as p
from shell.tests.uart_bfm import UartBfm

STEP16 = 89463225 * 16            # 16 kHz at 48.008 kHz: a few edges in a short simulated gate


class SimShell:
    """FpgaShell's read/write over the BFM, made synchronous per call by the test (awaited explicitly)."""
    def __init__(self, bfm):
        self.bfm = bfm

    async def read(self, addr):
        got = await self.bfm.transact(p.encode_request(p.CMD_READ, addr, 0))
        r = p.decode_response(got)
        assert r.status == 0, f"read {addr:#x} status {r.status}"
        return r.data

    async def write(self, addr, v):
        got = await self.bfm.transact(p.encode_request(p.CMD_WRITE, addr, v))
        assert p.decode_response(got).status == 0


@cocotb.test()
async def instruments_against_models(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, "ns").start())
    dut.CPU_RESETN.value = 0
    await ClockCycles(dut.CLK100MHZ, 5)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 5)
    sh = SimShell(UartBfm(dut.CLK100MHZ, dut.UART_TXD_IN, dut.UART_RXD_OUT, int(dut.CLKS_PER_BIT.value)))
    W = si.WINDOW
    assert await sh.read(0) == 0x48333041, "DESIGN_ID is not H30A"

    # tone: switch to 16 kHz so the frequency counter sees edges inside the simulated gate
    await sh.write(W + 1, STEP16)
    gate = int(dut.FD_GATE_CLKS.value)
    assert await sh.read(W + 0x13) == gate
    await ClockCycles(dut.CLK100MHZ, 3 * gate)
    edges = await sh.read(W + 0x10)
    high = await sh.read(W + 0x11)
    exp_edges = gate / (100e6 / (STEP16 / 2 ** 32 * 100e6 / 2083))
    assert abs(edges - exp_edges) <= 1.01, f"edges {edges}, expected about {exp_edges:.2f}"
    assert abs(high / gate - 0.5) < 0.2, f"duty {high / gate:.3f}"

    # logic analyser: always-true trigger (mask 0), 64 samples read back, a contiguous run of the DDS model
    await sh.write(W + 0x22, 0); await sh.write(W + 0x23, 0); await sh.write(W + 0x24, 0)
    await sh.write(W + 0x20, 1)
    for _ in range(200):
        st = await sh.read(W + 0x21)
        if st & 4:
            break
        await ClockCycles(dut.CLK100MHZ, 5000)
    assert st & 4, "LA never completed"
    got = []
    for k in range(64):
        await sh.write(W + 0x26, k)
        v = await sh.read(W + 0x27)
        got.append(v - 65536 if v & 0x8000 else v)
    ref = m.dds_stream(2000, STEP16, 0, 32, 8, 16, 2)
    ok = any(ref[i:i + 64] == got for i in range(len(ref) - 64))
    assert ok, f"LA samples are not a run of the DDS model: {got[:8]}"

    # frame CRC against the model, then the seeded data-path fault
    crc = m.frame_crc32(si.lfsr_frame(), 24)
    await sh.write(W + 0x54, crc)
    await ClockCycles(dut.CLK100MHZ, 9000)
    assert await sh.read(W + 0x50) == crc, "frame CRC differs from the model"
    assert await sh.read(W + 0x52) == 128
    assert await sh.read(W + 0x53) == sum(si.lfsr_frame()) & 0xFFFFFFFF
    m0 = await sh.read(W + 0x55)                  # frames before FC_EXPECT was written were compared with 0
    await ClockCycles(dut.CLK100MHZ, 9000)
    assert await sh.read(W + 0x55) == m0, "mismatches counted on good frames"
    await sh.write(W + 0, 3)                      # flip one pixel bit of every frame
    await ClockCycles(dut.CLK100MHZ, 9000)
    assert await sh.read(W + 0x55) > m0, "the one-bit pixel fault was not counted"
    assert await sh.read(W + 0x50) != crc

    # XADC polled into the code registers (the stand-in answers fixed codes)
    await ClockCycles(dut.CLK100MHZ, 4 * 2 ** 20 + 1000)
    codes = [await sh.read(W + 0x40 + i) for i in range(4)]
    assert codes == [0x9A5, 0x556, 0xB20, 0x557], f"XADC codes {[hex(c) for c in codes]}"
