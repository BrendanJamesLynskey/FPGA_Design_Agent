#!/usr/bin/env python3
"""Collect the records of the three demonstration builds of brief 196 into results/b196 (no key material, ever).

    python3 designs/b196_secure_demo/tests/collect_records.py <plain dir> <secure dir> <debug dir>

Each argument is a copy of a build directory (designs/b196_secure_demo/build/<variant>) of: the plain build, the production_secure build, and the
production_secure build of the debug variant (ILA). Copies only the evidence files the check read (security_request.json, security_apply.txt,
security_design.txt) and summarises run.json and the utilisation. A .nky, a key or a 64-digit hex string in any copied file stops the script."""

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results" / "b196"
EVIDENCE = ("security_request.json", "security_apply.txt", "security_design.txt")   # gates.json is summarised, not copied (it carries source hashes)


def util(d: Path) -> dict:
    sys.path.insert(0, str(ROOT))
    from flow import gates
    u = gates.parse_utilization((d / "utilization.rpt").read_text())
    return {k: u.get(k) for k in ("lut", "ff", "bram_tile", "dsp") if k in u}


def main(plain: str, secure: str, debug: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rec = {"design": "designs/b196_secure_demo", "part": "xck26-sfvc784-2LV-c", "board": "kr260", "builds": {}}
    for name, d in (("plain", plain), ("secure", secure), ("debug", debug)):
        d = Path(d)
        g = json.loads((d / "gates.json").read_text())
        rj = json.loads((d / "run.json").read_text())
        b = {"variant": g.get("variant"), "gates_pass": g["pass"], "failed_gates": sorted(k for k, v in g["gates"].items() if not v),
             "gates": g["gates"], "security_gates": {k: v for k, v in g["gates"].items() if k.startswith("security_")},
             "wall_s": rj.get("wall_s"), "stages_s": rj.get("stages_s"), "utilization": util(d),
             "bitstream_bytes": (g.get("bitstream") or {}).get("bytes"), "wns_ns": (g.get("timing") or {}).get("wns_ns"),
             "vivado_version": rj.get("vivado_version"), "scope_anon_peak_mib": rj.get("scope_anon_peak_mib")}
        sec = (g["stages"].get("bitstream") or {}).get("security")
        if sec:
            b["security"] = {k: sec.get(k) for k in ("source", "switches", "findings", "handed_to_owner", "policy_conflict")}
        rec["builds"][name] = b
        for f in EVIDENCE:
            if (d / f).is_file():
                txt = (d / f).read_text(errors="replace")
                if re.search(r"\b[0-9a-fA-F]{64}\b", txt):
                    raise SystemExit(f"{d / f}: a 64-digit hex string: refusing to copy (could be key material)")
                (OUT / f"{name}_{f}").write_text(txt)
        if list(d.glob("*.nky")) or list(d.glob("*.pem")):
            print(f"{name}: key file(s) present in the build directory (left there, not copied)")
    (OUT / "demo_builds.json").write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps({k: (v["gates_pass"], v["failed_gates"], v["wall_s"]) for k, v in rec["builds"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
