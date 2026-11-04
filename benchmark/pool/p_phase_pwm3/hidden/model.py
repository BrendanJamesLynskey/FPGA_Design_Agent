"""Golden model of p_phase_pwm3, written from spec.yaml alone."""

from __future__ import annotations

DUTY, ON, STAGGER, PERIOD = 0, 1, 2, 3
DESIGN_ID = 0x50483350


class Model:
    def __init__(self, period: int) -> None:
        assert period % 3 == 0
        self.period = period
        self.duty = 0
        self.stagger = False

    def latch(self, sw: int) -> None:
        self.duty = sw & 0xFF
        self.stagger = bool(sw & 0x100)

    @property
    def on(self) -> int:
        return self.duty * self.period // 256

    def waveform(self) -> list[int]:
        """LED[2:0] for one period, indexed by T (channel 0 starts at T = 0)."""
        out = []
        for t in range(self.period):
            v = 0
            for k in range(3):
                off = k * self.period // 3 if self.stagger else 0
                if (t - off) % self.period < self.on:
                    v |= 1 << k
            out.append(v)
        return out

    def read(self, off: int) -> int:
        return {DUTY: self.duty, ON: self.on, STAGGER: int(self.stagger), PERIOD: self.period}.get(off, 0)
