#!/usr/bin/env python3
"""Run the off-chip check on our board designs (brief 155 part 4): what the XDC sets, what the check says, what it would propose.

    python3 tools/offchip_board_report.py [--specs results/155_offchip/boards] [--out results/155_offchip/boards_report]

Each ``*.spec.yaml`` names a design XDC, the board and its ``off_chip`` groups. Loads and lines the repository does not hold are marked
ASSUMED in the spec and listed as missing data in the report. No board XDC is changed: the report only proposes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flow"))
import offchip_check as C   # noqa: E402


def master_counts(board: str) -> dict:
    d = ROOT / "boards" / board
    meta = yaml.safe_load((d / "board.yaml").read_text())
    f = d / meta["master_xdc"]
    text = f.read_text(errors="replace")
    live = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    allset = [ln.lstrip("#").strip() for ln in text.splitlines() if "set_property" in ln]
    return {"file": str(f.relative_to(ROOT)), "port_lines": len(allset), "with_drive": sum(1 for ln in allset if re.search(r"\bDRIVE\b", ln)),
            "with_slew": sum(1 for ln in allset if re.search(r"\bSLEW\b", ln)), "iostandards": sorted(set(re.findall(r"IOSTANDARD\s+(\w+)", "\n".join(allset))))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--specs", default=str(ROOT / "results/155_offchip/boards"))
    ap.add_argument("--out", default=str(ROOT / "results/155_offchip/boards_report"))
    a = ap.parse_args()
    rows, report = [], []
    for sp in sorted(Path(a.specs).glob("*.spec.yaml")):
        spec = yaml.safe_load(sp.read_text())
        errs = C.off_chip_errors(spec.get("off_chip"))
        fc = C.family_class(spec["family"], spec.get("part", ""))
        xdc_text = (ROOT / spec["xdc"]).read_text()
        props = C.parse_xdc(xdc_text)
        res = C.check(spec, xdc_text, fc, spec.get("bank_type", "HR"))
        props_names = sorted(props)
        entry = {"spec": sp.name, "design": spec["design"], "board": spec["board"], "master_xdc": master_counts(spec["board"]), "schema_errors": errs,
                 "findings": res["findings"], "groups": []}
        for g in spec["off_chip"]:
            if g.get("direction", "output") == "input":
                continue
            bt = g.get("bank_type", spec.get("bank_type", "HR"))
            ports = C.ports_of(g, props_names)
            cfgs = sorted({(props[p].get("IOSTANDARD", g["iostandard"]), int(props[p].get("DRIVE", C.DEFAULT_DRIVE)), props[p].get("SLEW", C.DEFAULT_SLEW).upper(),
                            "DRIVE" in props[p] and "SLEW" in props[p]) for p in ports})
            prop = C.propose(g, fc, bt)
            best = prop["best"]
            line = g.get("line", "short")
            cur = []
            for std, drive, slew, explicit in cfgs:
                mf = C.model_family(fc, bt)
                ev = C.evaluate_cached(mf, bt, std, drive, slew, 0.0, "none", 50.0 if line == "short" else float(line.get("z0_ohm", 50)),
                                       0.3 if line == "short" else float(line["length_in"]), float(g["load"]["c_pf"]), 3.2, (), None, None)
                cur.append({"iostandard": std, "drive": drive, "slew": slew, "explicit_in_xdc": explicit,
                            "worst_overshoot_v": round(ev["worst_over_vcco_v"], 2), "worst_undershoot_v": round(ev["worst_under_gnd_v"], 2),
                            "first_incident_margin_v": None if ev["min_first_incident_margin_v"] is None else round(ev["min_first_incident_margin_v"], 2),
                            "ringback_margin_v": None if ev["min_ringback_margin_v"] is None else round(ev["min_ringback_margin_v"], 2),
                            "lumped": ev["lumped"], "model": ev["source"]["model"]})
            what_if = []
            if line != "short":
                for rs in (22.0, 33.0):          # the board may already have a series resistor: the schematic is not in the repository
                    for std, drive, slew, explicit in cfgs[:1]:
                        mf = C.model_family(fc, bt)
                        ev = C.evaluate_cached(mf, bt, std, drive, slew, rs, "none", float(line.get("z0_ohm", 50)), float(line["length_in"]), float(g["load"]["c_pf"]), 3.2, (), None, None)
                        flags = C.judge(ev, C.rx_limits(fc, bt), not ev["lumped"], float(g.get("ui_ns", 10.0)))
                        what_if.append({"series_ohm_on_board": rs, "drive": drive, "slew": slew, "worst_overshoot_v": round(ev["worst_over_vcco_v"], 2),
                                        "worst_undershoot_v": round(ev["worst_under_gnd_v"], 2), "first_incident_margin_v": round(ev["min_first_incident_margin_always_v"], 2),
                                        "flags": sorted({f[0] for f in flags})})
            entry["groups"].append({"what_if_series_resistor": what_if, "group": g["name"], "ports": ports, "line": line, "c_pf": g["load"]["c_pf"], "priority": g.get("priority", "balanced"),
                                    "xdc_now": cur, "proposal": None if best is None else {k: best[k] for k in ("drive", "slew", "rs_ohm", "static_mismatch", "worst_over_v",
                                    "worst_under_v", "first_incident_margin_v", "ringback_margin_v", "settle_ns")}, "no_proposal_reason": prop["reason"],
                                    "n_passing": len(prop["all_passing"])})
        report.append(entry)
        print("done", sp.name, flush=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=1, default=str))
    print(out.with_suffix(".json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
