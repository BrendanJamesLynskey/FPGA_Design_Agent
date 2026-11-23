"""Bit-exact model of the WA x WB multiplier (arith/multiplier/spec.md), brief 139a.

``mul(wa, wb, signed, a, b)`` returns the (wa + wb)-bit product pattern of the wa-bit pattern a and the wb-bit pattern b, both read as signed
(two's complement) or both as unsigned. Written from Python's integers. ``mul_shift_add`` is a second formulation (the textbook shift-and-add on
bits, subtracting the sign row) and ``booth_digits`` gives the radix-4 Booth digits of b whose weighted sum the Booth variant implements; the
model's own tests compare them."""
from __future__ import annotations


def to_signed(x: int, w: int) -> int:
    return x - (1 << w) if x >> (w - 1) else x


def mul(wa: int, wb: int, signed: int, a: int, b: int) -> int:
    assert 0 <= a < 1 << wa and 0 <= b < 1 << wb
    x, y = (to_signed(a, wa), to_signed(b, wb)) if signed else (a, b)
    return (x * y) % (1 << (wa + wb))


def mul_shift_add(wa: int, wb: int, signed: int, a: int, b: int) -> int:
    pw = wa + wb
    ea = to_signed(a, wa) if signed else a
    acc = 0
    for i in range(wb):
        row = ea << i if (b >> i) & 1 else 0
        acc += -row if (signed and i == wb - 1) else row
    return acc % (1 << pw)


def booth_digits(wb: int, signed: int, b: int) -> list[int]:
    """Radix-4 Booth digits d_i = -2 x[2i+1] + x[2i] + x[2i-1] of b, extended by one zero bit when unsigned (so that sum d_i 4**i equals b's value)."""
    wbx = wb + (0 if signed else 1)
    npd = (wbx + 1) // 2
    sign = (b >> (wb - 1)) & 1 if signed else 0
    x = [((b >> i) & 1) if i < wb else sign for i in range(2 * npd)]
    return [-2 * x[2 * i + 1] + x[2 * i] + (x[2 * i - 1] if i else 0) for i in range(npd)]


LATENCY = {"dsp": lambda p: p["STAGES"], "lut_array": lambda p: p["REG"], "booth_r4": lambda p: p["REG"]}
