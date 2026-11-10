"""Small model behind the flow-notes animation: a 4-bit bus crossing into a two-flop synchroniser.

The same rule as the simulation injection of flow/cdc_inject.py (brief 16): a first-stage flop whose input changed keeps
its old value for one extra destination cycle with probability 1/2, never two cycles in a row. The source value changes
every HOLD destination cycles and every bit of the bus is sampled by its own flop, so with the extra cycle the bits of one
bus can arrive in different cycles. A sampled value is torn when it is neither the current nor the previous source value.
Pure function of (bus, extra, seed, cycles): site/export.py writes the frames; site/src/app.js only draws them.
"""
from __future__ import annotations

import random

WIDTH = 4
HOLD = 4          # destination cycles between source changes: the data is stable for longer than the synchroniser's latency
FRAMES = 48       # cycles in the animation
STAT_CYCLES = 4000
SEED = 5


def to_gray(v: int) -> int:
    return v ^ (v >> 1)


def from_gray(g: int) -> int:
    v = 0
    while g:
        v ^= g
        g >>= 1
    return v


def bits(v: int) -> list[int]:
    return [(v >> (WIDTH - 1 - i)) & 1 for i in range(WIDTH)]      # MSB first


def val(b: list[int]) -> int:
    return sum(x << (WIDTH - 1 - i) for i, x in enumerate(b))


def run(bus: str, extra: bool, cycles: int, seed: int = SEED) -> list[dict]:
    rnd = random.Random(seed)
    f1 = [0] * WIDTH
    f2 = [0] * WIDTH
    held_prev = [False] * WIDTH
    out = []
    n_mod = 1 << WIDTH
    for t in range(cycles):
        k = t // HOLD
        cur = k % n_mod
        prev = (k - 1) % n_mod if k else 0
        drive = to_gray(cur) if bus == "gray" else cur
        inb = bits(drive)
        held = [False] * WIDTH
        new1 = list(f1)
        for i in range(WIDTH):
            if extra and inb[i] != f1[i] and not held_prev[i] and rnd.random() < 0.5:
                held[i] = True                                  # keeps the old value this cycle
            else:
                new1[i] = inb[i]
        f2 = list(f1)                                           # second flop takes the first flop's previous value
        f1 = new1
        held_prev = held
        raw = val(f2)
        seen = from_gray(raw) if bus == "gray" else raw
        out.append({"t": t, "src": inb, "f1": list(f1), "f2": list(f2), "held": [int(h) for h in held],
                    "cur": cur, "prev": prev, "seen": seen, "torn": int(seen not in (cur, prev) and t >= 2 * HOLD)})
    return out


def export() -> dict:
    cfg = {}
    stats = []
    for bus in ("binary", "gray"):
        for extra in (False, True):
            key = f"{bus}_{'extra' if extra else 'plain'}"
            cfg[key] = run(bus, extra, FRAMES)
            long = run(bus, extra, STAT_CYCLES)
            stats.append({"bus": bus, "extra_cycle": extra, "cycles": STAT_CYCLES, "torn_cycles": sum(f["torn"] for f in long)})
    return {"width": WIDTH, "hold": HOLD, "frames": FRAMES, "seed": SEED, "configs": cfg, "stats": stats}
