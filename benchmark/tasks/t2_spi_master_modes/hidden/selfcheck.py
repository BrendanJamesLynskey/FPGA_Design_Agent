"""On-board self-check of t2_spi_master_modes (Pmod JB has nothing attached, so the check uses the loopback bit).

Pass rule (written before any board run):
  - DIV reads 50 after reset, ignores a write of 1 and reads back a write of 10;
  - in loopback, for each of the four modes, 8-bit and 16-bit, MSB and LSB first (16 frames), RXDATA equals the
    frame written to TXDATA (masked to the frame width) and STATUS shows DONE with BUSY clear after the frame;
  - with CS_HOLD set, STATUS.CS_ACTIVE is 1 after a frame and 0 after CS_HOLD is cleared.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x5350_494D          # "SPIM"
CTRL, DIV, TXDATA, RXDATA, STATUS = (p.WINDOW_BASE + i for i in range(5))
LSB, W16, CS_HOLD, LOOP = 4, 8, 16, 32
BUSY, DONE, CS_ACTIVE = 1, 2, 4


def frame(sh: Any, value: int) -> tuple[int, int]:
    sh.write(STATUS, DONE)
    sh.write(TXDATA, value)
    time.sleep(0.002)
    return sh.read(STATUS), sh.read(RXDATA)


def check(sh: Any) -> dict[str, Any]:
    res: dict[str, Any] = {}
    d0 = sh.read(DIV)
    sh.write(DIV, 1)
    d1 = sh.read(DIV)
    sh.write(DIV, 10)
    d2 = sh.read(DIV)
    res["div"] = [d0, d1, d2]
    ok = [d0, d1, d2] == [50, 50, 10]
    bad = []
    for mode in range(4):
        for opt in (0, LSB, W16, W16 | LSB):
            c = LOOP | mode | opt
            sh.write(CTRL, c)
            v = 0xA5C3 ^ (c * 0x0101)
            v &= 0xFFFF if opt & W16 else 0xFF
            st, rx = frame(sh, v)
            if rx != v or st & (BUSY | DONE) != DONE:
                bad.append({"ctrl": c, "sent": v, "got": rx, "status": st})
    res["loopback_failures"] = bad
    sh.write(CTRL, LOOP | CS_HOLD)
    st_held, _ = frame(sh, 0x3C)
    sh.write(CTRL, LOOP)
    st_rel = sh.read(STATUS)
    res["cs_status"] = [st_held, st_rel]
    ok = ok and not bad and st_held & CS_ACTIVE and not st_rel & CS_ACTIVE
    sh.write(CTRL, 0)
    res["pass"] = bool(ok)
    return res
