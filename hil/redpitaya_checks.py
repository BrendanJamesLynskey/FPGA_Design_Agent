"""Checks of the Red Pitaya custom instruments through a register window (brief 225). Standard library only: the owner copies this file and
``hil/redpitaya_regs.py`` to the board, and the dry run runs the same functions against a model.

    python3 redpitaya_checks.py <block> [--base 0x40700000] [--expect-hz F] [--tol-ppm N] [--drive-ok]    # on the board, as root, design loaded
    python3 redpitaya_checks.py <block> --base <slot base> --id-only      # one read of the ID register; exit 0 ok, 3 reads 0 (nothing answers), 1 another value (brief 243)

Each check returns rows ``{"check", "result": "pass" | "fail", "detail", ...}``; nothing is written to the board except the block's own registers. A check
that would make OUT1 move (:func:`check_patgen_output`) runs only with ``--drive-ok`` and after the caller's typed confirmation: the run script asks for it.
No check reads an offset outside the block's register map.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Callable

try:
    from hil.redpitaya_regs import MAPS, SLOT_BASE, FREQCOUNT, PATGEN, MemWindow, RegMap, Window, sext14
except ImportError:                                           # copied next to this file on the board
    from redpitaya_regs import MAPS, SLOT_BASE, FREQCOUNT, PATGEN, MemWindow, RegMap, Window, sext14      # type: ignore

F_CLK = 125_000_000.0


def row(check: str, ok: bool, detail: str, **kw) -> dict:
    return {"check": check, "result": "pass" if ok else "fail", "detail": detail, **kw}


def check_id(w: Window, m: RegMap) -> dict:
    got = w.read(m.by_name("ID").offset)
    return row("id", got == m.block_id, f"ID register reads {got:#010x}, expected {m.block_id:#010x} ({m.block})"
               + ("" if got == m.block_id else "; the design loaded is not this block, or nothing is loaded in slot 7"))


def check_scratch(w: Window, m: RegMap) -> dict:
    off, bad = m.by_name("SCRATCH").offset, []
    for pat in (0x00000000, 0xFFFFFFFF, 0xA5A5A5A5, 0x5A5A5A5A, 0x12345678):
        w.write(off, pat)
        got = w.read(off)
        if got != pat:
            bad.append(f"wrote {pat:#010x}, read {got:#010x}")
    w.write(off, 0)
    return row("scratch", not bad, "five patterns read back" if not bad else "; ".join(bad))


def check_reset_values(w: Window, m: RegMap, skip: tuple[str, ...] = ()) -> dict:
    """Right after a load every register with a reset value reads it (read-only result registers read 0). Run before any other write."""
    bad = []
    for r in m.regs:
        if r.name in skip:
            continue
        got = w.read(r.offset)
        want = r.reset if r.access == "RW" else None
        if want is not None and got != want:
            bad.append(f"{r.name} reads {got:#x}, reset is {want:#x}")
    return row("reset_values", not bad, "all RW registers at their reset values" if not bad else "; ".join(bad))


def wait_status(w: Window, m: RegMap, bit: int, timeout_s: float, sleep: Callable[[float], None] = time.sleep, now: Callable[[], float] = time.monotonic) -> bool:
    off, end = m.by_name("STATUS").offset, now() + timeout_s
    while now() < end:
        if w.read(off) & bit:
            return True
        sleep(0.01)
    return False


def check_freqcount(w: Window, expect_hz: float | None, tol_ppm: float = 1000.0, gate_cycles: int = 12_500_000, repeats: int = 3,
                    sleep: Callable[[float], None] = time.sleep) -> list[dict]:
    """Measure IN1 ``repeats`` times with a gate of ``gate_cycles`` (default 0.1 s) and compare both estimates with ``expect_hz`` (None: record, do not judge).

    The two estimates must agree with each other within 10 ppm x (the clock cycles are exact, the quantisation is one signal period over the gate), and with
    the expected frequency within ``tol_ppm`` plus that quantisation. Checks MEAS_DONE moves by one per gate, GATE_ACTUAL equals the gate, and DONE sets."""
    m = FREQCOUNT
    o = {r.name: r.offset for r in m.regs}
    rows: list[dict] = []
    w.write(o["GATE_LEN"], gate_cycles)
    got_len = w.read(o["GATE_LEN"])
    rows.append(row("gate_len_readback", got_len == gate_cycles, f"wrote {gate_cycles}, read {got_len}"))
    est: list[tuple[float, float]] = []
    for i in range(repeats):
        before = w.read(o["MEAS_DONE"])
        w.write(o["CTRL"], 1)
        done = wait_status(w, m, 2, timeout_s=gate_cycles / F_CLK * 4 + 2.0, sleep=sleep)
        if not done:
            rows.append(row(f"gate_{i}", False, "STATUS.DONE did not set within four gate lengths + 2 s"))
            break
        for _ in range(3):                                           # one gate's registers read together: MEAS_DONE must match before and after
            n1 = w.read(o["MEAS_DONE"])
            edges, actual, span, status = (w.read(o[k]) for k in ("EDGES", "GATE_ACTUAL", "SPAN", "STATUS"))
            if w.read(o["MEAS_DONE"]) == n1:
                break
        ok_meas = (n1 - before) & 0xFFFFFFFF == 1
        ok_len = actual == gate_cycles
        f_gate = edges / (actual / F_CLK) if actual else float("nan")
        f_recip = (edges - 1) * F_CLK / span if edges >= 2 and span else float("nan")
        est.append((f_gate, f_recip))
        rows.append(row(f"gate_{i}", ok_meas and ok_len and edges >= 1, f"EDGES {edges}, GATE_ACTUAL {actual} (asked {gate_cycles}), SPAN {span}, STATUS {status:#x}, MEAS_DONE +{(n1 - before) & 0xFFFFFFFF}",
                        edges=edges, gate_actual=actual, span=span, status=status, f_gate_hz=f_gate, f_recip_hz=f_recip))
    if est and expect_hz:
        quant_ppm = 1e6 / (expect_hz * gate_cycles / F_CLK)           # one signal period of a 1-edge uncertainty, in ppm of the frequency
        for k, name in ((0, "gate"), (1, "recip")):
            vals = [e[k] for e in est if e[k] == e[k]]
            if not vals:
                rows.append(row(f"freq_{name}", False, f"no {name} estimate"))
                continue
            f = sum(vals) / len(vals)
            err = (f - expect_hz) / expect_hz * 1e6
            tol = tol_ppm + (quant_ppm if name == "gate" else quant_ppm / 10)
            rows.append(row(f"freq_{name}", abs(err) <= tol, f"{f:.3f} Hz vs expected {expect_hz:.3f} Hz: {err:+.1f} ppm (limit {tol:.1f} ppm, of which quantisation {quant_ppm if name == 'gate' else quant_ppm / 10:.1f})",
                            f_hz=f, error_ppm=err, tolerance_ppm=tol))
    elif est:
        rows.append(row("freq_recorded", True, "no expected frequency given: the estimates are recorded, not judged", estimates=est))
    return rows


def check_patgen_registers(w: Window) -> list[dict]:
    """Register-level checks of the pattern generator that move no output: LIMIT's ceiling, the legal-value clamps and the read-back. START is never written."""
    m = PATGEN
    o = {r.name: r.offset for r in m.regs}
    rows = []
    w.write(o["LIMIT"], 0x7FFF)
    rows.append(row("limit_ceiling", w.read(o["LIMIT"]) == 7372, f"LIMIT after writing 0x7FFF reads {w.read(o['LIMIT'])} (the ceiling is 7372 = 0.9 V)"))
    w.write(o["LIMIT"], 4096)
    for name, wr, want in (("PERIOD", 0, 2), ("COUNT", 0, 1), ("PAT_LEN", 99, 16), ("SAMPLE_DIV", 0, 1), ("MODE", 7, 0)):
        w.write(o[name], wr)
        got = w.read(o[name])
        rows.append(row(f"clamp_{name.lower()}", got == want, f"{name}: wrote {wr}, read {got}, expected {want}"))
    w.write(o["LEVEL_HI"], 0x1FFF)
    rows.append(row("level_signed14", sext14(w.read(o["LEVEL_HI"])) == 8191, f"LEVEL_HI after 0x1FFF reads {w.read(o['LEVEL_HI']):#x}"))
    for name in ("PERIOD", "COUNT", "PAT_LEN", "SAMPLE_DIV", "MODE", "LEVEL_HI"):          # back to reset values
        w.write(o[name], next(r.reset for r in m.regs if r.name == name))
    st = w.read(o["STATUS"])
    rows.append(row("idle_status", st & 1 == 0, f"STATUS reads {st:#x}: not RUNNING after load, nothing started"))
    return rows


def check_patgen_output(w: Window, level_counts: int = 2048, period: int = 1250, periods: int = 4,
                        sleep: Callable[[float], None] = time.sleep) -> list[dict]:
    """Emit ``periods`` pulses of +``level_counts`` on OUT1 (default 0.25 V at 100 kHz). **Moves OUT1**: the caller has the owner's confirmation. The level is
    refused above 4096 counts here (0.5 V) whatever the register ceiling is: a self-test needs no more, and IN1 on LV takes +-1 V."""
    m = PATGEN
    o = {r.name: r.offset for r in m.regs}
    if abs(level_counts) > 4096:
        return [row("patgen_output", False, f"level {level_counts} counts is above the 4096 this self-test allows (0.5 V); not started")]
    w.write(o["MODE"], 0)
    w.write(o["PERIOD"], period)
    w.write(o["WIDTH"], period // 2)
    w.write(o["LEVEL_HI"], level_counts & 0x3FFF)
    w.write(o["LEVEL_LO"], 0)
    w.write(o["COUNT"], periods)
    w.write(o["LIMIT"], 4096)
    w.write(o["CTRL"], 1)
    done = wait_status(w, m, 2, timeout_s=1.0, sleep=sleep)
    st = w.read(o["STATUS"])
    n = w.read(o["PERIODS_DONE"])
    w.write(o["CTRL"], 2)                                                       # STOP: OUT1 back to 0, whatever happened
    return [row("patgen_output", done and n == periods and st & 4 == 0, f"DONE {done}, PERIODS_DONE {n} (asked {periods}), STATUS {st:#x} (CLAMPED must be 0)")]


def run_block(block: str, w: Window, expect_hz: float | None = None, tol_ppm: float = 1000.0, drive_ok: bool = False,
              sleep: Callable[[float], None] = time.sleep) -> list[dict]:
    m = MAPS[block]
    rows = [check_id(w, m)]
    if rows[0]["result"] != "pass":
        return rows                                                            # a different block: do not write anything else
    if block == "rp_freqcount":
        rows += [check_reset_values(w, m), check_scratch(w, m)] + check_freqcount(w, expect_hz, tol_ppm, sleep=sleep)
    else:
        rows += [check_reset_values(w, m), check_scratch(w, m)] + check_patgen_registers(w)
        if drive_ok:
            rows += check_patgen_output(w, sleep=sleep)
        else:
            rows.append(row("patgen_output", True, "not run: no confirmation to move OUT1 was given (the run script asks for it)", skipped=True))
    return rows


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("block", choices=sorted(MAPS))
    ap.add_argument("--base", type=lambda s: int(s, 0), default=SLOT_BASE)
    ap.add_argument("--expect-hz", type=float)
    ap.add_argument("--tol-ppm", type=float, default=1000.0)
    ap.add_argument("--drive-ok", action="store_true", help="the owner confirmed that OUT1 may move")
    ap.add_argument("--id-only", action="store_true", help="read the block's ID register once and stop: exit 0 if it is the block's ID, 3 if it reads 0 (no block answers the bus), 1 otherwise")
    a = ap.parse_args(argv)
    w = MemWindow(a.base)
    if a.id_only:
        try:
            m = MAPS[a.block]
            got = w.read(m.by_name("ID").offset)
        finally:
            w.close()
        ok = got == m.block_id
        print(json.dumps({"schema": "fpga-design-agent/rp-check/v1", "block": a.block, "base": hex(a.base), "id_read": hex(got), "id_expected": hex(m.block_id), "pass": ok}))
        return 0 if ok else (3 if got == 0 else 1)
    try:
        rows = run_block(a.block, w, a.expect_hz, a.tol_ppm, a.drive_ok)
    finally:
        w.close()
    print(json.dumps({"schema": "fpga-design-agent/rp-check/v1", "block": a.block, "mock": False, "rows": rows, "pass": all(r["result"] == "pass" for r in rows)}, indent=1))
    return 0 if all(r["result"] == "pass" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
