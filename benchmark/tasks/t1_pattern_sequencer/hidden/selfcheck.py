"""On-board self-check of t1_pattern_sequencer (run by flow/board_check.py; nobody touches the board).

Pass rule (written before any board run):
  - entries 0..2 written with patterns 0x0001/0x0003/0x0007 and durations 100/150/200 ms read back exactly;
  - LENGTH = 3, one-shot start (CTRL = 0b11): after 0.2 s STATUS reads RUN (bit 0) and INDEX 1; after a further
    0.5 s (0.7 s in all, the show lasts 0.45 s) STATUS reads 0b100 (DONE), INDEX 2, CTRL 0b10, LOOPS one more than
    before;
  - CTRL = 0 then clears STATUS to 0; offset 0x05 reads 0.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x5053_4551          # "PSEQ"
CTRL, LENGTH, INDEX, STATUS, LOOPS = (p.WINDOW_BASE + i for i in range(5))
ENTRY0 = p.WINDOW_BASE + 0x10


def check(sh: Any) -> dict[str, Any]:
    sh.write(CTRL, 0)
    prog = [(0x0001, 100), (0x0003, 150), (0x0007, 200)]
    for i, (pat, dur) in enumerate(prog):
        sh.write(ENTRY0 + i, pat | dur << 16)
    back = [sh.read(ENTRY0 + i) == (pat | dur << 16) for i, (pat, dur) in enumerate(prog)]
    sh.write(LENGTH, 3)
    l0 = sh.read(LOOPS)
    sh.write(CTRL, 0b11)
    time.sleep(0.2)
    st_mid, idx_mid = sh.read(STATUS), sh.read(INDEX)
    time.sleep(0.5)
    st_end, idx_end, ctrl_end, l1 = sh.read(STATUS), sh.read(INDEX), sh.read(CTRL), sh.read(LOOPS)
    sh.write(CTRL, 0)
    st_stop = sh.read(STATUS)
    unmapped = sh.read(p.WINDOW_BASE + 0x05)
    res = {"readback": back, "status_mid": st_mid, "index_mid": idx_mid, "status_end": st_end, "index_end": idx_end,
           "ctrl_end": ctrl_end, "loops_delta": (l1 - l0) & 0xFFFF, "status_stopped": st_stop, "unmapped": unmapped}
    res["pass"] = (all(back) and st_mid & 1 == 1 and idx_mid == 1 and st_end == 0b100 and idx_end == 2
                   and ctrl_end == 0b10 and res["loops_delta"] == 1 and st_stop == 0 and unmapped == 0)
    return res
