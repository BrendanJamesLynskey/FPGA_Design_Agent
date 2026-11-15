"""Bit-exact reference model of the stereo codec audio path (brief 78, phase 1).

The model is the single written-down meaning of "what the processing and the metering compute", in integers only, so
the RTL, the PC-side measurement scripts and the datasheet can be checked against it. It has no clock: one call is one
sample period of one channel, in the order the hardware does it:

    smooth the gain one step -> multiply and shift -> saturate -> meters (peak, clip counter, RMS window)

Conventions (every one of them is also stated in request.md and spec.yaml):

* sample: signed 24-bit two's complement, -8388608 .. 8388607;
* gain: unsigned 16 bit in Q4.12 (0x1000 is unity, 0xFFFF is just under +24 dB);
* the gain ramps linearly: each sample period moves the current gain toward its target by at most RAMP_STEP;
* the product is shifted right by 12 with the floor (arithmetic shift), then clamped to the 24-bit range;
* a clip is an output sample at either end of the 24-bit range (it counts every such sample, not every run of them);
* peak is the magnitude of the output, held for HOLD samples, then decays by max(1, peak >> DECAY_SHIFT) per sample;
* RMS is floor(sqrt(floor(sum of squares / 2**RMS_LOG2))) over each window of 2**RMS_LOG2 samples, published at the
  end of the window, and held until the next window ends.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isqrt

S_MIN, S_MAX = -(1 << 23), (1 << 23) - 1
UNITY = 0x1000
RAMP_STEP = 16
DECAY_SHIFT = 5
HOLD_RESET = 32
CLIP_MAX = 0xFFFF


def clamp24(v: int) -> int:
    return max(S_MIN, min(S_MAX, v))


def slew(cur: int, target: int, step: int = RAMP_STEP) -> int:
    """One sample period of the gain smoother: a constant step, never past the target."""
    if cur < target:
        return min(cur + step, target)
    return max(cur - step, target)


def apply_gain(x: int, gain: int) -> int:
    return clamp24((x * gain) >> 12)


@dataclass
class Meters:
    """Peak hold with decay, a clip counter and a windowed RMS for one channel."""
    rms_log2: int = 8
    hold: int = HOLD_RESET
    peak: int = 0
    hold_left: int = 0
    clips: int = 0
    rms: int = 0
    windows: int = 0
    _acc: int = 0
    _fill: int = 0

    def feed(self, y: int) -> None:
        mag = abs(y)
        if mag >= self.peak:
            self.peak, self.hold_left = mag, self.hold
        elif self.hold_left:
            self.hold_left -= 1
        else:
            self.peak -= max(1, self.peak >> DECAY_SHIFT)
        if y in (S_MIN, S_MAX):
            self.clips = min(self.clips + 1, CLIP_MAX)
        self._acc += y * y
        self._fill += 1
        if self._fill == 1 << self.rms_log2:
            self.rms = isqrt(self._acc >> self.rms_log2)
            self.windows = (self.windows + 1) & 0xFFFF
            self._acc = self._fill = 0

    def clear_peak(self) -> None:
        self.peak = self.hold_left = 0

    def clear_clips(self) -> None:
        self.clips = 0


@dataclass
class Channel:
    rms_log2: int = 8
    target: int = UNITY
    mute: int = 0
    cur: int = UNITY
    m: Meters = field(init=False)

    def __post_init__(self) -> None:
        self.m = Meters(self.rms_log2)

    def process(self, x: int) -> int:
        self.cur = slew(self.cur, 0 if self.mute else self.target)
        y = apply_gain(x, self.cur)
        self.m.feed(y)
        return y


class Path:
    """Two channels and the one-frame latency of the path: the frame received in period k leaves in period k + 1."""

    def __init__(self, rms_log2: int = 8) -> None:
        self.ch = [Channel(rms_log2), Channel(rms_log2)]
        self._pending = (0, 0)

    def frame(self, left_in: int, right_in: int) -> tuple[int, int]:
        """Feed one received frame; returns the frame that leaves in the same period (the previous frame, processed)."""
        out = self._pending
        self._pending = (self.ch[0].process(left_in), self.ch[1].process(right_in))
        return out


# ---- the I2S frame as bits (24-bit data, 32 clocks per channel, one clock after the word-select edge) -----------------

def slot_bits(sample: int) -> list[int]:
    """The 32 serial-data values of one channel slot, in BCLK order starting at the word-select edge: a zero, 24 data
    bits MSB first, seven zeros."""
    u = sample & 0xFFFFFF
    return [0] + [(u >> (23 - i)) & 1 for i in range(24)] + [0] * 7


def frame_bits(left: int, right: int) -> list[int]:
    return slot_bits(left) + slot_bits(right)


def bits_slot(bits: list[int]) -> int:
    assert len(bits) == 32 and bits[0] == 0 and not any(bits[25:])
    u = 0
    for b in bits[1:25]:
        u = u << 1 | b
    return u - (1 << 24) if u >> 23 else u
