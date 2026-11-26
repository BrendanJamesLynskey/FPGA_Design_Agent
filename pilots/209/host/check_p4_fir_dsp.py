"""P4 host check: 32-tap symmetric FIR against a Python fixed-point model. Criteria: pilots/209/p4_fir_dsp/preregistration.md."""
from __future__ import annotations

import random
from pathlib import Path

from report import Report, basics

COEFF_FILE = Path(__file__).resolve().parents[1] / "p4_fir_dsp" / "data" / "coeffs.hex"
CHUNK = 1000
SEED = 2094


def coeffs() -> list[int]:
    return [v - 0x10000 if v & 0x8000 else v for v in (int(l, 16) for l in COEFF_FILE.read_text().split())]


class Model:
    def __init__(self) -> None:
        self.h, self.hist, self.sat, self.done = coeffs(), [0] * 32, 0, 0

    def feed(self, xs: list[int]) -> list[int]:
        out = []
        for x in xs:
            self.hist = [x] + self.hist[:31]
            acc = sum(h * v for h, v in zip(self.h, self.hist))
            y = (acc + 0x4000) >> 15
            if y > 32767 or y < -32768:
                self.sat += 1
                y = 32767 if y > 0 else -32768
            out.append(y)
            self.done += 1
        return out


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def process(bus, clk, xs: list[int]) -> list[int]:
    got: list[int] = []
    for i in range(0, len(xs), CHUNK):
        part = xs[i:i + CHUNK]
        for x in part:
            bus.wr(0x014, x & 0xFFFF)
        bus.wr(0x010, 0x2)
        t0 = clk.now()
        while True:
            st = bus.rd(0x01C)
            if not st & 1 and (st >> 20) >= len(part):
                break
            if clk.now() - t0 > 10:
                raise TimeoutError(f"FIR run not done (STATUS {st:#x})")
            clk.sleep(0.01)
        for _ in part:
            v = bus.rd(0x018)
            got.append(s16(v) if v & 0x80000000 else None)
    return got


def section(bus, rep: Report, clk, name: str, xs: list[int]) -> None:
    bus.wr(0x010, 0x1)
    m = Model()
    want = m.feed(xs)
    got = process(bus, clk, xs)
    bad = [i for i in range(len(xs)) if got[i] != want[i]]
    rep.crit(f"{name}_bit_exact", not bad, f"{len(bad)} of {len(xs)} differ" + (f", first at {bad[0]}: got {got[bad[0]]} want {want[bad[0]]}" if bad else ""), "0 differ")
    rep.crit(f"{name}_sat_count", bus.rd(0x020) == m.sat, bus.rd(0x020), m.sat)
    rep.crit(f"{name}_samples_done", bus.rd(0x024) == len(xs), bus.rd(0x024), len(xs))
    rep.data[f"{name}_saturated"] = m.sat


def run(bus, rep: Report, clk, **_) -> None:
    basics(bus, rep)
    h = coeffs()
    rep.crit("coefficients_symmetric", h == h[::-1] and len(h) == 32, "model", "h[k] = h[31-k]")
    section(bus, rep, clk, "impulse", [0x4000] + [0] * 99)
    section(bus, rep, clk, "step", [0x4000] * 100)
    stress = [32767 if h[31 - (n % 32)] >= 0 else -32768 for n in range(256)]       # drives the sum to its maximum: saturation expected
    section(bus, rep, clk, "max_stress", stress)
    r = random.Random(SEED)
    section(bus, rep, clk, "random_10000", [r.randint(-32768, 32767) for _ in range(10_000)])
