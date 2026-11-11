#!/usr/bin/env python3
"""Table of the controller-on-pins runs (measure_io.tcl, placed and routed, xc7a100tcsg324-1, Vivado 2025.2).

    python3 make_io_table.py <dir with io_*.kv> <out md> <out json>

Per variant: what drives each output pad's buffer (flop type, whether the flop sits in the OLOGIC site), the routed clock-to-pad data path
(including the output buffer) and the slack against an output delay of 4 ns at 10 ns, and the first cell and delay of each input pin."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    d = Path(sys.argv[1])
    rows = {}
    for p in sorted(d.glob("io_*.kv")):
        r = {"out": {}, "in": {}}
        for line in p.read_text().splitlines():
            t = line.split()
            if t[0] == "OUT":
                r["out"][t[1]] = {"driver": t[2], "site": t[3].split("_")[0], "bel": t[4], **{kv.split("=")[0]: kv.split("=")[1] for kv in t[5:]}}
            elif t[0] == "IN":
                r["in"][t[1]] = {"endpoint": t[2], **{kv.split("=")[0]: kv.split("=")[1] for kv in t[3:]}}
            else:
                r[t[0]] = t[1]
        rows[p.stem] = r
    Path(sys.argv[3]).write_text(json.dumps(rows, indent=1) + "\n")
    out = ["# Controller on pins: routed (Vivado 2025.2, xc7a100tcsg324-1, 10 ns clock, output delay 4 ns max / -1 min)\n",
           "| variant | IOB property | output drivers | in an OLOGIC flop | clock-to-pad data path (ns, min..max) | levels | worst setup slack | worst hold slack |", "|---|---|---|---|---|---|---|---|"]
    for n, r in rows.items():
        o = r["out"]
        drv = sorted({v["driver"] for v in o.values()})
        packed = sum(1 for v in o.values() if v["site"].startswith("OLOGIC"))
        dp = [float(v["datapath"]) for v in o.values() if v["datapath"] != "NA"]
        lv = sorted({v["levels"] for v in o.values()})
        out.append(f"| {n} | {'TRUE' if n.endswith('_iob') else 'unset'} | {', '.join(drv)} | {packed} of {len(o)} | {min(dp):.2f}..{max(dp):.2f} | {', '.join(lv)} | {r['WS_setup']} | {r['WS_hold']} |")
    out.append("\n## Input pins: first cell of each path and routed delay (ns)\n")
    out += ["| variant | " + " | ".join(next(iter(rows.values()))["in"].keys()) + " |", "|---|" + "---|" * len(next(iter(rows.values()))["in"])]
    for n, r in rows.items():
        out.append(f"| {n} | " + " | ".join(f"{v['endpoint'].split('/')[-2] if '/' in v['endpoint'] else v['endpoint']}: {v['datapath']}" for v in r["in"].values()) + " |")
    Path(sys.argv[2]).write_text("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
