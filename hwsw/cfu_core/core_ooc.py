#!/usr/bin/env python3
"""What the custom-instruction unit costs the core: an out-of-context Vivado build of the BRV32P SoC for the baseline
and each patched configuration that run_bench.py prepared, one after the other, and their LUT, FF and Fmax estimate
side by side in results/64a_hwsw/core_ooc.json, with each run's raw reports in results/64a_hwsw/core_ooc/<config>/.

    python3 hwsw/cfu_core/run_bench.py            # first: prepares build/64a/cfu/<config>/
    python3 hwsw/cfu_core/core_ooc.py [--configs baseline,cfu_word,cfu_byte,cfu_word_keep] [--period 10]

A configuration name ending in _keep builds the same RTL as the name without it, with the library unit's hierarchy
kept in synthesis (CFU_KEEP_UNIT): no logic can move across the unit's boundary, which separates the unit's own logic
from what synthesis merged into it from the core.

Run it on an otherwise idle machine: Vivado runs one thread, under nice, in a memory-capped user scope (MemoryMax=6G),
about 3 GB at peak and some 15 minutes per configuration. The Fmax figure is 1000 / (period - WNS) from one routed
run at the target clock: an estimate, not a closure, and one place-and-route seed only.
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

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = Path(os.environ.get("CFU_BUILD", ROOT / "build" / "64a" / "cfu"))
OOC = ROOT / "build" / "64a" / "ooc"
RAW = ROOT / "results" / "64a_hwsw" / "core_ooc"
REPORTS = ("summary.txt", "utilization_hier.rpt", "timing_summary.rpt", "critical_path.rpt", "clock.xdc")
PART = "xc7a100tcsg324-1"


def vivado() -> str:
    return os.environ.get("VIVADO") or subprocess.run([sys.executable, str(ROOT / "flow" / "version_pin.py"), "--vivado"],
                                                      capture_output=True, text=True, check=True).stdout.strip()


def run_one(cfg: str, period: float) -> dict:
    keep = cfg.endswith("_keep")
    src = BUILD / (cfg[:-len("_keep")] if keep else cfg)
    if not (src / "rtl").is_dir():
        raise SystemExit(f"{src} missing: run hwsw/cfu_core/run_bench.py first")
    d = OOC / cfg                                                    # a copy: run_bench.py may rebuild its folders meanwhile
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(src / "rtl", d / "rtl")
    shutil.copy(src / "prog" / "crc.hex", d / "firmware.hex")        # the SRAM's initial image (block RAM init only)
    if (d / "rtl" / "cfu" / "cfu_crc32_step.sv").exists():
        shutil.copy(ROOT / "ip_lib" / "crc32_step" / "rtl" / "crc32_step.sv", d / "rtl" / "cfu" / "crc32_step.sv")
    unit = f"fda-64a-ooc-{cfg}-{os.getpid()}"
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", "MemoryMax=6G", "nice", "-n", "15",
           vivado(), "-mode", "batch", "-nojournal", "-log", str(d / "vivado.log"),
           "-source", str(HERE / "core_ooc.tcl"), "-tclargs", str(d), PART, str(period), "CFU_KEEP_UNIT" if keep else ""]
    print(f"core_ooc: {cfg} in scope {unit}", flush=True)
    subprocess.run(cmd, cwd=d)
    rec = parse(d)
    if rec["status"] == "ok":                                         # the raw reports the record is read from
        (RAW / cfg).mkdir(parents=True, exist_ok=True)
        for f in REPORTS:
            shutil.copy(d / "vivado" / f, RAW / cfg / f)
    return rec


def _hier(rpt: str) -> dict:
    """Rows of report_utilization -hierarchical: instance -> {lut, lutram, ff, ramb36, ramb18, dsp}."""
    out = {}
    for ln in rpt.splitlines():
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) == 10 and c[2].isdigit():
            out[c[0]] = {"lut": int(c[2]), "lutram": int(c[4]), "ff": int(c[6]), "ramb36": int(c[7]),
                         "ramb18": int(c[8]), "dsp": int(c[9])}
    return out


def parse(d: Path) -> dict:
    s = d / "vivado" / "summary.txt"
    if not s.exists():
        return {"status": f"error: no summary, see {d / 'vivado.log'}"}
    kv = dict(ln.split(None, 1) for ln in s.read_text().splitlines() if ln.strip())
    h = _hier((d / "vivado" / "utilization_hier.rpt").read_text())
    log = (d / "vivado.log").read_text()
    m = re.search(r"Vivado v(\S+) \(64-bit\)\s*\n#?\s*SW Build (\d+)", log)
    top = h["brv32p_soc"]
    return {"status": "ok", "tool": f"Vivado {m.group(1)} (build {m.group(2)})" if m else "Vivado (version not read)",
            "wns_ns": float(kv["wns_ns"]), "fmax_mhz": float(kv["fmax_mhz"]), "soc": top, "core": h["u_core"],
            "cfu": h.get("u_cfu"), "cfu_unit": h.get("u_unit"),
            "synthesis_define": kv.get("define", "none")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 hwsw/cfu_core/core_ooc.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--configs", default="baseline,cfu_word,cfu_byte")
    ap.add_argument("--period", type=float, default=10.0)
    ap.add_argument("--out", default=str(ROOT / "results" / "64a_hwsw" / "core_ooc.json"))
    ap.add_argument("--parse-only", action="store_true", help="rebuild the record from earlier runs' reports")
    a = ap.parse_args(argv)
    out = Path(a.out)
    rec = json.loads(out.read_text()) if out.exists() else {"configs": {}}
    rec.update({"schema": "core_ooc/1", "part": PART, "clock_ns": a.period, "date": datetime.date.today().isoformat(),
                "flow": "out-of-context synth_design (the clock constraint read first, so synthesis is timing "
                        "driven), opt_design, place_design, route_design of the whole SoC (core, caches, 32 KB SRAM, "
                        "peripherals); one thread; one run per configuration; Fmax = 1000 / (period - WNS), an "
                        "estimate from one routed run at the target clock; raw reports in results/64a_hwsw/core_ooc/",
                "tcl": "hwsw/cfu_core/core_ooc.tcl"})
    for cfg in [c for c in a.configs.split(",") if c]:
        rec["configs"][cfg] = parse(OOC / cfg) if a.parse_only else run_one(cfg, a.period)
        print(cfg, rec["configs"][cfg], flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rec, indent=1) + "\n")
    return 0 if all(c.get("status") == "ok" for c in rec["configs"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
