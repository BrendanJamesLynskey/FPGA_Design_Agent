"""False-fire probe: legal but unusual AXI4-Lite and AXI4-Stream traffic must fire no rule (the profile rules are not
enabled in this design, so they are not checked here). Each scenario is a list of cycles; a cycle sets only the signals it
names, the others keep their value. Results go to $AXI_TX_FF_OUT (results/59a_axi_tx/false_fire.json via the pytest entry)."""
from __future__ import annotations

import json
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge, Timer

IDLE = {"aresetn": 1, "awvalid": 0, "awready": 0, "wvalid": 0, "wready": 0, "bvalid": 0, "bready": 0, "arvalid": 0,
        "arready": 0, "rvalid": 0, "rready": 0, "tvalid": 0, "tready": 0, "tlast": 0, "tkeep": 0xF, "tstrb": 0xF,
        "awaddr": 0, "wdata": 0, "wstrb": 0xF, "bresp": 0, "araddr": 0, "rdata": 0, "rresp": 0, "tdata": 0}


STREAM_ON = 0b00111          # stream rules 0-2; 3 (MAXLEN) and 4 (PACKED) are profile rules, off unless a design enables them


def w(**k):
    return k


SCENARIOS = {
    "W three cycles before AW, B the cycle after the AW handshake": [
        w(wvalid=1, wdata=5, wready=1), w(wvalid=0, wready=0), w(), w(awvalid=1, awaddr=4, awready=1),
        w(awvalid=0, awready=0, bvalid=1, bready=1), w(bvalid=0, bready=0)],
    "two W beats ahead of their AWs": [
        w(wvalid=1, wready=1, wdata=1), w(wdata=2), w(wvalid=0, wready=0, awvalid=1, awready=1, awaddr=0),
        w(awaddr=4, bvalid=1, bready=1), w(awvalid=0, awready=0), w(bvalid=0, bready=0)],
    "back-to-back writes and reads with zero delay, a response every cycle": [
        w(awvalid=1, awready=1, wvalid=1, wready=1, arvalid=1, arready=1),
        w(bvalid=1, bready=1, rvalid=1, rready=1, awaddr=4, araddr=4),
        w(awaddr=8, araddr=8), w(awvalid=0, awready=0, wvalid=0, wready=0, arvalid=0, arready=0),
        w(bvalid=0, rvalid=0, bready=0, rready=0)],
    "READY before VALID, and READY toggling with no VALID": [
        w(awready=1, wready=1, arready=1, rready=1, bready=1, tready=1), w(awready=0, arready=0), w(awready=1, tready=0),
        w(arready=1, wready=0), w(awvalid=1, awaddr=12, wvalid=1, wready=1), w(awvalid=0, wvalid=0, bvalid=1),
        w(bvalid=0, awready=0, wready=0, arready=0, rready=0, bready=0)],
    "long BREADY and RREADY stalls with stable payload": [
        w(awvalid=1, awready=1, wvalid=1, wready=1, arvalid=1, arready=1), w(awvalid=0, awready=0, wvalid=0, wready=0,
        arvalid=0, arready=0), w(bvalid=1, bresp=2, rvalid=1, rdata=0xABCD, rresp=0), w(), w(), w(), w(), w(), w(),
        w(bready=1, rready=1), w(bvalid=0, rvalid=0, bready=0, rready=0)],
    "VALID raised on the second edge after reset release": [
        w(aresetn=0), w(aresetn=0), w(aresetn=1), w(awvalid=1, wvalid=1, arvalid=1, tvalid=1, tlast=1),
        w(awready=1, wready=1, arready=1, tready=1), w(awvalid=0, wvalid=0, arvalid=0, awready=0, wready=0,
        arready=0, tvalid=0, tready=0, tlast=0, bvalid=1, rvalid=1, bready=1, rready=1), w(bvalid=0, rvalid=0)],
    "reset in the middle of a transaction (VALIDs cleared at the first reset edge)": [
        w(awvalid=1, wvalid=1, arvalid=1), w(aresetn=0), w(aresetn=0, awvalid=0, wvalid=0, arvalid=0),
        w(aresetn=0), w(aresetn=1), w(), w(awvalid=1, awready=1, wvalid=1, wready=1), w(awvalid=0, awready=0,
        wvalid=0, wready=0, bvalid=1, bready=1), w(bvalid=0, bready=0)],
    "a B handshake in the same cycle as the next AW and W handshakes": [
        w(awvalid=1, awready=1, wvalid=1, wready=1), w(awaddr=4, bvalid=1, bready=1), w(awvalid=0, awready=0, wvalid=0,
        wready=0), w(bvalid=0, bready=0)],
    "a stream null beat (TKEEP and TSTRB zero) carrying TLAST": [
        w(tvalid=1, tready=1, tkeep=0xF, tdata=1), w(tkeep=0, tstrb=0, tlast=1), w(tvalid=0, tlast=0, tkeep=0xF, tstrb=0xF)],
    "stream position bytes (TKEEP high, TSTRB low)": [
        w(tvalid=1, tready=1, tkeep=0xF, tstrb=0x5), w(tstrb=0x0, tlast=1), w(tvalid=0, tlast=0, tstrb=0xF)],
    "non-contiguous TKEEP and TREADY stalls with a stable beat": [
        w(tvalid=1, tready=0, tkeep=0x9, tstrb=0x9, tdata=7), w(), w(), w(tready=1), w(tkeep=0x6, tstrb=0x6, tdata=8, tlast=1),
        w(tvalid=0, tready=0, tlast=0)],
}


@cocotb.test()
async def legal_unusual_traffic_fires_nothing(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for k, v in IDLE.items():
        getattr(dut, k).value = v
    dut.aresetn.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.aresetn.value = 1
    await RisingEdge(dut.clk)
    res, total = [], 0
    for name, cycles in SCENARIOS.items():
        fired = []
        for c in cycles + [w()] * 2:
            await Timer(1, unit="ns")
            for k, v in c.items():
                getattr(dut, k).value = v
            await ReadOnly()
            lv, sv_ = int(dut.lviol.value), int(dut.sviol.value) & STREAM_ON      # the profile rules are off in the design
            if lv or sv_:
                fired.append({"lite": lv, "stream": sv_})
            await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        for k, v in IDLE.items():
            getattr(dut, k).value = v
        for _ in range(2):
            await RisingEdge(dut.clk)
        total += len(cycles)
        res.append({"scenario": name, "cycles": len(cycles), "fired": fired})
        dut._log.info("%s: %s", name, "quiet" if not fired else fired)
    out = os.environ.get("AXI_TX_FF_OUT")
    if out:
        with open(out, "w") as f:
            json.dump({"scenarios": len(res), "cycles": total, "fired": sum(bool(r["fired"]) for r in res),
                       "rules": "10 AXI4-Lite, 3 AXI4-Stream protocol rules (profile rules off)", "results": res}, f, indent=1)
            f.write("\n")
    assert not any(r["fired"] for r in res), [r for r in res if r["fired"]]
