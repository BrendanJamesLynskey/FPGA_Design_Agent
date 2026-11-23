"""Bit-exact model of the floating-point multiplier (arith/fp_mul/spec.md), brief 139e.

``mul(exp, man, subnorm, a, b)`` returns the pattern of a * b for bit patterns a and b of the (exp, man) format: one exact product, one round-to-nearest-even
(arith/fp_common/fp_ref.py holds the whole rounding and special-case convention). ``LATENCY`` is the latency in clocks of each variant for a parameter set."""
from __future__ import annotations

try:
    from arith.fp_common import fp_ref
except ImportError:                                   # the packaged harness has fp_ref.py beside this file
    import fp_ref


def mul(exp: int, man: int, subnorm: int, a: int, b: int) -> int:
    return fp_ref.fp_mul(fp_ref.Fmt(exp, man), subnorm, a, b)


LATENCY = {"dsp": lambda p: p["STAGES"], "lut": lambda p: p["STAGES"]}
