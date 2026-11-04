"""On-board check of t1_bcd_updown over the shell (flow/board_check.py convention; not yet run on the board).

Pass rule (pre-registered 2026-11-03, before any board run):
  - after reset COUNT, BCD and WRAPS read 0, and STEP reads one of 1, 2, 5, 10;
  - writing COUNT = 9998 reads back 9998 and BCD 0x9998; writing 10000 leaves it at 9998;
  - writing COUNT = 407 reads BCD 0x0407; a write to WRAPS reads back 0.
No button presses are needed (the owner may press BTNU/BTND and watch the display as a manual extra).
"""

from __future__ import annotations

from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x42434455            # "BCDU"
COUNT, BCD, WRAPS, STEP = (p.WINDOW_BASE + i for i in range(4))


def check(sh: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"reset": [sh.read(COUNT), sh.read(BCD), sh.read(WRAPS)], "step": sh.read(STEP)}
    sh.write(COUNT, 9998)
    r["c9998"] = [sh.read(COUNT), sh.read(BCD)]
    sh.write(COUNT, 10000)
    r["after_10000"] = sh.read(COUNT)
    sh.write(COUNT, 407)
    r["bcd407"] = sh.read(BCD)
    sh.write(WRAPS, 1)
    r["wraps"] = sh.read(WRAPS)
    r["pass"] = (r["reset"] == [0, 0, 0] and r["step"] in (1, 2, 5, 10) and r["c9998"] == [9998, 0x9998]
                 and r["after_10000"] == 9998 and r["bcd407"] == 0x0407 and r["wraps"] == 0)
    return r
