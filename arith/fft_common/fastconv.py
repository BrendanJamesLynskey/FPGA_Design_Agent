"""Fast convolution on top of the FFT model (arith brief 148, phase 0: plan and model only; the RTL is the next phase).

Overlap-save and overlap-add FIR filtering of a complex or real stream x with a real filter h of L taps, using transforms of N points:
    X = FFT(block of x)  (unscaled: width W + LOGN)       Y = round(X * Hq / 2**FH)       y = IFFT(Y)  (scaled by 1/N: the plain circular convolution)
Hq is the filter's spectrum, computed once (offline, in double precision from h) and quantised to WH bits with FH fractional bits, so Hq = round(FFT(h, N) * 2**FH): the filter is
resident in a memory of N complex words. All transforms are fft_ref.fft_frame (bit-exact models of the FFT blocks) and the product is the exact complex multiply of fft_cmul rounded
by a shift of FH bits, so the model is bit-exact against the pipeline proposed in docs/fft_suite_plan.md.

    overlap_save(x, h, logn, w, tw, wh, fh, variant)  -> y of len(x) samples, equal to the linear convolution of x and h to within the stated error
    overlap_add (x, h, logn, w, tw, wh, fh, variant)  -> the same by the other method

Overlap-save: blocks of N input samples that overlap by L - 1; the first L - 1 outputs of each block are circular wrap-around and are dropped; B = N - L + 1 outputs per block.
Overlap-add: blocks of B = N - L + 1 input samples padded with zeros to N; each block's N outputs overlap the next block's by L - 1 and are added.
"""
from __future__ import annotations

import numpy as np

from arith.fft_common import fft_ref as f


def filter_spectrum(h: list[float], n: int, wh: int, fh: int) -> list[tuple[int, int]]:
    """Hq = round(FFT(h zero-padded to n) * 2**fh), each part a signed integer of at most wh bits (raises if it does not fit)."""
    hz = np.zeros(n)
    hz[:len(h)] = h
    sp = np.fft.fft(hz) * (1 << fh)
    out = [(int(round(c.real)), int(round(c.imag))) for c in sp]
    lim = 1 << (wh - 1)
    assert all(-lim <= a < lim and -lim <= b < lim for a, b in out), "the filter spectrum does not fit WH bits at this FH: lower FH or raise WH"
    return out


def _block(variant, blk, hq, logn, tw, fh, w):
    """One block through the pipeline: forward FFT unscaled, spectral product, inverse FFT scaled by 1/N. Input and output are lists of (re, im) integers."""
    xf = f.fft_frame(variant, blk, tw, 0, 1, 0, 1)
    prod = [f.cmul_round(a, b, c, d, fh + 2, 1) for (a, b), (c, d) in zip(xf, hq)]     # exact product, one rounded shift by fh (cmul_round shifts by its tw - 2 argument)
    return f.fft_frame(variant, prod, tw, 1, 1, 1, 1)


def overlap_save(x, h, logn, w, tw, wh, fh, variant="sdf"):
    n = 1 << logn
    ll = len(h)
    b = n - ll + 1
    assert b > 0
    hq = filter_spectrum(h, n, wh, fh)
    xs = [(0, 0)] * (ll - 1) + [tuple(v) if isinstance(v, (tuple, list)) else (int(v), 0) for v in x]
    out = []
    pos = 0
    while pos < len(x):
        blk = xs[pos:pos + n]
        blk = blk + [(0, 0)] * (n - len(blk))
        y = _block(variant, blk, hq, logn, tw, fh, w)
        out += y[ll - 1:ll - 1 + b]
        pos += b
    return out[:len(x)]


def overlap_add(x, h, logn, w, tw, wh, fh, variant="sdf"):
    n = 1 << logn
    ll = len(h)
    b = n - ll + 1
    assert b > 0
    hq = filter_spectrum(h, n, wh, fh)
    xs = [tuple(v) if isinstance(v, (tuple, list)) else (int(v), 0) for v in x]
    out = [(0, 0)] * (len(xs) + n)
    pos = 0
    while pos < len(xs):
        blk = xs[pos:pos + b]
        blk = blk + [(0, 0)] * (n - len(blk))
        y = _block(variant, blk, hq, logn, tw, fh, w)
        for i in range(n):
            if pos + i < len(out):
                out[pos + i] = (out[pos + i][0] + y[i][0], out[pos + i][1] + y[i][1])
        pos += b
    return out[:len(xs)]
