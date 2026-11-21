"""cocotb bench of the FFT variants against arith/fft/model.py (arith brief 148).

`directed` drives impulses (every position at small N), tones (every bin at small N), DC, Nyquist, a chirp and corner values, forward and inverse, as frames back to back and
separated by the shortest legal gap; `randomised` drives ARITH_N / N random frames with random direction and random legal gaps. Every output frame is compared with the model bit for bit,
the latency from in_sof to out_sof is compared with ARITH_LAT, and out_valid must be N consecutive clocks."""
from __future__ import annotations

import os
import random

import cocotb

from arith.fft import model
from arith.fft_common import frames as fr
from arith.tools import bench

VARIANT = os.environ.get("ARITH_VARIANT", "sdf")


def schedule(p, lst, rng, tight: bool):
    n = 1 << p["LOGN"]
    out = []
    for i, x in enumerate(lst):
        inv = rng.randrange(2)
        gap = 0 if (tight and rng.random() < 0.5) else (n // 4 + rng.choice((0, 0, 1, 7, n // 2))) if VARIANT == "sdf" else rng.choice((0, 0, 3, 40))
        if os.environ.get("ARITH_GAP"):                      # a fixed gap (used to find which gaps the sdf variant tolerates: see spec.md, the gap rule)
            gap = int(os.environ["ARITH_GAP"])
        out.append(fr.Frame([(a, b) for a, b in [(fr.to_unsigned(a, p["W"]), fr.to_unsigned(b, p["W"])) for a, b in x]], inv, gap))
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


async def run(dut, p, lat, frames_in, raws, label, do_reset=True):
    n = 1 << p["LOGN"]
    wo = model.out_width(p["W"], p["LOGN"], p["SCALE"])
    if do_reset:
        await reset(dut)
    outs, starts = await fr.run_frames(dut, frames_in, n, ("in_re", "in_im"), ("out_re", "out_im"), [wo, wo], lat + 2 * n + 400, True, label)
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
        if (l < lat) if os.environ.get("ARITH_BP") else (l != lat):          # with back-pressure the first word may wait: the latency is then a lower bound
            errors += 1
            dut._log.error(f"{label}: frame {i}: latency {l}, stated {lat}")
        if errors >= 3:
            break
    assert errors == 0, f"{label}: {errors} problems in {len(outs)} frames"
    return outs


@cocotb.test()
async def directed(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"])
    n = 1 << p["LOGN"]
    lst = fr.directed_frames(n, p["W"], rng, max_pos=int(os.environ.get("ARITH_POS", "16")), max_tones=int(os.environ.get("ARITH_TONES", "16")))
    await run(dut, p, lat, schedule(p, lst, rng, True), None, f"directed {p}")


@cocotb.test()
async def randomised(dut):
    p, lat = bench.env_params(), bench.env_latency()
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 77)
    n = 1 << p["LOGN"]
    k = max(4, int(os.environ["ARITH_N"]) // n)
    lst = [fr.random_frame(n, p["W"], rng) for _ in range(k)]
    await run(dut, p, lat, schedule(p, lst, rng, True), None, f"randomised {p}")


@cocotb.test()
async def roundtrip(dut):
    """Forward then inverse through the DUT: with SCALE = 1 both directions divide by N, so the result is the input divided by N (to within 3 LSB); the frames of the second pass are the
    first pass's outputs, in natural order (ORDER = 0)."""
    p, lat = bench.env_params(), bench.env_latency()
    assert p["ORDER"] == 0 and p["SCALE"] == 1
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 99)
    n = 1 << p["LOGN"]
    xs = [fr.random_frame(n, p["W"], rng) for _ in range(4)]
    f1 = [fr.Frame([(fr.to_unsigned(a, p["W"]), fr.to_unsigned(b, p["W"])) for a, b in x], 0, 0 if VARIANT == "sdf" else 3) for x in xs]
    outs = await run(dut, p, lat, f1, None, f"roundtrip forward {p}")
    f2 = [fr.Frame([(fr.to_unsigned(a, p["W"]), fr.to_unsigned(b, p["W"])) for a, b in o.words], 1, 0 if VARIANT == "sdf" else 3) for o in outs]
    back = await run(dut, p, lat, f2, None, f"roundtrip inverse {p}", do_reset=False)
    for x, o in zip(xs, back):
        worst = max(max(abs(c / n - a), abs(d / n - b)) for (c, d), (a, b) in zip(x, o.words))
        assert worst <= 3.0, f"{p}: round trip returns x / N to within 3 LSB, got {worst}"


@cocotb.test()
async def stalled(dut):
    """Random out_ready low in 40 per cent of the clocks (the sdf variant ignores out_ready and is run unstalled): frames unchanged, output held while stalled (checked by frames.run_frames)."""
    p, lat = bench.env_params(), bench.env_latency()
    if VARIANT != "burst":
        return
    os.environ["ARITH_BP"] = "0.4"
    rng = random.Random(int(os.environ["ARITH_SEED"]) * 1000 + p["LOGN"] + 13)
    n = 1 << p["LOGN"]
    k = max(4, int(os.environ["ARITH_N"]) // n)
    lst = [fr.random_frame(n, p["W"], rng) for _ in range(k)]
    await run(dut, p, lat, schedule(p, lst, rng, True), None, f"stalled {p}")
