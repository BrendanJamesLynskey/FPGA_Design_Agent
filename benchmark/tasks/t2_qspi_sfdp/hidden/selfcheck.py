"""On-board self-check of t2_qspi_sfdp with the board's configuration flash (S25FL128S or S25FL127S).

Pass rule (written before any board run):
  - after a start, DONE within 0.1 s; ID = 0x012018 (Cypress/Spansion, 128 Mb: S25FL128S Table 54 / S25FL127S
    Table 49; the owner's board answered 01 20 18 in results/board_v2);
  - a second start gives the same ID and the same 16 SFDP bytes;
  - SIG_OK and the four SFDP words are recorded but are not required: the S25FL127S lists SFDP (5Ah), and whether
    the owner's part (model bytes "00", an S25FL128S by its RDID) answers 5Ah with the JESD216 header is not yet
    known from hardware (see NOTES.md). If SIG_OK is 1, SFDP1 byte 1 (major revision) must be 1.
The design can send only 9Fh and 5Ah (tests); nothing is written to the flash.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x5346_4450          # "SFDP"
CTRL, STATUS, ID = (p.WINDOW_BASE + i for i in range(3))
SFDP = [p.WINDOW_BASE + 3 + i for i in range(4)]
DONE, SIG_OK = 2, 4


def run(sh: Any) -> tuple[int, int, list[int]]:
    sh.write(CTRL, 1)
    t0 = time.monotonic()
    while True:
        st = sh.read(STATUS)
        if st & DONE:
            break
        if time.monotonic() - t0 > 0.1:
            raise TimeoutError(f"reads did not finish (status 0x{st:X})")
    return st, sh.read(ID), [sh.read(a) for a in SFDP]


def check(sh: Any) -> dict[str, Any]:
    st1, id1, w1 = run(sh)
    st2, id2, w2 = run(sh)
    sig = bool(st1 & SIG_OK)
    res = {"id": f"0x{id1:06X}", "sfdp": [f"0x{w:08X}" for w in w1], "sig_ok": sig,
           "repeat_same": (id1, w1) == (id2, w2)}
    res["pass"] = bool(id1 == 0x012018 and res["repeat_same"] and (not sig or (w1[1] >> 8) & 0xFF == 1))
    return res
