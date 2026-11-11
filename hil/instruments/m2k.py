"""ADALM2000 (M2K) through libm2k (brief 30): scope, signal generator, 16-channel logic analyser and pattern generator.
libm2k is not installed on this PC and the M2K was not connected on 2026-11-11, so this module has NOT been run against
hardware; the decode and measurement it feeds are tested on synthetic data (logic_decode.py). libm2k's licence is believed
to be LGPL-2.1 (check before installing; no root: `pip install --user libm2k` if a wheel exists, else build into ~/.local).

Levels (house rules and the M2K data sheet): analogue inputs +-25 V (high-gain +-2.5 V range), 12 bit, 100 MS/s; the
logic inputs follow the digital supply VDD_DIGITAL set with the power supply (1.8 to 3.3 V): set it to 3.3 V for the Nexys
(LVCMOS33) before connecting; never connect a signal above the set digital supply. The generator outputs +-5 V.
"""
from __future__ import annotations

from hil.instruments import logic_decode as ld


def open_m2k(uri: str | None = None):
    import libm2k                                              # type: ignore[import-not-found]
    ctx = libm2k.m2kOpen(uri) if uri else libm2k.m2kOpen()
    if ctx is None:
        raise RuntimeError("no M2K found")
    return ctx


def logic_capture(ctx, fs: float = 10e6, n: int = 100_000, channels: int = 16) -> list[list[int]]:
    """n samples of the 16 digital inputs, as one list of 0/1 per channel."""
    import libm2k                                              # type: ignore[import-not-found]
    d = ctx.getDigital()
    d.setSampleRateIn(int(fs))
    d.setDirection(0x0000)                                     # all inputs
    d.enableAllOut(False)
    raw = d.getSamples(n)
    return [[(w >> ch) & 1 for w in raw] for ch in range(channels)]


def scope_capture(ctx, fs: float = 1e6, n: int = 16384, vrange_high: bool = False) -> tuple[list[float], list[float]]:
    a = ctx.getAnalogIn()
    a.setSampleRate(int(fs))
    a.enableChannel(0, True)
    a.enableChannel(1, True)
    import libm2k                                              # type: ignore[import-not-found]
    a.setRange(0, libm2k.PLUS_MINUS_25V if vrange_high else libm2k.PLUS_MINUS_2_5V)
    a.setRange(1, libm2k.PLUS_MINUS_25V if vrange_high else libm2k.PLUS_MINUS_2_5V)
    s = a.getSamples(n)
    return list(s[0]), list(s[1])


def decode_uart(ctx, ch: int, baud: float, fs: float = 10e6, n: int = 200_000) -> list[int]:
    return ld.uart(logic_capture(ctx, fs, n)[ch], fs, baud)
