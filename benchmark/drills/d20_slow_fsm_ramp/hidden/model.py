"""Golden model of d20_slow_fsm_ramp, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

STEP, TOP, GO, STATE, LEVEL, ACC = range(6)
DESIGN_ID = 0x52414D50          # "RAMP"
IDLE, UP, DOWN = 0, 1, 2


def ramp(step: int, top: int) -> list[int]:
    """The levels after each tick of one ramp from idle (the start tick excluded), ending with the 0 of the tick that
    goes idle."""
    step = step or 1
    out, level, st = [], 0, UP
    while True:
        if st == UP:
            if level + step >= top:
                level, st = top, DOWN
            else:
                level += step
        else:
            if level <= step:
                out.append(0)
                return out
            level -= step
        out.append(level)


def copies(step: int, top: int) -> list[int]:
    """The distinct runs of COPY (LED[15:8]) during one ramp, in order, after the leading 0: COPY lags the level by
    one tick, so it shows exactly ramp()'s levels, each for 8 clocks, and returns to 0."""
    return ramp(step, top)


def acc_of_ramp(step: int, top: int) -> int:
    """ACC gained by a whole ramp (from idle with COPY 0 back to COPY 0): each level is held by COPY for 8 clocks."""
    return 8 * sum(ramp(step, top)) & 0xFFFFFFFF
