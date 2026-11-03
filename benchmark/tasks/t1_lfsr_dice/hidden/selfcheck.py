"""On-board self-check of t1_lfsr_dice (run by flow/board_check.py; nobody touches the board).

Pass rule (written before any board run):
  - TAPS reads 0xB400 (after a write of 0xB400); SEED = 0x1234 makes STATE read 0x1234;
  - a burst of 1000 steps (STEP = 1000) leaves STATE equal to the host-side Galois model's 1000th state from 0x1234
    and STEP reads 0;
  - a SEED write of 0 makes STATE read 0x0001; ROLL reads 0..6 and HISTORY's nibbles each 0..6; 0x07 reads 0.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x4449_4345          # "DICE"
STATE, SEED, TAPS, ROLL, HISTORY, STEP, ROLLS = (p.WINDOW_BASE + i for i in range(7))


def lstep(s: int, taps: int) -> int:
    b = s & 1
    s >>= 1
    if b:
        s ^= taps
    return s or 1


def check(sh: Any) -> dict[str, Any]:
    sh.write(TAPS, 0xB400)
    sh.write(SEED, 0x1234)
    s0 = sh.read(STATE)
    sh.write(STEP, 1000)
    time.sleep(0.01)
    s1, left = sh.read(STATE), sh.read(STEP)
    want = 0x1234
    for _ in range(1000):
        want = lstep(want, 0xB400)
    sh.write(SEED, 0)
    s_zero = sh.read(STATE)
    roll, hist = sh.read(ROLL), sh.read(HISTORY)
    unmapped = sh.read(p.WINDOW_BASE + 0x07)
    res = {"taps": f"0x{sh.read(TAPS):04X}", "seeded": f"0x{s0:04X}", "after_1000": f"0x{s1:04X}",
           "expected_1000": f"0x{want:04X}", "steps_left": left, "zero_seed_state": s_zero, "roll": roll,
           "history": f"0x{hist:04X}", "unmapped": unmapped}
    res["pass"] = (res["taps"] == "0xB400" and s0 == 0x1234 and s1 == want and left == 0 and s_zero == 1
                   and roll <= 6 and all((hist >> (4 * i)) & 0xF <= 6 for i in range(4)) and unmapped == 0)
    return res
