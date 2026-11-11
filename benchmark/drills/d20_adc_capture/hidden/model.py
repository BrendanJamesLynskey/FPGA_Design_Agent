"""Golden model of d20_adc_capture, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

LAST, MIN, MAX, CLEAR = range(4)
DESIGN_ID = 0x41444338          # "ADC8"
IDLE = 0x77                     # the bench holds this sample on the pins through reset
PINS = ("JA1", "JA2", "JA3", "JA4", "JA7", "JA8", "JA9", "JA10")    # D0..D7


def bits(sample: int) -> dict[str, int]:
    """The pin values for one 8-bit sample."""
    return {p: (sample >> i) & 1 for i, p in enumerate(PINS)}


def min_max(samples: list[int]) -> tuple[int, int]:
    """MIN and MAX after a clear and these samples (each held for many clocks)."""
    return (min([255, *samples]), max([0, *samples]))
