#!/usr/bin/env python3
"""What the unmapped-address setting costs (brief 64A2): the example map hwsw/examples/demo_accel.yaml generated with
`unmapped: okay` (the default) and with `unmapped: slverr`, each built out of context in Vivado, one after the other;
LUTs, flip-flops and WNS side by side in results/64a_hwsw/regmap_ooc.json, each run's raw reports in
results/64a_hwsw/regmap_ooc/<setting>/.

    python3 hwsw/regmap_ooc.py [--period 10]

LUT and FF counts are read from the utilisation report's slice-logic table (its "Slice LUTs" and "Slice Registers"
rows). Run it on an otherwise idle machine: Vivado runs one thread, under nice, in a memory-capped user scope
(MemoryMax=4G); a few minutes per setting. One run per setting.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hwsw import regmap  # noqa: E402

HERE = Path(__file__).resolve().parent
OOC = ROOT / "build" / "64a" / "regmap_ooc"
RAW = ROOT / "results" / "64a_hwsw" / "regmap_ooc"
MAP = HERE / "examples" / "demo_accel.yaml"
PART = "xc7a100tcsg324-1"
REPORTS = ("summary.txt", "utilization.rpt", "timing_summary.rpt", "clock.xdc")


def vivado() -> str:
    return os.environ.get("VIVADO") or subprocess.run([sys.executable, str(ROOT / "flow" / "version_pin.py"), "--vivado"],
                                                      capture_output=True, text=True, check=True).stdout.strip()


def _util(rpt: str) -> dict:
    """The 'Slice LUTs' and 'Slice Registers' used counts of report_utilization."""
    out = {}
    for key, name in (("lut", "Slice LUTs"), ("ff", "Slice Registers")):
        m = re.search(rf"^\|\s*{name}\*?\s*\|\s*(\d+)\s*\|", rpt, re.M)
        out[key] = int(m.group(1)) if m else None
    return out


def run_one(setting: str, period: float) -> dict:
    d = yaml.safe_load(MAP.read_text())
    d["unmapped"] = setting                     # the same map with the setting under test (its own hash)
    m = regmap.from_dict(d, source=f"{MAP} with unmapped: {setting}")
    d = OOC / setting
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / f"{m.name}_regs.sv").write_text(regmap.emit_sv(m))
    unit = f"fda-64a2-regmap-ooc-{setting}-{os.getpid()}"
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", "MemoryMax=4G", "nice", "-n", "15",
           vivado(), "-mode", "batch", "-nojournal", "-log", str(d / "vivado.log"),
           "-source", str(HERE / "regmap_ooc.tcl"), "-tclargs", str(d), PART, str(period), f"{m.name}_regs"]
    print(f"regmap_ooc: {setting} in scope {unit}", flush=True)
    subprocess.run(cmd, cwd=d)
    s = d / "vivado" / "summary.txt"
    if not s.exists():
        return {"status": f"error: no summary, see {d / 'vivado.log'}"}
    kv = dict(ln.split(None, 1) for ln in s.read_text().splitlines() if ln.strip())
    log = (d / "vivado.log").read_text()
    mv = re.search(r"Vivado v(\S+) \(64-bit\)\s*\n#?\s*SW Build (\d+)", log)
    (RAW / setting).mkdir(parents=True, exist_ok=True)
    for f in REPORTS:
        shutil.copy(d / "vivado" / f, RAW / setting / f)
    return {"status": "ok", "tool": f"Vivado {mv.group(1)} (build {mv.group(2)})" if mv else "Vivado (version not read)",
            "regmap_sha256": m.sha256, **_util((d / "vivado" / "utilization.rpt").read_text()),
            "wns_ns": float(kv["wns_ns"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 hwsw/regmap_ooc.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--period", type=float, default=10.0)
    ap.add_argument("--out", default=str(ROOT / "results" / "64a_hwsw" / "regmap_ooc.json"))
    a = ap.parse_args(argv)
    rec = {"schema": "regmap_ooc/1", "map": "hwsw/examples/demo_accel.yaml", "part": PART, "clock_ns": a.period,
           "date": datetime.date.today().isoformat(), "tcl": "hwsw/regmap_ooc.tcl",
           "flow": "out-of-context synth_design (clock read first), opt_design, place_design, route_design of the "
                   "generated block alone; one thread; one run per setting", "settings": {}}
    for s in ("okay", "slverr"):
        rec["settings"][s] = run_one(s, a.period)
        print(s, rec["settings"][s], flush=True)
    ok = all(v.get("status") == "ok" for v in rec["settings"].values())
    if ok:
        o, e = rec["settings"]["okay"], rec["settings"]["slverr"]
        rec["slverr_minus_okay"] = {"lut": e["lut"] - o["lut"], "ff": e["ff"] - o["ff"]}
    Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    print("wrote", a.out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
