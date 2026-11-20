"""Brief 113 board driver: build rm_gp_ml (the ML decision stage in the 10G trading path) on the KR260 optical loopback. NOT YET RUN ON A BOARD.

One session, in this order (the lock text must start '113:'; SRAM only; the laser is on for the measurement and off on every path out):
  1. the stage-3 loopback sequence of every earlier build (b96_bench.run_all: polarity, link, 100 receive-datapath restarts, E, L, D, safety counters) with the stage in SHADOW mode (ML_CTRL = 0, the reset
     value): the rule decides alone, the model only counts. Its E, L and D are compared with the 96E run of build rm_gp (the same hardware without the stage);
  2. `sweep`: K repeats of one feed run of N frames each, in shadow mode and in veto mode, each after a state reset (ML_CTRL bit 1), with the stage's counters (MLV0 to MLV10) compared with the Python twin
     (rm_gp_ml/model/twin.py) on the same frames: the model's classes on the hardware, bit-exact on a synthetic stream;
  3. `verdict`: the PRE-REGISTERED decision of results/b113/preregistration.md applied to the numbers, printed with the reason.
Nothing is tuned: a result outside the prediction is reported as it is."""

from __future__ import annotations

import json
from pathlib import Path

from designs.b58a_trigger.model import benchfeed as bf
from designs.b96_kr260_10g.host import b96_bench as bb
from designs.b96_kr260_10g.host import b96c_ppm as pp
from designs.b96_kr260_10g.host.b96f1_bypass import CLOCK_NS, REF_D, REF_E, REF_FIBRE_NS, REF_L
from designs.b96_kr260_10g.rm_gp_ml.model.twin import Twin

ML_CTRL, ML_INST, ML_ID = 0x300, 0x304, 0x308
MLV_BASE = 0x310
MLV_NAMES = ["n_obs", "n_cls_down", "n_cls_flat", "n_cls_up", "n_dec", "n_veto", "n_would_veto", "n_late", "n_apply", "n_drop", "n_race"]
ID_VALUE = 0x01130001
#: pre-registered tolerances (results/b113/preregistration.md): E and L against the 96E rm_gp run, clocks of 6.2061 ns (the stamps have a resolution of one clock, medians of half a clock)
PASS_BAND, WARN_BAND = 1.0, 2.0
GEN_PRICE, GEN_INST, THR = 9950, 1, 9975          # the bench's generator frame (ADD ask 99.50, size 1, instrument 1) and the rule's threshold (the base design's reset values)


def predict(n_frames: int, veto: bool) -> dict:
    """The twin's counters for `n_frames` identical generator frames after a state reset (the stage tracks instrument 1; the frames are all good)."""
    tw = Twin(inst=GEN_INST, thr=THR, veto_mode=veto)
    for _ in range(n_frames):
        tw.frame(bf.Msg(bf.ADD, bf.ASK, GEN_INST, GEN_PRICE, 1), True)
    n = tw.n
    return {"n_obs": n["obs"], "n_cls_down": n["cls"][0], "n_cls_flat": n["cls"][1], "n_cls_up": n["cls"][2], "n_dec": n["dec"], "n_veto": n["veto"], "n_would_veto": n["would"],
            "n_late": 0, "n_apply": n["apply"], "n_drop": n["drop"], "n_race": 0, "orders": n["orders"]}


def ml_features(t: bb.Transport) -> dict:
    v = t.rd(0x008)
    return {"raw": f"{v:08x}", "ml_stage": (v >> 8) & 1, "rate_match": (v >> 3) & 1, "rm_own": (v >> 5) & 1, "ml_id": f"{t.rd(ML_ID):08x}", "ml_id_ok": t.rd(ML_ID) == ID_VALUE}


def ml_words(t: bb.Transport) -> dict:
    """The stage's status words of the snapshot already taken (b.snapshot() takes it)."""
    return {n: t.rd(MLV_BASE + 4 * i) for i, n in enumerate(MLV_NAMES)}


def sweep(b: bb.Board, veto: bool, repeats: int = 20, frames: int = 50, interval: int = 3000) -> dict:
    """`repeats` runs of `frames` feed frames, each after a state reset: the stage's counters against the twin, and the orders sent."""
    want = predict(frames, veto)
    rows, bad = [], []
    for i in range(repeats):
        b.t.wr(ML_CTRL, 0x2 | (1 if veto else 0))            # reset the stage's state and counters, set the mode
        b.clear()
        b.configure(arm=True, kind=1, count=frames, interval=interval, inst=GEN_INST, price=GEN_PRICE, thr=THR)
        b.run(0.05)
        tx, rx = bb.settled_snapshot(b, want["orders"])
        mlv = ml_words(b.t)
        row = {"i": i, "orders": tx["n_order"], "fired": rx["fired"], "mlv": mlv, "l_min": tx["l_min"], "l_cnt": tx["l_cnt"]}
        ok = all(mlv[k] == want[k] for k in MLV_NAMES) and tx["n_order"] == want["orders"] and rx["fired"] == want["orders"]
        row["match"] = ok
        if not ok:
            bad.append({k: (mlv[k], want[k]) for k in MLV_NAMES if mlv[k] != want[k]} | {"orders": (tx["n_order"], want["orders"])})
        rows.append(row)
    return {"mode": "veto" if veto else "shadow", "repeats": repeats, "frames": frames, "predicted": want, "all_match": not bad, "mismatches": bad[:5], "rows": rows}


def verdict(stage3: dict, sweeps: dict | None, roc_ok: bool | None, feat: dict | None) -> dict:
    """The pre-registered decision. Returns {'result': 'PASS'|'WARN'|'FAIL'|'ABORT', 'reasons': [...], numbers}.
    ABORT: the loaded bitstream is not build rm_gp_ml (FEATURES bit 8 or ML_ID wrong), the link did not lock, no E or L reading.
    FAIL: any safety counter in the stage-3 run, a failed lock, an operating-condition excursion, any stage counter different from the twin in either sweep, n_late or n_race not 0,
          or L (or E) more than WARN_BAND clocks from the 96E rm_gp reference (lead-corrected).
    WARN: E or L between PASS_BAND and WARN_BAND clocks from the reference. PASS: all of it, within PASS_BAND."""
    r = stage3.get("restarts", {}) or {}
    sf = stage3.get("safety", {}) or {}
    e = (r.get("E_min_per_link") or {}).get("median")
    l = (r.get("L_min_per_link") or {}).get("median")
    out = {"E_median": e, "L_median": l, "ref_E": REF_E, "ref_L": REF_L, "ref_D": REF_D}
    if feat is not None and not (feat.get("ml_stage") and feat.get("ml_id_ok")):
        return {"result": "ABORT", "reasons": ["FEATURES bit 8 or ML_ID wrong: the loaded bitstream is not build rm_gp_ml"], **out}
    if not stage3.get("link_up"):
        return {"result": "ABORT", "reasons": ["the link did not come up"], **out}
    if e is None or l is None:
        return {"result": "ABORT", "reasons": ["no E or L reading"], **out}
    fail: list[str] = []
    if r.get("failed_to_lock"):
        fail.append(f"{r['failed_to_lock']} of {r.get('restarts')} receive restarts did not lock")
    if not sf.get("ok"):
        fail.append(f"safety counters: {sf.get('failing_counters') or sf.get('reasons')}")
    if roc_ok is False:
        fail.append("operating conditions outside the recommended window (results void until repeated inside it)")
    if sweeps is not None:
        for name, s in sweeps.items():
            if not s.get("all_match"):
                fail.append(f"{name} sweep: stage counters differ from the twin: {s.get('mismatches')}")
    dfib = (stage3.get("fibre_one_way_ns", REF_FIBRE_NS) - REF_FIBRE_NS) / CLOCK_NS
    ref_e, ref_l = REF_E + dfib, REF_L + 2 * dfib
    de, dl = e - ref_e, l - ref_l
    out.update({"ref_E_adjusted_for_lead": ref_e, "ref_L_adjusted_for_lead": ref_l, "dE": de, "dL": dl, "D_from_medians": l - 2 * e})
    worst = max(abs(de), abs(dl))
    if worst > WARN_BAND:
        fail.append(f"E or L is {worst:.1f} clocks from the 96E rm_gp run (more than {WARN_BAND}): the stage added or removed latency that simulation says it does not")
    if fail:
        return {"result": "FAIL", "reasons": fail, **out}
    if worst > PASS_BAND:
        return {"result": "WARN", "reasons": [f"E or L is {worst:.1f} clocks from the 96E rm_gp run (predicted within {PASS_BAND})"], **out}
    return {"result": "PASS", "reasons": [f"dE {de:+.1f}, dL {dl:+.1f} clocks against the 96E rm_gp run (predicted 0, band {PASS_BAND}); stage counters equal the twin in both modes"], **out}


def main() -> None:
    """Board session for build rm_gp_ml: stage-3 loopback in shadow mode, the shadow and veto sweeps, the verdict. The laser is left off."""
    import argparse

    from flow import version_pin
    ap = argparse.ArgumentParser(description="Brief 113 board session (ML decision stage). Laser polarity first; the laser is left off at the end.")
    ap.add_argument("--serial", required=True)
    ap.add_argument("--lock-text", required=True, help="the text in _handoff/board.lock (must start '113:')")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--loop-m", type=float, required=True)
    ap.add_argument("--restarts", type=int, default=100)
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--frames", type=int, default=50)
    a = ap.parse_args()
    if not a.lock_text.startswith("113:"):
        raise SystemExit("the lock text must start '113:'")
    a.out.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[3]
    t = bb.VivadoTcl(repo, a.serial, version_pin.vivado_path())
    out: dict = {}
    sweeps: dict | None = None
    try:
        out["conditions_start"] = pp.safe_conditions(t)
        out["features"] = ml_features(t)
        if out["features"]["ml_stage"] and out["features"]["ml_id_ok"]:
            t.wr(ML_CTRL, 0x2)                                  # shadow mode, state and counters clear (the reset value of the mode)
        res = bb.run_all(t, a.lock_text, a.out, cable_loop_m=a.loop_m, n_restarts=a.restarts)
        sf = res.get("safety", {})
        out.update({"id": res.get("id"), "polarity_ok": res.get("polarity_ok"), "link_up": res.get("link_up"), "safety_ok": sf.get("ok", False),
                    "safety_failing": sf.get("failing_counters", []) or sf.get("reasons", [])})
        if res.get("link_up") and out["features"]["ml_stage"]:
            b = bb.Board(t)
            b.laser(True)
            try:
                b.reset(all_=True)
                b.wait(lambda s: s["tx_done"] and s["rx_done"] and s["pcs_lock"], 5.0)
                sweeps = {"shadow": sweep(b, False, a.repeats, a.frames), "veto": sweep(b, True, a.repeats, a.frames)}
                t.wr(ML_CTRL, 0x2)
            finally:
                b.laser(False)
            (a.out / "sweeps.json").write_text(json.dumps(sweeps, indent=1, default=str))
            out["sweeps"] = {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in sweeps.items()}
        out["conditions_end"] = pp.safe_conditions(t)
        out["roc_ok"] = all(c.get("inside_roc") for c in (out["conditions_start"], out["conditions_end"]))
        out["verdict"] = verdict(res, sweeps, out["roc_ok"], out["features"])
    finally:
        try:
            bb.Board(t).laser(False)
        except Exception:  # noqa: BLE001 - the laser is also off after run_all; the board may be gone
            pass
        try:
            t.wr(ML_CTRL, 0x0)
        except Exception:  # noqa: BLE001
            pass
        t.close()
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
