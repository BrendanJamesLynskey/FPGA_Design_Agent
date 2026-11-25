"""cocotb bench of the AXI4-Stream 2-parallel FFT with block floating point (arith brief 168): frames of N complex samples in as N/2 beats (tdata = {im1, re1, im0, re0}, tlast on the last beat, tuser[0] = the
direction on the first beat), frames out as N/2 beats (tdata = {im1, re1, im0, re0} = X[k] and X[k + N/2], tuser = the frame exponent, tlast on the last), compared bit for bit with arith/fft_mdc2_axis/model.py.
The wrapper's protocol checkers (arith/fft_common/axis_checker.sv) must count zero errors on both streams.

Every run also checks, for every pair of consecutive frames: the idle clocks between the last transferred beat of one and the first of the next are 0 or at least N/8 (the core's streaming rule: the wrapper, not the
source, has to guarantee it), and the exponent on tuser is the model's on EVERY beat of a frame (the contract is the first beat; the other beats hold it).
`directed`: the bench's directed frames, forward and inverse, the source never pausing (tvalid held, waiting on tready), the sink always ready; the first-beat latency must equal the stated latency exactly and the
frame period under the rule is measured. `randomised`: random frames, random idle clocks before each frame (including 1 to N/8 - 1, which the wrapper must turn into a legal gap), random tready.
`backpressure`: the sink holds tready low for long stretches (a whole frame period and more); nothing may be lost, the output must be held stable, and the input must be stalled by the credit (the bench counts
the clocks tready was low at a frame start). `gaps`: source idle of 0, 1 .. N/8 + 1 clocks and the measured idle between frames. `stress`: many short frames, every kind of idle, a sink that alternates between ready and stalled for random stretches. `drain`: frames so far apart that the store is empty before each one, 3 * NB + 2 of them. `checker`: deliberate violations that the checkers must count."""
from __future__ import annotations

import os
import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge

from arith.fft_common import fcover
from arith.fft_common import frames as fr
from arith.fft_mdc2_axis import model
from arith.tools import bench


def proto_errors(dut):
    """The protocol checkers' error counts: the repository's RTL has them inside (simulation only)."""
    return [(nm, int(getattr(dut, nm).value)) for nm in ("chk_s_errs", "chk_m_errs") if hasattr(dut, nm)]


async def reset(dut):
    await bench.start(dut)
    dut.aresetn.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tuser.value = 0
    dut.s_axis_tlast.value = 0
    dut.m_axis_tready.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.aresetn.value = 1


async def run(dut, p, lat, xs, invs, idles, ready, label, check_lat=True, max_clocks=None):
    """Drive frames xs (direction invs[i], idles[i] clocks of tvalid low before frame i) and take the outputs with the sink's `ready(t)` (0 or 1 per clock). Returns the measurements."""
    n, w = 1 << p["LOGN"], p["W"]
    h = n // 2
    ew = model.exp_width(w, p["LOGN"])
    max_clocks = max_clocks or len(xs) * (lat + 4 * n + max(idles) + 8) + 4000      # generous: a stalled sink in `backpressure` adds 3 frame times
    beats = [model.pack_beats(x, w) for x in xs]
    fi, bi, wait, t = 0, 0, idles[0], 0
    first_t, last_t, outs, cur, out_first, stall_clocks = [], [], [], None, [], 0
    prev = None                                                        # the beat offered in the last clock and not taken: it must still be offered unchanged
    tail = 0
    while True:
        await FallingEdge(dut.clk)
        r = ready(t)
        dut.m_axis_tready.value = r
        mv = int(dut.m_axis_tvalid.value)
        if mv:
            d, last, u = int(dut.m_axis_tdata.value), int(dut.m_axis_tlast.value), int(dut.m_axis_tuser.value)
            if prev is not None:
                assert (d, last, u) == prev, f"{label}: the offered beat changed while tready was low (clock {t})"
            if r:
                prev = None
                if cur is None:
                    cur = ([], [])
                    out_first.append(t)
                cur[0].append(model.unpack_out(d, w))
                cur[1].append(u)
                assert (last == 1) == (len(cur[0]) == h), f"{label}: tlast on beat {len(cur[0])} of {h} (clock {t})"
                if last:
                    outs.append(cur)
                    cur = None
            else:
                prev = (d, last, u)
            tail = 0
        else:
            assert prev is None, f"{label}: tvalid dropped while tready was low (clock {t})"
            tail += 1
        tv, data, last_b, us = 0, 0, 0, 0
        if fi < len(xs):
            can = int(dut.s_axis_tready.value) == 1
            if bi == 0 and wait > 0:
                wait -= 1
            else:
                tv = 1
                data, last_b = beats[fi][bi], int(bi == h - 1)
                us = invs[fi] if bi == 0 else 1 - invs[fi]
            if tv and bi == 0 and not can:
                stall_clocks += 1
            dut.s_axis_tvalid.value = tv
            dut.s_axis_tdata.value = data
            dut.s_axis_tuser.value = us
            dut.s_axis_tlast.value = last_b
            if tv and can:
                if bi == 0:
                    first_t.append(t)
                if bi == h - 1:
                    last_t.append(t)
                bi += 1
                if bi == h:
                    bi, fi = 0, fi + 1
                    if fi < len(xs):
                        wait = idles[fi]
        else:
            dut.s_axis_tvalid.value = 0
        t += 1
        if fi >= len(xs) and len(outs) == len(xs) and tail > 8:
            break
        assert t < max_clocks, f"{label}: the run does not finish ({len(outs)} of {len(xs)} output frames after {t} clocks)"
    for i, (o, x) in enumerate(zip(outs, xs)):
        beats_m, s = model.frame(p, x, invs[i])
        assert o[0] == [tuple(b) for b in beats_m], f"{label}: frame {i} differs from the model"
        assert all(u == s & ((1 << ew) - 1) for u in o[1]), f"{label}: frame {i}: tuser {sorted(set(o[1]))} on the beats, the model's exponent is {s}"
        if check_lat:
            assert out_first[i] - first_t[i] == lat, f"{label}: frame {i}: first-beat latency {out_first[i] - first_t[i]}, stated {lat}"
    g = model.gap(p["LOGN"])
    idle = [first_t[i] - last_t[i - 1] - 1 for i in range(1, len(xs))]
    for i, c in enumerate(idle, 1):
        assert c == 0 or c >= g, f"{label}: frame {i} starts {c} idle clocks after the previous one: the core needs 0 or at least {g}"
    errs = proto_errors(dut)
    assert all(v == 0 for _, v in errs), f"{label}: protocol checker errors: {errs}"
    cv = fcover.cover()
    for i in range(len(xs)):
        cv.hit("frames")
        cv.hit("inverse_frames" if invs[i] else "forward_frames")
    for c in idle:
        cv.hit("gap_zero" if c == 0 else "gap_n8" if c == g else "gap_other")
    cv.dump()
    return {"first_t": first_t, "last_t": last_t, "idle": idle, "stall_clocks": stall_clocks, "out_first": out_first, "clocks": t}


def sat_frames(n: int, w: int) -> list[list[tuple[int, int]]]:
    """Frames whose largest output part is 2**m - 1 (DC bin: the sum of the samples), so that the block exponent shifts it by s = m - (W - 1) and the rounding carries it to 2**(W-1): the saturation branch of the
    normalisation. The samples are the largest positive value until the sum is reached; real, imaginary and negative-real versions."""
    out = []
    hi = (1 << (w - 1)) - 1
    for m in (w + (n.bit_length() - 1) - 2, w + (n.bit_length() - 1) - 3):
        if m <= w:
            continue
        target = (1 << m) - 1
        assert target <= n * hi
        col = []
        left = target
        for _ in range(n):
            v = min(hi, left)
            col.append(v)
            left -= v
        out.append([(v, 0) for v in col])
        out.append([(0, v) for v in col])
        out.append([(-v, 0) for v in col])
    return out


def schedule(p, xs, rng, idle_of):
    return [rng.randrange(2) for _ in xs], [idle_of(rng, i) for i in range(len(xs))]


@cocotb.test()
async def directed(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"])
    n = 1 << p["LOGN"]
    xs = fr.directed_frames(n, p["W"], rng, max_pos=int(os.environ.get("ARITH_POS", "12")), max_tones=int(os.environ.get("ARITH_TONES", "12"))) + sat_frames(n, p["W"])
    invs, idles = schedule(p, xs, rng, lambda r, i: 0)
    await reset(dut)
    m = await run(dut, p, lat, xs, invs, idles, lambda t: 1, f"directed {p}")
    # throughput, measured: a frame is in the block from its first input beat until its last output beat is taken, lat + N/2 clocks with a ready sink; NB banks hold NB frames. When NB * N/2 >= lat + N/2 a source that
    # never pauses and a ready sink give one frame every N/2 clocks with no idle clock between frames; otherwise the credit holds the source and the missed window costs more (the rule was found by sweeping
    # LOGN 4 to 7, MULSTAGES 0 and 3, NB 2 to 4, and is checked here at every point); the period is never below N/2
    period = [m["first_t"][i] - m["first_t"][i - 1] for i in range(1, len(xs))]
    assert min(period) >= n // 2, f"frame period below N/2: {min(period)}"
    if p["NB"] * (n // 2) >= lat + n // 2:
        assert set(period) == {n // 2}, f"NB * N/2 = {p['NB'] * n // 2} >= latency + N/2 = {lat + n // 2}: one frame per N/2 = {n // 2} clocks expected, periods {sorted(set(period))}"
    else:
        assert max(period) > n // 2, f"NB * N/2 < latency + N/2 but the source was never held: periods {sorted(set(period))}"
    dut._log.info(f"directed {p}: frame periods {sorted(set(period))} clocks (N/2 = {n // 2}), idle clocks between frames {sorted(set(m['idle']))}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 5)
    n = 1 << p["LOGN"]
    k = max(3 * p["NB"] + 3, int(os.environ["ARITH_N"]) // n)           # enough frames for every bank to be reused several times, also after the store has drained (idles of 2N below)
    xs = [fr.random_frame(n, p["W"], rng) for _ in range(k)]
    invs, idles = schedule(p, xs, rng, lambda r, i: r.choice((0, 0, 1, 2, n // 8 - 1, n // 8, n // 8 + 1, n // 2, 2 * n)))
    await reset(dut)
    await run(dut, p, lat, xs, invs, idles, lambda t: 1, f"randomised {p}")
    # the same frames with a random sink: the data must be the same, the latency is not checked (the sink delays the output)
    prng = random.Random(9)
    pl = [0.2, 0.5, 0.8]
    await reset(dut)
    await run(dut, p, lat, xs, invs, idles, lambda t: int(prng.random() >= pl[(t // 97) % 3]), f"randomised random tready {p}", check_lat=False)


@cocotb.test()
async def backpressure(dut):
    """A sink that stalls for a frame period and more: nothing is lost, the offered beat is held, and the source waits at the credit when NB frames are in the block."""
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 11)
    n = 1 << p["LOGN"]
    xs = [fr.random_frame(n, p["W"], rng) for _ in range(8)]
    invs, idles = schedule(p, xs, rng, lambda r, i: 0)
    await reset(dut)
    stall_start = lat + 1                                              # the first output beat is offered at clock lat; hold the sink from the one after for 3 frames' worth of output
    m = await run(dut, p, lat, xs, invs, idles, lambda t: 0 if stall_start <= t < stall_start + 3 * n else 1, f"backpressure {p}", check_lat=False)
    assert m["stall_clocks"] > 0, "the source was never held off by the credit although the sink stalled for three frame times"
    cv = fcover.cover()
    cv.hit("credit_stall")
    cv.dump()
    # a sink that is ready one clock in four
    await reset(dut)
    await run(dut, p, lat, xs, invs, idles, lambda t: int(t % 4 == 0), f"backpressure quarter {p}", check_lat=False)


@cocotb.test()
async def gaps(dut):
    """Whatever the source's idle clocks (0, 1 .. N/8 + 1) the idle between frames the core sees is 0 or at least N/8; the wrapper turns an idle of 1 .. N/8 - 1 into a gap of N/8 (so those frames are correct)."""
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 3)
    n = 1 << p["LOGN"]
    h = n // 2
    g = n // 8
    xs = [fr.random_frame(n, p["W"], rng) for _ in range(2 * (g + 2))]
    cyc = list(range(g + 2))
    idles = [0] + [cyc[i % len(cyc)] for i in range(len(xs) - 1)]
    invs = [rng.randrange(2) for _ in xs]
    await reset(dut)
    m = await run(dut, p, lat, xs, invs, idles, lambda t: 1, f"gaps {p}", check_lat=False)
    assert 0 in m["idle"] and any(c >= g for c in m["idle"]), f"idle clocks seen {sorted(set(m['idle']))}"
    if p["NB"] * h >= lat + h:                                         # the credit never binds here: a source that idles k >= 1 clocks starts max(k, N/8) idle clocks after the previous frame, k = 0 starts at once
        want = [0 if k == 0 else max(k, g) for k in idles[1:]]
        assert m["idle"] == want, f"idle clocks between frames {m['idle']}, expected {want} for the source's idles {idles[1:]}"


@cocotb.test()
async def drain(dut):
    """Frames so far apart that the frame store is empty again before the next one arrives, for 3 * NB + 2 frames (every bank is used and reused several times by a frame that finds all banks empty): a bank flag that is
    not cleared when its frame has been read shows as a phantom frame read from a bank that has not been written yet."""
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 21)
    n = 1 << p["LOGN"]
    xs = [fr.random_frame(n, p["W"], rng) for _ in range(3 * p["NB"] + 2)]
    invs, idles = schedule(p, xs, rng, lambda r, i: 2 * n + r.randrange(n))
    await reset(dut)
    await run(dut, p, lat, xs, invs, idles, lambda t: 1, f"drain {p}")


@cocotb.test()
async def stress(dut):
    """Many short frames with every kind of idle between them and a sink that alternates between ready and stalled for random stretches (up to 4 frame times), so that the number of finished frames waiting in the store
    varies from 0 to NB from one read to the next: the bank flags, pointers and credit are exercised in every combination."""
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 31)
    n = 1 << p["LOGN"]
    h = n // 2
    k = max(20 * p["NB"], int(os.environ["ARITH_N"]) // n)
    xs = [fr.random_frame(n, p["W"], rng) for _ in range(k)]
    invs, idles = schedule(p, xs, rng, lambda r, i: r.choice((0, 0, 0, 1, n // 8, 5, h, 2 * h, 3 * h)))
    srng = random.Random(int(os.environ["ARITH_SEED"]) * 7 + p["LOGN"])
    segs, t_end, up = [], 0, True
    while t_end < 2000000:
        ln = srng.randrange(1, 4 * h + 2) if up else srng.randrange(1, 4 * h + 2)
        segs.append((t_end, t_end + ln, up))
        t_end += ln
        up = not up
    starts = [a for a, _, _ in segs]
    ups = [u for _, _, u in segs]
    import bisect

    def ready(t):
        return int(ups[bisect.bisect_right(starts, t) - 1])
    await reset(dut)
    await run(dut, p, lat, xs, invs, idles, ready, f"stress {p}", check_lat=False, max_clocks=len(xs) * (lat + 8 * n + 3 * n) + 20000)


@cocotb.test()
async def checker(dut):
    """The protocol checkers can fail: a source that pauses inside a frame, and a source that withdraws tvalid while tready is low."""
    p = bench.env_params()
    n, w = 1 << p["LOGN"], p["W"]
    h = n // 2
    rng = random.Random(77)
    await reset(dut)
    x = fr.random_frame(n, w, rng)
    bts = model.pack_beats(x, w)
    for i, d in enumerate(bts):
        await FallingEdge(dut.clk)
        dut.s_axis_tvalid.value, dut.s_axis_tdata.value, dut.s_axis_tlast.value = 1, d, int(i == h - 1)
        if i == 1:
            await FallingEdge(dut.clk)
            dut.s_axis_tvalid.value = 0
            await FallingEdge(dut.clk)
            dut.s_axis_tvalid.value = 1
    await FallingEdge(dut.clk)
    dut.s_axis_tvalid.value = 0
    if not hasattr(dut, "chk_s_errs"):
        return                                                         # no protocol checker around this instance: nothing to show
    assert int(dut.chk_s_errs.value) > 0, "the checker did not flag a pause inside a frame"
    # withdrawal: after a tlast beat, offer a beat for one clock in the gap (tready low from the second clock after the tlast beat when N/8 > 1)
    await reset(dut)
    for i, d in enumerate(bts):
        await FallingEdge(dut.clk)
        dut.s_axis_tvalid.value, dut.s_axis_tdata.value, dut.s_axis_tlast.value = 1, d, int(i == h - 1)
    await FallingEdge(dut.clk)
    dut.s_axis_tvalid.value = 0                                        # one idle clock: the window is missed and tready falls for N/8 - 1 clocks
    await FallingEdge(dut.clk)
    dut.s_axis_tvalid.value, dut.s_axis_tdata.value, dut.s_axis_tlast.value = 1, bts[0], 0
    await FallingEdge(dut.clk)
    dut.s_axis_tvalid.value = 0                                        # withdrawn while the wrapper's tready is low
    for _ in range(4):
        await FallingEdge(dut.clk)
    if n // 8 > 2:
        assert int(dut.chk_s_errs.value) > 0, "the checker did not flag a withdrawn tvalid"
