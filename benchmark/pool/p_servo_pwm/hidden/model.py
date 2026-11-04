"""Golden model of p_servo_pwm, written from spec.yaml alone."""

from __future__ import annotations

POS, WIDTH, FRAME = 0, 1, 2
DESIGN_ID = 0x5352564F


class Model:
    def __init__(self, frame: int, min_c: int, step: int) -> None:
        self.frame, self.min_c, self.step = frame, min_c, step
        self.pos = 0
        self.off = False

    def new_frame(self, sw: int) -> None:
        """The switches as sampled at a frame start."""
        self.pos = sw & 0xFF
        self.off = bool(sw & 0x8000)

    def width(self) -> int:
        return 0 if self.off else self.min_c + self.pos * self.step

    def pulse_train(self, n_frames: int) -> list[int]:
        """The JA1 samples for n frames at this frame's settings."""
        w = self.width()
        return ([1] * w + [0] * (self.frame - w)) * n_frames

    def read(self, off: int) -> int:
        return {POS: self.pos, WIDTH: self.width(), FRAME: self.frame}.get(off, 0)

    def leds(self) -> int:
        return self.pos | int(self.off) << 15
