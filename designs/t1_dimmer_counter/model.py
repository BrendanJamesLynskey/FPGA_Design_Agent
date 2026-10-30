"""Golden model of T1, written from spec.yaml alone (not from the RTL).

Transaction level: button presses, switch changes and shell register accesses
are events; the observable outputs are predicted as the spec states them
(LED on-time per PWM period, the glyph each display digit shows, register
values). The one cycle-level piece is the debounce rule, because the spec
defines it in clocks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml

SPEC = yaml.safe_load((Path(__file__).parent / "spec.yaml").read_text())
PARAMS: dict[str, int] = dict(SPEC["parameters"])
DESIGN_ID: int = SPEC["design_id"]

# Register offsets in the shell window (absolute address = 0x80 + offset)
COUNT, DUTY, CTRL, INPUTS, PRESSES = 0x00, 0x01, 0x02, 0x03, 0x04
CTRL_DUTY_SRC, CTRL_DISPLAY_EN = 1 << 0, 1 << 1

# Segments lit per hex digit, from spec.yaml's glyph list
_GLYPHS = {"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg", "6": "acdefg",
           "7": "abc", "8": "abcdefg", "9": "abcdfg", "A": "abcefg", "b": "cdefg", "C": "adef", "d": "bcdeg",
           "E": "adefg", "F": "aefg"}
GLYPHS: list[str] = [_GLYPHS[c] for c in "0123456789AbCdEF"]


def segments_to_pins(lit: str) -> int:
    """Active-low CA..CG as a 7-bit value, bit 0 = CA (segment a)."""
    return sum(0 if seg in lit else 1 << i for i, seg in enumerate("abcdefg"))


def pins_to_digit(pins: int) -> int | None:
    """The hex digit an active-low CA..CG pattern shows, or None if it is not a glyph."""
    lit = "".join(seg for i, seg in enumerate("abcdefg") if not (pins >> i) & 1)
    return GLYPHS.index(lit) if lit in GLYPHS else None


class DimmerCounterModel:
    def __init__(self, **overrides: int) -> None:
        self.p = {**PARAMS, **overrides}
        self.reset()

    def reset(self) -> None:
        self.count = 0
        self.duty = 0x40
        self.ctrl = CTRL_DISPLAY_EN
        self.presses = [0, 0, 0]          # up, down, clear
        self.sw = 0
        self.btn = [0, 0, 0]              # debounced levels: up, down, clear

    # --- events ---------------------------------------------------------------
    def press(self, up: bool = False, down: bool = False, clear: bool = False, reg_write: bool = False) -> None:
        """Debounced presses landing on one clock (priority clear > up > down)."""
        for i, hit in enumerate((up, down, clear)):
            if hit:
                self.presses[i] = (self.presses[i] + 1) & 0xFF
        if reg_write:
            return
        if clear:
            self.count = 0
        elif up:
            self.count = (self.count + 1) & 0xFFFF
        elif down:
            self.count = (self.count - 1) & 0xFFFF

    def set_switches(self, value: int) -> None:
        self.sw = value & 0xFFFF

    # --- shell window (the shell model calls these) ---------------------------
    def window_read(self, offset: int) -> int:
        if offset == COUNT:
            return self.count
        if offset == DUTY:
            return self.duty
        if offset == CTRL:
            return self.ctrl
        if offset == INPUTS:
            return self.sw | self.btn[0] << 16 | self.btn[1] << 17 | self.btn[2] << 18
        if offset == PRESSES:
            return self.presses[0] | self.presses[1] << 8 | self.presses[2] << 16
        return 0

    def window_write(self, offset: int, value: int) -> None:
        if offset == COUNT:
            self.count = value & 0xFFFF
        elif offset == DUTY:
            self.duty = value & 0xFF
        elif offset == CTRL:
            self.ctrl = value & 0x3

    # --- outputs ----------------------------------------------------------------
    @property
    def duty_eff(self) -> int:
        return self.sw & 0xFF if self.ctrl & CTRL_DUTY_SRC else self.duty

    @property
    def pwm_period_clocks(self) -> int:
        return 256 * self.p["PWM_PRESCALE"]

    def led_on_clocks(self) -> list[int]:
        """Clocks each LED is lit in one PWM period (LED[0] first)."""
        on = self.duty_eff * self.p["PWM_PRESCALE"]
        return [on if (self.count >> i) & 1 else 0 for i in range(16)]

    def display(self) -> list[int | None]:
        """Per digit 0..7: the active-low CA..CG pattern it shows, or None if it stays dark."""
        if not self.ctrl & CTRL_DISPLAY_EN:
            return [None] * 8
        nibbles = [(self.count >> (4 * k)) & 0xF for k in range(4)] + [None, None] + \
                  [self.duty_eff & 0xF, self.duty_eff >> 4]
        return [None if n is None else segments_to_pins(GLYPHS[n]) for n in nibbles]

    def digit_clocks(self) -> int:
        return 1 << self.p["REFRESH_BITS"]


def debounce(trace: Iterable[int], cycles: int, level: int = 0) -> list[int]:
    """The debounced level per clock for a synchronised input trace (spec.yaml behaviour.debounce).

    The level changes on the clock where the input has differed from it for
    ``cycles`` consecutive clocks.
    """
    out, run = [], 0
    for x in trace:
        if x != level:
            run += 1
            if run == cycles:
                level, run = x, 0
        else:
            run = 0
        out.append(level)
    return out


def presses_in(trace: Iterable[int], cycles: int) -> int:
    lv = debounce(trace, cycles)
    return sum(1 for a, b in zip([0] + lv, lv) if a == 0 and b == 1)
