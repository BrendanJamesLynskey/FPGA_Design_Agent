"""Brief 96C: the whole 10G core against a link PARTNER whose clock differs from ours by some ppm (gth_wiz_model96p.sv: separate user clocks,
receive words from this bench).

The partner is a Python 10GBASE-R transmitter (model/pcs.py TxPcs, clocked by the receive clock) sending Bench Feed v1 price frames to us
with idle blocks between them; each frame fires one order (armed, price under the threshold), which leaves on our transmit clock and is checked from
the GT words on the way out. The same bench runs against the main design before 96C (no rate matching) and the current one."""

from __future__ import annotations

import json
import os
import random
import struct
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from designs.b58a_trigger.model import benchfeed as bf
from designs.b96_kr260_10g.model import pcs
from designs.b96_kr260_10g.tests.core_cocotb import RX, TX, Host, frames_from_words

P_FS = 6_205_800                      # 161.1328125 MHz
RESULTS: dict = {}
NEW = os.environ.get("B96_PPM_RATE_MATCH", "1") == "1"
RXV = dict(rm_wr=18, rm_ovf=19, rm_ins=20, rm_del=21, rm_stall=22, rm_out=23, rm_drain=24, rm_fmin=25, rm_fmax=26, f_delta=27, f_win=28, order_ok=16, order_bad=17)
MY_MAC, VENUE_MAC = 0x02_00_00_00_58_0A, 0x02_00_00_00_58_0F
ip = lambda a, b, c, d: (a << 24) | (b << 16) | (c << 8) | d


def feed_frame(seq: int) -> bytes:
    fpl = struct.pack(">HBBI", bf.MAGIC, bf.VERSION, 1, seq) + struct.pack(">BBHIII", bf.ADD, bf.ASK, 7, 9950, 1, 1)
    return bf.ethernet(MY_MAC, VENUE_MAC, bf.ETH_IPV4, bf.ipv4_udp(ip(192, 168, 58, 15), ip(192, 168, 58, 10), 5801, 5800, fpl, ident=0))


GO = {"go": False}


def partner_blocks(n: int, gaps: list[int], rng: random.Random):
    """Generator of XGMII words (d, c): idles until the bench says go, then an idle run before each frame and the frame; forever idles after."""
    while not GO["go"]:
        yield pcs.IDLE_WORD
    for i in range(n):
        for _ in range(gaps[rng.randrange(len(gaps))]):
            yield pcs.IDLE_WORD
        for w in pcs.frame_words(feed_frame(i + 1), lane0=(i % 2 == 0)):
            yield w
    while True:
        yield pcs.IDLE_WORD


async def partner(dut, gen):
    """The partner's transmit side, on the receive clock: one scrambled GT word per edge (gearbox pause included)."""
    tx = pcs.TxPcs()
    nxt = next(gen)
    gt = dut.u.u_gt
    while True:
        await RisingEdge(gt.rxclk)
        take = tx.adv
        w = tx.step(*nxt)
        if take:
            nxt = next(gen)
        gt.rx_word.value = w


async def bring_up_p(dut, ppm, n_frames, gaps, seed):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    cocotb.start_soon(Clock(dut.refclk, P_FS, unit="fs").start())
    pr = round(P_FS / (1 + ppm * 1e-6) / 2) * 2         # a positive ppm: the partner's clock is faster than ours
    await Timer(1_234_567, unit="fs")
    cocotb.start_soon(Clock(dut.u.u_gt.rxclk, pr, unit="fs").start())
    cocotb.start_soon(partner(dut, partner_blocks(n_frames, gaps, random.Random(seed))))
    dut.rst.value = 1; dut.h_we.value = 0; dut.h_re.value = 0; dut.h_addr.value = 0; dut.h_wdata.value = 0
    for _ in range(6):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    h = Host(dut)
    for _ in range(600):
        await Timer(200, unit="ns")
        st = await h.r(0x014)
        if st & 1 and st & 2 and st & 0x200:
            return h
    raise AssertionError(f"link did not come up: GTSTAT {st:#x}")


async def run_point(dut, name, ppm, n_frames=400, gaps=(40, 55, 70, 90), seed=1):
    GO["go"] = False
    h = await bring_up_p(dut, ppm, n_frames, list(gaps), seed)
    words = []
    async def cap():
        while True:
            await RisingEdge(dut.refclk)
            words.append(int(dut.u.tx_data.value))
    cocotb.start_soon(cap())
    if os.environ.get("B96_PPM_DEBUG"):
        async def mon():
            while True:
                await Timer(3000, unit="ns")
                m = dut.u.u_rx.u_rm
                dut._log.info(f"RMDBG wptr {int(m.wptr.value)} rptr {int(m.rptr.value)} wp_s {int(m.wp_s.value)} rp_s {int(m.rp_s.value)} pace {int(m.pace.value)} lock_s {int(m.lock_s.value)} in_frame {int(m.in_frame.value)} ovf {int(m.n_ovf.value)} del {int(m.n_del.value)} ins {int(m.n_ins.value)}")
        cocotb.start_soon(mon())
    await h.w(0x018, 1)
    await Timer(3000, unit="ns")
    await h.w(0x060, 9975); await h.w(0x064, 100)
    await h.w(0x068, 0x1 | 0x4 | (1 << 4))
    GO["go"] = True           # the partner's frames start now
    mean_gap = sum(gaps) / len(gaps)
    run_ns = int(n_frames * (mean_gap + 12) * 6.2058 * 1.1) + 20000
    await Timer(run_ns, unit="ns")
    await h.w(0x018, 4)
    t = {k: await h.tx(v) for k, v in TX.items()}
    r = {k: await h.rx(v) for k, v in RX.items()}
    r.update({k: await h.rx(v) for k, v in RXV.items()} if NEW else {})
    orders = [f for f in frames_from_words(words) if len(f[0]) >= 66 and f[0][36:38] == bytes([0x16, 0xA9])]
    res = dict(name=name, ppm=ppm, frames_sent_by_partner=n_frames, tx=t, rx=r, orders_on_wire=len(orders), orders_fcs_ok=sum(1 for o in orders if o[1]),
               sim_us=run_ns / 1000)
    if NEW:
        res["ppm_measured_from_counter"] = ((r["f_delta"] - (1 << 24)) / (1 << 24) * 1e6) if r["f_win"] >= 2 else None
    dut._log.info("PPM " + json.dumps(res))
    RESULTS[name] = res
    return res


def verdict(res):
    t, r = res["tx"], res["rx"]
    return dict(all_frames_received=(r["good"] >= res["frames_sent_by_partner"] and r["bad"] == 0 and r["err"] == 0 and r["slip"] == 0),
                orders_match_frames=(r["fired"] == res["frames_sent_by_partner"] and t["n_order"] == r["fired"] and res["orders_on_wire"] == t["n_order"]
                                     and res["orders_fcs_ok"] == res["orders_on_wire"]),
                counters_clean=(t["poisoned"] == 0 and t["late"] == 0 and t["stale"] == 0 and t["underrun"] == 0 and t["dropped"] == 0))


POINTS = [float(x) for x in os.environ.get("B96_PPM_POINTS", "0,100,-100,300,-300").split(",")]


@cocotb.test()
@cocotb.parametrize(ppm=POINTS)
async def ppm_point(dut, ppm):
    """One offset (a test of its own, so the clock and partner coroutines of the point before are gone); the verdicts are recorded and, for the
    current design, must all hold."""
    res = await run_point(dut, f"ppm{ppm:+g}", ppm, n_frames=int(os.environ.get("B96_PPM_FRAMES", "400")),
                          gaps=tuple(int(g) for g in os.environ.get("B96_PPM_GAPS", "40,55,70,90").split(",")))
    v = verdict(res)
    res["verdict"] = v
    dut._log.info(f"PPM VERDICT {ppm:+g} {json.dumps(v)}")
    if os.environ.get("B96_PPM_RESULTS"):
        Path(os.environ["B96_PPM_RESULTS"]).write_text(json.dumps(RESULTS, indent=1) + "\n")
    if os.environ.get("B96_PPM_EXPECT_FAIL") != "1":
        assert all(v.values()), v
