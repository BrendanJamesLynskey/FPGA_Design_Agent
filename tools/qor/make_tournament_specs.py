#!/usr/bin/env python3
"""Brief 178: write the tournament specs for the evaluation points (arith out-of-context blocks measured near their clock limit by briefs 160/166).

    python3 tools/qor/make_tournament_specs.py        # writes results/178_tournament/specs/*.yaml

A point is "<function>/<variant>/<a7|k26>" plus the generics to build with. The clock and constraints come from the arith build file.
"""
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "178_tournament" / "specs"
# name -> (function, variant, part key, generics); chosen because brief 160 routed them within about 0.5 ns of the clock (dataset.csv)
POINTS = {
    "isqrt_restpipe_k26_w32": ("isqrt", "restoring_pipe", "k26", {"VARIANT": 1, "PIPE": 1, "W": 32}),
    "lzc_treebarrel_k26_w32": ("lzc_norm", "tree_barrel", "k26", {"VARIANT": 0, "PIPE": 1, "W": 32}),
    "divider_restpipe_k26_w16": ("divider", "restoring_pipe", "k26", {"VARIANT": 2, "PIPE": 1, "W": 16}),
    "mac_fabric_k26": ("mac", "fabric", "k26", {"WA": 16, "WB": 16, "LANES": 1, "ACCW": 40, "SIGNED": 1, "NREG": 1}),
    "adder_csel_a7_w64b16": ("adder", "carry_select", "a7", {"WIDTH": 64, "BLOCK": 16}),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (fn, var, key, gen) in POINTS.items():
        d = ROOT / "arith" / fn / "build" / var
        y = yaml.safe_load((d / "build.yaml").read_text() if (d / "build.yaml").exists() else (d / key / "build.yaml").read_text())
        if "ooc" in y:                                   # 139a layout: one file, both parts
            pd = y["ooc"]["parts"][key]
            part, clock, xdc = pd["part"], float(pd["clock_ns"]), None
        else:                                            # 139b layout: one file per part
            part, clock, xdc = y["part"], float(y["clock_ns"]), y.get("constraints")
        spec = {"name": name, "function": fn, "part": part, "top": y["top"], "sources": y["sources"], "clock_ns": clock, "generics": gen,
                "from": f"arith/{fn}/build/{var} ({key}), generics as the 160 point {re.sub(r'[ {}:]', '', str(gen))}"}
        if xdc:
            spec["xdc"] = xdc
        (OUT / f"{name}.yaml").write_text(yaml.safe_dump(spec, sort_keys=False))
        print(name, part, clock)


if __name__ == "__main__":
    main()
