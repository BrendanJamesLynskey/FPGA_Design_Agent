"""Bit-exact model of the integer adder/subtractor (arith/adder/spec.md), brief 139a.

``addsub(w, a, b, cin, sub)`` returns ``(s, co, ovf)`` for w-bit unsigned inputs a and b (the bit patterns; the two's-complement reading is used
only for the overflow flag). It is written from Python's integers, not from the RTL's ``a + (b ^ sub) + (cin ^ sub)`` formula, so the two can
disagree if either is wrong. ``addsub_bitserial`` is a third, bit-by-bit formulation (a ripple of full adders) used by the model's own tests."""
from __future__ import annotations


def to_signed(x: int, w: int) -> int:
    return x - (1 << w) if x >> (w - 1) else x


def addsub(w: int, a: int, b: int, cin: int, sub: int) -> tuple[int, int, int]:
    assert 0 <= a < 1 << w and 0 <= b < 1 << w and cin in (0, 1) and sub in (0, 1)
    if sub:
        full = a - b - cin
        co = 1 if full >= 0 else 0                       # carry out of a + ~b + ~cin: set when there is no borrow
        true_signed = to_signed(a, w) - to_signed(b, w) - cin
    else:
        full = a + b + cin
        co = full >> w
        true_signed = to_signed(a, w) + to_signed(b, w) + cin
    s = full % (1 << w)
    ovf = int(not (-(1 << (w - 1)) <= true_signed < (1 << (w - 1))))
    return s, co, ovf


def addsub_bitserial(w: int, a: int, b: int, cin: int, sub: int) -> tuple[int, int, int]:
    """The same function as a chain of one-bit full adders on a, b XOR sub and the carry in XOR sub (the hardware identity, spelled out per bit)."""
    c = cin ^ sub
    s = 0
    carries = []
    for i in range(w):
        x, y = (a >> i) & 1, ((b >> i) & 1) ^ sub
        s |= (x ^ y ^ c) << i
        c = (x & y) | (c & (x ^ y))
        carries.append(c)
    msb_in = carries[w - 2] if w > 1 else (cin ^ sub)     # carry into the top bit
    return s, c, c ^ msb_in                                # signed overflow = carry into the top bit differs from the carry out


LATENCY = {"ripple": lambda p: 0, "carry_select": lambda p: 0, "pipelined": lambda p: p["STAGES"]}
