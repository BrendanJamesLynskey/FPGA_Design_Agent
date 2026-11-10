"""Golden model of t2_pdm_vu, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

DESIGN_ID = 0x50444D56
CTRL, LEVEL, PEAK, ONES, BLOCKS = range(5)


class Model:
    """Per-block history from the microphone bit stream; registers as of any block count."""

    def __init__(self, window: int) -> None:
        self.w = window
        self.hold_set, self.decay = 8, 1
        self.history: list[dict] = [{"level": 0, "peak": 0, "ones": 0, "hold": 0, "led": 0}]

    def ctrl(self) -> int:
        return self.decay << 8 | self.hold_set

    def write_ctrl(self, v: int) -> None:
        self.hold_set, self.decay = v & 0xFF, (v >> 8) & 0xF

    def clear_peak(self) -> None:
        self.history[-1] = dict(self.history[-1], peak=0, hold=0)

    def block(self, ones: int) -> None:
        prev = self.history[-1]
        level = abs(ones - self.w // 2)
        peak, hold = prev["peak"], prev["hold"]
        if level > peak:
            peak, hold = level, self.hold_set
        elif hold > 0:
            hold -= 1
        else:
            peak = max(0, peak - self.decay)
        led = sum(1 << i for i in range(16) if level >= (i + 1) * self.w // 32)
        self.history.append({"level": level, "peak": peak, "ones": ones, "hold": hold, "led": led})

    def regs(self, k: int) -> dict[int, int]:
        h = self.history[k]
        return {LEVEL: h["level"], PEAK: h["peak"], ONES: h["ones"], BLOCKS: k}
