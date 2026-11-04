"""On-board self-check of t2_vga_sprite (registers only; a monitor is checked by eye).

Pass rule (written before any board run):
  - reset values: ROW0-15 = 0, X = Y = 0, SPRITE_COLOR 0xFFF, BG_COLOR 0, CTRL 1, and every RW register reads back
    a written value masked to its width;
  - FRAME advances by 60 +/- 2 in 1.00 s (59.52 Hz);
  - with BOUNCE on from X = 100, Y = 100 (moving right and down) X and Y both advance by the number of frames
    that passed between the CTRL write and the X / Y reads, as long as no edge is reached (about 1 s). That
    number is bracketed (v1.1, below): FRAME is read before and after the CTRL write and before and after the
    X / Y reads, and X - 100 and Y - 100 must each lie in [FRAME_before_reads - FRAME_after_CTRL_write - 1,
    FRAME_after_reads - FRAME_before_CTRL_write + 1].

Rule changed in v1.1, after the first board run (2026-11-03, reference build 791b101): the v1 rule compared X - 100 and
Y - 100 with one FRAME difference (read after the CTRL write, and again before the X / Y reads), to +/- 1. The board
showed that difference as 60 while X and Y had both moved 62 (measured FRAME rate 59.53 Hz). The two UART register
reads of X and Y, after the FRAME read, take real time, and frames pass during them. The design behaved correctly
(X and Y moved together, one pixel per frame); the fault was the measurement window, not the behaviour. The
bracket makes the window explicit and does not loosen what is checked: X and Y must still track the frame counter
to within one frame. Board record: results/board_v2/t2_vga_sprite.json (v1 run).
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
    fa_lo = sh.read(FRAME)                           # before the CTRL write: motion cannot have started
    sh.write(CTRL, 0x3)
    fa_hi = sh.read(FRAME)                           # after it: frames counted so far may include motion
    time.sleep(1.0)
    fb_lo = sh.read(FRAME)                           # before the X / Y reads
    x, y = sh.read(X), sh.read(Y)
    fb_hi = sh.read(FRAME)                           # after them
    lo, hi = fb_lo - fa_hi - 1, fb_hi - fa_lo + 1
    moved = fb_lo - fa_hi
    bounce_ok = lo <= x - 100 <= hi and lo <= y - 100 <= hi
    res = {"reset_ok": reset_ok, "rows_ok": rows_ok, "colours_ok": col_ok, "frames_per_s": round(rate, 2),
           "frames": moved, "frames_lo": lo, "frames_hi": hi, "x": x, "y": y}
    res["pass"] = bool(reset_ok and rows_ok and col_ok and 58 <= rate <= 62 and bounce_ok)
    return res
