"""On-board self-check of t1_elevator_fsm (run by flow/board_check.py; SW[3:0] must be down).

Pass rule (written before any board run):
  - wait (up to 15 s) for STATE = 0 (IDLE) and PENDING = 0; note FLOOR f0 and MOVES m0;
  - a shell call for the floor 3 - f0 (PENDING = 1 << (3 - f0)) is served: within 15 s the car is IDLE at that floor,
    PENDING = 0, and MOVES = m0 + |3 - 2 f0| (one count per floor);
  - DIR reads 0 or 1, STATE never reads 3, and offset 0x05 reads 0.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x454C_4556          # "ELEV"
FLOOR, DIR, PENDING, STATE, MOVES = (p.WINDOW_BASE + i for i in range(5))


def wait_idle(sh: Any, timeout: float = 15.0) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = sh.read(STATE)
        if st == 3:
            return False
        if st == 0 and sh.read(PENDING) == 0:
            return True
        time.sleep(0.1)
    return False


def check(sh: Any) -> dict[str, Any]:
    ok0 = wait_idle(sh)
    f0, m0 = sh.read(FLOOR), sh.read(MOVES)
    target = 3 - f0
    sh.write(PENDING, 1 << target)
    time.sleep(0.5)
    ok1 = wait_idle(sh)
    f1, m1, d = sh.read(FLOOR), sh.read(MOVES), sh.read(DIR)
    unmapped = sh.read(p.WINDOW_BASE + 0x05)
    res = {"idle_before": ok0, "floor_before": f0, "target": target, "idle_after": ok1, "floor_after": f1,
           "moves": (m1 - m0) & 0xFFFF, "moves_expected": abs(target - f0), "dir": d, "unmapped": unmapped}
    res["pass"] = (ok0 and ok1 and f1 == target and res["moves"] == abs(target - f0) and d in (0, 1)
                   and unmapped == 0)
    return res
