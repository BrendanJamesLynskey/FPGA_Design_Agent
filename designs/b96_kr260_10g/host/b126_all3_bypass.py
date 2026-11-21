"""Brief 126 board driver: build lat_all3_bypass (the default receive path, 97C's three latency cuts, both GT elastic buffers bypassed) on the KR260 optical loopback. NOT YET RUN ON A BOARD.

The session is brief 96F1's (host/b96f1_bypass.py, which this module imports from: the stage-3 loopback sequence of b96_bench.run_all, N resets of the whole GT with the controllers' done, error,
retry and gave-up fields, the operating conditions), with a different reference and a different pre-registered verdict (results/b126/preregistration.md):
  reference = the 97C board run of lat_all3 (GT buffers on): E 20.0, L 46.0, D 6.0, tick-to-trade (L - E) 26 clocks;
  prediction = the GT bypass's measured effect (96F1b board run: E -4.0, D 0) applied to it: E 16.0, L 38.0, D 6.0, L - E 22.
The lock text must start '96F:' (b96_bench.run_all accepts it, and take_heavy_slot.sh's board-session reservation does). SRAM only; the laser is on for the measurement and off on every path out.
Nothing is tuned: a result outside the prediction is reported as it is."""

from __future__ import annotations

import json
from pathlib import Path

from designs.b96_kr260_10g.host import b96_bench as bb
from designs.b96_kr260_10g.host import b96c_ppm as pp
from designs.b96_kr260_10g.host.b96f1_bypass import bp_status, features, full_restarts, gave_up

#: The 97C board run of lat_all3 (results/b97c/hw/20261118_194221/all3/stage3.json): medians of the per-link minima over 100 restarts, clocks of 6.2061 ns.
REF_E, REF_L, REF_D = 20.0, 46.0, 6.0
#: The fibre lead of that run: one-way 0.8324 ns (0.17 m). A different lead moves E once and L twice by the difference.
REF_FIBRE_NS = 0.8324425559765083
CLOCK_NS = 6.2061
#: The measured effect of bypassing both GT buffers (96F1b board run, results/b96f1/hw/20261120_215255/rm_gp_bypass against results/b96e/hw/20261119_231251/rm_gp): E fell by 4.0 clocks, D did not change.
MEASURED_E_DROP = 4.0
#: Pre-registered bands (results/b126/preregistration.md): E falls by 3.4 to 4.4 clocks (AR 68177's reading, which the 96F1b measurement of 4.0 sits inside); D stays within 1 clock; the build must beat lat_all3's own tick-to-trade.
PRED_DROP = (3.4, 4.4)
PRED_D = (5.0, 7.0)
FAIL_DROP = 1.5            # fail if E does not fall by at least this
T2T_REF = REF_L - REF_E    # 26 clocks, lat_all3 with the GT buffers on


def verdict(stage3: dict, restarts: dict | None, roc_ok: bool | None, feat: dict | None, bp_after_stage3: dict | None = None) -> dict:
    """The pre-registered decision. ABORT: the loaded build is not lat_all3_bypass (FEATURES bit 6 = 0, or bit 3 = 1: a rate-matched build), the link did not lock, alignment never completed, no E or L.
    FAIL: any safety counter, a failed lock, an operating-condition excursion, a controller error, a controller that gave up, a link up with a controller not done, E not falling by FAIL_DROP,
    or a tick-to-trade (L - E) that is not below lat_all3's 26 clocks. WARN: E falls by less than 3.4 or more than 4.4, or D leaves 5 to 7. PASS: all of it inside."""
    r = stage3.get("restarts", {}) or {}
    sf = stage3.get("safety", {}) or {}
    e = (r.get("E_min_per_link") or {}).get("median")
    l = (r.get("L_min_per_link") or {}).get("median")
    out = {"E_median": e, "L_median": l, "ref_E": REF_E, "ref_L": REF_L}
    if feat is not None and not feat.get("gt_bypass"):
        return {"result": "ABORT", "reasons": ["FEATURES bit 6 (GT_BYPASS) is 0: the loaded bitstream has the GT buffers on"], **out}
    if feat is not None and feat.get("rate_match"):
        return {"result": "ABORT", "reasons": ["FEATURES bit 3 (RATE_MATCH) is 1: the loaded bitstream is a rate-matched build, not lat_all3_bypass"], **out}
    if bp_after_stage3 is not None and gave_up(bp_after_stage3):
        return {"result": "FAIL", "reasons": ["a buffer-bypass controller gave up after its alignment timeouts (30 ms TX, 130 ms RX, 3 retries)"], **out}
    if not stage3.get("link_up"):
        return {"result": "ABORT", "reasons": ["the link did not come up (or alignment never completed)"], **out}
    if e is None or l is None:
        return {"result": "ABORT", "reasons": ["no E or L reading"], **out}
    fail: list[str] = []
    if r.get("failed_to_lock"):
        fail.append(f"{r['failed_to_lock']} of {r.get('restarts')} receive restarts did not lock")
    if not sf.get("ok"):
        fail.append(f"safety counters: {sf.get('failing_counters') or sf.get('reasons')}")
    if roc_ok is False:
        fail.append("operating conditions outside the recommended window (results void until repeated inside it)")
    if restarts is not None:
        if restarts.get("failed_to_lock"):
            fail.append(f"{restarts['failed_to_lock']} of {restarts['n']} full GT restarts did not lock")
        if restarts.get("controller_error_seen"):
            fail.append("a buffer-bypass controller flagged an error (PHALIGNDONE not high)")
        if restarts.get("controllers_done_at_link_up") is False:
            fail.append("link up with a controller not done (the gate failed)")
        if restarts.get("gave_up_seen"):
            fail.append("a buffer-bypass controller gave up after its alignment timeouts in a full GT restart")
    dfib = (stage3.get("fibre_one_way_ns", REF_FIBRE_NS) - REF_FIBRE_NS) / CLOCK_NS         # clocks the lead adds to E against the 97C run
    ref_e, ref_l = REF_E + dfib, REF_L + 2 * dfib
    drop = ref_e - e
    d = l - 2 * e
    t2t = l - e
    out.update({"ref_E_adjusted_for_lead": ref_e, "E_drop_clocks": drop, "L_drop_clocks": ref_l - l, "D_from_medians": d, "ref_D": REF_D, "T2T_clocks_L_minus_E": t2t,
                "T2T_ns_L_minus_E_minus_fibre": t2t * CLOCK_NS - stage3.get("fibre_one_way_ns", REF_FIBRE_NS), "T2T_ref_clocks": T2T_REF})
    if drop < FAIL_DROP:
        fail.append(f"E fell by {drop:.1f} clocks, less than the {FAIL_DROP} clocks the pre-registration requires: the bypass did not take effect; report, do not tune")
    if t2t >= T2T_REF + dfib:
        fail.append(f"tick-to-trade (L - E) {t2t:.1f} clocks is not below lat_all3's {T2T_REF:.0f}: the combination is not faster than its parts")
    if fail:
        return {"result": "FAIL", "reasons": fail, **out}
    warn: list[str] = []
    if not (PRED_DROP[0] <= drop <= PRED_DROP[1]):
        warn.append(f"E fell by {drop:.1f} clocks, outside the predicted {PRED_DROP[0]} to {PRED_DROP[1]}")
    if not (PRED_D[0] <= d <= PRED_D[1]):
        warn.append(f"D = L - 2E is {d:.1f} clocks, outside the predicted {PRED_D[0]} to {PRED_D[1]} (the cuts or the crossing moved)")
    if warn:
        return {"result": "WARN", "reasons": warn, **out}
    return {"result": "PASS", "reasons": [f"E fell by {drop:.1f} clocks (predicted {PRED_DROP[0]} to {PRED_DROP[1]}), D {d:.1f} (predicted {PRED_D[0]} to {PRED_D[1]}), tick-to-trade {t2t:.1f} clocks (lat_all3: {T2T_REF:.0f})"], **out}


def main() -> None:
    """Board session for build lat_all3_bypass: stage-3 loopback, N full GT restarts, the verdict. The laser is left off."""
    import argparse

    from flow import version_pin
    ap = argparse.ArgumentParser(description="Brief 126 board session (97C cuts + GT buffer bypass). Laser polarity first; the laser is left off at the end.")
    ap.add_argument("--serial", required=True)
    ap.add_argument("--lock-text", required=True, help="the text in _handoff/board.lock (must start '96F:')")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--loop-m", type=float, required=True)
    ap.add_argument("--restarts", type=int, default=100)
    ap.add_argument("--full-restarts", type=int, default=20)
    a = ap.parse_args()
    if not a.lock_text.startswith("96F:"):
        raise SystemExit("the lock text must start '96F:'")
    a.out.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[3]
    t = bb.VivadoTcl(repo, a.serial, version_pin.vivado_path())
    out: dict = {}
    try:
        out["conditions_start"] = pp.safe_conditions(t)
        out["features"] = features(t)
        res = bb.run_all(t, a.lock_text, a.out, cable_loop_m=a.loop_m, n_restarts=a.restarts)
        sf = res.get("safety", {})
        out.update({"id": res.get("id"), "polarity_ok": res.get("polarity_ok"), "link_up": res.get("link_up"), "safety_ok": sf.get("ok", False),
                    "safety_failing": sf.get("failing_counters", []) or sf.get("reasons", [])})
        out["bypass_after_stage3"] = bp_status(t)
        fr = None
        if res.get("link_up"):
            b = bb.Board(t)
            b.laser(True)
            try:
                fr = full_restarts(b, a.full_restarts)
            finally:
                b.laser(False)
            (a.out / "full_restarts.json").write_text(json.dumps(fr, indent=1, default=str))
            out["full_restarts"] = {k: v for k, v in fr.items() if k != "rows"}
        out["conditions_end"] = pp.safe_conditions(t)
        out["roc_ok"] = all(c.get("inside_roc") for c in (out["conditions_start"], out["conditions_end"]))
        out["verdict"] = verdict(res, fr, out["roc_ok"], out["features"], out["bypass_after_stage3"])
    finally:
        try:
            bb.Board(t).laser(False)
        except Exception:  # noqa: BLE001 - the laser is also off after run_all; the board may be gone
            pass
        t.close()
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
