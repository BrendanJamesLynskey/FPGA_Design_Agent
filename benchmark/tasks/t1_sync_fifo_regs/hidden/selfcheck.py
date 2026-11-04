"""On-board self-check of t1_sync_fifo_regs (run by flow/board_check.py; nobody touches the board).

Pass rule (written before any board run):
  - after draining (POP until LEVEL = 0) and clearing both error flags (FLAGS = 0x300), FLAGS reads 0x001;
  - pushing 0x11, 0x22, 0x33: HEAD reads 0x11 (first-word-fall-through), LEVEL 3; POP reads 0x11, 0x22, 0x33;
  - a fourth POP reads 0 and sets UNDERFLOW (FLAGS 0x201); 17 pushes give LEVEL 16 and FLAGS 0x106 (empty 0, full,
    almost full at the reset threshold 12, OVERFLOW, UNDERFLOW cleared first); FLAGS = 0x100 then clears OVERFLOW only;
  - the FIFO is drained again at the end.
"""

from __future__ import annotations

from typing import Any

from shell.host import protocol as p

DESIGN_ID = 0x4649_464F          # "FIFO"
PUSH, POP, HEAD, LEVEL, FLAGS, AF_THRESH = (p.WINDOW_BASE + i for i in range(6))


def drain(sh: Any) -> None:
    for _ in range(17):
        if sh.read(LEVEL) == 0:
            break
        sh.read(POP)


def check(sh: Any) -> dict[str, Any]:
    sh.write(AF_THRESH, 12)
    drain(sh)
    sh.write(FLAGS, 0x300)
    f0 = sh.read(FLAGS)
    for v in (0x11, 0x22, 0x33):
        sh.write(PUSH, v)
    head, level = sh.read(HEAD), sh.read(LEVEL)
    popped = [sh.read(POP) for _ in range(3)]
    extra = sh.read(POP)
    f1 = sh.read(FLAGS)
    sh.write(FLAGS, 0x200)
    for i in range(17):
        sh.write(PUSH, i)
    level_full, f2 = sh.read(LEVEL), sh.read(FLAGS)
    sh.write(FLAGS, 0x100)
    f3 = sh.read(FLAGS)
    drain(sh)
    res = {"flags_clean": f"0x{f0:03X}", "head": f"0x{head:02X}", "level": level, "popped": popped,
           "empty_pop": extra, "flags_underflow": f"0x{f1:03X}", "level_full": level_full,
           "flags_full": f"0x{f2:03X}", "flags_after_w1c": f"0x{f3:03X}"}
    res["pass"] = (f0 == 0x001 and head == 0x11 and level == 3 and popped == [0x11, 0x22, 0x33] and extra == 0
                   and f1 == 0x201 and level_full == 16 and f2 == 0x106 and f3 == 0x006)
    return res
