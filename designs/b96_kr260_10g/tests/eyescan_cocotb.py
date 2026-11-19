"""cocotb bench of brief 96D's DRP access and eye-scan point sequencer (rtl/es_ctrl.sv inside b96_core, EYESCAN = 1) against the Python twin
(model/eyescan.py) and the GT's DRP STAND-IN (sim/gth_wiz_model96.sv). What this proves: the register layout, the sequence of DRP accesses (every address and
every value written, read-modify-write keeping the neighbouring bits), the result registers, the timeout path and the raw access. What it does not: that the real
GTHE4 answers these accesses as UG576 says (the board does that)."""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from designs.b96_kr260_10g.model import eyescan as tw

R_DRP_ADDR, R_DRP_DATA, R_CMD, R_STAT, R_POINT, R_TMO, R_RES, R_DRIVE = 0x024, 0x028, 0x02C, 0x030, 0x034, 0x038, 0x03C, 0x084
REF_PS = 6206


class Host:
    def __init__(self, dut):
        self.dut = dut

    async def w(self, addr, val):
        d = self.dut
        d.h_addr.value = addr; d.h_wdata.value = val; d.h_we.value = 1
        await RisingEdge(d.clk)
        d.h_we.value = 0
        await RisingEdge(d.clk)

    async def r(self, addr):
        d = self.dut
        d.h_addr.value = addr; d.h_re.value = 1
        await RisingEdge(d.clk)
        d.h_re.value = 0
        await RisingEdge(d.clk)
        await RisingEdge(d.clk)
        await Timer(1, unit="ns")
        return int(d.h_rdata.value)

    async def raw_read(self, a):
        await self.w(R_DRP_ADDR, a); await self.w(R_CMD, 1)
        await self.wait_idle()
        return await self.r(R_DRP_DATA)

    async def raw_write(self, a, v):
        await self.w(R_DRP_ADDR, a); await self.w(R_DRP_DATA, v); await self.w(R_CMD, 2)
        await self.wait_idle()

    async def wait_idle(self, limit=400):
        for _ in range(limit):
            if not (await self.r(R_STAT)) & 1:
                return
        raise AssertionError("sequencer stayed busy")


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    cocotb.start_soon(Clock(dut.refclk, REF_PS, unit="ps").start())
    dut.rst.value = 1; dut.h_we.value = 0; dut.h_re.value = 0; dut.h_addr.value = 0; dut.h_wdata.value = 0
    for _ in range(6):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
    return Host(dut)


def monitor(dut, log):
    gt = dut.u.u_gt

    async def run():
        while True:
            await RisingEdge(dut.clk)
            if int(gt.drpen_in.value):
                log.append(("W" if int(gt.drpwe_in.value) else "R", int(gt.drpaddr_in.value), int(gt.drpdi_in.value) if int(gt.drpwe_in.value) else None))
    return cocotb.start_soon(run())


def mem_of(dut, a):
    return int(dut.u.u_gt.drp_mem[a].value)


@cocotb.test()
async def features_and_reset_values(dut):
    h = await start(dut)
    assert (await h.r(0x008)) & 0x10, "FEATURES bit 4 (EYESCAN) must read 1"
    assert await h.r(R_TMO) == 500_000_000
    assert await h.r(R_DRIVE) == 0b11000, "reset drive: TXDIFFCTRL 11000, no cursors, no DFE/LPM reset"
    assert await h.r(R_STAT) == 0
    assert int(dut.u.tx_diff.value) == 0b11000 and int(dut.u.tx_pre.value) == 0 and int(dut.u.tx_post.value) == 0


@cocotb.test()
async def raw_access_and_flags(dut):
    h = await start(dut)
    assert await h.raw_read(tw.A_ES_CONTROL) == 0x0360, "the stand-in's ES_CONTROL word"
    assert await h.raw_read(tw.A_ES_HORZ) == 0x0005
    await h.raw_write(0x100, 0xBEEF)
    assert mem_of(dut, 0x100) == 0xBEEF
    assert await h.raw_read(0x100) == 0xBEEF
    # a write does not change the last-read data register
    await h.raw_write(0x101, 0x1234)
    assert await h.r(R_DRP_DATA) == 0xBEEF, "DRP_DATA reads the last READ, not the last write"
    # a raw command while a point runs is rejected
    await h.w(R_POINT, 0)
    await h.w(R_CMD, 4)                       # start a point
    await h.w(R_CMD, 1)                       # raw read while busy
    await h.wait_idle()
    st = await h.r(R_STAT)
    assert st & 0x10, f"rejected flag not set: {st:#x}"
    await h.w(R_CMD, 8)
    assert (await h.r(R_STAT)) & 0x10 == 0


async def run_point(dut, h, horz, code, neg, ut, rng, pre):
    log = []
    mon = monitor(dut, log)
    pre_mem = {a: mem_of(dut, a) for a in (tw.A_ES_HORZ, tw.A_VS, tw.A_ES_CONTROL)}
    word = (horz & 0xFFF) | (code << 12) | (neg << 19) | (ut << 20) | (rng << 21) | (pre << 23)
    await h.w(R_POINT, word)
    assert await h.r(R_POINT) == word
    await h.w(R_CMD, 4)
    await h.wait_idle()
    mon.cancel()
    st = await h.r(R_STAT)
    res = await h.r(R_RES)
    return log, pre_mem, st, res


@cocotb.test()
async def points_match_the_twin(dut):
    h = await start(dut)
    n_done = 0
    for (horz, code, neg, ut, rng, pre) in [(0, 0, 0, 0, 0, 0), (5, 17, 1, 0, 2, 3), (0x7E0, 127, 0, 1, 3, 31), (0x820, 64, 1, 1, 1, 9), (32, 1, 0, 0, 0, 10), (0xFE0 | 0x800 & 0xFFF, 9, 0, 1, 0, 4)]:
        log, pre_mem, st, res = await run_point(dut, h, horz & 0xFFF, code, neg, ut, rng, pre)
        n_done += 1
        assert st & 3 == 2, f"point not done / still busy: {st:#x}"
        assert st & 4 == 0 and st & 8 == 0, f"timeout flags: {st:#x}"
        assert (await h.r(R_STAT)) >> 16 == n_done, "points completed counter"
        assert (st >> 8) & 0xF == 0b0101, "es_control_status as last read is END"
        polls = sum(1 for x in log if x[1] == tw.A_STATUS)
        exp = tw.point_transactions(pre_mem, horz & 0xFFF, code, neg, ut, rng, pre, polls=polls)
        assert log == exp, f"DRP traffic differs:\n got {log}\n exp {exp}"
        assert res & 0xFFFF == tw.stand_in_error_count(horz & 0xFFF, code, neg, ut, rng, pre), (hex(res), horz, code)
        assert res >> 16 == 0xFFFF
        # the run bit is cleared at the end, the neighbours survived (read-modify-write), and every owned field is where the sequencer put it
        m3c, m4f, m97 = mem_of(dut, tw.A_ES_CONTROL), mem_of(dut, tw.A_ES_HORZ), mem_of(dut, tw.A_VS)
        assert (m3c >> 10) == 0 and (m3c >> 5) & 0x1F == (pre_mem[tw.A_ES_CONTROL] >> 5) & 0x1F and m3c & 0x1F == pre
        assert m4f == ((horz & 0xFFF) << 4 | 5) and m97 & 0xF800 == 0x1800
        assert m97 == (0x1800 | neg << 10 | ut << 9 | code << 2 | rng)


@cocotb.test()
async def timeout_path_stops_the_run(dut):
    h = await start(dut)
    dut.u.u_gt.es_hold.value = 1
    await h.w(R_TMO, 2000)
    log = []
    mon = monitor(dut, log)
    await h.w(R_POINT, (3 & 0xFFF) | (5 << 12) | (4 << 23))
    await h.w(R_CMD, 4)
    await h.wait_idle(limit=2000)
    mon.cancel()
    st = await h.r(R_STAT)
    assert st & 3 == 2 and st & 4, f"expected done with the point-timeout flag: {st:#x}"
    assert await h.r(R_RES) == 0, "results are 0 after a timeout"
    assert log[-1] == ("W", tw.A_ES_CONTROL, (((0x0360 >> 5) & 0x1F) << 5) | 4), f"the run bit must be cleared after a timeout: {log[-1]}"
    assert (mem_of(dut, tw.A_ES_CONTROL) >> 10) == 0
    assert all(x[1] != tw.A_ERR for x in log), "no result read after a timeout"
    dut.u.u_gt.es_hold.value = 0


@cocotb.test()
async def drp_timeout_aborts_the_point_without_writing(dut):
    h = await start(dut)
    dut.u.u_gt.drp_dead.value = 1
    log = []
    mon = monitor(dut, log)
    await h.w(R_POINT, 7 | (5 << 12))
    await h.w(R_CMD, 4)
    await h.wait_idle(limit=2000)
    mon.cancel()
    st = await h.r(R_STAT)
    assert st & 3 == 2 and st & 4 and st & 8, f"done with point-timeout and DRP-timeout flags expected: {st:#x}"
    assert [x for x in log if x[0] == "W"] == [], "no DRP write after a first-access timeout"
    assert await h.r(R_RES) == 0
    dut.u.u_gt.drp_dead.value = 0
    await h.w(R_CMD, 8)
    assert (await h.r(R_STAT)) & 8 == 0


@cocotb.test()
async def point_is_latched_at_start(dut):
    h = await start(dut)
    word = 5 | (17 << 12) | (1 << 19) | (2 << 21) | (3 << 23)
    await h.w(R_POINT, word)
    await h.w(R_CMD, 4)
    await h.w(R_POINT, 0x7FFFFFF)            # the host (wrongly) rewrites ES_POINT mid-point
    await h.wait_idle()
    assert (await h.r(R_RES)) & 0xFFFF == tw.stand_in_error_count(5, 17, 1, 0, 2, 3)


@cocotb.test()
async def drive_registers_reach_the_gt_ports(dut):
    h = await start(dut)
    await h.w(R_DRIVE, 0x10000 | (6 << 10) | (3 << 5) | 0b10000)
    await RisingEdge(dut.clk)
    assert int(dut.u.tx_diff.value) == 0b10000 and int(dut.u.tx_pre.value) == 3 and int(dut.u.tx_post.value) == 6
    assert int(dut.u.rx_dfelpm_rst.value) == 1
    assert await h.r(R_DRIVE) == 0x10000 | (6 << 10) | (3 << 5) | 0b10000
    await h.w(R_DRIVE, 0b11000)


@cocotb.test()
async def eyescan_absent_reads_zero(dut):
    """Run with EYESCAN = 0 (B96_EYESCAN_OFF=1 selects this test): the registers read 0, the DRP port is tied, the drive ports are the old constants."""
    import os
    if os.environ.get("B96_EYESCAN_OFF") != "1":
        return
    h = await start(dut)
    assert (await h.r(0x008)) & 0x10 == 0
    for a in (R_DRP_ADDR, R_DRP_DATA, R_STAT, R_POINT, R_TMO, R_RES, R_DRIVE):
        await h.w(a, 0xFFFFFFFF)
        assert await h.r(a) == 0, hex(a)
    await h.w(R_CMD, 0xF)
    assert int(dut.u.drp_en.value) == 0 and int(dut.u.tx_diff.value) == 0b11000 and int(dut.u.tx_pre.value) == 0 and int(dut.u.tx_post.value) == 0
