"""cocotb bench of the 2-parallel FFT against arith/fft_mdc2/model.py (arith brief 161).

A frame of N complex samples is driven as N/2 clocks, clock m carrying the pair (x[2m], x[2m+1]); the output frame is N/2 clocks of the pair (X[k], X[k + N/2]). `directed` drives impulses,
tones, DC, Nyquist, a chirp and corner values, forward and inverse, back to back and at the shortest legal gap (N/8 clocks); `randomised` drives ARITH_N / N random frames with random direction and
legal gaps; `gaps` finds the shortest legal gap from the model's point of view (a gap of N/8 - 1 clocks must corrupt a frame: the rule is real, not a guess). Every output frame is compared with the model
bit for bit, the latency from in_sof to out_sof with ARITH_LAT, and out_valid must be N/2 consecutive clocks."""
from __future__ import annotations

import os
import random

import cocotb

import fcover
import frames as fr
import model
import bench

IN = ("in_re0", "in_im0", "in_re1", "in_im1")
OUT = ("out_re0", "out_im0", "out_re1", "out_im1")


def to_words(p, x):
    return [tuple(fr.to_unsigned(v, p["W"]) for v in w) for w in model.pairs(x)]


def schedule(p, lst, rng, tight: bool):
    n = 1 << p["LOGN"]
    out = []
    for x in lst:
        inv = rng.randrange(2)
        gap = 0 if (tight and rng.random() < 0.5) else n // 8 + rng.choice((0, 0, 1, 7, n // 4))
        if os.environ.get("ARITH_GAP"):
            gap = int(os.environ["ARITH_GAP"])
        out.append(fr.Frame(to_words(p, x), inv, gap))
    return out


async def reset(dut):
    await bench.start(dut)
    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.in_sof.value = 0
    dut.in_inverse.value = 0
    for nm in IN:
        getattr(dut, nm).value = 0
    for _ in range(3):
        await cocotb.triggers.RisingEdge(dut.clk)
    await cocotb.triggers.FallingEdge(dut.clk)
    dut.rst.value = 0


async def run(dut, p, lat, frames_in, xs, label, do_reset=True, check=True):
    n = 1 << p["LOGN"]
    wo = model.out_width(p["W"], p["LOGN"], p["SCALE"])
    if do_reset:
        await reset(dut)
    outs, starts = await fr.run_frames(dut, frames_in, n // 2, IN, OUT, [wo] * 4, lat + n + 400, True, label)
    if not check:
        return outs, starts
    assert len(outs) == len(frames_in), f"{label}: {len(outs)} output frames for {len(frames_in)} input frames"
    errors = 0
    for i, (o, x, f, s) in enumerate(zip(outs, xs, frames_in, starts)):
        want = [tuple(w) for w in model.frame("par2", p, x, f.inverse)]
        got = [tuple(w) for w in o.words]
        if got != want:
            errors += 1
            bad = [k for k in range(n // 2) if got[k] != want[k]]
            dut._log.error(f"{label}: frame {i} (inverse {f.inverse}): {len(bad)} words differ, first at {bad[0]}: got {got[bad[0]]}, model {want[bad[0]]}")
        l = o.start - s + 1
        if l != lat:
            errors += 1
            dut._log.error(f"{label}: frame {i}: latency {l}, stated {lat}")
        if errors >= 3:
            break
    assert errors == 0, f"{label}: {errors} problems in {len(outs)} frames"
    if hasattr(dut, "chk_errs"):                                        # the packaged harness's frame checker (chk_top.sv) around an instance
        assert int(dut.chk_errs.value) == 0, f"{label}: the frame checker counted {int(dut.chk_errs.value)} violations"
    cv = fcover.cover()
    for f in frames_in:
        cv.hit("frames")
        cv.hit("inverse_frames" if f.inverse else "forward_frames")
        cv.hit("gap_zero" if f.gap == 0 else "gap_nonzero")
    cv.dump()
    return outs, starts


@cocotb.test()
async def directed(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"])
    n = 1 << p["LOGN"]
    xs = fr.directed_frames(n, p["W"], rng, max_pos=int(os.environ.get("ARITH_POS", "12")), max_tones=int(os.environ.get("ARITH_TONES", "12")))
    await run(dut, p, lat, schedule(p, xs, rng, True), xs, f"directed {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 77)
    n = 1 << p["LOGN"]
    k = max(4, int(os.environ["ARITH_N"]) // n)
    xs = [fr.random_frame(n, p["W"], rng) for _ in range(k)]
    await run(dut, p, lat, schedule(p, xs, rng, True), xs, f"randomised {p}")


@cocotb.test()
async def gaps(dut):
    """A gap of N/8 clocks between frames is legal (every frame equals the model); a gap of N/8 - 1 clocks (when that is at least 1) corrupts the previous frame, so the stated rule is the real one."""
    p, lat = bench.env_params(), bench.env_latency()
    n = 1 << p["LOGN"]
    g = n // 8
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 5)
    xs = [fr.random_frame(n, p["W"], rng) for _ in range(5)]
    ok = [fr.Frame(to_words(p, x), rng.randrange(2), g) for x in xs]
    await run(dut, p, lat, ok, xs, f"gap {g} {p}")
    if g >= 2:
        bad = [fr.Frame(to_words(p, x), 0, g - 1) for x in xs]
        outs, _ = await run(dut, p, lat, bad, xs, f"gap {g - 1} {p}", check=False)
        wrong = sum(1 for o, x in zip(outs, xs) if [tuple(w) for w in o.words] != [tuple(w) for w in model.frame("par2", p, x, 0)])
        assert wrong > 0, f"a gap of {g - 1} clocks did not corrupt any frame: the stated N/8 rule would be too strict at {p}"
