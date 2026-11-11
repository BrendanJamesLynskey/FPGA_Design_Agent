"""Golden models for the library instruments (brief 30): plain Python written from the definitions, not from the RTL."""
from __future__ import annotations

import math
import zlib


def pixel_bytes(words: list[int], pix_w: int) -> bytes:
    """Pixel words as the byte stream frame_crc consumes: each word least-significant byte first."""
    n = pix_w // 8
    return b"".join(int(w).to_bytes(n, "little") for w in words)


def frame_crc32(words: list[int], pix_w: int = 24) -> int:
    """CRC-32 (IEEE 802.3, the zlib one) of a frame's pixel words."""
    return zlib.crc32(pixel_bytes(words, pix_w)) & 0xFFFFFFFF


def dds_sample(phase: int, wave: int, phase_w: int, lut_w: int, out_w: int, amp_shift: int) -> int:
    """One dds_awg output sample for the phase value held *before* the tick that produces it."""
    top = phase >> (phase_w - out_w)
    if wave == 0:
        i = phase >> (phase_w - lut_w)
        raw = int(math.sin(2.0 * math.pi * i / (1 << lut_w)) * ((1 << (out_w - 1)) - 1))
    else:
        sign = 1 << (out_w - 1)
        mask = (1 << out_w) - 1
        if wave == 1:
            tri_u = ((~top & mask) << 1 & mask) if top & sign else (top << 1) & mask
            raw_u = tri_u ^ sign
        elif wave == 2:
            raw_u = top ^ sign
        else:
            raw_u = sign if top & sign else (~sign) & mask
        raw = raw_u - (1 << out_w) if raw_u & sign else raw_u
    return raw >> amp_shift


def dds_stream(n: int, step: int, wave: int, phase_w: int = 32, lut_w: int = 8, out_w: int = 16, amp_shift: int = 0) -> list[int]:
    """The first n samples after reset (one per tick)."""
    out, ph = [], 0
    for _ in range(n):
        out.append(dds_sample(ph, wave, phase_w, lut_w, out_w, amp_shift))
        ph = (ph + step) & ((1 << phase_w) - 1)
    return out


def histogram(samples: list[int], samp_w: int, bin_w: int, cnt_w: int) -> list[int]:
    h = [0] * (1 << bin_w)
    cap = (1 << cnt_w) - 1
    for s in samples:
        b = s >> (samp_w - bin_w)
        h[b] = min(h[b] + 1, cap)
    return h


def dnl_inl(counts: list[int]) -> tuple[list[float], list[float]]:
    """DNL and INL of a code-density histogram of a full-scale uniform-ramp or noise input, in LSB of one bin.
    The two end bins are excluded (they collect the clipped codes); DNL_k = count_k / mean - 1; INL is its running sum."""
    inner = counts[1:-1]
    mean = sum(inner) / len(inner)
    dnl = [c / mean - 1.0 for c in inner]
    inl, acc = [], 0.0
    for d in dnl:
        acc += d
        inl.append(acc)
    return dnl, inl


def freq_duty(edges: int, high_clks: int, gate_clks: int, f_clk: float) -> tuple[float, float]:
    """(frequency in Hz, duty 0..1) from one gate's counts."""
    return edges * f_clk / gate_clks, high_clks / gate_clks


def dds_find_offset(got: list[int], step: int, wave: int, phase_w: int = 32, lut_w: int = 8, out_w: int = 16,
                    amp_shift: int = 0, max_n: int = 1 << 23) -> int | None:
    """The tick count n0 (since reset, 0 <= n0 < max_n) at which `got` is a contiguous run of the DDS output, or None.
    The accumulator has run since reset, so a capture starts at an unknown n0; the known answer is the whole run, not
    its position. Vectorised with numpy: filter all n0 by the first sample, then by each next one."""
    import numpy as np
    mask = (1 << phase_w) - 1
    n = np.arange(max_n, dtype=np.uint64)

    def f(nn):
        ph = (nn * np.uint64(step)) & np.uint64(mask)
        return ph
    # per-phase sample via the scalar model on the few candidates: first filter by LUT index / top bits in numpy
    ph0 = f(n)
    if wave == 0:
        idx = (ph0 >> np.uint64(phase_w - lut_w)).astype(np.int64)
        table = np.array([dds_sample(i << (phase_w - lut_w), 0, phase_w, lut_w, out_w, amp_shift) for i in range(1 << lut_w)])
        cand = np.nonzero(table[idx] == got[0])[0]
    else:
        top = (ph0 >> np.uint64(phase_w - out_w)).astype(np.int64)
        table = np.array([dds_sample(t << (phase_w - out_w), wave, phase_w, lut_w, out_w, amp_shift) for t in range(1 << out_w)])
        cand = np.nonzero(table[top] == got[0])[0]
    for i in range(1, len(got)):
        if len(cand) == 0:
            return None
        ph = f((cand + i).astype(np.uint64))
        if wave == 0:
            v = table[(ph >> np.uint64(phase_w - lut_w)).astype(np.int64)]
        else:
            v = table[(ph >> np.uint64(phase_w - out_w)).astype(np.int64)]
        cand = cand[v == got[i]]
    return int(cand[0]) if len(cand) else None
