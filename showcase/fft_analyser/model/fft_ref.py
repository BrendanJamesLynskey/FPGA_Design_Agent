"""Bit-exact reference model of the streaming power-spectrum core (brief 79, ladder project 5; integers only).

``spectrum(samples, n, window, frames_log2)`` is the batch definition (a frame at a time); ``SdfPipeline`` is the same transform as the
hardware computes it, one sample per call through single-path delay-feedback stages, and the tests prove the two give identical numbers.
All butterflies are the scaled radix-2 ones of ``spec.yaml``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

LIMITS = (-32768, 32767)


def _floor_half(x: float) -> int:
    return math.floor(x + 0.5)


def window_table(kind: int, n: int) -> list[int] | None:
    """0 and 3 rectangular (None), 1 Hann, 2 Hamming."""
    if kind == 1:
        return [min(32767, _floor_half(16384 * (1 - math.cos(2 * math.pi * i / n)))) for i in range(n)]
    if kind == 2:
        return [_floor_half(32767 * (0.54 - 0.46 * math.cos(2 * math.pi * i / n))) for i in range(n)]
    return None


def twiddle(t: int, m: int) -> tuple[int, int]:
    """W = exp(-2 pi j t / m) in Q1.15: (rounded cosine, minus rounded sine)."""
    angle = math.tau * t / m
    cos_q, sin_q = (_floor_half(32767 * f(angle)) for f in (math.cos, math.sin))
    return cos_q, -sin_q


def _limit(v: int) -> int:
    return min(max(v, LIMITS[0]), LIMITS[1])


def butterfly(a: tuple[int, int], b: tuple[int, int], w: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    """Scaled radix-2 DIF butterfly: sum and twiddled difference, each halved, rounded half up and limited to 16 bits."""
    total = [(a[i] + b[i] + 1) >> 1 for i in (0, 1)]
    diff_re, diff_im = a[0] - b[0], a[1] - b[1]
    twisted = [(diff_re * w[0] - diff_im * w[1] + 32768) >> 16, (diff_re * w[1] + diff_im * w[0] + 32768) >> 16]
    return (_limit(total[0]), _limit(total[1])), (_limit(twisted[0]), _limit(twisted[1]))


def bit_reverse(k: int, bits: int) -> int:
    return int(format(k, f"0{bits}b")[::-1], 2)


def windowed(frame: list[int], kind: int) -> list[int]:
    tab = window_table(kind, len(frame))
    return list(frame) if tab is None else [(x * w + 16384) >> 15 for x, w in zip(frame, tab)]


def fft_frame(x: list[int]) -> list[tuple[int, int]]:
    """Natural-order bins of one windowed real frame, with 1/N scaling."""
    n = len(x)
    bits = n.bit_length() - 1
    arr = [(v, 0) for v in x]
    half = n // 2
    while half >= 1:
        for base in range(0, n, 2 * half):
            for t in range(half):
                arr[base + t], arr[base + t + half] = butterfly(arr[base + t], arr[base + t + half], twiddle(t, 2 * half))
        half //= 2
    return [arr[bit_reverse(k, bits)] for k in range(n)]


def power(c: tuple[int, int]) -> int:
    return c[0] * c[0] + c[1] * c[1]


def spectrum(memory: list[int], window: int, frames_log2: int, rotate: int = 5) -> list[int]:
    """The averaged power of bins 0..N/2-1 for a run over ``memory`` (N = len(memory)): frame f is the memory rotated by ``rotate`` f."""
    n = len(memory)
    k = 1 << frames_log2
    acc = [0] * (n // 2)
    for f in range(k):
        frame = [memory[(i + rotate * f) % n] for i in range(n)]
        for j, c in enumerate(fft_frame(windowed(frame, window))[: n // 2]):
            acc[j] += power(c)
    return [(a + k // 2) >> frames_log2 for a in acc]


@dataclass
class SdfStage:
    """One single-path delay-feedback stage of half-length ``d``: out = delay-line head in the first half of a frame, sum in the second."""
    d: int
    line: list[tuple[int, int]] = field(default_factory=list)
    pos: int = 0

    def __post_init__(self) -> None:
        self.line = [(0, 0)] * self.d

    def push(self, x: tuple[int, int]) -> tuple[int, int]:
        head = self.line.pop(0)
        first_half = self.pos < self.d
        if first_half:
            emit, keep = head, x
        else:
            emit, keep = butterfly(head, x, twiddle(self.pos - self.d, 2 * self.d))
        self.line.append(keep)
        self.pos = (self.pos + 1) % (2 * self.d)
        return emit


class SdfPipeline:
    """The stages for frame size ``n`` in series; the stream of outputs lags the input by n - 1 samples (the sum of the delay lines)."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.stages = [SdfStage(n >> (s + 1)) for s in range(n.bit_length() - 1)]

    def push(self, x: int) -> tuple[int, int]:
        c = (x, 0)
        for st in self.stages:
            c = st.push(c)
        return c

    def latency(self) -> int:
        return self.n - 1


def streamed_spectrum(memory: list[int], window: int, frames_log2: int, rotate: int = 5) -> list[int]:
    """``spectrum`` computed the way the hardware streams it: samples in one per call, bit-reversed outputs stored by position."""
    n = len(memory)
    bits = n.bit_length() - 1
    k = 1 << frames_log2
    pipe = SdfPipeline(n)
    acc = [0] * n
    stream: list[int] = []
    for f in range(k):
        stream += windowed([memory[(i + rotate * f) % n] for i in range(n)], window)
    stream += [0] * (n - 1)                                       # flush with zeros
    for m_, x in enumerate(stream):
        c = pipe.push(x)
        idx = m_ - pipe.latency()
        if idx >= 0:
            acc[bit_reverse(idx % n, bits)] += power(c)
    return [(a + k // 2) >> frames_log2 for a in acc[: n // 2]]
