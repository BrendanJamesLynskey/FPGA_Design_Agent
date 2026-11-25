"""Bit-exact model of the fast-convolution block (arith brief 161): overlap-save on the bit-exact FFT models of arith/fft_common/fft_ref.py. Python integers only.

The RTL equals it, bit for bit, for every input within the overflow rule of spec.yaml (the filter's absolute gain at most 2**GB, no frame of magnitude beyond full scale). One output per input sample
once a block of B = N - L + 1 new samples is complete; a partial block is never processed (flush it with zeros)."""
from __future__ import annotations

from arith.fft_common import fft_ref as f
from arith.fft_common import fastconv

filter_spectrum = fastconv.filter_spectrum      # Hq = round(FFT(h, N) * 2**FH), signed WH-bit parts


def derived(p: dict) -> dict:
    n = 1 << p["LOGN"]
    wf = p["W"] + p["LOGN"]
    return {"N": n, "B": n - p["L"] + 1, "WF": wf, "WI": wf + p["GB"]}


def block(p: dict, blk: list[tuple[int, int]], hq: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """One block of N words (L - 1 old samples then B new ones) to its N circular-convolution outputs (the inverse transform's words, WI bits, before saturation)."""
    d = derived(p)
    xf = f.fft_frame("sdf", blk, p["TW"], 0, p["RND"], 0, 1)                       # unscaled, natural order, W + LOGN bits
    prod = []
    for (a, b), (c, e) in zip(xf, hq):
        pr, pi = a * c - b * e, a * e + b * c                                       # the exact complex product of fft_cmul
        prod.append((f.to_signed(f.rshift_round(pr, p["FH"], p["RND"]), d["WI"]), f.to_signed(f.rshift_round(pi, p["FH"], p["RND"]), d["WI"])))
    return f.fft_frame("sdf", prod, p["TW"], 1, p["RND"], 1, 1)                      # scaled by 1/N, natural order


def clamp(v: int, w: int) -> int:
    return max(-(1 << (w - 1)), min((1 << (w - 1)) - 1, v))


def process(p: dict, hq: list[tuple[int, int]], x: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], int]:
    """(output samples, number of output samples in which a part saturated) for the input samples x (tuples of (re, im) integers). Output k is the filtered sample k of the stream
    (the block's circular convolution at position L - 1 + i for the block's i-th new sample); only complete blocks produce outputs."""
    d = derived(p)
    ll = p["L"]
    hist = [(0, 0)] * (ll - 1)
    out, sat = [], 0
    for s in range(0, len(x) - d["B"] + 1, d["B"]):
        blk = hist + list(x[s:s + d["B"]])
        y = block(p, blk, hq)
        for a, b in y[ll - 1:]:
            ca, cb = clamp(a, p["W"]), clamp(b, p["W"])
            sat += (ca != a) or (cb != b)
            out.append((ca, cb))
        hist = blk[len(blk) - (ll - 1):] if ll > 1 else []
    return out, sat


def latency(p: dict) -> int:
    """Clocks from the last input beat of a block to the first output beat of that block (empty pipeline, sink ready, room available): spec.yaml's expression."""
    n = 1 << p["LOGN"]
    lm = p["TWSTAGES"] + p["MULSTAGES"] + 1
    return 2 * (2 * n + p["LOGN"] + ((p["LOGN"] - 1) // 2) * lm) + p["MULSTAGES"] + p["L"] + 7


class Stream:
    """The model as a running stream: samples are fed in any chunks (complete blocks are processed as they fill), each block with the filter spectrum that is current when the block starts. The
    filter may change between blocks; the history of the last L - 1 samples carries over."""

    def __init__(self, p: dict):
        self.p, self.d = p, derived(p)
        self.hist = [(0, 0)] * (p["L"] - 1)
        self.buf: list[tuple[int, int]] = []
        self.out: list[tuple[int, int]] = []
        self.sat = 0
        self.blocks = 0

    def feed(self, hq, x):
        self.buf += list(x)
        while len(self.buf) >= self.d["B"]:
            new, self.buf = self.buf[:self.d["B"]], self.buf[self.d["B"]:]
            blk = self.hist + new
            for a, b in block(self.p, blk, hq)[self.p["L"] - 1:]:
                ca, cb = clamp(a, self.p["W"]), clamp(b, self.p["W"])
                self.sat += (ca != a) or (cb != b)
                self.out.append((ca, cb))
            self.hist = blk[len(blk) - (self.p["L"] - 1):] if self.p["L"] > 1 else []
            self.blocks += 1
