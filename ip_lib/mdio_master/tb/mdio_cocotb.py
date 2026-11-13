"""cocotb bench for ip_lib/mdio_master against a clause 22 PHY written from IEEE 802.3 clause 22 (model.py).

The PHY samples MDIO on each rising edge of MDC, decodes the frame and, for a read, drives the second TA bit and the
data a random number of clocks after a rising edge (its clock-to-output delay, under one MDC half period), so the
master must sample on the next rising edge. Checked: every bit the master drives, that it releases the line where it
must, that MDIO never changes within a clock of a rising edge of MDC, the MDC period, the frame length and the value
read back. Environment: MDIO_SEED, MDIO_N."""
from __future__ import annotations

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge, Timer

from ip_lib.mdio_master import model

SEED = int(os.environ.get("MDIO_SEED", "1"))
N = int(os.environ.get("MDIO_N", "12"))


@cocotb.test()
async def frames(dut):
    div = int(dut.DIV.value)
    rng = random.Random(SEED + div)
    cocotb.start_soon(Clock(dut.clk, 8, unit="ns").start())
    dut.rst.value = 1
    dut.go.value = 0
    dut.rd.value = 0
    dut.phy.value = 0
    dut.reg_a.value = 0
    dut.wdata.value = 0
    dut.mdio_i.value = 1
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    for k in range(N):
        read = rng.random() < 0.5
        phy, reg, data, value = rng.randrange(32), rng.randrange(32), rng.randrange(65536), rng.randrange(65536)
        want = model.frame(read, phy, reg, data)
        drive = model.phy_drives(read, value)
        dut.rd.value, dut.phy.value, dut.reg_a.value, dut.wdata.value = int(read), phy, reg, data
        dut.go.value = 1
        await RisingEdge(dut.clk)
        dut.go.value = 0
        busy_clks = 0
        if k % 3 == 2:                                   # a go while busy is ignored
            dut.go.value = 1
            await RisingEdge(dut.clk)
            dut.go.value = 0
            busy_clks = 1
        seen, rises, hist = [], [], []
        pend = []                                        # (clock, value) the PHY will drive
        clk_n, prev_mdc = 0, 0
        while True:
            await ReadOnly()
            mdc, t, o = int(dut.mdc.value), int(dut.mdio_t.value), int(dut.mdio_o.value)
            busy = int(dut.busy.value)
            hist.append((mdc, t, o))
            if mdc and not prev_mdc:                     # a rising edge of MDC: the PHY samples
                rises.append(clk_n)
                e = len(seen)
                seen.append(None if t else o)
                if e + 1 in drive:
                    pend.append((clk_n + rng.randrange(1, max(2, div)), drive[e + 1]))
                elif e + 1 >= 64 or (e + 1) not in drive:
                    pend.append((clk_n + 1, 1))         # released: the pull-up
            prev_mdc = mdc
            busy_clks += busy
            await Timer(1, unit="ns")
            for c, v in list(pend):
                if c <= clk_n:
                    dut.mdio_i.value = v
                    pend.remove((c, v))
            await RisingEdge(dut.clk)
            clk_n += 1
            if not busy and clk_n > 4:
                break
        assert len(seen) == 64, len(seen)
        assert seen == want, ("".join("z" if b is None else str(b) for b in seen),
                              "".join("z" if b is None else str(b) for b in want))
        assert busy_clks == 64 * 2 * div, (busy_clks, div)
        assert all(b - a == 2 * div for a, b in zip(rises, rises[1:])), "MDC period"
        for r in rises:                                  # setup and hold: MDIO steady one clock either side
            assert hist[r - 1][1:] == hist[r][1:] == hist[r + 1][1:], (r, hist[r - 1:r + 2])
        if read:
            assert int(dut.rdata.value) == value, (hex(int(dut.rdata.value)), hex(value))
        await RisingEdge(dut.clk)
        dut._log.info(f"frame {k}: {'read' if read else 'write'} PHY {phy} reg {reg} ok")
