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

MIN_KEEP = int(os.environ.get("B96_RM_MIN_KEEP", "0"))
IMPL = os.environ.get("B96_RM_IMPL", "macro")        # brief 96E: "gp" = rtl/rate_match_gp.sv (own gray-pointer buffer), twin RateMatchGP
HI = int(os.environ.get("B96_RM_HI", "4"))
ENT_SYNC = os.environ.get("B96_RM_ENT_SYNC", "1") == "1"      # rate_match_gp's ENT_SYNC (the twin follows)
P_NOM_FS = 6_205_800          # 161.1328125 MHz is 6205.8 ps
RESULTS: dict = {}


async def run_case(dut, name, ppm, n_frames=300, gaps=(2,), seed=1, hi=None, os_every=0, err_every=0, lock_drop=None, w_offset_fs=1_234_567,
                   r_start_fs=0, phase=0, clr_at=None, pause_after_start=0, r_rst_clks=40):
    """One run. The write clock is nominal (the partner's) and the read clock is offset by `ppm` (ours = partner * (1 - ppm*1e-6), so a
    positive ppm means the partner is faster than we are). Returns a dict of results and asserts RTL == twin."""
    hi = HI if hi is None else hi
    rng = random.Random(seed)
    pw = P_NOM_FS
    pr = round(P_NOM_FS * (1 + ppm * 1e-6) / 2) * 2
    frames = st.make_frames(rng, n_frames)
    blocks = st.block_stream(rng, frames, list(gaps), os_every=os_every, err_every=err_every)
    ent = st.to_entries(blocks, phase=phase, pause_after_start=pause_after_start)
    n_w = len(ent) - 300
    in_flight = {"w_t": [], "r_t": [], "wclr": [0], "w_in": [(0, 0, 0, 0)], "w_lock": [0], "r_rst": [1], "clr": [0], "out": []}
    dut.w_v.value = 0; dut.w_d.value = 0; dut.w_c.value = 0; dut.w_os.value = 0; dut.w_lock.value = 0; dut.rrst.value = 1; dut.clr_r.value = 0; dut.clr_w.value = 0
    cocotb.start_soon(Clock(dut.wclk, pw, unit="fs").start())
    await Timer(r_start_fs + w_offset_fs, unit="fs")
    cocotb.start_soon(Clock(dut.rclk, pr, unit="fs").start())
    done = {"w": False}
    n_rst = 40

    async def w_drv():
        i = 0
        for _ in range(2_000_000):
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
            wc = 1 if (k == 5 or (clr_at and k == clr_at[0])) else 0      # the write-side counters are cleared at the start (the DUT is never reset between cases)
            dut.clr_w.value = wc
            in_flight["wclr"].append(wc)
            in_flight["w_in"].append(e); in_flight["w_lock"].append(lock)
            if k > n_w:
                done["w"] = True
                dut.w_v.value = 0
            if done.get("stop"):
                return

    async def r_mon():
        j = 0
        for _ in range(2_000_000):
            await RisingEdge(dut.rclk)
            in_flight["r_t"].append(get_sim_time("fs"))
            j = len(in_flight["r_t"])
            in_flight["out"].append((int(dut.r_v.value), int(dut.r_d.value), int(dut.r_c.value), int(dut.r_lock.value)))
            rst = 1 if j < r_rst_clks else 0
            dut.rrst.value = rst
            in_flight["r_rst"].append(rst)
            cl = 1 if (clr_at and j == clr_at[1]) else 0
            dut.clr_r.value = cl
            in_flight["clr"].append(cl)
            if done["w"] and j > n_w + 120:
                done["stop"] = True
                await Timer(1, unit="ns")
                in_flight["out"].append((int(dut.r_v.value), int(dut.r_d.value), int(dut.r_c.value), int(dut.r_lock.value)))     # state after the last edge
                in_flight["cnt"] = {k: int(getattr(dut, k).value) for k in ("n_ovf", "n_wr", "n_ins", "n_del", "n_stall", "n_out", "n_drain", "fill_min", "fill_max")}
                return

    wt = cocotb.start_soon(w_drv())
    rt = cocotb.start_soon(r_mon())
    await wt
    await rt
    cnt = in_flight["cnt"]
    # twin on the same edges and inputs
    r_t = in_flight["r_t"]
    w_t = [t for t in in_flight["w_t"] if t < r_t[-1]]
    out, m = rm.run(w_t, r_t, in_flight["w_in"][:len(w_t)], w_lock=in_flight["w_lock"], r_rst=in_flight["r_rst"][:len(r_t)], clr=in_flight["clr"][:len(r_t)], w_clr=in_flight["wclr"], hi=hi, min_keep=MIN_KEEP, impl=IMPL, **({"ent_sync": ENT_SYNC} if IMPL == "gp" else {}))
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
    tw = dict(n_ovf=m.n_ovf, n_wr=m.n_wr, n_ins=m.n_ins, n_del=m.n_del, n_stall=m.n_stall, n_out=m.n_out, n_drain=m.n_drain, fill_min=m.fill_min, fill_max=m.fill_max)
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


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def same_clocks(dut):
    """Equal frequencies, a fixed phase: after the start-up insertions nothing is inserted or deleted."""
    r = await run_case(dut, "same", 0)
    assert r["frames_equal"] and r["rtl"]["n_ovf"] == 0, r


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def partner_faster(dut):
    """The partner's clock is 400 ppm faster than ours: the fill grows, idles are deleted, every frame is intact."""
    r = await run_case(dut, "p400", 400, n_frames=700, gaps=(2, 3, 1, 4))
    assert r["frames_equal"] and r["rtl"]["n_del"] > 0 and r["rtl"]["n_ovf"] == 0, r


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def partner_slower(dut):
    """The partner's clock is 400 ppm slower: the fill falls, idles are inserted, every frame is intact."""
    r = await run_case(dut, "m400", -400, n_frames=700, gaps=(2, 3, 1, 4))
    assert r["frames_equal"] and r["rtl"]["n_ins"] > 0 and r["rtl"]["n_ovf"] == 0, r


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def minimum_gap_partner_faster(dut):
    """One idle block between frames (a minimum-gap stream, 802.3's 12-byte gap holds one pure idle block), the partner 300 ppm faster, 5000 frames (about 4,000 clocks per
    deletion needed, so the buffer would fill from about 1 to its 16 blocks after about 60,000 clocks). With MIN_KEEP = 0 a lone idle block may be deleted: nothing overflows.
    With MIN_KEEP = 1 (B96_RM_MIN_KEEP=1) it cannot be: this bench then shows the limit, a buffer that overflows and cuts frames (counted, FCS-failing, never silent)."""
    r = await run_case(dut, "p300_gap1_long", 300, n_frames=5000, gaps=(1,), seed=3)
    if MIN_KEEP == 0:
        assert r["frames_equal"] and r["rtl"]["n_ovf"] == 0 and r["rtl"]["n_del"] > 5, r
    else:
        assert r["rtl"]["n_ovf"] > 0 and not r["frames_equal"], r


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def ordered_sets_and_errors_pass(dut):
    """Ordered-set blocks (shown as idles) and error blocks between frames: the RTL equals the twin; frames intact."""
    r = await run_case(dut, "os_err", 300, n_frames=600, gaps=(2, 1, 3), seed=4, os_every=3, err_every=5)
    assert r["frames_equal"], r


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def lock_loss_discards(dut):
    """The block lock drops for a while mid-stream: the buffer is discarded, nothing is output meanwhile; the RTL equals the twin."""
    r = await run_case(dut, "lockdrop", 100, n_frames=300, gaps=(2,), seed=5, lock_drop=(6000, 6100))
    assert r["rtl"]["n_ovf"] == 0, r


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def clear_wins_over_a_count(dut):
    """A counter clear in the write and read domains in the middle of a stream (blocks are being counted in that very clock): the counters restart from the clear."""
    r = await run_case(dut, "clear", 150, n_frames=200, gaps=(2,), seed=7, clr_at=(3000, 3000))
    assert r["frames_equal"] and r["rtl"]["n_wr"] < 7000, r


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def pause_right_after_a_frame_start(dut):
    """Brief 152: the write side has nothing to write for 40 clocks right after every frame-start block (Start in lane 0 for two frames in three, in lane 4 for one in three), so
    the buffer is empty when the reader has output the start block and the next slot finds nothing to read. Inside a frame the reader must stall (n_stall counts it) and never insert an idle
    block: a reader that does not recognise a start block as the start of a frame (the in-frame flag is set from the block just output) inserts an idle there and cuts the frame.
    Found by brief 152: a mutant that changed the lane-4 start byte compared in head_frame (0xFB to 0xFA) survived the five-case bench of brief 143b, because in its streams the buffer
    never happens to be empty right after a lane-4 start block."""
    r = await run_case(dut, "pause_after_start", 0, n_frames=40, gaps=(2, 3), seed=11, pause_after_start=40)
    assert r["frames_equal"] and r["rtl"]["n_stall"] > 0 and r["rtl"]["n_ovf"] == 0, r


@cocotb.test(timeout_time=50, timeout_unit="ms")
async def writer_outruns_a_reader_held_in_reset(dut):
    """Brief 152: the read side is held in reset for 400 clocks while the write side offers a stream, so the 16-entry buffer fills and the writer must refuse the blocks that do not fit
    (n_ovf counts every one, the pointers never wrap onto unread entries). The RTL equals the twin, counters included, and n_ovf is not zero. Found by brief 152: a mutant whose full flag
    was never true (the mask of the write-side fill computation tied to 0) survived every case of brief 143b's bench, none of which fills the buffer (fill_max 6 of 16 in the longest);
    the SymbiYosys bench of brief 115 (p1_no_overflow) caught it."""
    r = await run_case(dut, "reader_in_reset", 0, n_frames=30, gaps=(2, 3), seed=13, r_rst_clks=400)
    assert r["rtl"]["n_ovf"] > 0 and r["rtl"]["fill_max"] >= 15, r


# ---- Brief 168: MIN_KEEP 1 to 3 on rate_match_gp ----------------------------------------------------------------------------------------------------------------------------------------------
# A documented parameter (design.md section 9: delete only after MIN_KEEP consecutive pure idle blocks were output) that no earlier bench instantiated on the own buffer (the MIN_KEEP = 1 case ran the xpm macro).
# The cases below run only when B96_RM_MIN_KEEP is 1, 2 or 3 (they skip at 0, so the nine cases above and their mutation records are unchanged); the Python twin follows min_keep. Stream gaps are written in
# terms of K = MIN_KEEP: a deletion needs K pure idles output and then one more idle at the head, in the one clock in 33 that is not a read slot, so a gap of K idle blocks cannot allow one (the block after the K
# idles is a frame start) and a gap of K + 6 gives six chances per gap. The partner is 1000 to 2500 ppm fast (or slow) so that a few hundred frames are enough for the buffer to need many deletions
# (+400 ppm would need thousands of frames); the deletion capacity of a K + 6 gap is a few thousand ppm, so the stream is sustainable, and that of a gap of K is none.
K = MIN_KEEP


@cocotb.test(timeout_time=50, timeout_unit="ms", skip=(MIN_KEEP == 0))
async def keep_deletes_after_enough_idles(dut):
    """Every gap is MIN_KEEP + 6 idle blocks: the reader may delete after MIN_KEEP idles, so the fast partner never overflows the buffer, deletions happen, every frame is intact, RTL == twin."""
    r = await run_case(dut, "keep_deletes", 1500, n_frames=250, gaps=(K + 6,), seed=21)
    assert r["frames_equal"] and r["rtl"]["n_del"] > 5 and r["rtl"]["n_ovf"] == 0, r


@cocotb.test(timeout_time=50, timeout_unit="ms", skip=(MIN_KEEP == 0))
async def keep_refuses_short_gaps(dut):
    """Every gap is MIN_KEEP idle blocks (one idle fewer than a deletion needs) and the partner is fast: nothing can be deleted between frames, the 16-entry buffer fills and overflows (counted in n_ovf,
    never silent: the frames it cuts fail their FCS), RTL == twin. This is the documented limit of MIN_KEEP (design.md section 9), now shown on the own buffer for 1 to 3."""
    r = await run_case(dut, "keep_short", 2500, n_frames=200, gaps=(K,), seed=22)
    assert r["rtl"]["n_ovf"] > 0 and not r["frames_equal"], r


@cocotb.test(timeout_time=50, timeout_unit="ms", skip=(MIN_KEEP == 0))
async def keep_mixed_gaps(dut):
    """Gaps of MIN_KEEP, MIN_KEEP + 1, 1, MIN_KEEP + 6, MIN_KEEP + 3 and 1 idle blocks in turn: some gaps allow a deletion and some do not; RTL == twin, deletions happen."""
    r = await run_case(dut, "keep_mixed", 1000, n_frames=300, gaps=(K, K + 1, 1, K + 6, K + 3, 1), seed=23)
    assert r["rtl"]["n_del"] > 0, r


@cocotb.test(timeout_time=50, timeout_unit="ms", skip=(MIN_KEEP == 0))
async def keep_with_ordered_sets_and_errors(dut):
    """Ordered-set and error blocks between frames (they are not pure idles, so they restart the idle run), gaps of MIN_KEEP + 6 and MIN_KEEP + 7; RTL == twin, counters included."""
    r = await run_case(dut, "keep_os_err", 1000, n_frames=250, gaps=(K + 6, K + 7), seed=24, os_every=3, err_every=5)
    assert r["rtl"]["n_out"] > 0, r


@cocotb.test(timeout_time=50, timeout_unit="ms", skip=(MIN_KEEP == 0))
async def keep_inserted_idles_count(dut):
    """The partner is 1500 ppm slow: the buffer runs empty and the reader inserts idle blocks (they count as output idles for the run); gaps of MIN_KEEP + 6; RTL == twin, insertions happen, frames intact."""
    r = await run_case(dut, "keep_inserts", -1500, n_frames=250, gaps=(K + 6,), seed=25)
    assert r["frames_equal"] and r["rtl"]["n_ins"] > 0, r


@cocotb.test(timeout_time=50, timeout_unit="ms", skip=(MIN_KEEP == 0))
async def keep_run_restarts_after_lock_loss(dut):
    """The block lock drops mid-stream (the idle run restarts with it, the buffer is discarded) in a stream that needs deletions; RTL == twin."""
    r = await run_case(dut, "keep_lockdrop", 1000, n_frames=250, gaps=(K + 6,), seed=26, lock_drop=(3000, 3100))
    assert r["rtl"]["n_out"] > 0, r
