"""On-board self-check of t2_vga_sprite (registers only; a monitor is checked by eye).

Pass rule (written before any board run):
  - reset values: ROW0-15 = 0, X = Y = 0, SPRITE_COLOR 0xFFF, BG_COLOR 0, CTRL 1, and every RW register reads back
    a written value masked to its width;
  - FRAME advances by 60 +/- 2 in 1.00 s (59.52 Hz);
  - with BOUNCE on from X = 100, Y = 100 (moving right and down) X and Y both advance by the number of frames
    counted (+/- 1), as long as no edge is reached (about 1 s).
The bench leaves a bouncing arrow sprite running for the owner to look at (REQ-05).
"""

from __future__ import annotations

import time
from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x5350_5254          # "SPRT"
W = p.WINDOW_BASE
ROWS = [W + i for i in range(16)]
X, Y, SPRITE_COLOR, BG_COLOR, CTRL, FRAME = (W + 0x10 + i for i in range(6))
ARROW = [0x8000, 0xC000, 0xE000, 0xF000, 0xF800, 0xFC00, 0xFE00, 0xFF00, 0xFF80, 0xFC00, 0xEC00, 0xC600, 0x8600,
         0x0300, 0x0300, 0x0181]


def check(sh: Any) -> dict[str, Any]:
    reset = [sh.read(a) for a in ROWS + [X, Y, SPRITE_COLOR, BG_COLOR, CTRL]]
    reset_ok = reset == [0] * 18 + [0xFFF, 0, 1]
    for a, v in zip(ROWS, ARROW):
        sh.write(a, v | 0xFFFF0000)
    rows_ok = [sh.read(a) for a in ROWS] == ARROW
    sh.write(SPRITE_COLOR, 0xFF80)
    sh.write(BG_COLOR, 0x1123)
    col_ok = sh.read(SPRITE_COLOR) == 0xF80 and sh.read(BG_COLOR) == 0x123
    f0, t0 = sh.read(FRAME), time.monotonic()
    time.sleep(1.0)
    f1, t1 = sh.read(FRAME), time.monotonic()
    rate = (f1 - f0) / (t1 - t0)
    sh.write(X, 100)
    sh.write(Y, 100)
    sh.write(CTRL, 0x3)
    fa = sh.read(FRAME)
    time.sleep(1.0)
    fb, x, y = sh.read(FRAME), sh.read(X), sh.read(Y)
    moved = fb - fa
    bounce_ok = abs((x - 100) - moved) <= 1 and abs((y - 100) - moved) <= 1
    res = {"reset_ok": reset_ok, "rows_ok": rows_ok, "colours_ok": col_ok, "frames_per_s": round(rate, 2),
           "frames": moved, "x": x, "y": y}
    res["pass"] = bool(reset_ok and rows_ok and col_ok and 58 <= rate <= 62 and bounce_ok)
    return res
