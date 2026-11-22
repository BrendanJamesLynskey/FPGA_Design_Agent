"""Frame-level cocotb driver and stimulus generators shared by the benches of the frame-based blocks (arith brief 148): the FFT variants and the reorder buffer.

A schedule is a list of frames; each frame has its words, its in_inverse flag (FFT only) and the number of idle clocks before it. The driver starts a frame only when the
block's in_ready (if it has one) is high, drives one word per clock, and records every output frame with the clock of its first word, so the bench can check the latency and
that out_valid is N consecutive clocks."""
from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass, field

from cocotb.triggers import FallingEdge, RisingEdge, Timer

from fft_ref import to_signed, to_unsigned


@dataclass
class Frame:
    words: list            # list of tuples (one tuple of ints per word: (re, im) or (d,))
    inverse: int = 0
    gap: int = 0           # idle clocks before the frame (at least)


@dataclass
class Out:
    start: int
    words: list = field(default_factory=list)


async def run_frames(dut, frames: list[Frame], n: int, in_names: tuple[str, ...], out_names: tuple[str, ...], wout: list[int], extra_clocks: int, has_inverse: bool, label: str, n_out: int | None = None):
    """Drive the schedule and collect output frames (n_out words each, n by default). Returns (outs, starts) where starts[i] is the clock of in_sof of frame i."""
    n_out = n if n_out is None else n_out
    outs: list[Out] = []
    starts: list[int] = []
    cur: Out | None = None
    fi, pos, wait, t, tail = 0, 0, frames[0].gap if frames else 0, 0, 0
    active = False
    has_ready = hasattr(dut, "in_ready")
    has_oready = hasattr(dut, "out_ready")
    bp = float(os.environ.get("ARITH_BP", "0"))              # probability that out_ready is low in a clock (blocks that honour out_ready only)
    brng = random.Random(1234)
    prev = None                                              # the output word observed after the last edge: (valid, vals, sof, clock)
    stalled = None
    while True:
        await FallingEdge(dut.clk)
        r = 1
        if has_oready:
            r = 0 if (bp and brng.random() < bp) else 1
            dut.out_ready.value = r
        if prev is not None and prev[0]:
            if r:                                           # the transfer: valid and ready at the end of this clock
                stalled = None
                vals, sof, tt = prev[1], prev[2], prev[3]
                if sof:
                    assert cur is None or len(cur.words) == n_out, f"{label}: out_sof inside a frame of the output"
                    cur = Out(start=tt)
                    outs.append(cur)
                assert cur is not None and len(cur.words) < n_out, f"{label}: out_valid outside a frame (clock {tt})"
                cur.words.append(tuple(vals))
                tail = 0
            else:
                stalled = prev                              # AXI rule: valid and data stay as they are until the transfer
        elif prev is not None:
            assert cur is None or len(cur.words) == n_out, f"{label}: out_valid dropped inside an output frame ({len(cur.words)} of {n_out} words, clock {t})"
            tail += 1
        drive_valid, drive_sof = 0, 0
        word = tuple(0 for _ in in_names)
        if not active and fi < len(frames):
            if wait > 0:
                wait -= 1
            elif (not has_ready) or int(dut.in_ready.value) == 1:
                active, pos = True, 0
                starts.append(t)
        if active:
            fr = frames[fi]
            drive_valid, drive_sof = 1, int(pos == 0)
            word = fr.words[pos]
            if has_inverse:
                dut.in_inverse.value = fr.inverse if pos == 0 else 1 - fr.inverse       # the direction counts only with in_sof: it is the opposite in every later clock of the frame
            pos += 1
            if pos == n:
                active = False
                fi += 1
                if fi < len(frames):
                    wait = frames[fi].gap
        dut.in_valid.value = drive_valid
        dut.in_sof.value = drive_sof
        for nm, v in zip(in_names, word):
            getattr(dut, nm).value = v
        if not drive_valid and has_inverse:
            dut.in_inverse.value = 0
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        ov = dut.out_valid.value
        vals = []
        if ov.is_resolvable and int(ov) == 1:
            for nm, w in zip(out_names, wout):
                sig = dut.__getattr__(nm).value
                vals.append(to_signed(int(sig), w) if sig.is_resolvable else None)
            prev = (1, vals, int(dut.out_sof.value), t)
        else:
            prev = (0, [], 0, t)
        if stalled is not None:
            assert prev[0] == 1 and prev[1] == stalled[1] and prev[2] == stalled[2], f"{label}: out_valid or the data changed while out_ready was low (clock {t})"
        t += 1
        if fi >= len(frames) and not active and tail > extra_clocks:
            break
        assert t < 400000, f"{label}: the run does not finish"
    return outs, starts


# ---- stimuli --------------------------------------------------------------------------------------------------------------
def tone(n: int, k: int, amp: float, phase: float = 0.0) -> list[tuple[float, float]]:
    return [(amp * math.cos(2 * math.pi * k * i / n + phase), amp * math.sin(2 * math.pi * k * i / n + phase)) for i in range(n)]


def quant(v: list[tuple[float, float]], w: int) -> list[tuple[int, int]]:
    lim = (1 << (w - 1)) - 1
    return [(max(-lim - 1, min(lim, round(a))), max(-lim - 1, min(lim, round(b)))) for a, b in v]


def directed_frames(n: int, w: int, rng: random.Random, max_pos: int = 24, max_tones: int = 24) -> list[list[tuple[int, int]]]:
    """Impulses (every position when n is small), tones (every bin when n is small, plus the bins at the edges), DC, Nyquist, a chirp, full-scale corners. Every frame's magnitude
    stays below 0.95 of full scale so that neither scaling mode can overflow."""
    fs = (1 << (w - 1))
    out = []
    poss = list(range(n)) if n <= max_pos else sorted({0, 1, 2, n // 2 - 1, n // 2, n // 2 + 1, n - 2, n - 1} | {rng.randrange(n) for _ in range(max_pos - 8)})
    for p in poss:
        f = [(0, 0)] * n
        f[p] = (round(0.9 * fs * rng.choice((-1, 1))), round(0.3 * fs * rng.choice((-1, 0, 1))))
        out.append(f)
    ks = list(range(n)) if n <= max_tones else sorted({0, 1, 2, 3, n // 4, n // 2 - 1, n // 2, n // 2 + 1, n - 3, n - 2, n - 1} | {rng.randrange(n) for _ in range(max_tones - 11)})
    for k in ks:
        out.append(quant(tone(n, k, 0.9 * fs, rng.uniform(0, 6.28)), w))
    out.append([(round(0.65 * fs), round(0.65 * fs))] * n)                            # DC at a corner
    out.append([(round(0.65 * fs) * (1 if i % 2 == 0 else -1), -round(0.65 * fs) * (1 if i % 2 == 0 else -1)) for i in range(n)])   # Nyquist at the other corner
    out.append(quant([(0.9 * fs * math.cos(math.pi * i * i / n), 0.9 * fs * math.sin(math.pi * i * i / n)) for i in range(n)], w))    # a chirp
    out.append([(-fs, 0)] * n)                                                          # the most negative real value everywhere
    out.append([(0, -fs) if i % 3 == 0 else (0, 0) for i in range(n)])
    return out


def random_frame(n: int, w: int, rng: random.Random) -> list[tuple[int, int]]:
    fs = (1 << (w - 1))
    kind = rng.randrange(4)
    if kind == 0:
        return [(rng.randrange(-int(0.65 * fs), int(0.65 * fs) + 1), rng.randrange(-int(0.65 * fs), int(0.65 * fs) + 1)) for _ in range(n)]
    if kind == 1:                                       # small amplitudes (rounding noise dominates)
        a = max(1, fs >> 8)
        return [(rng.randrange(-a, a + 1), rng.randrange(-a, a + 1)) for _ in range(n)]
    if kind == 2:                                       # sparse
        return [(rng.randrange(-int(0.9 * fs), int(0.9 * fs)), 0) if rng.random() < 0.1 else (0, 0) for _ in range(n)]
    return quant(tone(n, rng.randrange(n), 0.8 * fs, rng.uniform(0, 6.28)), w)
