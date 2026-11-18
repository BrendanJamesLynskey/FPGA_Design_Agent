"""Brief 96C board driver: a real frequency offset on one board, and what the rate matcher does about it. NOT YET RUN ON A BOARD.

Idea: the GTHE4 transmitter's phase-interpolator ppm controller (TXPIPPMEN, TXPIPPMSEL, TXPIPPMSTEPSIZE; the ppm_* bitstreams set TXPI_PPM = 1) is meant
to shift the transmitted line rate against the transmit PLL. In the SFP+ loopback the receiver's clock is recovered from our own transmission,
so the receive user clock should then run at +X ppm against the core clock (the transmit user clock): a plesiochronous link with no second board.
Whether TXUSRCLK2 follows the shifted serial clock (then both user clocks move together and the offset between them is 0) is exactly what the
frequency counter (RXV27, RXV28) measures first. Nothing here ASSUMES the offset: every point's ppm is the measured one.

Order of work (`run_ppm_session`): (1) calibration: for each (TXPIPPMSEL, step code) the frequency counter's ppm and the GT buffer status, link kept or not;
(2) pick the calibrated settings closest to the targets; (3) at each: dwell for a stated time sending armed feed frames, with operating conditions
(SYSMON) at the start, the end and every `cond_every_s`; then E and L distribution over link restarts; (4) every point is judged on its own numbers and a
point that fails is reported failed, not dropped. Transport and Board are those of b96_bench."""

from __future__ import annotations

import json
import time
from pathlib import Path

from designs.b96_kr260_10g.host import b96_bench as bb

F_CORE_HZ = 161_132_812.5
WINDOW_CLOCKS = 1 << 24                         # the frequency counter's window, in core clocks (104.1 ms)
BLOCK_RATE = F_CORE_HZ * 32 / 33                # blocks a second in either clock domain
#: SYSMON (SYSMONE4) status registers read through the register block (0x090 address, 0x094 data: bit 16 valid, 15:6 the 10-bit result).
SYSMON = {"temp_c": 0x00, "vccint_v": 0x01, "vccaux_v": 0x02, "vccbram_v": 0x06}
#: Operating-condition windows, from DS925 (Zynq UltraScale+ DC and AC switching characteristics, v1.x in ~/Claude_sandbox/_amd_docs), Table "Recommended operating conditions":
#: VCCINT for -2LV (0.72 V) devices 0.698 to 0.742 V; VCCBRAM 0.825 to 0.876 V (it is 0.85 V nominal even on the 0.72 V parts); VCCAUX 1.746 to 1.854 V; Tj of an extended-temperature
#: device 0 to 100 C, and the board's own rule is 85 C (house rules), so 0 to 85 C here. Read with the SYSMON's own 10-bit resolution (about 3 mV, 0.5 C).
ROC = {"temp_c": (0.0, 85.0), "vccint_v": (0.698, 0.742), "vccaux_v": (1.746, 1.854), "vccbram_v": (0.825, 0.876)}

#: UG576 v1.7.1, "TX Phase Interpolator PPM Controller" (Equation 3-3): in continuous mode the line rate is offset by
#: ppm = 1e6 x TXPIPPMSTEPSIZE[3:0] / (64 x TXOUT_DIV x TX_INT_DATAWIDTH x (TXPI_SYNFREQ_PPM + 1)); TXPIPPMSTEPSIZE[4] = 1 increments the PI code, 0 decrements;
#: TXPIPPMSEL must be 1 and TXPIPPMEN held at 1. This design: TXOUT_DIV 1, internal data width 32, TXPI_SYNFREQ_PPM 7 (3'b111, set by ppm.xdc; the Wizard's default 1
#: would give 244 ppm a step, too coarse): 1e6 / (64 x 1 x 32 x 8) = 61.04 ppm a step. Which sign is faster against the core clock is NOT assumed (the counter says).
PPM_PER_STEP = 1e6 / (64 * 1 * 32 * 8)


def predicted_ppm(code: int) -> float:
    """The offset Equation 3-3 predicts for a 5-bit step code (bit 4 the sign: 1 increments the PI code). Signed as 'increment = positive'; the measured sign may differ."""
    mag = code & 0xF
    return (mag if (code >> 4) & 1 else -mag) * PPM_PER_STEP if mag else 0.0


def sysmon_to_units(name: str, raw: int) -> float:
    r10 = (raw >> 6) & 0x3FF
    if name == "temp_c":
        return r10 * 501.3743 / 1024 - 273.6777            # the formula of docs/register_map.md (0x094)
    return r10 / 1024 * 3.0


def read_conditions(t: bb.Transport, wait_s: float = 0.01) -> dict:
    out: dict = {}
    for name, addr in SYSMON.items():
        t.wr(0x090, addr)
        raw = None
        for _ in range(20):
            v = t.rd(0x094)
            if (v >> 16) & 1:
                raw = v & 0xFFFF
                break
            time.sleep(wait_s)
        out[name] = None if raw is None else round(sysmon_to_units(name, raw), 4)
    out["inside_roc"] = all(out[k] is not None and ROC[k][0] <= out[k] <= ROC[k][1] for k in SYSMON)
    out["t"] = time.time()
    return out


def safe_conditions(t: bb.Transport) -> dict:
    """read_conditions that records a failure instead of stopping the session (the start sample can be taken before the register block answers)."""
    try:
        return read_conditions(t)
    except Exception as e:  # noqa: BLE001 - recorded, and roc_ok is then false
        return {"error": f"{type(e).__name__}: {e}", "inside_roc": False}


def gt_buffers(t: bb.Transport) -> dict:
    v = t.rd(0x020)
    return {"txbuf": v & 3, "rxbuf": (v >> 2) & 7, "txbuf_seen": (v >> 4) & 3, "rxbuf_seen": (v >> 6) & 7}


def set_ppm(t: bb.Transport, step: int, en: bool, sel: bool) -> None:
    t.wr(0x01C, (step & 0x1F) | (0x20 if en else 0) | (0x40 if sel else 0))


def ppm_from_delta(delta: int) -> float:
    """Positive: the receive user clock runs faster than the core clock (the partner is faster than we are)."""
    return (delta - WINDOW_CLOCKS) / WINDOW_CLOCKS * 1e6


def measure_ppm(t: bb.Transport, windows: int = 2, timeout_s: float = 3.0) -> dict:
    """The receive clock against the core clock from the frequency counter: wait for `windows` new windows and return their ppm values. `stable` is true
    when they agree within 0.5 ppm (a window that spans a clock restart does not)."""
    def snap() -> tuple[int, int]:
        t.wr(0x018, 4)          # one snapshot: the window count and its delta belong together
        return t.rd(0x100 + 4 * bb.RX["f_win"]), t.rd(0x100 + 4 * bb.RX["f_delta"])
    t0 = time.time()
    start = snap()[0]
    seen: dict[int, int] = {}
    while time.time() - t0 < timeout_s and len(seen) < windows:
        n, dlt = snap()
        if n > start and n not in seen and n >= 2:        # window 1 after a core restart has no valid earlier sample
            seen[n] = dlt
        time.sleep(0.02)
    ppms = [ppm_from_delta(d) for d in seen.values()]
    return {"windows": len(ppms), "ppm": (sum(ppms) / len(ppms)) if ppms else None, "ppm_each": ppms,
            "stable": len(ppms) == windows and (max(ppms) - min(ppms)) < 0.5}


def link_ok(b: bb.Board) -> bool:
    s = b.status()
    return bool(s["tx_done"] and s["rx_done"] and s["pcs_lock"])


def relock(b: bb.Board, timeout_s: float = 5.0) -> bool:
    b.reset(all_=True)
    return b.wait(lambda s: s["tx_done"] and s["rx_done"] and s["pcs_lock"], timeout_s)


def calibrate(b: bb.Board, sels=(1,), steps=range(32), settle_s: float = 0.3) -> list[dict]:
    """Every (sel, step) with the controller enabled: the achieved ppm, the GT buffer status and whether the link stayed up. Step 0 with the controller off is
    the reference row. A setting that drops the link is recorded and the offset is put back to 0 before the next."""
    rows: list[dict] = []
    set_ppm(b.t, 0, False, False)
    time.sleep(settle_s)
    b.clear()
    rows.append({"en": 0, "sel": 0, "step": 0, **measure_ppm(b.t), "link": link_ok(b), **gt_buffers(b.t)})
    for sel in sels:
        for step in steps:
            set_ppm(b.t, step, True, bool(sel))
            time.sleep(settle_s)
            b.clear()
            m = measure_ppm(b.t)
            row = {"en": 1, "sel": sel, "step": step, "predicted_ppm": predicted_ppm(step), **m, "link": link_ok(b), **gt_buffers(b.t)}
            rows.append(row)
            if not row["link"]:
                set_ppm(b.t, 0, False, False)
                relock(b)
    set_ppm(b.t, 0, False, False)
    return rows


def choose_points(rows: list[dict], targets=(0.0, -183.1, -122.1, -61.0, 61.0, 122.1, 183.1), tol_ppm: float = 20.0) -> list[dict]:
    """For each target the usable calibrated setting (link kept, stable, no buffer error seen) with the measured ppm closest to it. A target with none within
    `tol_ppm` is reported unreachable with the nearest one found, never silently replaced."""
    good = [r for r in rows if r.get("link") and r.get("stable") and r["ppm"] is not None and r["txbuf_seen"] == 0 and r["rxbuf_seen"] == 0]
    out = []
    for tg in targets:
        best = min(good, key=lambda r: abs(r["ppm"] - tg), default=None)
        if best is not None and abs(best["ppm"] - tg) <= tol_ppm:
            out.append({"target_ppm": tg, "reachable": True, **best})
        else:
            out.append({"target_ppm": tg, "reachable": False, "nearest": best})
    return out


def expected_rates(ppm: float) -> dict:
    """What the rate matcher must do at a measured offset: a faster receive clock (ppm > 0) gives more blocks than the core takes, which are deleted idles;
    a slower one gives idles inserted. Per second, in the steady state (between frames: the counters can differ by the gaps in the traffic)."""
    per_s = abs(ppm) * 1e-6 * BLOCK_RATE
    return {"deletes_per_s": per_s if ppm > 0 else 0.0, "inserts_per_s": per_s if ppm < 0 else 0.0}


def dwell(b: bb.Board, seconds: float, *, interval_clocks: int = 20000, poll_s: float = 2.0, cond_every_s: float = 5.0) -> dict:
    """Armed feed frames for `seconds` of the core clock's own time (counted in frequency-counter windows, not the host's clock): each fires an order that
    loops back. Reads the counters, the GT buffers and the operating conditions throughout; judged by `judge_point`."""
    count = int(seconds * F_CORE_HZ / interval_clocks)
    b.clear()
    time.sleep(0.05)
    b.configure(arm=True, kind=1, count=count, interval=interval_clocks)
    w0 = b.t.rd(0x100 + 4 * bb.RX["f_win"])
    cond = [read_conditions(b.t)]
    tx0, rx0 = b.snapshot()
    b.run(0.0)
    t_start = time.time()
    last_cond = t_start
    tx, rx = tx0, rx0
    seen: dict[int, int] = {}
    while True:
        time.sleep(poll_s)
        tx, rx = b.snapshot()
        if rx["f_win"] >= 2:
            seen[rx["f_win"]] = rx["f_delta"]       # the offset DURING the dwell: every window completed in it
        if time.time() - last_cond >= cond_every_s:
            cond.append(read_conditions(b.t)); last_cond = time.time()
        if tx["n_order"] >= count and rx["fired"] >= count:
            break
        if time.time() - t_start > seconds * 2 + 30:
            break
    time.sleep(0.2)
    tx, rx = b.snapshot()
    cond.append(read_conditions(b.t))
    windows = rx["f_win"] - w0
    elapsed = windows * WINDOW_CLOCKS / F_CORE_HZ
    ppms = [ppm_from_delta(v) for k, v in seen.items() if k > w0 + 1]
    return {"ppm_dwell": (sum(ppms) / len(ppms)) if ppms else None, "ppm_dwell_spread": (max(ppms) - min(ppms)) if ppms else None, "orders_expected": count, "tx": tx, "rx": rx, "elapsed_s_by_windows": elapsed, "host_elapsed_s": time.time() - t_start,
            "conditions": cond, "gt_buffers": gt_buffers(b.t), "interval_clocks": interval_clocks}


SAFE_TX = ("poisoned", "dropped", "underrun", "late", "stale")
SAFE_RX = ("bad", "err", "toolong", "order_bad", "rm_ovf", "slip", "loss")


def judge_point(d: dict, ppm: float, rate_tol: float = 0.15) -> dict:
    """The acceptance for a ppm point: safety counters 0, orders sent = fired = content-checked ok = expected, no overflow in the elastic buffer, no GT buffer error,
    every operating-condition sample inside the windows, and the insert/delete rate within `rate_tol` of the one the measured ppm predicts (stated, not assumed)."""
    tx, rx = d["tx"], d["rx"]
    why: list[str] = []
    for k in SAFE_TX:
        if tx[k]:
            why.append(f"{k}={tx[k]}")
    for k in SAFE_RX:
        if rx[k]:
            why.append(f"{k}={rx[k]}")
    n = d["orders_expected"]
    if not (tx["n_order"] == rx["fired"] == rx["order_ok"] == n):
        why.append(f"orders sent {tx['n_order']} fired {rx['fired']} order_ok {rx['order_ok']} expected {n}")
    g = d["gt_buffers"]
    if g["txbuf_seen"] or g["rxbuf_seen"]:
        why.append(f"GT buffer status seen {g}")
    outside = [c for c in d["conditions"] if not c["inside_roc"]]
    if outside:
        why.append(f"operating conditions outside the window in {len(outside)} samples")
    el = d["elapsed_s_by_windows"]
    exp = expected_rates(ppm)
    meas = {"deletes_per_s": rx["rm_del"] / el if el else None, "inserts_per_s": rx["rm_ins"] / el if el else None}
    rate_ok = None
    if el and abs(ppm) >= 5:
        key = "deletes_per_s" if ppm > 0 else "inserts_per_s"
        rate_ok = abs(meas[key] - exp[key]) <= rate_tol * exp[key]
        if not rate_ok:
            why.append(f"{key} measured {meas[key]:.0f} expected {exp[key]:.0f}")
    return {"ok": not why, "failing": why, "expected_rates": exp, "measured_rates": meas, "rate_matches_prediction": rate_ok,
            "blocks_in_minus_out": rx["rm_wr"] - (rx["rm_out"] - rx["rm_ins"] + rx["rm_del"] + rx["rm_drain"])}


def run_ppm_session(t: bb.Transport, lock_text: str, out_dir: Path, *, dwell_s: float = 20.0, restarts: int = 20, targets=(0.0, -183.1, -122.1, -61.0, 61.0, 122.1, 183.1),
                    sels=(1,), steps=range(32)) -> dict:
    """The whole ppm session on a board whose laser polarity and link bring-up have already passed (the caller, `run_96c`, does steps 1 to 3 of the stage-3
    sequence first through b96_bench.run_all's pieces). Refuses without the lock text."""
    if not lock_text.startswith("96C:"):
        raise RuntimeError("take _handoff/board.lock with a text starting '96C:' first, and pass that text")
    b = bb.Board(t)
    res: dict = {"lock": lock_text, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "dwell_s": dwell_s}
    assert b.id() == 0x96A00001, "wrong design loaded"
    res["conditions_start"] = read_conditions(t)
    cal = calibrate(b, sels=sels, steps=steps)
    res["calibration"] = cal
    res["points"] = []
    for pt in choose_points(cal, targets):
        rec: dict = {"target_ppm": pt["target_ppm"], "reachable": pt["reachable"]}
        if not pt["reachable"]:
            rec["nearest"] = pt["nearest"]
            res["points"].append(rec)
            continue
        set_ppm(t, pt["step"], bool(pt["en"]), bool(pt["sel"]))
        time.sleep(0.5)
        if not link_ok(b) and not relock(b):
            rec["failed"] = "link would not come up at this setting"
            res["points"].append(rec)
            set_ppm(t, 0, False, False)
            continue
        m = measure_ppm(t)
        rec.update({"setting": {k: pt[k] for k in ("en", "sel", "step")}, "ppm_calibrated": pt["ppm"], "ppm_now": m})
        if m["ppm"] is None:
            rec["failed"] = "no frequency reading"
            res["points"].append(rec)
            continue
        d = dwell(b, dwell_s)
        rec["dwell"] = d
        rec["verdict"] = judge_point(d, d["ppm_dwell"] if d.get("ppm_dwell") is not None else m["ppm"])
        rec["distribution"] = bb.restart_distribution(b, restarts)
        set_ppm(t, pt["step"], bool(pt["en"]), bool(pt["sel"]))          # a restart does not change the register, but state it
        rec["ppm_after"] = measure_ppm(t)
        res["points"].append(rec)
    set_ppm(t, 0, False, False)
    res["conditions_end"] = read_conditions(t)
    (out_dir / "ppm_session.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def summary(res: dict) -> dict:
    pts = []
    for p in res["points"]:
        v = p.get("verdict")
        d = p.get("distribution", {})
        pts.append({"target_ppm": p["target_ppm"], "reachable": p["reachable"], "ppm": (p.get("ppm_now") or {}).get("ppm"), "ok": (v or {}).get("ok", False),
                    "failing": (v or {}).get("failing", p.get("failed")), "safety_restarts_ok": (d.get("safety") or {}).get("ok"),
                    "E_min_median": (d.get("E_min_per_link") or {}).get("median"), "L_min_median": (d.get("L_min_per_link") or {}).get("median")})
    return {"points": pts}


def main() -> None:
    """Board session for one bitstream: the stage-3 loopback sequence at 0 ppm (b96_bench.run_all: polarity, link, 100 restarts, E, L, safety), then, if --ppm
    is given, the ppm calibration and sweep. The laser is left off."""
    import argparse

    from flow import version_pin
    ap = argparse.ArgumentParser(description="Brief 96C board session (rate matching, ppm sweep). Laser polarity first; the laser is left off at the end.")
    ap.add_argument("--serial", required=True)
    ap.add_argument("--lock-text", required=True, help="the text in _handoff/board.lock (must start '96C:')")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--loop-m", type=float, required=True)
    ap.add_argument("--restarts", type=int, default=100)
    ap.add_argument("--ppm", action="store_true", help="also run the ppm calibration and sweep (needs a ppm_* bitstream)")
    ap.add_argument("--dwell-s", type=float, default=20.0)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[3]
    t = bb.VivadoTcl(repo, a.serial, version_pin.vivado_path())
    out: dict = {}
    try:
        out["conditions_start"] = safe_conditions(t)
        res = bb.run_all(t, a.lock_text, a.out, cable_loop_m=a.loop_m, n_restarts=a.restarts)
        sf = res.get("safety", {})
        out.update({"id": res.get("id"), "polarity_ok": res.get("polarity_ok"), "link_up": res.get("link_up"), "safety_ok": sf.get("ok", False),
                    "safety_failing": sf.get("failing_counters", []) or sf.get("reasons", [])})
        if a.ppm and res.get("link_up"):
            b = bb.Board(t)
            b.laser(True)
            if relock(b):
                ps = run_ppm_session(t, a.lock_text, a.out, dwell_s=a.dwell_s)
                out["ppm"] = summary(ps)
            else:
                out["ppm"] = {"stopped": "link did not come back for the ppm session"}
            bb.Board(t).laser(False)
        out["conditions_end"] = safe_conditions(t)
        out["roc_ok"] = all(c.get("inside_roc") for c in (out["conditions_start"], out["conditions_end"]))
    finally:
        t.close()
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
