"""Bit-exact model of the fused multiply-add and of the unfused cascade (arith/fp_fma/spec.md), brief 139e.

``fma(exp, man, subnorm, a, b, c)`` returns the pattern of a * b + c with ONE rounding (the exact value rounded to nearest even). ``cascade(...)`` is a multiplier followed by
an adder, each rounding, so the product is rounded to the format before the addition: it differs from ``fma`` in the last place for some inputs (spec.md says by how much).
arith/fp_common/fp_ref.py holds the whole rounding and special-case convention. ``LATENCY`` is the latency in clocks of each variant for a parameter set."""
from __future__ import annotations

try:
    from arith.fp_common import fp_ref
except ImportError:                                   # the packaged harness has fp_ref.py beside this file
    import fp_ref


def fma(exp: int, man: int, subnorm: int, a: int, b: int, c: int) -> int:
    return fp_ref.fp_fma(fp_ref.Fmt(exp, man), subnorm, a, b, c)


def cascade(exp: int, man: int, subnorm: int, a: int, b: int, c: int) -> int:
    return fp_ref.fma_cascade(fp_ref.Fmt(exp, man), subnorm, a, b, c)


LATENCY = {"fused": lambda p: p["STAGES"], "cascade": lambda p: p["STAGES_M"] + p["STAGES_A"]}
