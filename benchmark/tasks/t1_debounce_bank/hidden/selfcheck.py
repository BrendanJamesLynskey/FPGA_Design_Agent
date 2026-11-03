"""On-board self-check of t1_debounce_bank (run by flow/board_check.py; nobody touches the switches).

Pass rule (written before any board run):
  - LEVEL reads the same value twice 0.2 s apart (switches untouched), with [31:16] = 0;
  - after writes of 0xFFFF to EDGES and to COUNT0..COUNT3, EDGES reads 0 and every count reads 0;
  - RISE_EN and FALL_EN read back 0x1234 and 0x8001 when written, and are restored to 0xFFFF / 0x0000;
  - writes to LEVEL are ignored; offset 0x08 reads 0.
The host reports LEVEL so the operator can compare it with the switch positions (the visible check).
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x4442_4E4B          # "DBNK"
LEVEL, EDGES, RISE_EN, FALL_EN = (p.WINDOW_BASE + i for i in range(4))
COUNTS = [p.WINDOW_BASE + 4 + i for i in range(4)]


def check(sh: Any) -> dict[str, Any]:
    l0 = sh.read(LEVEL)
    time.sleep(0.2)
    l1 = sh.read(LEVEL)
    sh.write(EDGES, 0xFFFF)
    for a in COUNTS:
        sh.write(a, 0xFFFF_FFFF)
    edges, counts = sh.read(EDGES), [sh.read(a) for a in COUNTS]
    sh.write(RISE_EN, 0x1234)
    sh.write(FALL_EN, 0x8001)
    rb = (sh.read(RISE_EN), sh.read(FALL_EN))
    sh.write(RISE_EN, 0xFFFF)
    sh.write(FALL_EN, 0x0000)
    sh.write(LEVEL, l1 ^ 0xFFFF)
    l2 = sh.read(LEVEL)
    unmapped = sh.read(p.WINDOW_BASE + 0x08)
    res = {"level": f"0x{l1:04X}", "level_stable": l0 == l1, "edges_cleared": edges, "counts_cleared": counts,
           "enable_readback": [f"0x{v:04X}" for v in rb], "level_after_ro_write": f"0x{l2:04X}", "unmapped": unmapped}
    res["pass"] = (l0 == l1 and l1 >> 16 == 0 and edges == 0 and counts == [0, 0, 0, 0] and rb == (0x1234, 0x8001)
                   and l2 == l1 and unmapped == 0)
    return res
