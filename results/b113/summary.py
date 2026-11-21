"""Brief 113: results/b113/summary.json from the committed records; `--check` recomputes it and compares (the number in any text comes from summary.json).

Records: latency.json (whole-core xsim, lat/*.log), twin/*.json (bit-exactness runs: ml_check.py, loop_check.py), builds/rm_gp_ml/{digest,run}.json and stage/stage_timing.json (Vivado 2026.1), and the control
build rm_gp of brief 96F1 (results/b96f1/builds/rm_gp/digest.json) for the resource difference.
"""
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
ROOT = R.parent.parent


def load(p: Path):
    return json.loads(p.read_text())


def build() -> dict:
    d = load(R / "builds/rm_gp_ml/digest.json")
    run = load(R / "builds/rm_gp_ml/run.json")
    ctl = load(ROOT / "results/b96f1/builds/rm_gp/digest.json")
    st = load(R / "builds/rm_gp_ml/stage/stage_timing.json")
    gates = d["gates"] if "gates" in d else {}
    u, c = d["utilization"], ctl["utilization"]
    stage_paths = {k: {"slack_ns": v["slack_ns"], "data_path_delay_ns": v["data_path_delay_ns"], "logic_levels": v["logic_levels"]} for k, v in st.items()}
    return {"part": "xck26-sfvc784-2LV-c", "vivado": run["vivado_version"], "core_clock_period_ns": d["timing"]["period_ns"], "build_stamp": run["build_stamp"], "sources_sha256": run["sources_sha256"],
            "wns_ns": d["timing"]["wns_ns"], "whs_ns": d["timing"]["whs_ns"], "timing_met": d["timing"]["timing_met"], "gates_total": len(gates), "gates_true": sum(1 for v in gates.values() if v),
            "drc_critical": d["drc"]["critical_warnings"], "methodology_critical": d["methodology"]["critical_warnings"], "power_w_vectorless": d["power"]["total_w"], "tj_c": d["power"]["junction_c"],
            "lut": u["lut"], "ff": u["ff"], "bram": u["bram_tile"], "dsp": u["dsp"], "lut_control_rm_gp": c["lut"], "ff_control_rm_gp": c["ff"], "lut_added": u["lut"] - c["lut"], "ff_added": u["ff"] - c["ff"],
            "wall_s": run["wall_s"], "vivado_peak_rss_mib": run["vivado_peak_rss_mib"], "scope_cap_hits": run["scope_cap_hits"],
            "stage_paths_post_route": stage_paths, "stage_worst_slack_ns": min(v["slack_ns"] for v in st.values())}


def sim() -> dict:
    lat = load(R / "latency.json")
    out = {"tick_to_trade_clocks": lat["means_over_phases_clocks"], "change_vs_base_clocks": lat["tick_to_trade_change_vs_base_clocks"], "rx_start_change": lat["rx_start_strobe_change_vs_base_clocks"],
           "d_change": lat["d_change_vs_base_clocks"]}
    tw = {}
    for name in ("ml_veto_p0", "ml_veto_p3100", "ml_shadow_p1550"):
        r = load(R / f"twin/{name}.json")
        tw[name] = {"pass": r["pass"], "messages": r["messages_seen"], "mismatches": r["n_mismatch"], "orders_expected": r["orders_expected"], "tx_n_order": r["tx_n_order"], "counters_equal": r.get("ml_counters_equal")}
    base_log = (R / "twin/logs/base_p1550.log").read_text().splitlines()
    base_orders = next(int(ln.split()[2]) for ln in base_log if ln.startswith("REG tx_n_order"))
    tw["base_rm_gp_p1550_orders"] = base_orders
    tw["shadow_orders_equal_base"] = base_orders == tw["ml_shadow_p1550"]["tx_n_order"]
    for v in ("v1", "v0"):
        r = load(R / f"twin/ml_loop_{v}.json")
        tw[f"board_stream_{v}"] = {"pass": r["pass"], "stage_counters": r["stage_counters"], "orders": r["tx_n_order"]}
    out["bit_exact"] = tw
    return out


def make() -> dict:
    return {"brief": 113, "build": build(), "simulation": sim()}


if __name__ == "__main__":
    s = make()
    p = R / "summary.json"
    if "--check" in sys.argv:
        if load(p) != s:
            sys.exit("results/b113/summary.json is out of date: run python3 results/b113/summary.py")
        print("summary.json current")
    else:
        p.write_text(json.dumps(s, indent=1) + "\n")
        print("wrote", p)
