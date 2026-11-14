#!/usr/bin/env python3
"""Brief 70: turn the matrix records (records/<part>.tsv) into the tables of the README and the numbers the reset check quotes.

    python3 results/70_resets/summary.py            # print the tables; write records/matrix_summary.json
    python3 results/70_resets/summary.py --check    # fail if records/matrix_summary.json is not what the records give

Every number in the README, in flow/checks/resets.py's MEASURED and in the KB skills comes from matrix_summary.json. The
records are one run each (Vivado 2026.1, out of context, one thread): the numbers are single measurements, not averages.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE / "records"
PARTS = ("xc7a100tcsg324-1", "xck26-sfvc784-2LV-c")
#: variant -> (asynchronous, active low, which registers, one reset in both polarities, reset registered once inside)
VARIANTS = {
    "sH_all": "synchronous, active high, reset all", "sL_all": "synchronous, active low, reset all",
    "sH_ctl": "synchronous, active high, reset control only", "sL_ctl": "synchronous, active low, reset control only",
    "aH_all": "asynchronous, active high, reset all", "aL_all": "asynchronous, active low, reset all",
    "aH_ctl": "asynchronous, active high, reset control only", "aL_ctl": "asynchronous, active low, reset control only",
    "sBs_all": "synchronous, one reset condition written in both polarities, reset all",
    "aBs_all": "asynchronous, one reset condition written in both polarities, reset all",
    "sB_all": "synchronous, one signal tested at both levels (two polarities of one reset), reset all",
    "aB_all": "asynchronous, one signal tested at both levels (two polarities of one reset), reset all",
    "rH_all_fo_default": "synchronous, active high, reset registered, no fan-out limit",
    "rH_all_mf50": "synchronous, active high, reset registered, MAX_FANOUT = 50 on the register",
    "rL_all_fo_default": "synchronous, active low, reset registered, no fan-out limit",
    "rL_all_mf50": "synchronous, active low, reset registered, MAX_FANOUT = 50 on the register",
}
BLOCKS = {"1": "register bank", "2": "counter", "4": "DSP", "8": "block RAM", "15": "all four"}


def load(part: str) -> dict:
    d: dict = defaultdict(dict)
    f = REC / f"{part}.tsv"
    if not f.is_file():
        return {}
    for ln in f.read_text().splitlines():
        if not ln.strip():
            continue
        p, v, b, k, val = ln.split("\t", 4)
        d[(v, b)][k] = val
    return d


def num(x, default=None):
    try:
        return int(x)
    except (TypeError, ValueError):
        try:
            return float(x)
        except (TypeError, ValueError):
            return default


def ffs(r: dict, stage: str = "synth") -> dict:
    return {t: num(r.get(f"{stage}:cell {t}"), 0) for t in ("FDRE", "FDSE", "FDCE", "FDPE", "LDCE", "LDPE")}


def sinks(r: dict, stage: str = "synth", tag: str = "rst_in") -> dict:
    pre = f"{stage}:{tag}_sink "
    return {k[len(pre):]: num(v) for k, v in r.items() if k.startswith(pre)}


def summarise(part: str) -> dict:
    d = load(part)
    out: dict = {}
    for (v, b), r in d.items():
        e = out.setdefault(v, {}).setdefault(b, {})
        for st in ("synth", "route"):
            if f"{st}:luts" not in r:
                continue
            e[st] = {"luts": num(r[f"{st}:luts"]), "ffs": num(r[f"{st}:flipflops"]), "control_sets": num(r.get(f"{st}:control_sets")),
                     "inverter_luts_on_reset": num(r.get(f"{st}:rst_in_inverter_luts")), "ff_types": ffs(r, st),
                     "ff_IS_R_INVERTED": num(r.get(f"{st}:ff_IS_R_INVERTED")), "sinks": sinks(r, st),
                     "dsp": num(r.get(f"{st}:cell DSP48E1"), 0) + num(r.get(f"{st}:cell DSP48E2"), 0),
                     "ramb": sum(num(r.get(f"{st}:cell {t}"), 0) for t in ("RAMB36E1", "RAMB18E1", "RAMB36E2", "RAMB18E2")),
                     "luts_inverters": num(r.get(f"{st}:cell LUT1"), 0)}
        for k in ("synth:wns_setup", "route:wns_setup", "route:wns_hold", "synth:wns_to_reset_pins", "route:wns_to_reset_pins",
                  "synth_ms", "impl_ms"):
            if k in r:
                e[k] = num(r[k], r[k])
        e["dsp_regs"] = {k.split(" reg ")[1]: num(v) for k, v in r.items() if k.startswith("synth:DSP48") and " reg " in k}
        e["dsp_reset_pins"] = {k.split(" pin ")[1]: v for k, v in r.items() if k.startswith("synth:DSP48") and " pin " in k}
        e["ram_reset_pins"] = {k.split(" pin ")[1]: v for k, v in r.items() if k.startswith("synth:RAMB") and " pin " in k}
        e["rstreg_inverters"] = num(r.get("synth:rstreg_inverter_luts"))
        e["rstreg_sinks"] = sinks(r, "synth", "rstreg")
        if "status" in r:
            e["status"] = r["status"]
    return out


def costs(s: dict) -> dict:
    """The differences the reset check and the KB skills quote, per part, all from the one-run-each records (the arms are named in
    VARIANTS). Absent arms are left out."""
    def g(v: str, b: str = "15", st: str = "synth") -> dict | None:
        return (s.get(v) or {}).get(b, {}).get(st)

    out: dict = {}
    sh, sl = g("sH_all"), g("sL_all")
    if sh and sl:
        rh, rl = g("sH_all", "15", "route"), g("sL_all", "15", "route")
        out["active_low_vs_active_high_sync_all"] = {
            "luts": sl["luts"] - sh["luts"], "ffs": sl["ffs"] - sh["ffs"], "control_sets": sl["control_sets"] - sh["control_sets"],
            "inverter_luts_on_reset_net": sl["inverter_luts_on_reset"], "ff_IS_R_INVERTED": sl["ff_IS_R_INVERTED"],
            "after_route_luts": rl["luts"] - rh["luts"] if rh and rl else None,
            "after_route_inverter_luts_on_reset_net": rl["inverter_luts_on_reset"] if rl else None,
            "wns_to_reset_pin_active_high": (s["sH_all"]["15"]).get("route:wns_to_reset_pins"),
            "wns_to_reset_pin_active_low": (s["sL_all"]["15"]).get("route:wns_to_reset_pins")}
    ah = g("aH_all")
    if sh and ah:
        d4s, d4a, d8s, d8a = g("sH_all", "4"), g("aH_all", "4"), g("sH_all", "8"), g("aH_all", "8")
        out["async_vs_sync_all"] = {"luts": ah["luts"] - sh["luts"], "ffs": ah["ffs"] - sh["ffs"],
                                    "control_sets": ah["control_sets"] - sh["control_sets"],
                                    "dsp_block_ffs_sync": d4s["ffs"], "dsp_block_ffs_async": d4a["ffs"],
                                    "ram_block_ffs_sync": d8s["ffs"], "ram_block_ffs_async": d8a["ffs"],
                                    "dsp_regs_in_dsp_sync": (s["sH_all"]["4"]["dsp_regs"]),
                                    "dsp_regs_in_dsp_async": (s["aH_all"]["4"]["dsp_regs"])}
    sc = g("sH_ctl")
    if sh and sc:
        out["reset_control_only_vs_all_sync"] = {"luts": sc["luts"] - sh["luts"], "ffs": sc["ffs"] - sh["ffs"],
                                                 "control_sets": sc["control_sets"] - sh["control_sets"]}
    ac = g("aH_ctl")
    if sc and ac:
        out["async_control_only_vs_sync_control_only"] = {"luts": ac["luts"] - sc["luts"], "ffs": ac["ffs"] - sc["ffs"],
                                                         "control_sets": ac["control_sets"] - sc["control_sets"],
                                                         "fdce": ac["ff_types"]["FDCE"]}
    for tag, name in (("sB_all", "two_levels_sync_vs_active_low"), ("aB_all", "two_levels_async_vs_active_low")):
        b, base = g(tag), g("sL_all" if tag == "sB_all" else "aL_all")
        if b and base:
            rb, rbase = g(tag, "15", "route"), g("sL_all" if tag == "sB_all" else "aL_all", "15", "route")
            out[name] = {"luts": b["luts"] - base["luts"], "control_sets": b["control_sets"] - base["control_sets"],
                         "inverter_luts_on_reset_net": b["inverter_luts_on_reset"], "ffs": b["ffs"] - base["ffs"],
                         "after_route_luts": rb["luts"] - rbase["luts"] if rb and rbase else None,
                         "after_route_control_sets": rb["control_sets"] - rbase["control_sets"] if rb and rbase else None}
    for tag, name in (("sBs_all", "same_condition_both_polarities_sync_vs_active_low"),):
        b, base = g(tag), g("sL_all")
        if b and base:
            out[name] = {"luts": b["luts"] - base["luts"], "control_sets": b["control_sets"] - base["control_sets"]}
    fd = g("rH_all_fo_default")
    sh = g("sH_all")
    if fd and sh:
        out["registered_reset_vs_direct_sync_all"] = {"ffs": fd["ffs"] - sh["ffs"], "luts": fd["luts"] - sh["luts"],
                                                      "control_sets": fd["control_sets"] - sh["control_sets"]}
    # the *_fo_50 arms (synth_design -fanout_limit 50) are void: the option is deprecated and changed nothing (review finding);
    # their records stay in the files, and the *_mf50 arms (MAX_FANOUT on the reset register) replace them
    for tag, base, name in (("rH_all_mf50", "rH_all_fo_default", "max_fanout_attribute_50_vs_none_active_high"),
                            ("rL_all_mf50", "rL_all_fo_default", "max_fanout_attribute_50_vs_none_active_low")):
        f50, b0 = g(tag), g(base)
        if b0 and f50:
            out[name] = {"ffs": f50["ffs"] - b0["ffs"], "control_sets": f50["control_sets"] - b0["control_sets"],
                         "luts": f50["luts"] - b0["luts"]}
    return out


def table(part: str, s: dict) -> str:
    rows = ["| variant | LUTs | flip-flops (FDRE / FDSE / FDCE / FDPE) | control sets | inverter LUTs on the reset | WNS to a reset pin (ns) | WNS overall (ns) |",
            "|---|---|---|---|---|---|---|"]
    for v, name in VARIANTS.items():
        e = s.get(v, {}).get("15")
        if not e or "route" not in e:
            if e and "synth" in e:
                t = e["synth"]
                ft = t["ff_types"]
                rows.append(f"| {name} | {t['luts']} | {t['ffs']} ({ft['FDRE']} / {ft['FDSE']} / {ft['FDCE']} / {ft['FDPE']}) | {t['control_sets']} | "
                            f"{t['inverter_luts_on_reset']} | - | - |")
            continue
        t, ft = e["route"], e["route"]["ff_types"]
        rows.append(f"| {name} | {t['luts']} | {t['ffs']} ({ft['FDRE']} / {ft['FDSE']} / {ft['FDCE']} / {ft['FDPE']}) | {t['control_sets']} | "
                    f"{t['inverter_luts_on_reset']} | {e.get('route:wns_to_reset_pins', '-')} | {e.get('route:wns_setup', '-')} |")
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    res = {"vivado": "2026.1", "runs": "one each", "parts": {p: summarise(p) for p in PARTS}}
    res["parts"] = {p: {v: b for v, b in e.items() if not v.endswith("_fo_50")} for p, e in res["parts"].items()}
    res["voided_arms"] = "rH_all_fo_50 and rL_all_fo_50 (synth_design -fanout_limit 50: deprecated, changed nothing); " \
                         "the xck26 rL_all_fo_50 record (53 LUTs, 149 flip-flops) did not reproduce in records/xck26-sfvc784-2LV-c_rerun.tsv"
    res["costs"] = {p: costs(res["parts"][p]) for p in PARTS if res["parts"][p]}
    text = json.dumps(res, indent=1, sort_keys=True) + "\n"
    f = REC / "matrix_summary.json"
    cf = HERE.parents[1] / "flow" / "checks" / "reset_costs.json"
    ctext = json.dumps({"source": "results/70_resets/records/matrix_summary.json (written by results/70_resets/summary.py)",
                        "vivado": "2026.1", "runs": "one each", "parts": res["costs"]}, indent=1, sort_keys=True) + "\n"
    if a.check:
        if not f.is_file() or f.read_text() != text or not cf.is_file() or cf.read_text() != ctext:
            print("records/matrix_summary.json or flow/checks/reset_costs.json is stale: run results/70_resets/summary.py")
            return 1
        return 0
    f.write_text(text)
    cf.write_text(ctext)
    for p in PARTS:
        if res["parts"][p]:
            print(f"\n### {p}\n\n" + table(p, res["parts"][p]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
