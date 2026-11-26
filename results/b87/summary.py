#!/usr/bin/env python3
"""Build results/b87/summary.json and latency_vs_accuracy.svg from the committed records (no new measurement).

    python3 results/b87/summary.py           # write
    python3 results/b87/summary.py --check   # fail if summary.json is out of date

Latency of an arm = its LATENCY (clocks from the registered features to the registered class; the RTL test shows
it holds for every test sample) x the period it closed at post-route (results/b87/ooc/<arm>.json).
Published points: figure 8 of the trading-path research report (jet-substructure classification on a VU9P/KU115,
out-of-context synthesis estimates, I/O and features excluded), kept in published_jsc.json with their sources.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from flow import fmax_cap  # noqa: E402  (brief 201: clock-buffer cap on the closed-clock Fmax)
GEN = ROOT / "designs" / "b87_ml_trading" / "rtl" / "gen"
# Out of context the clock is a port: no clock buffer, no MMCM jitter. A tiny design then "closes" at the flip-flops'
# minimum period (0.55 ns), which no clock network delivers. Every latency is quoted at no faster than 2.0 ns
# (500 MHz); the raw closed period is kept in closed_at_ns.
FLOOR_NS = 2.0
ARMS = [("imb_rule", "imbalance_rule", "trivial rule (imbalance threshold)"),
        ("gbt_comb", "gbt", "(a) boosted trees, combinational"),
        ("gbt_pipe", "gbt", "(a) boosted trees, one clock per level"),
        ("mlp_hand", "mlp", "(b) MLP, hand RTL"),
        ("mlp_hls4ml", "mlp", "(b) MLP, hls4ml + Vitis HLS"),
        ("lutnet", "lutnet", "(c) LUT network")]


def build() -> dict:
    acc = json.loads((HERE / "accuracy.json").read_text())
    det = json.loads((HERE / "determinism.json").read_text())["arms"]
    rows = []
    for arm, model, label in ARMS:
        o = HERE / "ooc" / f"{arm}.json"
        if not o.exists():
            continue
        oc = json.loads(o.read_text())
        a = acc["arms"]["imbalance_rule"]["test"] if model == "imbalance_rule" else \
            acc["arms"][model]["runs"][0]["test_quantised"]
        if arm == "mlp_hls4ml":
            hc = json.loads((HERE / "hls4ml_csim.json").read_text())
            d = det["mlp_hls4ml_wrap"]
            lat = d["latency_param"]
            det_ok = hc["logits_bit_exact_with_integer_model"] and d["mismatches"] == 0 and \
                d["latency_min"] == d["latency_max"] == lat
        else:
            lat = int(re.search(r"LATENCY = (\d+);", (GEN / f"{arm}.sv").read_text()).group(1))
            d = det[arm]
            det_ok = d["mismatches"] == 0 and d["latency_min"] == d["latency_max"] == lat
        b = oc["at_closed_clock"] or {}
        rows.append({"arm": arm, "label": label, "model": model,
                     "test_accuracy": a["mean"], "test_accuracy_ci95": a["ci95"],
                     "latency_clocks": lat, "initiation_interval": 1,
                     "closed_at_ns": oc["closed_at_ns"], "closed_at_mhz": oc["closed_at_mhz"],
                     **fmax_cap.restate("k26", oc["closed_at_mhz"], "closed clock of the search (setup, hold, primitive pulse width)"),
                     "quoted_period_ns": max(oc["closed_at_ns"], FLOOR_NS) if oc["closed_at_ns"] else None,
                     "latency_ns": round(lat * max(oc["closed_at_ns"], FLOOR_NS), 2) if oc["closed_at_ns"] else None,
                     "lut": b.get("lut"), "ff": b.get("ff"), "dsp": b.get("dsp"), "bram_tiles": b.get("bram_tiles"),
                     "wns_ns": b.get("wns_ns"), "whs_ns": b.get("whs_ns"),
                     "bit_exact_and_fixed_latency_over_test_split": det_ok})
    return {"schema": "b87-summary/1", "part": "xck26-sfvc784-2LV-c",
            "note": "accuracy: seed-0 quantised model, test split, 95% t-interval over 10 sessions; latency: "
                    "LATENCY clocks x max(closed period, 2.0 ns), out of context, post-route; in the 58A path every "
                    "arm runs at 8 ns, so there its latency is LATENCY x 8 ns",
            "floor_ns": FLOOR_NS,
            "rows": rows}


def chart(s: dict) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pub = json.loads((HERE / "published_jsc.json").read_text())["points"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "none"})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), sharex=True)
    for p in pub:
        ax1.plot(p["latency_ns"], p["accuracy"], marker="o", mfc="white", mec="#444", ls="none")
        ax1.annotate(p["label"], (p["latency_ns"], p["accuracy"]), xytext=(4, 3), textcoords="offset points",
                     fontsize=7, color="#555")
    ax1.set_title("Published (jet substructure, 5 classes; not trading)", fontsize=9)
    ax1.set_ylabel("accuracy (%)")
    for r in s["rows"]:
        if r["latency_ns"] is None:
            continue
        m = "s" if r["arm"] == "imb_rule" else "D"
        ax2.errorbar(r["latency_ns"], 100 * r["test_accuracy"],
                     yerr=[[100 * (r["test_accuracy"] - r["test_accuracy_ci95"][0])],
                           [100 * (r["test_accuracy_ci95"][1] - r["test_accuracy"])]],
                     marker=m, color="#111", mfc="#111" if r["arm"] != "imb_rule" else "white", capsize=2, ls="none")
        ax2.annotate(r["label"], (r["latency_ns"], 100 * r["test_accuracy"]), xytext=(5, -3),
                     textcoords="offset points", fontsize=7, color="#222")
    ax2.set_title("Measured here (synthetic order flow, 3 classes; K26 post-route)", fontsize=9)
    for ax in (ax1, ax2):
        ax.set_xscale("log")
        ax.set_xlabel("latency (ns, log scale)")
        ax.grid(True, color="#e6e6e6", lw=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    fig.text(0.5, 0.005, "Left: figure 8 of the trading-path research report (out-of-context synthesis estimates on "
             "VU9P/KU115). Right: our measurements. Different tasks: compare the latency axis only.", ha="center",
             fontsize=7, color="#555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    import io
    buf = io.StringIO()
    fig.savefig(buf, format="svg", metadata={"Date": None})
    return re.sub(r'id="[0-9a-f]{10,}"', "", buf.getvalue())


def main() -> int:
    s = build()
    txt = json.dumps(s, indent=1) + "\n"
    if "--check" in sys.argv:
        ok = (HERE / "summary.json").read_text() == txt
        print("summary.json current" if ok else "summary.json out of date")
        return 0 if ok else 1
    (HERE / "summary.json").write_text(txt)
    (HERE / "latency_vs_accuracy.svg").write_text(chart(s))
    for r in s["rows"]:
        print(f"{r['arm']:<11} acc {r['test_accuracy']:.4f} lat {r['latency_clocks']} clk @ {r['closed_at_ns']} ns = "
              f"{r['latency_ns']} ns  LUT {r['lut']} FF {r['ff']} DSP {r['dsp']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
