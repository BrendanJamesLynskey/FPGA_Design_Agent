"""The 59-byte order payload, as brief 110's packers build it (the bytes the fast path carries)."""
from __future__ import annotations

import random

from designs.b110_itch_ouch.model import proto
from designs.b110_itch_ouch.model.ref import Cfg


def payload(ref: int, qty: int, sym: str | bytes, px: int, cfg: Cfg | None = None) -> bytes:
    c = cfg or Cfg()
    s = proto.alpha(sym, 8) if isinstance(sym, str) else sym
    m = proto.ouch_enter(ref, "B", qty, s, px, c.tif, c.display, c.capacity, c.ise, c.cross, proto.clordid(ref), c.minqty, c.custtype)
    return proto.soup_unsequenced(m)


def random_order(rng: random.Random, ref: int | None = None) -> dict:
    """Fields of one order (random but valid); every byte of every field takes both values over a few hundred draws."""
    syms = ["AAA", "BBB", "CCC", "DDD", "ZZZZ", "A", "QQQQQQQQ"]
    return {"ref": rng.getrandbits(32) if ref is None else ref, "qty": rng.choice([1, 100, 999_999, rng.getrandbits(20)]),
            "sym": rng.choice(syms), "px": rng.choice([0, 1, 0xFFFFFFFF, 1_000_000, rng.getrandbits(32)])}
