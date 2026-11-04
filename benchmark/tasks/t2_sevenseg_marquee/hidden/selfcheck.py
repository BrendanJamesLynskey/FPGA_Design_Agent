"""On-board self-check of t2_sevenseg_marquee (the display itself is checked by eye; this checks the registers).

Pass rule (written before any board run):
  - reset values CTRL 0, LENGTH 8, POS 0, DIM 7; the 16 message bytes read back what was written (raw bytes, 8 bits);
  - LENGTH ignores 0 and 17; POS ignores a value >= LENGTH;
  - with SCROLL on (SCROLL_CYCLES = 0.25 s on the board) POS advances by 4 +/- 1 in 1.0 s, modulo LENGTH, and by
    the same amount backwards with DIR = 1.
The message "HELLO-12" in raw segments is left scrolling at DIM 7 for the owner to look at (REQ-05).
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x4D41_5251          # "MARQ"
CTRL, LENGTH, POS, DIM = (p.WINDOW_BASE + i for i in range(4))
MSG = [p.WINDOW_BASE + 0x10 + i for i in range(16)]
HELLO = [0x76, 0x79, 0x38, 0x38, 0x3F, 0x40, 0x06, 0x5B, 0x00, 0x49, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00]


def check(sh: Any) -> dict[str, Any]:
    reset = [sh.read(a) for a in (CTRL, LENGTH, POS, DIM)]
    for a, v in zip(MSG, HELLO):
        sh.write(a, v)
    back = [sh.read(a) for a in MSG]
    sh.write(LENGTH, 0)
    sh.write(LENGTH, 17)
    l_ign = sh.read(LENGTH)
    sh.write(LENGTH, 12)
    sh.write(POS, 12)
    p_ign = sh.read(POS)
    sh.write(CTRL, 1)
    p0 = sh.read(POS)
    time.sleep(1.0)
    fwd = (sh.read(POS) - p0) % 12
    sh.write(CTRL, 3)
    p1 = sh.read(POS)
    time.sleep(1.0)
    back_steps = (p1 - sh.read(POS)) % 12
    sh.write(CTRL, 1)
    res = {"reset": reset, "readback_ok": back == HELLO, "length_after_bad": l_ign, "pos_after_bad": p_ign,
           "steps_forward_1s": fwd, "steps_back_1s": back_steps}
    res["pass"] = (reset == [0, 8, 0, 7] and back == HELLO and l_ign == 8 and p_ign == 0
                   and 3 <= fwd <= 5 and 3 <= back_steps <= 5)
    return res
