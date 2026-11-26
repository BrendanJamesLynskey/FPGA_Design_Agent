"""P1 host check: the C3 clock frequency against the 156.25 MHz GT reference clock. Criteria: pilots/209/p1_clkmeter/preregistration.md."""
from __future__ import annotations

from report import Report, basics

REF_HZ = 156.25e6
NOMINAL_HZ = 25e6
PPM = 100.0
GATES_LONG = [156_250_000] * 5            # five one-second gates
GATES_SHORT = [15_625_000, 1_562_500, 156_250, 31_250_000]   # 0.1 s, 10 ms, 1 ms, 0.2 s


def measure(bus, clk, gate: int, timeout: float = 5.0) -> tuple[int, int]:
    bus.wr(0x010, gate)
    bus.wr(0x014, 0x1 | (bus.rd(0x014) & 0x2))
    t0 = clk.now()
    while True:
        st = bus.rd(0x018)
        if st & 0x2 and not st & 0x1:
            break
        if clk.now() - t0 > timeout + gate / REF_HZ:
            raise TimeoutError(f"gate {gate} not done within the timeout (STATUS {st:#x})")
        clk.sleep(0.05)
    return bus.rd(0x01C), bus.rd(0x020)


def run(bus, rep: Report, clk, **_) -> None:
    basics(bus, rep)
    bus.wr(0x014, 0)                                   # LEDs off while measuring
    done0 = bus.rd(0x024)
    freqs, spread_ok, actual_ok, rows = [], True, True, []
    for g in GATES_LONG + GATES_SHORT:
        cnt, act = measure(bus, clk, g)
        f = cnt * REF_HZ / act if act else 0.0
        rows.append({"gate": g, "count": cnt, "actual": act, "freq_hz": f})
        actual_ok &= act == g
        exp = g * NOMINAL_HZ / REF_HZ
        tol = exp * PPM * 1e-6 + 2
        if g in GATES_LONG:
            freqs.append(cnt)
        rep.crit(f"count_gate_{g}", abs(cnt - exp) <= tol, cnt, f"{exp:.0f} +- {tol:.1f}")
    rep.data["measurements"] = rows
    rep.crit("gate_actual_equals_gate", actual_ok, [r["actual"] for r in rows], [r["gate"] for r in rows])
    rep.crit("five_long_readings_agree", max(freqs) - min(freqs) <= 100, max(freqs) - min(freqs), "<= 100 counts (4 ppm)")
    mean_hz = sum(r["freq_hz"] for r in rows[:5]) / 5
    rep.data["c3_freq_hz_mean_of_five_1s"] = mean_hz
    rep.crit("c3_frequency_within_100ppm", abs(mean_hz - NOMINAL_HZ) <= NOMINAL_HZ * PPM * 1e-6, f"{mean_hz:.1f} Hz ({(mean_hz / NOMINAL_HZ - 1) * 1e6:+.1f} ppm)", "25 MHz +- 100 ppm")
    rep.crit("meas_done_counts", (bus.rd(0x024) - done0) & 0xFFFFFFFF == len(rows), (bus.rd(0x024) - done0) & 0xFFFFFFFF, len(rows))
    bus.wr(0x014, 0)                                   # safe state: LEDs off
    rep.crit("leds_off_at_end", bus.rd(0x014) & 0x2 == 0, f"{bus.rd(0x014):#x}", "LED_EN = 0")
