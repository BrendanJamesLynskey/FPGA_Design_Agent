"""Golden model of p_nec_rx, written from spec.yaml alone."""

from __future__ import annotations

ADDR, CMD, GOOD, REPEATS, E_FORMAT, E_CHECK, CTRL = range(7)
DESIGN_ID = 0x4E454352


def classify(durs: list[int], t: int):
    """durs: alternating low and high durations in clocks, starting with the leader mark. Returns
    ('frame', addr, cmd), ('check',), ('repeat',), ('format',) or ('ignored',)."""
    it = iter(durs)

    def nxt():
        return next(it, None)

    d = nxt()
    if d is None or not (12 * t <= d <= 20 * t):
        return ("ignored",)
    s = nxt()
    if s is None:
        return ("format",)
    if 3 * t <= s <= 5 * t:
        m = nxt()
        return ("repeat",) if m is not None and t // 2 <= m <= (3 * t) // 2 else ("format",)
    if not (6 * t <= s <= 10 * t):
        return ("format",)
    bits = []
    for _ in range(32):
        m, sp = nxt(), nxt()
        if m is None or sp is None or not (t // 2 <= m <= (3 * t) // 2) or sp > 4 * t:
            return ("format",)
        bits.append(0 if sp < 2 * t else 1)
    stop = nxt()
    if stop is None or not (t // 2 <= stop <= (3 * t) // 2):
        return ("format",)
    by = [sum(bits[8 * j + i] << i for i in range(8)) for j in range(4)]
    if by[0] ^ by[1] != 0xFF or by[2] ^ by[3] != 0xFF:
        return ("check",)
    return ("frame", by[0], by[2])


class Model:
    def __init__(self, t: int) -> None:
        self.t = t
        self.addr = self.cmd = 0
        self.c = {"good": 0, "repeat": 0, "format": 0, "check": 0}

    def receive(self, durs: list[int]) -> tuple:
        r = classify(durs, self.t)
        if r[0] == "frame":
            self.addr, self.cmd = r[1], r[2]
            self.c["good"] = min(255, self.c["good"] + 1)
        elif r[0] in self.c:
            self.c[r[0]] = min(255, self.c[r[0]] + 1)
        return r

    def read(self, off: int) -> int:
        return {ADDR: self.addr, CMD: self.cmd, GOOD: self.c["good"], REPEATS: self.c["repeat"], E_FORMAT: self.c["format"], E_CHECK: self.c["check"]}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == CTRL:
            self.c = {"good": 0, "repeat": 0, "format": 0, "check": 0}

    def leds(self) -> int:
        return self.cmd | self.addr << 8


def ideal(addr: int, cmd: int, t: int, comp_flip: bool = False) -> list[int]:
    """Durations of a perfect frame (leader, space, 32 mark/space pairs, stop mark)."""
    out = [16 * t, 8 * t]
    cmp2 = (cmd ^ 0xFF) ^ (1 if comp_flip else 0)
    for byte in (addr, addr ^ 0xFF, cmd, cmp2):
        for i in range(8):
            out += [t, 3 * t if (byte >> i) & 1 else t]
    return out + [t]


def ideal_repeat(t: int) -> list[int]:
    return [16 * t, 4 * t, t]
