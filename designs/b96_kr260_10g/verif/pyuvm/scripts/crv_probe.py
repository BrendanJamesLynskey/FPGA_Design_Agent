#!/usr/bin/env python3
"""Probe for the comparison (brief 123): can cocotb-coverage's `Randomized` with one constraint across two fields (the nearest thing pyuvm-on-cocotb has to SystemVerilog's randomize() with constraints)
replace the plain `random` calls of this bench's sequences? Times `randomize()` / `randomize_with()` on a frame item with the same fields and ranges as 112's
`frame_item` (len 60..1514, gap 0..40, pat 5 values, poison 2 values) and prints one line per case. Needs cocotb-coverage (python-constraint)."""
import random
import time

from cocotb_coverage.crv import Randomized


class F(Randomized):
    def __init__(self, nlen=1455):
        super().__init__()
        self.len = self.gap = self.pat = self.poison = 0
        self.add_rand("len", list(range(60, 60 + nlen)))
        self.add_rand("gap", list(range(0, 41)))
        self.add_rand("pat", list(range(5)))
        self.add_rand("poison", [0, 1])
        self.add_constraint(lambda gap, len: len + gap < 1550)            # one constraint over two fields, the argument names of a constraint lambda must be in alphabetical order


def timed(label, fn):
    t0 = time.time()
    try:
        fn()
        print(f"{label}\t{time.time() - t0:.2f} s")
    except Exception as e:          # noqa: BLE001
        print(f"{label}\tfailed after {time.time() - t0:.2f} s: {type(e).__name__}")


if __name__ == "__main__":
    random.seed(1)
    timed("randomize(), 4 fields, len domain 60..1514 (600k combinations)", lambda: F().randomize())
    timed("randomize_with(len == 100)", lambda: F().randomize_with(lambda len: len == 100))
    timed("randomize(), len domain 60..99 (40 values; 3.3k combinations)", lambda: F(40).randomize())
    f = F(40)
    t0 = time.time()
    for _ in range(20):
        f.randomize()
    print(f"20 x randomize(), len domain 60..99\t{time.time() - t0:.2f} s")
