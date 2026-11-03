"""On-board self-check of t2_i2c_scanner (the board's sensor bus has the ADT7420 at 0x4B).

Pass rule (written before any board run):
  - a scan completes (DONE set, BUSY clear) within 1 s;
  - MAP bit 0x4B is set (MAP2 bit 11), COUNT >= 1 and equals the number of set MAP bits, LOWEST <= 0x4B and its
    MAP bit is set, no MAP bit outside 0x08-0x77 is set;
  - a second scan gives the same map.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x5343_414E          # "SCAN"
CTRL, STATUS, COUNT, LOWEST = (p.WINDOW_BASE + i for i in range(4))
MAPS = [p.WINDOW_BASE + 4 + i for i in range(4)]


def scan(sh: Any) -> tuple[int, int, int, int]:
    sh.write(CTRL, 1)
    t0 = time.monotonic()
    while True:
        st = sh.read(STATUS)
        if st & 2 and not st & 1:
            break
        if time.monotonic() - t0 > 1.0:
            raise TimeoutError(f"scan did not finish (status 0x{st:X})")
    m = sum(sh.read(a) << (32 * i) for i, a in enumerate(MAPS))
    return st, sh.read(COUNT), sh.read(LOWEST), m


def check(sh: Any) -> dict[str, Any]:
    _, count, lowest, m = scan(sh)
    _, count2, _, m2 = scan(sh)
    found = [a for a in range(128) if m >> a & 1]
    res = {"found": [f"0x{a:02X}" for a in found], "count": count, "lowest": f"0x{lowest:02X}",
           "repeat_same": m == m2 and count == count2}
    res["pass"] = bool(m >> 0x4B & 1 and count >= 1 and count == len(found) and lowest <= 0x4B
                       and m >> lowest & 1 and all(0x08 <= a <= 0x77 for a in found) and res["repeat_same"])
    return res
