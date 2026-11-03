"""On-board self-check of t1_press_classifier (run by flow/board_check.py; nobody touches the board).

Pass rule (written before any board run):
  - SHORT_COUNT and LONG_COUNT read 0 after a write to each (write clears);
  - a write to LAST (read-only) leaves it unchanged;
  - STATUS[0] (debounced BTNC) reads 0, the button being untouched, and STATUS[31:3] read 0;
  - LAST[31:17] read 0 and the unmapped offsets 0x04 and 0x7F read 0.
"""

from __future__ import annotations

from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x5052_5343          # "PRSC"
SHORT_COUNT, LONG_COUNT, LAST, STATUS = (p.WINDOW_BASE + i for i in range(4))


def check(sh: Any) -> dict[str, Any]:
    sh.write(SHORT_COUNT, 0xFFFF)
    sh.write(LONG_COUNT, 0)
    short, long_ = sh.read(SHORT_COUNT), sh.read(LONG_COUNT)
    last0 = sh.read(LAST)
    sh.write(LAST, last0 ^ 0xFFFF)
    last1 = sh.read(LAST)
    status = sh.read(STATUS)
    unmapped = [sh.read(p.WINDOW_BASE + o) for o in (0x04, 0x7F)]
    res = {"short_count": short, "long_count": long_, "last_before": f"0x{last0:08X}", "last_after": f"0x{last1:08X}",
           "status": f"0x{status:08X}", "unmapped": unmapped}
    res["pass"] = (short == 0 and long_ == 0 and last0 == last1 and last0 >> 17 == 0
                   and status & 1 == 0 and status >> 3 == 0 and unmapped == [0, 0])
    return res
