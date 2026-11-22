"""cocotb bench of the block-floating-point FFT variants against arith/fft_bfp/model.py (arith brief 161).

`directed` drives impulses, tones, DC, Nyquist, a chirp and corner values, forward and inverse, back to back and at the shortest legal gap; `randomised` drives ARITH_N / N random frames
with random direction and legal gaps; `levels` drives frames of very different levels (all zero, one LSB, a quiet noise, a loud tone, the most negative value) so that every exponent
range is visited; `stalled` and `stalled_hard` (burst only) stall out_ready in 40 and 92 per cent of the clocks. Every output frame is compared with the model bit for bit, including the exponent word, the latency from in_sof to out_sof is
compared with ARITH_LAT, out_valid must be N consecutive clocks, and out_exp must not change inside a frame."""
from __future__ import annotations

import os
import random

import cocotb

from arith.fft_bfp import model
from arith.fft_common import fcover
from arith.fft_common import frames as fr
from arith.tools import bench

VARIANT = os.environ.get("ARITH_VARIANT", "sdf")


def schedule(p, lst, rng, tight: bool):
    n = 1 << p["LOGN"]
    out = []
    for x in lst:
        inv = rng.randrange(2)
        gap = 0 if (tight and rng.random() < 0.5) else (n // 4 + rng.choice((0, 0, 1, 7, n // 2))) if VARIANT == "sdf" else rng.choice((0, 0, 3, 40))
        out.append(fr.Frame([(fr.to_unsigned(a, p["W"]), fr.to_unsigned(b, p["W"])) for a, b in x], inv, gap))
    return out


async def reset(dut):
    await bench.start(dut)
    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.in_sof.value = 0
    dut.in_inverse.value = 0
    dut.in_re.value = 0
    dut.in_im.value = 0
    for _ in range(3):
        await cocotb.triggers.RisingEdge(dut.clk)
    await cocotb.triggers.FallingEdge(dut.clk)
    dut.rst.value = 0


async def run(dut, p, lat, frames_in, label, do_reset=True):
    n = 1 << p["LOGN"]
    ew = model.exp_width(p["W"], p["LOGN"])
    if do_reset:
        await reset(dut)
    outs, starts = await fr.run_frames(dut, frames_in, n, ("in_re", "in_im"), ("out_re", "out_im", "out_exp"), [p["W"], p["W"], ew], lat + 2 * n + 400, True, label)
    assert len(outs) == len(frames_in), f"{label}: {len(outs)} output frames for {len(frames_in)} input frames"
    errors = 0
    for i, (o, f, s) in enumerate(zip(outs, frames_in, starts)):
        want = model.frame(VARIANT, p, [(fr.to_signed(a, p["W"]), fr.to_signed(b, p["W"])) for a, b in f.words], f.inverse)
        got = [tuple(w) for w in o.words]
        if got != [tuple(w) for w in want]:
            errors += 1
            bad = [k for k in range(n) if got[k] != tuple(want[k])]
            dut._log.error(f"{label}: frame {i} (inverse {f.inverse}): {len(bad)} words differ, first at {bad[0]}: got {got[bad[0]]}, model {want[bad[0]]}")
        l = o.start - s + 1
        if (l < lat) if os.environ.get("ARITH_BP") else (l != lat):
            errors += 1
            dut._log.error(f"{label}: frame {i}: latency {l}, stated {lat}")
        if errors >= 3:
            break
    assert errors == 0, f"{label}: {errors} problems in {len(outs)} frames"
    if hasattr(dut, "chk_errs"):                                        # the packaged harness's frame checker (chk_top.sv) around an instance
        assert int(dut.chk_errs.value) == 0, f"{label}: the frame checker counted {int(dut.chk_errs.value)} violations"
    cv = fcover.cover()
    for o, f in zip(outs, frames_in):
        e = o.words[0][2]
        cv.hit("frames")
        cv.hit("inverse_frames" if f.inverse else "forward_frames")
        cv.hit("gap_zero" if f.gap == 0 else "gap_nonzero")
        cv.hit("exp_negative" if e < 0 else "exp_zero" if e == 0 else "exp_positive")
        if e == 1 - p["W"]:
            cv.hit("exp_all_zero_frame")
        if any(w[0] in (-(1 << (p["W"] - 1)), (1 << (p["W"] - 1)) - 1) or w[1] in (-(1 << (p["W"] - 1)), (1 << (p["W"] - 1)) - 1) for w in o.words):
            cv.hit("saturated_or_extreme_word")
    cv.dump()
    return outs


@cocotb.test()
async def directed(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"])
    n = 1 << p["LOGN"]
    lst = fr.directed_frames(n, p["W"], rng, max_pos=int(os.environ.get("ARITH_POS", "12")), max_tones=int(os.environ.get("ARITH_TONES", "12")))
    await run(dut, p, lat, schedule(p, lst, rng, True), f"directed {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 77)
    n = 1 << p["LOGN"]
    k = max(4, int(os.environ["ARITH_N"]) // n)
    lst = [fr.random_frame(n, p["W"], rng) for _ in range(k)]
    await run(dut, p, lat, schedule(p, lst, rng, True), f"randomised {p}")


def level_frames(n, w, rng):
    fs = 1 << (w - 1)
    out = [[(0, 0)] * n, [(1, 0)] + [(0, 0)] * (n - 1), [(0, -1)] * n, [(-fs, -fs)] + [(0, 0)] * (n - 1), [(-fs, 0)] * n]
    for amp in (2, 7, 100, fs // 8, fs // 2, int(0.9 * fs)):          # noise at several levels
        out.append([(rng.randrange(-amp, amp + 1), rng.randrange(-amp, amp + 1)) for _ in range(n)])
    out.append([(fs - 1, 0), (fs - 1, 0), (1, 0)] + [(0, 0)] * (n - 3))   # bin 0 = 2**w - 1 (all ones): the rounding carries and the word saturates
    out.append(fr.quant(fr.tone(n, 3 % n, 0.9 * fs), w))               # a loud tone: one bin takes all the energy (the largest exponent)
    out.append(fr.quant(fr.tone(n, 3 % n, 3.0), w))                    # a quiet tone
    return out


@cocotb.test()
async def levels(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 41)
    n = 1 << p["LOGN"]
    outs = await run(dut, p, lat, schedule(p, level_frames(n, p["W"], rng), rng, True), f"levels {p}")
    es = {w[2] for o in outs for w in o.words}
    assert len(es) >= 6, f"the level frames reached only {len(es)} different exponents"


async def stalled_run(dut, prob, label):
    p, lat = bench.env_params(), bench.env_latency()
    if VARIANT != "burst":
        return
    os.environ["ARITH_BP"] = str(prob)
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 13)
    n = 1 << p["LOGN"]
    k = max(4, int(os.environ["ARITH_N"]) // n)
    lst = [fr.random_frame(n, p["W"], rng) for _ in range(k)]
    await run(dut, p, lat, schedule(p, lst, rng, True), f"{label} {p}")


@cocotb.test()
async def stalled(dut):
    """Random out_ready low in 40 per cent of the clocks (the sdf variant ignores out_ready and is run unstalled): frames unchanged, the output held while stalled (checked by frames.run_frames)."""
    await stalled_run(dut, 0.4, "stalled")


@cocotb.test()
async def stalled_hard(dut):
    """out_ready low in 92 per cent of the clocks: reading a frame takes longer than the core needs for the next, so both frame banks fill and the core must wait (wr_ready): nothing is lost or overwritten."""
    await stalled_run(dut, 0.92, "stalled_hard")
