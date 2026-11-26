"""P6 host check: 1,000 run-time clock switches through a glitch-free mux. Criteria: pilots/209/p6_glitchfree_mux/preregistration.md."""
from __future__ import annotations

import random

from report import Report, basics

SEED = 2096
SWITCHES = 1000
A_HZ, REF_HZ = 25e6, 156.25e6
PPM = 200.0
GATE_LONG, GATE_SHORT = 25_000_000, 2_500_000


def select(bus, clk, sel: int, timeout: float = 1.0) -> bool:
    bus.wr(0x010, sel)
    t0 = clk.now()
    while True:
        st = bus.rd(0x014)
        if (st >> 1) & 1 == sel and not st & 1:
            return True
        if clk.now() - t0 > timeout:
            return False


def freq_count(bus, clk, gate: int) -> int:
    bus.wr(0x01C, gate)
    bus.wr(0x020, 1)
    t0 = clk.now()
    while True:
        st = bus.rd(0x024)
        if st & 2 and not st & 1:
            return bus.rd(0x028)
        if clk.now() - t0 > 3 + gate / A_HZ:
            raise TimeoutError(f"gate {gate} not done (FREQ_STATUS {st:#x})")
        clk.sleep(0.02)


def check_freq(bus, rep: Report, clk, sel: int, gate: int, bdiv: int, label: str) -> None:
    cnt = freq_count(bus, clk, gate)
    exp = gate * (1.0 if sel == 0 else REF_HZ / A_HZ / bdiv)
    tol = exp * PPM * 1e-6 + 2
    rep.crit(f"freq_{label}_sel{sel}", abs(cnt - exp) <= tol, cnt, f"{exp:.0f} +- {tol:.1f}")


def run(bus, rep: Report, clk, switches: int = SWITCHES, **_) -> None:
    basics(bus, rep)
    bdiv = bus.rd(0x018)
    rep.data["b_div"] = bdiv
    rep.crit("b_div_in_range", 1 <= bdiv <= 8, bdiv, "1..8")
    rep.crit("start_state", bus.rd(0x010) & 1 == 0 and bus.rd(0x02C) == 0 and bus.rd(0x034) == 0, f"SEL {bus.rd(0x010)} ERRS {bus.rd(0x02C)} SWITCHES {bus.rd(0x034)}", "0, 0, 0 after configuration")
    check_freq(bus, rep, clk, 0, GATE_LONG, bdiv, "start_1s")
    assert select(bus, clk, 1), "initial switch to B failed"
    check_freq(bus, rep, clk, 1, GATE_LONG, bdiv, "start_1s")
    bus.wr(0x038, 1)
    m1 = bus.rd(0x030)
    clk.sleep(0.05)
    bus.wr(0x038, 1)
    rep.crit("mux_counter_moves", bus.rd(0x030) != m1, "changed" if bus.rd(0x030) != m1 else "static", "changes between snapshots")
    r = random.Random(SEED)
    cur, changes, timeouts = 1, 1, 0                  # the switch to B above counted
    seq = [r.randint(0, 1) for _ in range(switches)]
    for i, s in enumerate(seq, 1):
        if s != cur:
            changes += 1
        cur = s
        if not select(bus, clk, s):
            timeouts += 1
        clk.sleep(r.random() * 0.005)
        if i % 100 == 0 and cur == s:
            check_freq(bus, rep, clk, s, GATE_SHORT, bdiv, f"after_{i}")
    rep.data["requested_changes"] = changes
    rep.crit("all_switches_completed", timeouts == 0, f"{timeouts} timeouts", "0")
    sc, errs = bus.rd(0x034), bus.rd(0x02C)
    rep.crit("mux_domain_errors_zero", errs == 0, errs, 0)
    rep.crit("switch_count_equals_changes", sc == changes, sc, changes)
    check_freq(bus, rep, clk, cur, GATE_LONG, bdiv, "end_1s")
    other = 1 - cur
    assert select(bus, clk, other), "final switch failed"
    check_freq(bus, rep, clk, other, GATE_LONG, bdiv, "end_other_1s")
    rep.crit("mux_domain_errors_zero_at_end", bus.rd(0x02C) == 0, bus.rd(0x02C), 0)
    select(bus, clk, 0)                                # safe state: clock A
