"""cocotb bench of the whole 10G core (rtl/b96_core.sv: registers, GT stand-in, tx_path, rx_path, crossings) in brief 96.

The GT is the behavioural stand-in (it closes the loop word for word, with a chosen bit offset); the reference for every frame is the Python
Bench Feed v1 builder of brief 58A (designs/b58a_trigger/model/benchfeed.py) and the Python PCS model of this design."""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from designs.b58a_trigger.model import benchfeed as bf
from designs.b96_kr260_10g.model import pcs

REF_PS = 6206
RESULTS: dict = {}


class Host:
    """The register bus as the JTAG front end drives it: write and read one 32-bit register at a time."""

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

    async def snap(self):
        await self.w(0x018, 4)

    async def tx(self, i):
        return await self.r(0x200 + 4 * i)

    async def rx(self, i):
        return await self.r(0x100 + 4 * i)


TX = dict(n_order=0, n_feed=1, n_probe=2, n_test=3, poisoned=4, dropped=5, underrun=6, late=7, stale=8, go=9, t_tx_feed=10, t_tx_probe=11,
          t_tx_order=12, t_rx_feed=13, t_rx_probe=14, t_rx_order=15, e_last=16, e_min=17, e_max=18, e_cnt=19, l_last=20, l_min=21,
          l_max=22, l_cnt=23, d_last=24, ts=25)
RX = dict(lock=0, slip=1, loss=2, lock_ev=3, sh=4, type=5, os=6, frames=7, good=8, bad=9, err=10, fired=11, blocked=12, toolong=13,
          last_len=14, lock_clk=15)


async def bring_up(dut, near_end=True):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    cocotb.start_soon(Clock(dut.refclk, REF_PS, unit="ps").start())
    dut.rst.value = 1; dut.h_we.value = 0; dut.h_re.value = 0; dut.h_addr.value = 0; dut.h_wdata.value = 0
    for _ in range(6):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    h = Host(dut)
    # wait for tx_done, rx_done and block lock (the GT stand-in takes about 700 free-running clocks, then 66 words to lock)
    for _ in range(400):
        await Timer(200, unit="ns")
        st = await h.r(0x014)
        if st & 1 and st & 2 and st & 0x200:
            return h
    raise AssertionError(f"link did not come up: GTSTAT {st:#x}")


def capture(dut, store):
    async def run():
        while True:
            await RisingEdge(dut.refclk)
            store.append(int(dut.u.tx_data.value))
    return cocotb.start_soon(run())


def frames_from_words(words):
    """Frames (bytes without FCS, fcs_ok) in the transmitted GT words, decoded by the reference receiver."""
    rx = pcs.RxPcs()
    for w in words:
        rx.step(w)
    return [(f["data"], f.get("fcs_ok")) for f in pcs.parse_xgmii([(d, c) for d, c, _ in rx.out]) if "data" in f]


async def run_loop(dut, h, kind, count=1, price=9950, interval=2000, wait_ns=9000):
    await h.w(0x068, (kind << 4) | (h_arm(dut)))
    await h.w(0x070, price)
    await h.w(0x074, interval)
    await h.w(0x078, count)
    await h.w(0x018, 2)
    await Timer(wait_ns, unit="ns")
    await h.snap()


def h_arm(dut):
    return int(os.environ.get("B96_ARM", "0"))


@cocotb.test()
async def echo_probe(dut):
    """A probe frame sent by the generator comes back through the (near-end) loop: counted once, FCS good, echo time recorded."""
    h = await bring_up(dut)
    await h.w(0x018, 1)                       # clear counters
    await run_loop(dut, h, kind=2, count=3, interval=300)
    n_probe = await h.tx(TX["n_probe"]); e_cnt = await h.tx(TX["e_cnt"]); e_min = await h.tx(TX["e_min"]); e_max = await h.tx(TX["e_max"])
    good = await h.rx(RX["good"]); bad = await h.rx(RX["bad"])
    dut._log.info(f"echo: sent {n_probe} cnt {e_cnt} E {e_min}..{e_max} good {good} bad {bad}")
    assert n_probe == 3 and e_cnt == 3 and good == 3 and bad == 0
    assert e_min == e_max and 8 <= e_min <= 40, (e_min, e_max)
    RESULTS["echo_clocks_sim"] = {"min": e_min, "max": e_max}
    assert await h.tx(TX["underrun"]) == 0


@cocotb.test()
async def trading_loop_armed(dut):
    """A feed frame (ask 99.50, threshold 99.75) loops back, the trading path fires, the order frame loops back: all frame bytes checked."""
    h = await bring_up(dut)
    words = []
    capture(dut, words)
    await h.w(0x018, 1)
    await h.w(0x060, 9975); await h.w(0x064, 250)
    await h.w(0x06C, (7 << 16) | 66)
    os.environ["B96_ARM"] = "1"
    await h.w(0x068, 0x1 | 0x4 | (1 << 4))
    await h.w(0x070, 9950); await h.w(0x074, 1000); await h.w(0x078, 1)
    await h.w(0x018, 2)
    await Timer(8000, unit="ns")
    await h.snap()
    t = {k: await h.tx(v) for k, v in TX.items()}
    r = {k: await h.rx(v) for k, v in RX.items()}
    dut._log.info(f"tx {t}\nrx {r}")
    assert t["n_feed"] == 1 and t["n_order"] == 1 and r["fired"] == 1 and t["stale"] == 0 and t["late"] == 0 and t["poisoned"] == 0
    assert t["l_cnt"] == 1 and r["good"] == 2 and r["bad"] == 0 and t["underrun"] == 0 and t["dropped"] == 0
    fr = frames_from_words(words)
    assert len(fr) >= 2, len(fr)
    feed, order = fr[-2], fr[-1]
    assert feed[1] and order[1]
    want = bf.ethernet(0x0F58000000 << 8 | 0x02, 0, 0, b"")  # placeholder replaced below
    my_mac, venue_mac = 0x02_00_00_00_58_0A, 0x02_00_00_00_58_0F
    ip = lambda a, b, c, d: (a << 24) | (b << 16) | (c << 8) | d
    my_ip, venue_ip = ip(192, 168, 58, 10), ip(192, 168, 58, 15)
    # the order: NEW_ORDER, buy, instrument 7, price 99.50, qty 250, order id 1, sequence 1
    pl = struct.pack(">HBBI", bf.MAGIC, bf.VERSION, 1, 1) + struct.pack(">BBHIII", bf.NEW_ORDER, bf.BUY, 7, 9950, 250, 1)
    want = bf.ethernet(venue_mac, my_mac, bf.ETH_IPV4, bf.ipv4_udp(my_ip, venue_ip, 5800, 5801, pl, ident=0))
    assert order[0] == want, (order[0].hex(), want.hex())
    # the feed frame: from the "venue", an ADD on the ask side
    fpl = struct.pack(">HBBI", bf.MAGIC, bf.VERSION, 1, 1) + struct.pack(">BBHIII", bf.ADD, bf.ASK, 7, 9950, 1, 1)
    wantf = bf.ethernet(my_mac, venue_mac, bf.ETH_IPV4, bf.ipv4_udp(venue_ip, my_ip, 5801, 5800, fpl, ident=0))
    assert feed[0] == wantf, (feed[0].hex(), wantf.hex())
    RESULTS["loop_clocks_sim"] = {"L": t["l_last"], "E_not_measured_here": True, "d_last": t["d_last"]}


@cocotb.test()
async def trade_decisions(dut):
    """Prices above the threshold, the kill bit and the disarmed state send no order; counters say why."""
    h = await bring_up(dut)
    await h.w(0x018, 1)
    await h.w(0x060, 9975); await h.w(0x064, 100)
    await h.w(0x068, 0x1 | 0x4 | (1 << 4))
    await h.w(0x06C, (1 << 16) | 66)
    for price, arm, kill, expect in ((10000, 1, 0, 0), (9975, 1, 0, 1), (9950, 0, 0, 0), (9950, 1, 1, 0)):
        await h.w(0x068, arm | (kill << 1) | 0x4 | (1 << 4))
        await h.w(0x018, 1)
        await h.w(0x070, price); await h.w(0x074, 500); await h.w(0x078, 1)
        await h.w(0x018, 2)
        await Timer(6000, unit="ns")
        await h.snap()
        fired = await h.rx(RX["fired"]); sent = await h.tx(TX["n_order"])
        dut._log.info(f"price {price} arm {arm} kill {kill}: fired {fired} sent {sent} blocked {await h.rx(RX['blocked'])}")
        assert fired == expect and sent == expect, (price, arm, kill, fired, sent)


async def poison_case(dut, trigger_wi, expect_err):
    h = await bring_up(dut)
    await h.w(0x018, 1)
    await h.w(0x060, 9975); await h.w(0x064, 100)
    await h.w(0x06C, (1 << 16) | 66)
    await h.w(0x068, 0x1 | 0x4 | (1 << 4))
    await h.w(0x070, 9950); await h.w(0x074, 500); await h.w(0x078, 1)
    words = []
    capture(dut, words)
    await h.w(0x018, 2)
    hit = False
    for _ in range(4000):
        await RisingEdge(dut.refclk)
        if int(dut.u.u_rx.u_td.wi.value) == trigger_wi:
            dut.u.u_gt.corrupt_xor.value = 1 << 20
            await RisingEdge(dut.refclk)
            dut.u.u_gt.corrupt_xor.value = 0
            hit = True
            break
    assert hit
    await Timer(6000, unit="ns")
    await h.snap()
    t = {k: await h.tx(v) for k, v in TX.items()}
    r = {k: await h.rx(v) for k, v in RX.items()}
    dut._log.info(f"poison {trigger_wi}: tx {t}\nrx {r}")
    assert r["fired"] == 1 and t["n_order"] == 1 and t["poisoned"] == 1, (r, t)
    assert r["bad"] >= 1 and (r["err"] >= 1) == expect_err
    assert t["late"] == 0 and t["stale"] == 0
    fr = frames_from_words(words)
    order = [f for f in fr if len(f[0]) >= 66 and f[0][36:38] == bytes([0x16, 0xA9])]       # UDP destination port 5801 (0x16A9)
    assert order and order[-1][1] is False, "the order must leave with a wrong FCS"


@cocotb.test()
async def poisoned_order_bad_fcs(dut):
    """The feed frame is damaged on the wire after the decision (its FCS fails): the order, already under way, leaves with a wrong FCS."""
    await poison_case(dut, 4, expect_err=False)


@cocotb.test()
async def poisoned_order_cut_frame(dut):
    """The feed frame is cut by a line error that makes a block an error block: the order leaves with a wrong FCS too."""
    await poison_case(dut, 3, expect_err=True)


@cocotb.test()
async def tick_to_trade_digital(dut):
    """The fabric's own tick-to-trade in clocks, from the clock edge that captures the GT word completing the price field (RX side) to the clock
    edge at which the first word of the order frame is in the MAC output register (sop) and to the one at which its start block is complete on
    the GT's TXDATA. Same-frequency, same-phase clocks in this bench: the receive-to-transmit crossing is its fixed part only (on the board it
    is that plus up to one clock of phase)."""
    h = await bring_up(dut)
    await h.w(0x018, 1)
    await h.w(0x060, 9975); await h.w(0x064, 100)
    await h.w(0x06C, (1 << 16) | 66)
    await h.w(0x068, 0x1 | 0x4 | (1 << 4))
    await h.w(0x070, 9950); await h.w(0x074, 500); await h.w(0x078, 1)
    await h.w(0x018, 2)
    ev = {}
    k = 0
    for _ in range(6000):
        await RisingEdge(dut.refclk)
        await Timer(100, unit="ps")
        k += 1
        td = dut.u.u_rx.u_td
        if "w7" not in ev and int(dut.u.u_rx.m_v.value) and int(td.wi.value) == 7 and int(td.is_feed.value):
            ev["w7_at_mac"] = k
        if "fire" not in ev and int(td.fire.value):
            ev["fire_reg"] = k
        if "go" not in ev and int(dut.u.u_tx.go_p.value):
            ev["go_pulse_tx"] = k
        if "sop" not in ev and int(dut.u.u_tx.sop.value) and int(dut.u.u_tx.cur_kind.value) == 0:
            ev["sop_mac_reg"] = k
            break
    assert {"w7_at_mac", "fire_reg", "go_pulse_tx", "sop_mac_reg"} <= set(ev), ev
    out = {
        "price_word_captured_at_gt_to_mac_register_clocks": 2,          # measured in latency_by_gearbox_phase (pcs_mac_cocotb): captured +2
        "mac_register_to_fire_register_clocks": ev["fire_reg"] - ev["w7_at_mac"],
        "fire_register_to_go_pulse_in_tx_domain_clocks": ev["go_pulse_tx"] - ev["fire_reg"],
        "go_pulse_to_order_preamble_in_mac_register_clocks": ev["sop_mac_reg"] - ev["go_pulse_tx"],
        "mac_register_of_price_word_to_order_preamble_clocks": ev["sop_mac_reg"] - ev["w7_at_mac"],
    }
    # capture edge of the price word = MAC register edge - 2; the order's start block is complete on TXDATA 2 clocks after the preamble is in the MAC register
    out["gt_rxdata_price_word_to_gt_txdata_order_start_clocks"] = out["mac_register_of_price_word_to_order_preamble_clocks"] + 2 + 2
    dut._log.info("TTT " + json.dumps(out))
    RESULTS["tick_to_trade_digital_sim"] = out


@cocotb.test()
async def zz_write_results(dut):
    if os.environ.get("B96_CORE_RESULTS"):
        Path(os.environ["B96_CORE_RESULTS"]).write_text(json.dumps(RESULTS, indent=1) + "\n")
