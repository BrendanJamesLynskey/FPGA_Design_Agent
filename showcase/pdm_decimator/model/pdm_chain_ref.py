"""Bit-exact reference model of the PDM microphone audio path (brief 79, ladder project 1; integers only).

``AudioChain`` takes the microphone's bits one at a time, exactly as the fabric sees them after the sampling rule of ``spec.yaml``, and
produces 16-bit audio samples at 1/64 of the bit rate. Every stage is the integer arithmetic of the specification:

    bits -> CIC (3 integrators, /16, 3 combs, two fills dropped) -> x8 -> half-band /2 -> half-band /2 -> 9-tap FIR -> DC blocker

``process(bits)`` runs a whole stream. ``first_samples`` is what the board's capture memory holds (audio samples 0..63 of a run).
"""
from __future__ import annotations

from dataclasses import dataclass, field

FS_PDM = 3_125_000                     # M_CLK: 100 MHz / 32
FS_OUT = FS_PDM / 64                   # 48.828125 kHz
FIRST_SAMPLE_AT = 96                   # PDM samples taken when audio sample 0 appears; one more audio sample every 64
CIC_RATE, CIC_ORDER, CIC_FILLS = 16, 3, 2
SCALE = 8
HALFBAND = (-1, 0, 9, 16, 9, 0, -1)
COMP_FIR = (2, -6, 16, -48, 584, -48, 16, -6, 2)
DC_SHIFT = 7
LIMITS = (-32768, 32767)


@dataclass
class _Halfband:
    taps: list[int] = field(default_factory=lambda: [0] * 7)
    parity: int = 0

    def push(self, x: int):
        """Return the quotient-rounded sum on every second sample, else None; the 32 in the divisor is the tap sum."""
        self.taps = [x, *self.taps[:-1]]
        self.parity ^= 1
        if self.parity:
            return None
        acc = sum(c * t for c, t in zip(HALFBAND, self.taps))
        whole, part = acc // 32, acc % 32
        if part > 16 or (part == 16 and whole % 2):
            whole += 1
        return whole


class AudioChain:
    def __init__(self) -> None:
        self.integ = [0] * CIC_ORDER
        self.comb = [0] * CIC_ORDER
        self.seen = 0
        self.fills_left = CIC_FILLS
        self.hb = [_Halfband(), _Halfband()]
        self.fir = [0] * len(COMP_FIR)
        self.x_prev = 0
        self.y_prev = 0
        self.saturated = False

    def _clip(self, v: int) -> int:
        lo, hi = LIMITS
        if v < lo or v > hi:
            self.saturated = True
        return min(max(v, lo), hi)

    def push(self, bit: int) -> list[int]:
        """Feed one microphone bit; returns the audio samples that came out (zero or one)."""
        step = 1 if bit else -1
        for k in range(CIC_ORDER):                       # each integrator adds the already updated stage before it
            step = self.integ[k] = self.integ[k] + step
        self.seen += 1
        if self.seen % CIC_RATE:
            return []
        v = step
        for k in range(CIC_ORDER):
            v, self.comb[k] = v - self.comb[k], v
        if self.fills_left:
            self.fills_left -= 1
            return []
        x = self._clip(v * SCALE)
        for stage in self.hb:
            y = stage.push(x)
            if y is None:
                return []
            x = self._clip(y)
        self.fir = [x, *self.fir[:-1]]
        x = self._clip((sum(c * t for c, t in zip(COMP_FIR, self.fir)) + 256) >> 9)
        y = self._clip(x - self.x_prev + self.y_prev - (self.y_prev >> DC_SHIFT))
        self.x_prev, self.y_prev = x, y
        return [y]


def process(bits) -> tuple[list[int], bool]:
    """(audio samples, saturation seen) for a whole bit stream, starting from empty."""
    chain = AudioChain()
    out: list[int] = []
    for b in bits:
        out += chain.push(b)
    return out, chain.saturated


def first_samples(bits, n: int = 64) -> list[int]:
    return process(bits)[0][:n]


def bits_needed(n_samples: int = 64) -> int:
    """PDM samples that must be taken before audio sample n_samples - 1 exists."""
    return FIRST_SAMPLE_AT + 64 * (n_samples - 1)
