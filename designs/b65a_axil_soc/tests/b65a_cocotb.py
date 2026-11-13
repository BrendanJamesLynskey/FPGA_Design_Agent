"""cocotb test of the generated b65a_axil_soc_top: the host's view, through the UART test shell, the shell-to-AXI4-Lite
bridge and the generated crossbar, of all three ip_lib blocks. Expected values come from the address map the generator
exported (gen/address_map.json), the blocks' Python models (hil/instruments/models.py) and the AXI4-Lite rules, never
from the RTL. Every top-level AXI4-Lite link has brief 59's checker on it (b65a_tb.sv); it must stay silent."""
from __future__ import annotations

import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from hil.instruments import models as m
from shell.host import protocol as p
from shell.tests.uart_bfm import UartBfm

DESIGN = Path(__file__).resolve().parents[1]
AMAP = json.loads((DESIGN / "gen" / "address_map.json").read_text())
W = p.WINDOW_BASE                      # the bridge's registers: ADDR, WDATA, CTRL, STATUS, RDATA
OKAY, SLVERR, DECERR = 0, 2, 3


def base(slave: str) -> int:
    return next(r["base"] for r in AMAP["ranges"] if r["slave"] == slave)


def reg(slave: str, name: str) -> int:
    r = next(r for r in AMAP["ranges"] if r["slave"] == slave)
    return r["base"] + next(g["offset"] for g in r["registers"] if g["name"] == name)


class Host:
    """AXI4-Lite transfers as the board host makes them: shell writes and reads of the bridge's window registers."""

    def __init__(self, bfm):
        self.bfm = bfm
        self.n = 0

    async def sread(self, addr):
        r = p.decode_response(await self.bfm.transact(p.encode_request(p.CMD_READ, addr, 0)))
        assert r.status == 0, f"shell read {addr:#x}: status {r.status_name}"
        return r.data

    async def swrite(self, addr, v):
        r = p.decode_response(await self.bfm.transact(p.encode_request(p.CMD_WRITE, addr, v)))
        assert r.status == 0, f"shell write {addr:#x}: status {r.status_name}"

    async def _wait(self):
        for _ in range(50):
            st = await self.sread(W + 3)
            if not (st & 1) and (st & 2):
                self.n += 1
                assert (st >> 16) == self.n & 0xFFFF, f"bridge count {st >> 16}, expected {self.n}"
                return (st >> 2) & 3
        raise AssertionError("AXI4-Lite transfer did not finish")

    async def write(self, addr, data, strb=0xF):
        await self.swrite(W + 0, addr)
        await self.swrite(W + 1, data)
        await self.swrite(W + 2, 1 | (strb << 4))
        return await self._wait()

    async def read(self, addr):
        await self.swrite(W + 0, addr)
        await self.swrite(W + 2, 2)
        resp = await self._wait()
        return resp, await self.sread(W + 4)

    async def rd(self, addr):
        resp, v = await self.read(addr)
        assert resp == OKAY, f"read {addr:#x}: response {resp}"
        return v

    async def wr(self, addr, v, strb=0xF):
        resp = await self.write(addr, v, strb)
        assert resp == OKAY, f"write {addr:#x}: response {resp}"


def find_run(got, step):
    """The table index i0 (the phase's top 8 bits, all a sine sample depends on) at which `got` is a contiguous run of
    the DDS model's sine output for this step, or None. The phase accumulator carries whatever earlier steps left in
    it, so the run's starting phase is unknown; only the top LUT_W = 8 bits of it matter."""
    for i0 in range(256):
        ph0 = i0 << 24
        if all(m.dds_sample((ph0 + k * step) & 0xFFFFFFFF, 0, 32, 8, 16, 0) == got[k] for k in range(len(got))):
            return i0
    return None


@cocotb.test()
async def end_to_end(dut):
    clk = dut.CLK100MHZ
    cocotb.start_soon(Clock(clk, 10, unit="ns").start())
    dut.CPU_RESETN.value = 0
    await ClockCycles(clk, 5)
    dut.CPU_RESETN.value = 1
    await ClockCycles(clk, 5)
    h = Host(UartBfm(clk, dut.UART_TXD_IN, dut.UART_RXD_OUT, int(dut.SHELL_CLKS_PER_BIT.value)))
    assert await h.sread(p.REG_DESIGN_ID) == 0x42363541, "DESIGN_ID is not B65A"

    dds, fd, la = "tone.s_dds", "tone.s_fd", "la.s_axil"
    # ---- the generated register bank: reset values from the design file, read/write, byte strobes, RO and unmapped words
    assert await h.rd(reg(dds, "STEP")) == 0x0A7C5AC4
    assert await h.rd(reg(dds, "WAVE")) == 0
    assert await h.rd(reg(dds, "TICKDIV")) == 99
    await h.wr(reg(dds, "STEP"), 0x11223344)
    assert await h.rd(reg(dds, "STEP")) == 0x11223344
    await h.wr(reg(dds, "STEP"), 0xAABBCCDD, strb=0b0101)
    assert await h.rd(reg(dds, "STEP")) == 0x11BB33DD, "byte strobes not honoured"
    assert await h.write(reg(dds, "SAMPLE"), 1) == SLVERR, "a write to a status register must answer SLVERR"
    r, v = await h.read(base(dds) + 0x100)
    assert (r, v) == (SLVERR, 0), f"unmapped word in the bank: {r}, {v:#x}"
    # ---- the address map: every hole answers DECERR from the crossbar, reads with data 0
    for hole in AMAP["holes"]:
        for a in (hole["base"], hole["base"] + hole["size"] - 4):
            assert await h.write(a, 0x5A5A5A5A) == DECERR, f"write to hole {a:#x}"
            assert await h.read(a) == (DECERR, 0), f"read of hole {a:#x}"
    r, _ = await h.read(0x0000_0000)
    assert r == DECERR, "below the map"

    # ---- tone -> frequency counter (same hierarchy, sign bit): a known frequency, checked against the gate length
    step = 1 << 26                      # 1/64 of a turn a tick: a period of 64 ticks
    await h.wr(reg(dds, "TICKDIV"), 0)  # a tick every clock
    await h.wr(reg(dds, "STEP"), step)
    await h.wr(reg(dds, "WAVE"), 0)     # sine, full amplitude
    gate = int(dut.TONE_FD_GATE_CLKS.value)
    g0 = await h.rd(reg(fd, "GATES"))
    while await h.rd(reg(fd, "GATES")) < g0 + 2:     # a whole gate after the change
        await ClockCycles(clk, gate // 4)
    edges = await h.rd(reg(fd, "EDGES"))
    high = await h.rd(reg(fd, "HIGH"))
    exp = gate / 64
    assert abs(edges - exp) <= 1, f"edges {edges} in a {gate}-clock gate, expected {exp:.1f} +- 1"
    assert abs(high / gate - 0.5) < 0.05, f"duty {high / gate:.3f}, expected 0.5"
    sample = await h.rd(reg(dds, "SAMPLE"))
    assert sample >> 16 in (0, 0xFFFF), f"SAMPLE {sample:#x} is not sign extended"

    # ---- tone -> logic analyser (across the hierarchy boundary): a capture that is a contiguous run of the DDS model
    await h.wr(reg(dds, "TICKDIV"), 3)  # a tick every 4 clocks: the analyser samples on the tick
    LA = base(la)
    await h.wr(LA + 4 * 2, 0)           # MASK 0: the trigger is true at once
    await h.wr(LA + 4 * 3, 0)
    await h.wr(LA + 4 * 4, 0)           # PRE 0
    assert await h.rd(LA + 4 * 5) == 256, "DEPTH is not 2**ADDR_W"
    assert await h.write(LA + 4 * 2, 0, strb=0b0011) == SLVERR, "the window adapter must refuse partial writes"
    await h.wr(LA + 4 * 0, 1)           # arm
    for _ in range(40):
        st = await h.rd(LA + 4 * 1)
        if st & 4:
            break
        await ClockCycles(clk, 500)
    assert st & 4, "the capture did not finish"
    got = []
    for k in range(24):
        await h.wr(LA + 4 * 6, k)
        v = await h.rd(LA + 4 * 7)
        got.append(v - 0x10000 if v & 0x8000 else v)
    n0 = find_run(got, step)
    assert n0 is not None, f"captured samples are not a run of the DDS model: {got}"
    # ---- no AXI4-Lite rule broken on any link
    chk = int(dut.chk_any.value)
    links = json.loads(os.environ.get("B65A_LINKS", "[]"))
    assert chk == 0, f"AXI4-Lite rule broken on {[links[i] for i in range(len(links)) if (chk >> i) & 1]}"
    out = {"axi_transfers": h.n, "edges": edges, "high": high, "gate": gate, "la_run_start_index": n0, "links_checked": links}
    dut._log.info(f"b65a end to end: {out}")
    res = os.environ.get("B65A_SIM_OUT")
    if res:
        Path(res).write_text(json.dumps(out, indent=1) + "\n")
