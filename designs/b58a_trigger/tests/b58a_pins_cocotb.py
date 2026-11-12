"""Pin-level bench for kr260_top in simulation (brief 58A step 0): port B's RGMII transmit pins are looped into port A's
RGMII receive pins, with RX_CLK a quarter period (2 ns) after the transmit clock. Checks that every frame of the
in-FPGA generator crosses RGMII TX -> RGMII RX -> the clock-crossing FIFO (the XPM simulation model) -> mac_rx with a
good FCS, and measures the cycles each pin-side stage adds. In simulation the MMCM is absent (the core clock is the
input clock) and the JTAG bus is idle, so the generator is switched on by depositing its register."""

from __future__ import annotations

import json
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge, Timer


@cocotb.test()
async def rgmii_loop_b_to_a(dut):
    cocotb.start_soon(Clock(dut.clk_25, 8, unit="ns").start())

    async def rx_clock():
        await Timer(2, unit="ns")
        while True:
            dut.a_rxc.value = 1
            dut.b_rxc.value = 1
            await Timer(4, unit="ns")
            dut.a_rxc.value = 0
            dut.b_rxc.value = 0
            await Timer(4, unit="ns")

    async def wire():
        while True:
            await Timer(1, unit="ns")
            dut.a_rxd.value = dut.b_txd.value
            dut.a_rx_ctl.value = dut.b_tx_ctl.value

    dut.b_rxd.value = 0
    dut.b_rx_ctl.value = 0
    dut.a_rxd.value = 0
    dut.a_rx_ctl.value = 0
    cocotb.start_soon(rx_clock())
    cocotb.start_soon(wire())
    core = dut.u_core
    for _ in range(400):
        await RisingEdge(dut.clk_25)
    core.gen_interval.value = 300
    core.gen_npkts.value = 20
    core.gen_nmsg.value = 3
    core.gen_en.value = 1
    first_core, ctl_out, ctl_in, sof_rx, good = [], [], [], [], 0
    prev_txctl = prev_rxctl = 0
    cyc = 0
    for _ in range(20 * 300 + 2000):
        await RisingEdge(dut.clk_25)
        await ReadOnly()
        cyc += 1
        if int(core.bt_first.value):
            first_core.append(cyc)
        txc = int(dut.b_tx_ctl.value) if dut.b_tx_ctl.value.is_resolvable else 0
        if txc and not prev_txctl:
            ctl_out.append(cyc)
        prev_txctl = txc
        if int(core.ar_sof.value):
            sof_rx.append(cyc)
        if int(core.ar_end.value) and int(core.ar_good.value):
            good += 1
    assert good == 20, f"{good} of 20 frames crossed with a good FCS"
    n = min(len(first_core), len(sof_rx))
    loop = [sof_rx[i] - first_core[i] for i in range(n)]
    tx_pin = [ctl_out[i] - first_core[i] for i in range(min(len(ctl_out), len(first_core)))]
    res = {"frames": 20, "good_at_a": good,
           "mac_tx_first_byte_to_tx_ctl_pin_cycles": sorted(set(tx_pin)),
           "mac_tx_first_byte_to_mac_rx_sfd_cycles": sorted(set(loop)),
           "note": "the second includes 7 preamble bytes and the SFD (8 cycles on the wire), RGMII RX, and the "
                   "asynchronous FIFO's simulation model; on silicon the PHYs and the cable add to it"}
    dut._log.info(json.dumps(res))
    out = os.environ.get("B58A_PINS_OUT")
    if out:
        with open(out, "w") as f:
            json.dump(res, f, indent=1)
