#!/usr/bin/env python3
"""How eqy's open engines scale with the CRC word width (why the demonstration block is 16 bits, not the 10G design's 64).

    python3 designs/b102_managed_fcs/scripts/eqy_width_scaling.py [--timeout 120] [--out results/102_managed/eqy_width_scaling.json]

For each width the supplier's RTL (ext/reference/crc32_d16.sv with the width changed) is synthesised by Yosys for UltraScale+
(the same recipe as produce_crc_netlist.sh), flattened to plain Verilog (flow/managed_import.flatten_netlist) and proved equivalent to
its RTL with eqy under two strategies: ``sat`` (the built-in SAT) and ``sby`` with ``abc pdr``. A strategy that does not finish
within the timeout is recorded as such, not as a failure. Needs the OSS CAD Suite (FDA_OSS_CAD).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from flow import managed_import as I  # noqa: E402

REF = ROOT / "designs" / "b102_managed_fcs" / "ext" / "reference" / "crc32_d16.sv"
STRATS = {"sat": "[strategy sat]\nuse sat\ndepth 5\n", "abc_pdr": I.EQY_STRATEGY}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--widths", default="8,16,32,64")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "102_managed" / "eqy_width_scaling.json")
    ap.add_argument("--work", type=Path, default=ROOT / "build" / "102_eqy_width")
    a = ap.parse_args(argv)
    cad = os.environ.get("FDA_OSS_CAD")
    env = {**os.environ, "PATH": (f"{cad}/bin:" if cad else "") + os.environ["PATH"]}
    rows = []
    for w in (int(x) for x in a.widths.split(",")):
        d = a.work / f"w{w}"
        d.mkdir(parents=True, exist_ok=True)
        src = REF.read_text().replace("crc32_d16", "crc32_dw").replace("[15:0]", f"[{w - 1}:0]").replace("i < 16", f"i < {w}")
        (d / "gold.sv").write_text(src)
        subprocess.run(["yosys", "-q", "-p", f"read_verilog -sv {d}/gold.sv; synth_xilinx -family xcup -top crc32_dw -flatten; write_verilog -noattr {d}/net.v"],
                       check=True, capture_output=True, env=env)
        flat = I.flatten_netlist(d / "net.v", "crc32_dw", d / "flat.v")
        row = {"width_bits": w, "luts": len(re.findall(r"\bLUT[1-6]\b", (d / "net.v").read_text()))}
        for name, strat in STRATS.items():
            r = I.eqy_prove([d / "gold.sv"], flat, "crc32_dw", d / f"eqy_{name}", strat, timeout=a.timeout)
            row[name] = {"result": "proved" if r["equivalent"] else ("not finished in the timeout" if r["equivalent"] is None else "failed"),
                         "seconds": r.get("seconds")}
            print(w, name, row[name])
        rows.append(row)
    ver = subprocess.run(["yosys", "-V"], capture_output=True, text=True, env=env).stdout.strip()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"yosys": ver, "timeout_s": a.timeout, "rows": rows,
                                 "note": "one CPU thread; the proved/not-finished split is for these two strategies on this machine"}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
