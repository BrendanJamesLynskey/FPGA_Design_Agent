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


RX_NEW = dict(order_ok=16, order_bad=17)       # brief 97C: order-content counters (read 0 on a design built before 97C)


async def counters(h):
    await h.snap()
    t = {k: await h.tx(v) for k, v in TX.items()}
    r = {k: await h.rx(v) for k, v in RX.items()}
    r.update({k: await h.rx(v) for k, v in RX_NEW.items()})
    return t, r


async def order_round(dut, h, n=3, clear=False, interval=300, wait_ns=14000):
    """Send n feed frames that each fire an order (the loop returns both) and return the change in every counter over the round."""
    if clear:
        await h.w(0x018, 1)
        await Timer(2000, unit="ns")
    t0, r0 = await counters(h)
    await h.w(0x060, 9975); await h.w(0x064, 250)
    await h.w(0x06C, (7 << 16) | 66)
    await h.w(0x068, 0x1 | 0x4 | (1 << 4))
    await h.w(0x070, 9950); await h.w(0x074, interval); await h.w(0x078, n)
    await h.w(0x018, 2)
    await Timer(wait_ns, unit="ns")
    t1, r1 = await counters(h)
    d = {("t_" + k): t1[k] - t0[k] for k in ("n_order", "n_feed", "poisoned", "late", "stale", "go", "dropped", "underrun")}
    d.update({("r_" + k): r1[k] - r0[k] for k in ("fired", "good", "bad", "err", "order_ok", "order_bad")})
    if clear:       # the cleared counters restart from 0, so the absolute value is the change
        d = {("t_" + k): t1[k] for k in ("n_order", "n_feed", "poisoned", "late", "stale", "go", "dropped", "underrun")}
        d.update({("r_" + k): r1[k] for k in ("fired", "good", "bad", "err", "order_ok", "order_bad")})
    return d


def clean_round(d, n=3):
    return (d["t_n_order"] == n and d["r_fired"] == n and d["t_stale"] == 0 and d["t_poisoned"] == 0 and d["t_late"] == 0 and d["t_dropped"] == 0
            and d["t_underrun"] == 0 and d["r_err"] == 0 and d["t_go"] == n)


async def relink(dut, h, bits):
    """Write the GT reset register (bit 0 all, 3 TX datapath, 4 RX datapath) and wait for both sides and the block lock to come back."""
    await h.w(0x010, bits)
    await Timer(300, unit="ns")
    for _ in range(400):
        await Timer(200, unit="ns")
        st = await h.r(0x014)
        if st & 1 and st & 2 and st & 0x200:
            return
    raise AssertionError(f"link did not come back after reset {bits:#x}: GTSTAT {st:#x}")


async def seq_scenario(dut, name, action, rounds=2):
    """From a clean start (cleared counters, one clean round of 3 orders), do `action` and then run `rounds` rounds of 3 orders; each must be clean
    (no stale, late or poisoned order, the right counts) and every returned order must pass the content check (97C)."""
    h = await bring_up(dut)
    os.environ["B96_ARM"] = "1"
    log = {"start": await order_round(dut, h, clear=True)}
    assert clean_round(log["start"]), log["start"]
    await action(dut, h)
    for i in range(rounds):
        log[f"round{i}"] = await order_round(dut, h)
    dut._log.info(f"SEQ {name} " + json.dumps(log))
    RESULTS.setdefault("seq_scenarios", {})[name] = log
    bad = {k: v for k, v in log.items() if not clean_round(v)}
    assert not bad, bad
    notok = {k: v for k, v in log.items() if k != "start" and (v["r_order_ok"] != 3 or v["r_order_bad"] != 0)}
    assert not notok, notok


async def act_clear(dut, h):
    await h.w(0x018, 1)                       # the bench clears after every relink
    await Timer(2000, unit="ns")              # the clear crosses to both domains (the bench waits much longer)


async def act_rx_relink(dut, h):
    await relink(dut, h, 1 << 4)


async def act_tx_relink(dut, h):
    await relink(dut, h, 1 << 3)


async def act_all_reset(dut, h):
    await relink(dut, h, 1)


async def act_bench_sequence(dut, h):
    for _ in range(4):                        # restart the RX datapath, then clear, as restart_distribution does
        await relink(dut, h, 1 << 4)
        await h.w(0x018, 1)
        await Timer(2000, unit="ns")
        d = await order_round(dut, h)
        assert clean_round(d) and d["r_order_ok"] == 3 and d["r_order_bad"] == 0, d


@cocotb.test()
async def seq_after_counter_clear(dut):
    """Brief 97C: CMD bit 0 clears the order number on the receive side; the transmit side's expectation must follow."""
    await seq_scenario(dut, "counter_clear", act_clear)


@cocotb.test()
async def seq_after_rx_relink(dut):
    """An RX datapath restart (no clear) leaves the order sequence in step."""
    await seq_scenario(dut, "rx_relink", act_rx_relink)


@cocotb.test()
async def seq_after_tx_relink(dut):
    """A TX datapath restart (no clear) leaves the order sequence in step."""
    await seq_scenario(dut, "tx_relink", act_tx_relink)


@cocotb.test()
async def seq_after_all_reset(dut):
    """A reset of the whole GT leaves the order sequence in step."""
    await seq_scenario(dut, "all_reset", act_all_reset)


@cocotb.test()
async def seq_bench_restart_sequence(dut):
    """The stage-3 bench's own sequence: restart the RX datapath, clear, send orders; four times over, then two more rounds."""
    await seq_scenario(dut, "bench_sequence", act_bench_sequence)


@cocotb.test()
async def seq_clear_while_orders_flow(dut):
    """A counter clear in the middle of a stream of orders (the window where a fire and the clear straddle in the two domains): the orders around
    the clear may be flagged stale (fail closed), but the sequence is back in step for the round that follows, at every offset tried."""
    h = await bring_up(dut)
    os.environ["B96_ARM"] = "1"
    await h.w(0x018, 1)
    await Timer(2000, unit="ns")
    await h.w(0x060, 9975); await h.w(0x064, 250)
    await h.w(0x06C, (7 << 16) | 66)
    await h.w(0x068, 0x1 | 0x4 | (1 << 4))
    log = []
    for off in (0, 30, 60, 90, 120, 150, 180):
        await h.w(0x070, 9950); await h.w(0x074, 40); await h.w(0x078, 6)
        await h.w(0x018, 2)
        await Timer(1400 + off, unit="ns")          # the run starts 200 clocks after the command; orders are flowing
        await h.w(0x018, 1)                          # clear in the middle of the stream
        await Timer(12000, unit="ns")
        d = await order_round(dut, h)
        log.append(d)
        assert clean_round(d) and d["r_order_ok"] == 3 and d["r_order_bad"] == 0, (off, d)
    RESULTS["seq_clear_while_orders_flow"] = log


@cocotb.test()
async def seq_mismatch_still_poisons(dut):
    """Fail-safe kept: if the transmit side's count is forced out of step with the order number, the next order is flagged stale, late and
    poisoned (it leaves with a wrong FCS) and the content check counts it bad; the count then re-synchronises, so a persistent offset cannot stay."""
    h = await bring_up(dut)
    os.environ["B96_ARM"] = "1"
    d0 = await order_round(dut, h, clear=True)
    assert clean_round(d0), d0
    dut.u.u_tx.go_cnt.value = int(dut.u.u_tx.go_cnt.value) + 7           # forced mismatch
    await Timer(100, unit="ns")
    d1 = await order_round(dut, h)
    dut._log.info("MISMATCH " + json.dumps(d1))
    RESULTS["seq_forced_mismatch"] = d1
    # the first order after the forced offset is flagged stale, goes out poisoned and is counted bad; it re-loads the count (self-heal), so the
    # orders after it are in step again and pass
    assert d1["t_stale"] == 1 and d1["t_poisoned"] == 1 and d1["t_late"] == 1 and d1["r_order_bad"] == 1 and d1["r_order_ok"] == 2, d1
    d2 = await order_round(dut, h)
    assert clean_round(d2) and d2["r_order_ok"] == 3, d2
    await h.w(0x018, 1)
    d3 = await order_round(dut, h, clear=True)
    assert clean_round(d3) and d3["r_order_ok"] == 3, d3


@cocotb.test()
async def order_content_check_catches_a_wrong_order(dut):
    """An order that leaves with a good FCS but a wrong quantity (the receive side's decision register is changed after the frame source
    sampled it) is counted bad, not ok."""
    h = await bring_up(dut)
    os.environ["B96_ARM"] = "1"
    await h.w(0x018, 1)
    await h.w(0x060, 9975); await h.w(0x064, 250)
    await h.w(0x06C, (7 << 16) | 66)
    await h.w(0x068, 0x1 | 0x4 | (1 << 4))
    await h.w(0x070, 9950); await h.w(0x074, 300); await h.w(0x078, 1)
    await h.w(0x018, 2)
    hit = False
    for _ in range(4000):
        await RisingEdge(dut.refclk)
        if int(dut.u.u_tx.sop.value) and int(dut.u.u_tx.cur_kind.value) == 0:
            hit = True
            break
    assert hit
    for _ in range(12):
        await RisingEdge(dut.refclk)
    dut.u.u_rx.u_td.o_qty.value = 999
    await Timer(10000, unit="ns")
    t, r = await counters(h)
    dut._log.info(f"content: tx {t}\nrx {r}")
    assert t["n_order"] == 1 and t["poisoned"] == 0 and r["good"] == 2 and r["bad"] == 0, (t, r)
    assert r["order_bad"] == 1 and r["order_ok"] == 0, r
    RESULTS["order_content_wrong_qty"] = {"order_ok": r["order_ok"], "order_bad": r["order_bad"], "poisoned": t["poisoned"]}


@cocotb.test()
async def zz_write_results(dut):
    if os.environ.get("B96_CORE_RESULTS"):
        Path(os.environ["B96_CORE_RESULTS"]).write_text(json.dumps(RESULTS, indent=1) + "\n")
