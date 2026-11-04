"""On-board self-check of t1_gray_stepper (run by flow/board_check.py; nobody touches the board).

Pass rule (written before any board run):
  - with AUTO off, for BIN written to 0, 1, 511, 512, 1023 and 0x2A5, BIN reads back the value and GRAY reads
    BIN xor (BIN >> 1);
  - with RATE = 100 (100 ms a step at TICK_CYCLES = 1 ms) and AUTO on for about 2 s, STEPS advances by 15 to 25
    and BIN moves by the same number of steps (mod 1024) in the direction CTRL[8] reports;
  - after AUTO is turned off, STEPS stands still for 0.5 s; unmapped offset 0x05 reads 0.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x4752_4159          # "GRAY"
GRAY, BIN, CTRL, RATE, STEPS = (p.WINDOW_BASE + i for i in range(5))


def check(sh: Any) -> dict[str, Any]:
    sh.write(CTRL, 0)
    conv = []
    for v in (0, 1, 511, 512, 1023, 0x2A5):
        sh.write(BIN, v)
        b, g = sh.read(BIN), sh.read(GRAY)
        conv.append(b == v and g == v ^ (v >> 1))
    sh.write(BIN, 100)
    sh.write(RATE, 100)
    s0 = sh.read(STEPS)
    sh.write(CTRL, 1)
    time.sleep(2.0)
    sh.write(CTRL, 0)
    s1, b1, ctrl = sh.read(STEPS), sh.read(BIN), sh.read(CTRL)
    n = (s1 - s0) & 0xFFFF
    down = (ctrl >> 8) & 1
    want_bin = (100 - n) % 1024 if down else (100 + n) % 1024
    time.sleep(0.5)
    s2 = sh.read(STEPS)
    unmapped = sh.read(p.WINDOW_BASE + 0x05)
    res = {"conversion_ok": conv, "auto_steps": n, "bin_after": b1, "bin_expected": want_bin, "down": down,
           "steps_still": s2 == s1, "unmapped": unmapped}
    res["pass"] = all(conv) and 15 <= n <= 25 and b1 == want_bin and s2 == s1 and unmapped == 0
    return res
