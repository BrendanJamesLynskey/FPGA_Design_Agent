"""P5 host check: PRBS soak through a 25 MHz to 156.25 MHz asynchronous FIFO. Criteria: pilots/209/p5_async_fifo/preregistration.md."""
from __future__ import annotations

from report import Report, basics

M32 = 0xFFFFFFFF
DEPTH = 512
WRITE_HZ = 25e6
READ_HZ = 156.25e6
RUN, SLOW, CLEAR, INJECT = 1, 2, 4, 8
NAMES = ["words_w", "words_r", "data_errs", "overflows", "underflows", "stall_w", "occ_max"]
SOAK_S = 600.0
SNAP_EVERY_S = 10.0


def snap(bus, clk) -> dict:
    bus.wr(0x030, 1)
    t = clk.now()
    d = {n: bus.rd(0x014 + 4 * i) for i, n in enumerate(NAMES)}
    d["t"] = t
    return d


def delta(b: dict, a: dict, k: str) -> int:
    return (b[k] - a[k]) & M32


def run(bus, rep: Report, clk, soak_s: float = SOAK_S, snap_every: float = SNAP_EVERY_S, **_) -> None:
    basics(bus, rep)
    bus.wr(0x010, 0)
    bus.wr(0x010, CLEAR)
    # 1. the checker notices one flipped word
    bus.wr(0x010, RUN)
    clk.sleep(1.0)
    bus.wr(0x010, RUN | INJECT)
    clk.sleep(1.0)
    s = snap(bus, clk)
    bus.wr(0x010, 0)
    rep.data["inject"] = s
    rep.crit("inject_one_error", s["data_errs"] == 1 and s["overflows"] == 0 and s["underflows"] == 0, f"errs {s['data_errs']} ovf {s['overflows']} und {s['underflows']}", "1, 0, 0")
    # 2. slow reader: the FIFO fills, the writer is held off, nothing is lost
    bus.wr(0x010, CLEAR)
    bus.wr(0x010, RUN | SLOW)
    clk.sleep(2.0)
    a = snap(bus, clk)
    clk.sleep(5.0)
    b = snap(bus, clk)
    bus.wr(0x010, 0)
    dt = b["t"] - a["t"]
    rate_r = delta(b, a, "words_r") / dt
    exp_r = READ_HZ / 8
    rep.data["slow_read"] = {"a": a, "b": b, "rate_r": rate_r}
    rep.crit("slow_read_no_errors", b["data_errs"] == 0 and b["overflows"] == 0 and b["underflows"] == 0, f"errs {b['data_errs']} ovf {b['overflows']} und {b['underflows']}", "0, 0, 0")
    rep.crit("slow_read_writer_held_off", b["stall_w"] > 0 and DEPTH - 8 <= b["occ_max"] <= DEPTH, f"stall {b['stall_w']} occ_max {b['occ_max']}", f"stall > 0, occ_max in [{DEPTH - 8}, {DEPTH}]")
    rep.crit("slow_read_rate", abs(rate_r - exp_r) <= 0.01 * exp_r, f"{rate_r / 1e6:.3f} Mword/s", f"{exp_r / 1e6:.3f} +- 1 %")
    rep.crit("slow_read_fill_within_depth", 0 <= (b["words_w"] - b["words_r"]) & M32 <= DEPTH, (b["words_w"] - b["words_r"]) & M32, f"0..{DEPTH}")
    # 3. the soak
    bus.wr(0x010, CLEAR)
    bus.wr(0x010, RUN)
    first = snap(bus, clk)
    snaps, bad_fill, tw, tr = [first], 0, 0, 0                 # the 32-bit counters wrap every 171 s: sum the deltas between consecutive snapshots
    while snaps[-1]["t"] - first["t"] < soak_s:
        clk.sleep(snap_every)
        s = snap(bus, clk)
        bad_fill += not (0 <= (s["words_w"] - s["words_r"]) & M32 <= DEPTH)
        for k in ("data_errs", "overflows", "underflows"):
            if s[k] != 0 and "first_nonzero" not in rep.data:
                rep.data["first_nonzero"] = {"counter": k, "snapshot": s}
        tw += delta(s, snaps[-1], "words_w")
        tr += delta(s, snaps[-1], "words_r")
        snaps.append(s)
    last = snaps[-1]
    dt = last["t"] - first["t"]
    rw, rr = tw / dt, tr / dt
    rep.data["soak"] = {"n_snapshots": len(snaps), "seconds": dt, "rate_w": rw, "rate_r": rr, "last": last}
    bus.wr(0x010, 0)
    rep.crit("soak_duration", dt >= soak_s, f"{dt:.1f} s", f">= {soak_s:.0f} s")
    rep.crit("soak_data_errors_zero", last["data_errs"] == 0, last["data_errs"], 0)
    rep.crit("soak_overflows_zero", last["overflows"] == 0, last["overflows"], 0)
    rep.crit("soak_underflows_zero", last["underflows"] == 0, last["underflows"], 0)
    rep.crit("soak_writer_never_held_off", last["stall_w"] == 0, last["stall_w"], "0 (the reader is 6.25 times faster)")
    rep.crit("soak_write_rate", abs(rw - WRITE_HZ) <= 0.005 * WRITE_HZ, f"{rw / 1e6:.4f} Mword/s", "25 +- 0.5 %")
    rep.crit("soak_read_rate", abs(rr - WRITE_HZ) <= 0.005 * WRITE_HZ, f"{rr / 1e6:.4f} Mword/s", "25 +- 0.5 %")
    rep.crit("soak_fill_within_depth_every_snapshot", bad_fill == 0, bad_fill, 0)
