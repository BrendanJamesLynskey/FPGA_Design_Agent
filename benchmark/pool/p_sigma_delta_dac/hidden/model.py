"""Golden model of p_sigma_delta_dac, written from spec.yaml alone."""

from __future__ import annotations

VALUE = 0
DESIGN_ID = 0x53444441


class Model:
    def __init__(self) -> None:
        self.value = 0
        self.acc = 0

    def write(self, off: int, v: int) -> None:
        if off == VALUE:
            self.value = v & 0xFF

    def read(self, off: int) -> int:
        return self.value if off == VALUE else 0

    def stream(self, n: int, inv: int = 0) -> list[int]:
        """The next n enabled-clock output bits (the accumulator advances)."""
        out = []
        for _ in range(n):
            s = self.acc + self.value
            self.acc = s & 0xFF
            out.append((s >> 8) ^ inv)
        return out

    def pattern(self, inv: int = 0) -> list[int]:
        """256 bits of the stream from ACC = 0 (the accumulator state is restored)."""
        save = self.acc
        self.acc = 0
        out = self.stream(256, inv)
        self.acc = save
        return out

    def leds(self, en: bool = True) -> int:
        return self.value | int(en) << 15
