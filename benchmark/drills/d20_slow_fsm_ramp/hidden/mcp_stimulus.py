"""Stimulus for lib/enable_monitor.py on d20_slow_fsm_ramp: ramps, GO written at assorted phases, STEP/TOP writes."""

from __future__ import annotations

STEP, TOP, GO = 0, 1, 2


async def stimulus(b) -> None:
    for step, top, gap in ((40, 200, 3), (7, 30, 5), (255, 100, 1), (9, 90, 6)):
        await b.write(STEP, step)
        await b.write(TOP, top)
        await b.cycles(gap)
        await b.write(GO, 1)
        await b.cycles(8 * (2 * top // step + 6) + gap)
