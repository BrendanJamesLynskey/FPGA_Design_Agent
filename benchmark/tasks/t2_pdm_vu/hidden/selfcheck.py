"""On-board self-check of t2_pdm_vu with the board's PDM microphone (CLK_HALF 20 = 2.5 MHz, WINDOW 4096).

Pass rule (written before any board run):
  - CTRL reads its reset value 0x108 and reads back a written 0x204;
  - BLOCKS grows by 610 +/- 15 over 1.00 s (2.5 MHz / 4096);
  - ONES of a block is between 25 % and 75 % of WINDOW (1024..3072): a live microphone in a room, neither stuck at 0
    nor at 1 (a stuck or high-Z line reads near 0 or 4096, or exactly the same value every time);
  - 20 ONES readings are not all equal.
No human is needed; a clap near the board (optional) should raise PEAK, recorded only.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x5044_4D56          # "PDMV"
CTRL, LEVEL, PEAK, ONES, BLOCKS = (p.WINDOW_BASE + i for i in range(5))


def check(sh: Any) -> dict[str, Any]:
    c0 = sh.read(CTRL)
    sh.write(CTRL, 0x204)
    c1 = sh.read(CTRL)
    sh.write(CTRL, 0x108)
    b0, t0 = sh.read(BLOCKS), time.monotonic()
    time.sleep(1.0)
    b1, t1 = sh.read(BLOCKS), time.monotonic()
    rate = (b1 - b0) / (t1 - t0)
    ones = []
    for _ in range(20):
        ones.append(sh.read(ONES))
        time.sleep(0.01)
    res = {"ctrl": [f"0x{c0:X}", f"0x{c1:X}"], "blocks_per_s": round(rate, 1), "ones": ones,
           "level": sh.read(LEVEL), "peak": sh.read(PEAK)}
    res["pass"] = (c0 == 0x108 and c1 == 0x204 and 595 <= rate <= 625 and all(1024 <= o <= 3072 for o in ones)
                   and len(set(ones)) > 1)
    return res
