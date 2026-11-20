"""The scan itself: the grid, the adaptive prescale ladder, the operating conditions around it, and the capture it writes.

Per point: rungs of increasing ES_PRESCALE (p0, p0+3, ... up to the prescale that reaches the target BER); a rung ends when the sample counter or the error counter
saturates (the hardware's rule); the ladder stops early once a rung saw `min_errors` errors (the point's BER is then resolved and clean-point time is not spent on it).
The point's BER is that of its LAST rung. Bits examined = samp x 2^(1+pre) x 32. A point whose deepest rung saw no error reports "BER below 3/bits (95 %)", never "0".
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from flow.eyescan import capture as cap
from flow.eyescan import hw as H

DATA_WIDTH = 32
LINE_RATE_GBPS = 10.3125
LADDER_STEP = 3
#: A scan stops (laser off by the caller, DRP words restored) after this many CONSECUTIVE points whose measurement timed out or counted zero samples. A working eye scan never times
#: out: a closed point saturates the error counter and ends at once, an open one saturates the sample counter. Five in a row is a fault, not noise; one rare timeout (a lost lock)
#: is tolerated and recorded. The self-test (centre point, prescale 0) is stricter: ONE failure stops the scan before the grid starts.
K_CONSECUTIVE_NO_DATA = 5


@dataclass
class ScanConfig:
    target_ber: float = 1e-9          # deepest BER a point is run to (when it shows no errors)
    min_errors: int = 10              # a rung with at least this many errors ends a point's ladder
    p0: int = 0                       # first prescale
    hstep: int = 2                    # horizontal step in counts (1/64 UI at 10.3125 Gb/s with RXOUT_DIV 1: 2 counts = 1/32 UI)
    vstep: int = 8                    # vertical step in codes
    vmax: int = 120                   # vertical range +-vmax codes
    vs_range: int = 0                 # RX_EYESCAN_VS_RANGE (0: 1.5 mV per code)
    equaliser: str = "keep"           # "lpm", "dfe" or "keep" (leave the equaliser as it is)
    line_rate_gbps: float = LINE_RATE_GBPS
    label: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


P_MAX = 15            # longest single rung: 65535 x 2^16 x 32 bits = 13.3 s at 10.3125 Gb/s, inside the 32-bit timeout register (42.9 s at 100 MHz)


def ladder(p0: int, target_ber: float, step: int = LADDER_STEP, width: int = DATA_WIDTH) -> list[int]:
    """Prescale rungs from p0 up to the first one whose saturated run examines at least 3/target_ber bits (the zero-error 95 % bound at the target). Beyond P_MAX the last
    rung is repeated (the repeats at one prescale are pooled by capture.point_stats)."""
    if not 0 < target_ber < 1:
        raise ValueError("target BER must be in (0, 1)")
    need = cap.ZERO_ERR_FACTOR / target_ber
    p_top = max(p0, min(P_MAX, math.ceil(math.log2(need / (cap.ES_COUNT_MAX * width)) - 1)))
    rungs = list(range(p0, p_top, step)) + [p_top]
    per_run = cap.ES_COUNT_MAX * (1 << (1 + p_top)) * width
    reps = max(1, math.ceil(need / per_run))
    return rungs + [p_top] * (reps - 1)


def grid(cfg: ScanConfig, counts_half_ui: int) -> tuple[list[int], list[int]]:
    hs = list(range(-counts_half_ui, counts_half_ui + 1, cfg.hstep))
    if 0 not in hs:
        hs = sorted(set(hs) | {0})
    vm = cfg.vmax - cfg.vmax % cfg.vstep
    vs = list(range(-vm, vm + 1, cfg.vstep))
    return hs, vs


def estimate_seconds(cfg: ScanConfig, counts_half_ui: int, eye_fraction: float = 0.35, n_ut: int = 1, per_op_s: float = 0.03, ops_per_point: float = 6.0) -> dict[str, float]:
    """Rough planning figures: the hardware time of the clean points plus the host's JTAG overhead. A planning aid, not a measurement."""
    hs, vs = grid(cfg, counts_half_ui)
    n = len(hs) * len(vs) * n_ut
    rungs = ladder(cfg.p0, cfg.target_ber)
    t_clean = sum(H.rung_seconds(p, DATA_WIDTH, cfg.line_rate_gbps) for p in rungs)
    return {"points": n, "clean_point_s": t_clean, "hardware_s": n * eye_fraction * t_clean, "host_overhead_s": n * ops_per_point * per_op_s * (1 + 0.5 * (len(rungs) - 1) * eye_fraction)}


def measure_point(hw: H.EyeHW, h: int, v: int, ut: int, cfg: ScanConfig, rungs_p: list[int]) -> dict[str, Any]:
    rungs = []
    pooled_err = 0
    for pre in rungs_p:
        t_rung = H.rung_seconds(pre, DATA_WIDTH, cfg.line_rate_gbps)
        r = hw.point(h, v, ut, cfg.vs_range, pre, timeout_s=2.0 * t_rung + 0.5)
        rungs.append({k: r[k] for k in ("pre", "err", "samp", "tmo", "status")})
        if r["drp_tmo"]:
            raise H.EyeScanError(f"DRP access timed out at h={h} v={v} (the sequencer saw no DRDY)")
        if r["tmo"]:
            break
        pooled_err = pooled_err + r["err"] if len(rungs) > 1 and rungs[-2]["pre"] == pre else r["err"]
        if pooled_err >= cfg.min_errors:
            break
    return {"h": h, "v": v, "ut": ut, "rungs": rungs}


def point_no_data(p: dict[str, Any]) -> bool:
    """True if the point's measurement timed out or counted no samples on any rung (no data, as opposed to no errors)."""
    return any(r["tmo"] or r["samp"] == 0 for r in p["rungs"])


_STATE = {0b0001: "WAIT (run not taken)", 0b0010: "RESET", 0b0110: "COUNT (the sample counter is not advancing: check ES_QUAL_MASK / ES_QUALIFIER, all ten words)", 0b0101: "END",
          0b1010: "ARMED", 0b1001: "READ"}


def selftest(hw: H.EyeHW, cfg: ScanConfig) -> dict[str, Any]:
    """Choose the eye-scan 4T clock phase (hw.choose_clk_phase: the eye centre must be error-free), then one point at the eye centre (h = 0, v = 0, ut 0),
    prescale 0, before the grid: it must end and count samples. Raises NoDataError otherwise."""
    phase = hw.choose_clk_phase()
    p = measure_point(hw, 0, 0, 0, cfg, [0])
    r = p["rungs"][-1]
    res = {"h": 0, "v": 0, "ut": 0, "pre": 0, "err": r["err"], "samp": r["samp"], "tmo": r["tmo"], "es_control_status": f"{r['status']:#06b}", "ok": not point_no_data(p), "clk_phase": phase}
    if not res["ok"]:
        raise H.NoDataError(f"NO DATA: the self-test point (eye centre, prescale 0) {'timed out' if r['tmo'] else 'counted no samples'} "
                            f"(es_control_status {r['status']:#06b} = {_STATE.get(r['status'], 'unknown state')}); no scan was run")
    return res


def run_scan(hw: H.EyeHW, cfg: ScanConfig, *, conditions: Callable[[], dict[str, Any]] | None = None, link_ok: Callable[[], bool] | None = None,
             gt_info: Callable[[], dict[str, Any]] | None = None, progress: Callable[[dict[str, Any], int, int], None] | None = None,
             design: dict[str, Any] | None = None, synthetic: bool = False, driver: str = "flow.eyescan") -> dict[str, Any]:
    """One scan, start to finish, written as a capture dict. The DRP words the scan touches are saved first and restored at the end, also on an error
    (the capture then says so in `restore`); the equaliser and the TX drive are left as found."""
    t_start = time.time()
    hw.n_ops = 0
    cond0 = conditions() if conditions else {}
    link0 = link_ok() if link_ok else None
    eq_before = hw.equaliser()
    drive_before = hw.get_tx_drive()
    changed_eq = cfg.equaliser in ("lpm", "dfe") and (cfg.equaliser.upper() != eq_before)
    points: list[dict[str, Any]] = []
    link_rows: list[bool] = []
    err_text = None
    saved: dict[int, int] = {}
    selftest_res: dict[str, Any] = {}
    n_no_data = 0
    restore: dict[str, Any] = {"ok": False, "reason": "not reached"}
    geo: dict[str, Any] = {}
    uts = [0]
    hs: list[int] = []
    vs: list[int] = []
    rungs_p: list[int] = []
    eq = eq_before
    try:
        if changed_eq:
            hw.set_equaliser(cfg.equaliser == "lpm")
        eq = hw.equaliser()
        geo = hw.geometry()
        uts = [0, 1] if eq == "DFE" else [0]
        hs, vs = grid(cfg, geo["counts_half_ui"])
        rungs_p = ladder(cfg.p0, cfg.target_ber)
        try:
            saved = hw.setup()
            total = len(hs) * len(vs) * len(uts)
            try:
                selftest_res = selftest(hw, cfg)
            except H.NoDataError:
                selftest_res = {"ok": False}
                raise
            consec = 0
            for v in vs:
                for h in hs:
                    for ut in uts:
                        p = measure_point(hw, h, v, ut, cfg, rungs_p)
                        points.append(p)
                        if point_no_data(p):
                            n_no_data += 1
                            consec += 1
                            if consec >= K_CONSECUTIVE_NO_DATA:
                                raise H.NoDataError(f"NO DATA: {consec} consecutive points timed out or counted no samples (the last at h={h}, v={v}); {n_no_data}/{len(points)} points so far; scan stopped early")
                        else:
                            consec = 0
                        if progress:
                            progress(p, len(points), total)
                if link_ok:
                    link_rows.append(bool(link_ok()))
        except Exception as e:  # noqa: BLE001 - recorded in the capture; the restores below still run
            err_text = f"{type(e).__name__}: {e}"
        finally:
            try:
                restore = hw.restore()
            except Exception as e2:  # noqa: BLE001
                restore = {"ok": False, "reason": f"restore raised {type(e2).__name__}: {e2}"}
    except Exception as e:  # noqa: BLE001
        err_text = err_text or f"{type(e).__name__}: {e}"
    finally:
        if changed_eq:
            try:
                hw.set_equaliser(eq_before == "LPM")
            except Exception as e3:  # noqa: BLE001
                err_text = (err_text + "; " if err_text else "") + f"equaliser not restored: {type(e3).__name__}: {e3}"
    cond1 = conditions() if conditions else {}
    link1 = link_ok() if link_ok else None
    t_end = time.time()
    out: dict[str, Any] = {
        "schema": cap.SCHEMA, "kind": "rx_eye_scan", "created": cap.now(), "label": cfg.label, "synthetic": bool(synthetic),
        "instrument": {"kind": "gth_eye_scan", "driver": driver, "mock": bool(synthetic),
                       "settings": {"hstep": cfg.hstep, "vstep": cfg.vstep, "vmax": cfg.vmax}},
        "design": design or {}, "build": {},
        "settings": {"line_rate_gbps": cfg.line_rate_gbps, "equaliser": eq, "equaliser_before": eq_before, "data_width": DATA_WIDTH, "rxout_div": geo.get("rxout_div"),
                     "counts_half_ui": geo.get("counts_half_ui"), "ui_per_count": geo.get("ui_per_count", 0.0), "vs_range": cfg.vs_range, "mv_per_code": cap.MV_PER_CODE[cfg.vs_range],
                     "target_ber": cfg.target_ber, "min_errors": cfg.min_errors, "prescale_rungs": rungs_p, "hstep": cfg.hstep, "vstep": cfg.vstep, "vmax": cfg.vmax,
                     "ut_signs": uts, "expected_points": len(hs) * len(vs) * len(uts), "tx": {**hw.get_tx_drive(), "before": drive_before}, **cfg.extra},
        "attributes_before": {f"{a:#05x}": v for a, v in saved.items()},
        "restore": restore, "link": {"before": link0, "after": link1, "rows_ok": link_rows, "ok_throughout": bool(link0 and link1 and all(link_rows))} if link_ok else {},
        "conditions": {"start": cond0, "end": cond1}, "points": points,
        "selftest": selftest_res,
        "run": {"seconds": round(t_end - t_start, 2), "register_ops": hw.n_ops, "points_done": len(points), "no_data_points": n_no_data, "error": err_text},
    }
    if gt_info:
        out["gt"] = gt_info()
    return out
