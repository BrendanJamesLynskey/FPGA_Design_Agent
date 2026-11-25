"""A reference-number stream for sizing order tables (brief 190, item 18; idea from Edwards 2026, ch 7: test streams are too tidy).

``gen.py`` keeps every live reference inside one table's worth of indices, so index collisions are only ever tested by hand-built cases. This
module is the other kind of test input: references that look like a venue's, for judging how big a table must be and whether a lookup with two
candidate slots is worth having. It writes no packets; it yields (time, add or delete, reference) events and replays them against a table model.

What makes the stream realistic (all of it is a parameter, nothing is taken from real exchange data):

- references come from one counter the whole market shares, so our instruments' references are sparse: between two of ours there are
  ``gap_mean`` others on average (a geometric gap);
- lifetimes are heavy-tailed (log-normal): most orders die within a few events, a few live for thousands, and ``day_long`` of them are never
  deleted in the run;
- the number of live orders therefore grows through the run instead of staying at a tidy cap.

``reference_mode="sequential"`` keeps the references as the counter gives them; ``"random"`` draws each reference as 64 random bits (a stand-in
for a venue whose references are not issued in order), which makes the low bits behave like random indices. (Multiplying the counter by an odd
constant would change nothing for a table indexed by the low bits: an odd multiplier is a bijection on the low b bits, so the collision pattern
is identical. The first draft of this module did that and the measurement showed it.)

Seeded and deterministic. Birthday-bound helpers (our own derivation, see the knowledge-bank skill ``table-sizing-and-bounded-lookup``) are here too.
"""
from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass

_ODD2 = 0xC2B2AE3D27D4EB4F         # a second odd constant for the second candidate slot


# ---- the birthday bound ------------------------------------------------------------------------------------------------------------------
def p_any_collision(n: int, m: int) -> float:
    """Exact probability that n items placed uniformly at random into m slots share at least one slot: 1 - prod_{i<n} (1 - i/m)."""
    if n > m:
        return 1.0
    log_p = sum(math.log1p(-i / m) for i in range(n))
    return -math.expm1(log_p)


def p_any_collision_approx(n: int, m: int) -> float:
    """1 - exp(-n(n-1)/(2m)): from ln(1 - x) ~ -x, and sum_{i<n} i = n(n-1)/2."""
    return -math.expm1(-n * (n - 1) / (2 * m))


def slots_for_collision_probability(n: int, p: float) -> int:
    """Smallest number of slots m (not rounded to a power of two) for which the approximation gives at most p: m >= n(n-1) / (2 ln(1/(1-p)))."""
    return math.ceil(n * (n - 1) / (2 * -math.log1p(-p)))


def pow2_at_least(m: int) -> int:
    return 1 << max(0, (m - 1).bit_length())


def p_new_item_finds_slot_taken(live: int, m: int) -> float:
    """The per-insert version of the same bound: with ``live`` other items already placed uniformly, a new one finds its slot taken with probability
    1 - (1 - 1/m)^live ~ live/m. This is the rate that matters for a table whose live count changes (insert and delete)."""
    return 1.0 - (1.0 - 1.0 / m) ** live


# ---- the stream ---------------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class StreamCfg:
    seed: int = 1
    n_orders: int = 20000            # adds in the run
    gap_mean: float = 30.0           # market references issued between two of ours (geometric; 0 = every reference is ours)
    life_median: float = 40.0        # median lifetime in adds (log-normal)
    life_sigma: float = 2.0          # log-normal sigma: larger = heavier tail
    day_long: float = 0.01           # fraction never deleted in the run
    reference_mode: str = "sequential"   # "sequential" or "random"


def events(cfg: StreamCfg) -> list[tuple[int, str, int]]:
    """(time, "add" | "del", reference), in time order; a delete follows its add by at least one time step; deletes at the same time come first."""
    r = random.Random(cfg.seed)
    ref = 1_000_000 + r.randrange(0, 1 << 20)
    out: list[tuple[int, int, int, str, int]] = []
    for t in range(cfg.n_orders):
        ref += 1 + (int(r.expovariate(1.0 / cfg.gap_mean)) if cfg.gap_mean > 0 else 0)
        shown = r.getrandbits(64) if cfg.reference_mode == "random" else ref
        out.append((t, 1, t, "add", shown))
        if r.random() >= cfg.day_long:
            life = max(1, int(r.lognormvariate(math.log(cfg.life_median), cfg.life_sigma)))
            out.append((t + life, 0, t, "del", shown))
    out.sort()
    return [(t, kind, rf) for t, _, _, kind, rf in out]


# ---- table models (counting only; the RTL's own counters are the real measurement) -----------------------------------------------------------
def replay_direct(ev: list[tuple[int, str, int]], index_bits: int) -> dict[str, int]:
    """Direct-mapped table indexed by the low index_bits of the reference, as designs/b110_itch_ouch's order table. An add whose slot holds
    another live reference is refused (the RTL counts it as ``oovf`` and marks the instrument inexact); a delete of a refused order does nothing."""
    mask = (1 << index_bits) - 1
    slot: dict[int, int] = {}
    refused: set[int] = set()
    adds = collisions = peak = 0
    for _, kind, rf in ev:
        i = rf & mask
        if kind == "add":
            adds += 1
            if i in slot:
                collisions += 1
                refused.add(rf)
            else:
                slot[i] = rf
                peak = max(peak, len(slot))
        elif rf in refused:
            refused.discard(rf)
        elif slot.get(i) == rf:
            del slot[i]
    return {"adds": adds, "refused": collisions, "peak_live": peak, "slots": 1 << index_bits}


def second_index(rf: int, index_bits: int) -> int:
    """The second candidate slot: the top index_bits of a multiplicative hash with a constant other than the first mode's."""
    return ((rf * _ODD2) & ((1 << 64) - 1)) >> (64 - index_bits)


def replay_two_slot(ev: list[tuple[int, str, int]], index_bits: int) -> dict[str, int]:
    """Bounded lookup: two candidate slots (the low bits, and ``second_index``), looked up in parallel, so a lookup always costs two reads
    whatever the load. An add takes the first free candidate; if both are taken it is refused (no moving of resident entries). A hit in either
    slot serves the reference."""
    mask = (1 << index_bits) - 1
    slot: dict[int, int] = {}
    where: dict[int, int] = {}
    refused: set[int] = set()
    adds = collisions = peak = 0
    for _, kind, rf in ev:
        a, b = rf & mask, second_index(rf, index_bits)
        if kind == "add":
            adds += 1
            for i in (a, b):
                if i not in slot:
                    slot[i] = rf
                    where[rf] = i
                    peak = max(peak, len(slot))
                    break
            else:
                collisions += 1
                refused.add(rf)
        elif rf in refused:
            refused.discard(rf)
        elif rf in where:
            del slot[where.pop(rf)]
    return {"adds": adds, "refused": collisions, "peak_live": peak, "slots": 1 << index_bits}


def uniform_monte_carlo(n: int, m: int, trials: int, seed: int = 1) -> float:
    """Fraction of trials in which n uniform random indices into m slots contain a repeat (checks the closed form)."""
    r = random.Random(seed)
    hit = 0
    for _ in range(trials):
        seen: set[int] = set()
        for _ in range(n):
            x = r.randrange(m)
            if x in seen:
                hit += 1
                break
            seen.add(x)
    return hit / trials
