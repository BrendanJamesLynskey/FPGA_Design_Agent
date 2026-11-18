"""cocotb bench of rtl/rate_match.sv against its twin model/ratematch.py (brief 96C): two free-running clocks at a chosen offset, a block
stream from the stimulus module, and a cycle-by-cycle comparison of the reader's output and every counter."""

from __future__ import annotations

import json
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.utils import get_sim_time

from designs.b96_kr260_10g.model import ratematch as rm
from designs.b96_kr260_10g.tests import ratematch_stim as st

P_NOM_FS = 6_205_800          # 161.1328125 MHz is 6205.8 ps
RESULTS: dict = {}


async def run_case(dut, name, ppm, n_frames=300, gaps=(2,), seed=1, hi=4, os_every=0, err_every=0, lock_drop=None, w_offset_fs=1_234_567,
                   r_start_fs=0, phase=0):
    """One run. The write clock is nominal (the partner's) and the read clock is offset by `ppm` (ours = partner * (1 - ppm*1e-6), so a
    positive ppm means the partner is faster than we are). Returns a dict of results and asserts RTL == twin."""
    rng = random.Random(seed)
    pw = P_NOM_FS
    pr = round(P_NOM_FS * (1 + ppm * 1e-6) / 2) * 2
    frames = st.make_frames(rng, n_frames)
    blocks = st.block_stream(rng, frames, list(gaps), os_every=os_every, err_every=err_every)
    ent = st.to_entries(blocks, phase=phase)
    n_w = len(ent) - 300
    in_flight = {"w_t": [], "r_t": [], "w_in": [(0, 0, 0, 0)], "w_lock": [0], "r_rst": [1], "clr": [0], "out": []}
    dut.w_v.value = 0; dut.w_d.value = 0; dut.w_c.value = 0; dut.w_os.value = 0; dut.w_lock.value = 0; dut.rrst.value = 1; dut.clr_r.value = 0
    cocotb.start_soon(Clock(dut.wclk, pw, unit="fs").start())
    await Timer(r_start_fs + w_offset_fs, unit="fs")
    cocotb.start_soon(Clock(dut.rclk, pr, unit="fs").start())
    done = {"w": False}
    n_rst = 40

    async def w_drv():
        i = 0
        while True:
            await RisingEdge(dut.wclk)
            in_flight["w_t"].append(get_sim_time("fs"))
            k = len(in_flight["w_t"])               # edges seen; inputs set now are held before edge k
            # lock rises after the reset period, drops for [lock_drop[0], lock_drop[1]) write edges if asked
            lock = 1 if k > n_rst else 0
            if lock_drop and lock_drop[0] <= k < lock_drop[1]:
                lock = 0
            e = ent[k - n_rst - 8] if (lock and 0 <= k - n_rst - 8 < len(ent) and k <= n_w) else (0, 0, 0, 0)
            if lock_drop and lock_drop[0] <= k < lock_drop[1] + 70:
                e = (0, 0, 0, 0)
            dut.w_v.value = e[0]; dut.w_d.value = e[1]; dut.w_c.value = e[2]; dut.w_os.value = e[3]; dut.w_lock.value = lock
            in_flight["w_in"].append(e); in_flight["w_lock"].append(lock)
            if k > n_w:
                done["w"] = True
                dut.w_v.value = 0
            if done.get("stop"):
                return

    async def r_mon():
        j = 0
        while True:
            await RisingEdge(dut.rclk)
            in_flight["r_t"].append(get_sim_time("fs"))
            j = len(in_flight["r_t"])
            in_flight["out"].append((int(dut.r_v.value), int(dut.r_d.value), int(dut.r_c.value), int(dut.r_lock.value)))
            rst = 1 if j < n_rst else 0
            dut.rrst.value = rst
            in_flight["r_rst"].append(rst)
            in_flight["clr"].append(0)
            if done["w"] and j > n_w + 120:
                done["stop"] = True
                await Timer(1, unit="ns")
                in_flight["out"].append((int(dut.r_v.value), int(dut.r_d.value), int(dut.r_c.value), int(dut.r_lock.value)))     # state after the last edge
                in_flight["cnt"] = {k: int(getattr(dut, k).value) for k in ("n_ovf", "n_ins", "n_del", "n_stall", "n_out", "fill_min", "fill_max")}
                return

    wt = cocotb.start_soon(w_drv())
    rt = cocotb.start_soon(r_mon())
    await wt
    await rt
    cnt = in_flight["cnt"]
    # twin on the same edges and inputs
    r_t = in_flight["r_t"]
    w_t = [t for t in in_flight["w_t"] if t < r_t[-1]]
    out, m = rm.run(w_t, r_t, in_flight["w_in"][:len(w_t)], w_lock=in_flight["w_lock"], r_rst=in_flight["r_rst"][:len(r_t)], hi=hi, min_keep=1)
    # RTL output sampled at read edge j (pre-edge) = state after edge j-1
    bad = 0
    first = None
    for j in range(1, len(r_t) + 1):
        v, d, c, lk = in_flight["out"][j]
        tv, tb, tl = out[j - 1]
        same = (bool(v) == tv) and (bool(lk) == tl) and (not v or (d, c) == (tb[0], tb[1]))
        if not same:
            bad += 1
            if first is None:
                first = (j, (v, hex(d), hex(c), lk), (tv, [hex(tb[0]), hex(tb[1])], tl))
    tw = dict(n_ovf=m.n_ovf, n_ins=m.n_ins, n_del=m.n_del, n_stall=m.n_stall, n_out=m.n_out, fill_min=m.fill_min, fill_max=m.fill_max)
    # the frames out of the RTL (valid blocks only) against the frames offered
    got = [(d, c) for (v, d, c, lk) in in_flight["out"] if v]
    frames_in = st.frames_of([(b[0], b[1]) for b in blocks])
    frames_out = st.frames_of(got)
    res = dict(name=name, ppm=ppm, edges_w=len(w_t), edges_r=len(r_t), mismatch=bad, first=first, rtl=cnt, twin=tw,
               frames_in=len(frames_in), frames_out=len(frames_out), frames_equal=frames_in == frames_out,
               secs=(r_t[-1] - r_t[0]) * 1e-15)
    dut._log.info("RM " + json.dumps(res, default=str))
    RESULTS[name] = res
    assert bad == 0, res
    assert cnt == tw, (cnt, tw)
    return res


@cocotb.test()
async def same_clocks(dut):
    """Equal frequencies, a fixed phase: after the start-up insertions nothing is inserted or deleted."""
    r = await run_case(dut, "same", 0)
    assert r["frames_equal"] and r["rtl"]["n_ovf"] == 0, r


@cocotb.test()
async def partner_faster(dut):
    """The partner's clock is 400 ppm faster than ours: the fill grows, idles are deleted, every frame is intact."""
    r = await run_case(dut, "p400", 400, n_frames=700, gaps=(2, 3, 1, 4))
    assert r["frames_equal"] and r["rtl"]["n_del"] > 0 and r["rtl"]["n_ovf"] == 0, r


@cocotb.test()
async def partner_slower(dut):
    """The partner's clock is 400 ppm slower: the fill falls, idles are inserted, every frame is intact."""
    r = await run_case(dut, "m400", -400, n_frames=700, gaps=(2, 3, 1, 4))
    assert r["frames_equal"] and r["rtl"]["n_ins"] > 0 and r["rtl"]["n_ovf"] == 0, r


@cocotb.test()
async def minimum_gap_partner_faster(dut):
    """One idle block between frames (a minimum-gap stream), the partner 150 ppm faster: deletion is possible only after an idle block was
    output, so fewer chances; every frame still intact and nothing lost."""
    r = await run_case(dut, "p150_gap1", 150, n_frames=900, gaps=(1,), seed=3)
    assert r["frames_equal"] and r["rtl"]["n_ovf"] == 0, r


@cocotb.test()
async def ordered_sets_and_errors_pass(dut):
    """Ordered-set blocks (shown as idles) and error blocks between frames: the RTL equals the twin; frames intact."""
    r = await run_case(dut, "os_err", 300, n_frames=600, gaps=(2, 1, 3), seed=4, os_every=3, err_every=5)
    assert r["frames_equal"], r


@cocotb.test()
async def lock_loss_discards(dut):
    """The block lock drops for a while mid-stream: the buffer is discarded, nothing is output meanwhile; the RTL equals the twin."""
    r = await run_case(dut, "lockdrop", 100, n_frames=300, gaps=(2,), seed=5, lock_drop=(6000, 6100))
    assert r["rtl"]["n_ovf"] == 0, r
