"""On-board self-check of the PDM microphone (run by flow/board_check.py).

Pass rule (pre-registered in brief 04c, written before any board run):
  - three windows of 1,048,576 PDM bits each (0.44 s at 2.381 MHz) with M_LRSEL low;
  - in every window the fraction of ones is within [0.40, 0.60] and the fraction of bit-to-bit
    changes is at least 0.10.
Why: a PDM stream's density of ones follows the sound pressure (RM section 14.1), so a quiet room
gives about half ones, and a delta-sigma modulator near mid-scale changes state often; a dead
microphone, a stuck line or a missing clock gives all ones, all zeros or almost no changes. It
says nothing about audio quality (no decimation here), and it needs nobody to make a sound.
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x4232_4D43          # "B2MC"
CTRL, STATUS, NBITS, ONES, CHANGES, INFO = (p.WINDOW_BASE + i for i in range(6))
WINDOW_BITS = 1_048_576
WINDOWS = 3
ONES_RANGE = (0.40, 0.60)
MIN_CHANGES = 0.10


def window(sh: Any, nbits: int = WINDOW_BITS, timeout_s: float = 3.0) -> tuple[int, int]:
    sh.write(NBITS, nbits)
    sh.write(CTRL, 1)
    t0 = time.monotonic()
    while True:
        st = sh.read(STATUS)
        if not st & 1 and st & 2:
            return sh.read(ONES), sh.read(CHANGES)
        if time.monotonic() - t0 > timeout_s:
            raise TimeoutError(f"PDM window did not finish (status 0x{st:X})")


def check(sh: Any) -> dict[str, Any]:
    half = sh.read(INFO) & 0xFFFF
    wins = []
    for _ in range(WINDOWS):
        ones, changes = window(sh)
        wins.append({"ones": ones, "changes": changes, "ones_fraction": round(ones / WINDOW_BITS, 4),
                     "change_fraction": round(changes / (WINDOW_BITS - 1), 4)})
    ok = all(ONES_RANGE[0] <= w["ones_fraction"] <= ONES_RANGE[1] and w["change_fraction"] >= MIN_CHANGES
             for w in wins)
    return {"windows": wins, "window_bits": WINDOW_BITS, "m_clk_mhz": round(100.0 / (2 * half), 3),
            "ones_range": list(ONES_RANGE), "min_change_fraction": MIN_CHANGES, "pass": ok}
