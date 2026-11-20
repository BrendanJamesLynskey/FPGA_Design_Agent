"""Brief 96F1 board driver: build rm_gp_bypass (both GT elastic buffers bypassed) on the KR260 optical loopback. NOT YET RUN ON A BOARD.

One session, in this order (the lock text must start '96F:'; SRAM only; the laser is on for the measurement and off on every path out):
  1. the stage-3 loopback sequence of every earlier build (b96_bench.run_all: polarity, link, 100 receive-datapath restarts, E, L, D, safety counters), unchanged;
  2. `full_restarts`: N resets of the WHOLE GT (GT_RESET bit 0), which re-run both bypass controllers (the receive restarts of step 1 only re-run the RX one): the time to link-up, the controllers'
     done and error bits (GT_BUF bits 15:10, rm_gp_bypass only), the alignment timeout-retry counts and gave-up flags (GT_BUF bits 29:16, brief 96F1b: a gave-up flag is a FAIL), and the operating conditions;
  3. `verdict`: the PRE-REGISTERED decision of results/b96f1/preregistration.md applied to the numbers (E against the 96E rm_gp board run, 21.0 clocks), printed with the reason.
Nothing is tuned: a result outside the prediction is reported as it is."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from designs.b96_kr260_10g.host import b96_bench as bb
from designs.b96_kr260_10g.host import b96c_ppm as pp

#: The 96E board run of build rm_gp (results/b96e/hw/20261119_231251/rm_gp/stage3.json): medians of the per-link minima, clocks of 6.2061 ns.
REF_E, REF_L, REF_D = 21.0, 54.0, 12.0
#: The fibre lead of that run: one-way 0.8324 ns (a 0.17 m lead). E and L carry the lead's delay, so a different lead moves the reference by the difference (E once, L twice).
REF_FIBRE_NS = 0.8324425559765083
CLOCK_NS = 6.2061
#: Predicted E fall from bypassing both GT buffers (results/b96f/latency_prediction.json: third-party GTY figures, UNCONFIRMED for this GTH): 2.9 to 4.5 clocks.
PRED_DROP = (2.9, 4.5)
FAIL_DROP = 1.5          # fail if E does not fall by at least this
GT_BUF = 0x020
BP_BITS = dict(tx_bp_done=10, rx_bp_done=11, tx_bp_err_seen=12, rx_bp_err_seen=13, tx_bp_err=14, rx_bp_err=15)
#: Brief 96F1b (build rm_gp_bypass with gt_bp_ctl): the alignment timeout and retry fields of GT_BUF. Retry counts are 4-bit fields; the rest are single bits.
BP_GAVE_BITS = dict(tx_gave_up=24, rx_gave_up=25, tx_gave_up_seen=26, rx_gave_up_seen=27, tx_retried_seen=28, rx_retried_seen=29)
BP_RETRY_FIELDS = dict(tx_retries=16, rx_retries=20)


def bp_status(t: bb.Transport) -> dict:
    """The controllers' done and error bits (GT_BUF 15:10) and, since brief 96F1b, the retry counts and the gave-up flags (GT_BUF 29:16), as a flat dict."""
    v = t.rd(GT_BUF)
    out = {k: (v >> b) & 1 for k, b in BP_BITS.items()}
    out.update({k: (v >> b) & 1 for k, b in BP_GAVE_BITS.items()})
    out.update({k: (v >> b) & 0xF for k, b in BP_RETRY_FIELDS.items()})
    return out


def gave_up(st: dict) -> bool:
    """True when either controller has given up (now or seen since the last clear): a FAIL in the pre-registration (amendment 2026-11-20)."""
    return bool(st.get("tx_gave_up") or st.get("rx_gave_up") or st.get("tx_gave_up_seen") or st.get("rx_gave_up_seen"))


def features(t: bb.Transport) -> dict:
    v = t.rd(0x008)
    return {"raw": f"{v:08x}", "gt_bypass": (v >> 6) & 1, "rate_match": (v >> 3) & 1, "rm_own": (v >> 5) & 1}


def full_restarts(b: bb.Board, n: int = 20, timeout_s: float = 5.0) -> dict:
    """n resets of the whole GT. After each: wait for tx_done, rx_done and PCS block lock; record the host-clock time to link-up (poll interval 50 ms: coarse, a pass or fail figure, not a latency),
    the controllers' done and error bits at link-up, and the operating conditions every 5th restart. A restart whose link does not come up is counted and the bits read anyway."""
    rows, fails = [], 0
    for i in range(n):
        b.reset(all_=True)
        t0 = time.time()
        ok = b.wait(lambda s: s["tx_done"] and s["rx_done"] and s["pcs_lock"], timeout_s)
        dt = time.time() - t0
        row = {"i": i, "link": ok, "s": round(dt, 3), **bp_status(b.t), **{"gt": b.status()}}
        if i % 5 == 0:
            row["conditions"] = pp.safe_conditions(b.t)
        if not ok:
            fails += 1
        rows.append(row)
    good = [r for r in rows if r["link"]]
    return {"n": n, "failed_to_lock": fails, "rows": rows,
            "controllers_done_at_link_up": all(r["tx_bp_done"] and r["rx_bp_done"] for r in good) if good else None,
            "controller_error_seen": any(r["tx_bp_err_seen"] or r["rx_bp_err_seen"] or r["tx_bp_err"] or r["rx_bp_err"] for r in rows),
            # brief 96F1b: alignment timeout and retry (30 ms TX, 130 ms RX, 3 retries): gave-up is a FAIL; retries are recorded per restart and counted here, not judged
            "gave_up_seen": any(gave_up(r) for r in rows),
            "restarts_with_retries": sum(1 for r in rows if r["tx_retries"] or r["rx_retries"]),
            "max_tx_retries": max((r["tx_retries"] for r in rows), default=0), "max_rx_retries": max((r["rx_retries"] for r in rows), default=0),
            "retried_seen": any(r["tx_retried_seen"] or r["rx_retried_seen"] for r in rows),
            "time_to_link_s": bb.summarise([int(r["s"] * 1000) for r in good]) if good else {"n": 0}}      # milliseconds


def verdict(stage3: dict, restarts: dict | None, roc_ok: bool | None, feat: dict | None, bp_after_stage3: dict | None = None) -> dict:
    """The pre-registered decision (results/b96f1/preregistration.md, section 'Decision'). Returns {'result': 'PASS'|'WARN'|'FAIL'|'ABORT', 'reasons': [...], numbers}.
    ABORT: the link did not lock, the wrong design/build was loaded, or alignment never completed. FAIL: any safety counter, a failed lock, an operating-condition excursion,
    a controller error, a controller that gave up after its alignment timeouts (amendment 2026-11-20, before any board time), or E not falling by at least FAIL_DROP. WARN: E fell, but outside the predicted 2.9 to 4.5 clocks. PASS: all of it, E fall inside the prediction."""
    why: list[str] = []
    r = stage3.get("restarts", {}) or {}
    sf = stage3.get("safety", {}) or {}
    e = (r.get("E_min_per_link") or {}).get("median")
    l = (r.get("L_min_per_link") or {}).get("median")
    out = {"E_median": e, "L_median": l, "ref_E": REF_E, "ref_L": REF_L}
    if feat is not None and not feat.get("gt_bypass"):
        return {"result": "ABORT", "reasons": ["FEATURES bit 6 (GT_BYPASS) is 0: the loaded bitstream is not build rm_gp_bypass"], **out}
    if bp_after_stage3 is not None and gave_up(bp_after_stage3):          # amendment 2026-11-20: gave-up is a FAIL, also when it is why the link did not come up
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
            fail.append("a buffer-bypass controller gave up after its alignment timeouts (30 ms TX, 130 ms RX, 3 retries) in a full GT restart")
    dfib = (stage3.get("fibre_one_way_ns", REF_FIBRE_NS) - REF_FIBRE_NS) / CLOCK_NS         # clocks the lead adds to E against the 96E run
    ref_e, ref_l = REF_E + dfib, REF_L + 2 * dfib
    drop = ref_e - e
    out.update({"ref_E_adjusted_for_lead": ref_e, "E_drop_clocks": drop, "L_drop_clocks": ref_l - l, "D_from_medians": l - 2 * e, "ref_D": REF_D})
    if drop < FAIL_DROP:
        fail.append(f"E fell by {drop:.1f} clocks, less than the {FAIL_DROP} clocks the pre-registration requires: the bypass did not take effect or the GT figures are wrong; report, do not tune")
    if fail:
        return {"result": "FAIL", "reasons": fail, **out}
    if not (PRED_DROP[0] <= drop <= PRED_DROP[1]):
        return {"result": "WARN", "reasons": [f"E fell by {drop:.1f} clocks, outside the predicted {PRED_DROP[0]} to {PRED_DROP[1]}"], **out}
    return {"result": "PASS", "reasons": [f"E fell by {drop:.1f} clocks (predicted {PRED_DROP[0]} to {PRED_DROP[1]})"], **out}


def main() -> None:
    """Board session for build rm_gp_bypass: stage-3 loopback, N full GT restarts, the verdict. The laser is left off."""
    import argparse

    from flow import version_pin
    ap = argparse.ArgumentParser(description="Brief 96F1 board session (GT buffer bypass). Laser polarity first; the laser is left off at the end.")
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
        out["bypass_after_stage3"] = bp_status(t)           # gave-up and retry fields after the 100 receive-datapath restarts (brief 96F1b); the flags that the verdict reads
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
