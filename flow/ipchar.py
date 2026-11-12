#!/usr/bin/env python3
"""Measure each implementation variant of an IP block with Vivado, built alone (out of context, no I/O constraints),
and write the results to ip_lib/<block>/char/<part>.json.

    python3 -m flow.ipchar fir dds_awg adc_histogram [--part xc7a100tcsg324-1] [--only dsp_bram] [--dry-run]
    python3 -m flow.ipchar fir --parse-only          # rebuild the JSON from an earlier run's reports

For each entry, every variant at every point of `characterisation.points` in its ip.yaml is synthesised, placed and
routed in one Vivado batch session (flow/ipchar.tcl), with a clock of `characterisation.clock_ns` on port `clk`. The
JSON (schema "ipchar/1", docs/ip_variants.md) holds LUT, FF, LUT RAM, SRL, block RAM, DSP, WNS at the target clock, an
Fmax estimate (1000 / (period - WNS)), vectorless power, and the variant's latency and II from ip.yaml. Run
directories: build/ipchar/<block>/<variant>_<point>/.

Each point takes a few minutes and up to about 6 GB of memory: run one characterisation at a time. The Vivado session
runs with one thread, under nice, in a memory-capped user scope (MemoryMax=6G).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flow import ipvariants as iv  # noqa: E402

BUILD = ROOT / "build" / "ipchar"


def vivado() -> str:
    return os.environ.get("VIVADO") or subprocess.run([sys.executable, str(ROOT / "flow" / "version_pin.py"), "--vivado"],
                                                      capture_output=True, text=True, check=True).stdout.strip()


def point_id(p: dict) -> str:
    return "_".join(f"{k}{v}" for k, v in sorted(p.items()))


def jobs(block: str, part: str, only: set[str]) -> list[dict]:
    y = yaml.safe_load((iv.IP / block / "ip.yaml").read_text())
    ch, vp = y["characterisation"], y.get("variant_param")
    out = []
    for name in y["variants"]:
        if only and name not in only:
            continue
        for pt in ch["points"]:
            full = iv.point(block, pt, name)
            params = {k: v for k, v in full.items() if k != vp}
            gen = {k: (f'"{v}"' if isinstance(v, str) else v) for k, v in full.items()}
            out.append({"block": block, "variant": name, "params": params, "generics": gen, "top": y["top"],
                        "clock_ns": ch["clock_ns"], "wd": BUILD / block / f"{name}_{point_id(params)}",
                        "sources": [str(iv.IP / block / f) for f in y["rtl"]]})
    return out


def tcl_list(items) -> str:
    return "{" + " ".join(tcl_word(i) for i in items) + "}"


def tcl_word(v) -> str:
    if isinstance(v, (list, tuple)):
        return tcl_list(v)
    s = str(v)
    return "{" + s + "}" if (not s or re.search(r'[\s"{}$\[\]\\;]', s)) else s


def write_jobs(js: list[dict], part: str, path: Path) -> None:
    srcs = sorted({s for j in js for s in j["sources"]})
    lines = [f"set ipchar(part) {part}", f"set ipchar(sources) {tcl_list(srcs)}", "set ipchar(jobs) {}"]
    for j in js:
        g = [x for k, v in j["generics"].items() for x in (k, v)]
        lines.append("lappend ipchar(jobs) " + tcl_list([f"{j['block']}/{j['wd'].name}", j["top"], str(j["wd"]),
                                                          j["clock_ns"], g]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")



# ---- report parsing ------------------------------------------------------------------------------------------------
def _row(txt: str, label: str):
    m = re.search(rf"^\|\s*{re.escape(label)}\*?\s*\|\s*([\d.]+)", txt, re.M)
    if not m:
        return None
    return float(m.group(1)) if "." in m.group(1) else int(m.group(1))


def parse(wd: Path, clock_ns: float) -> dict:
    if (wd / "error.txt").exists():
        return {"status": "error: " + (wd / "error.txt").read_text().strip().splitlines()[0][:300]}
    if not (wd / "done.txt").exists():
        return {"status": "not run"}
    u = (wd / "utilization.rpt").read_text()
    r = {"status": "ok",
         "lut": _row(u, "Slice LUTs") if _row(u, "Slice LUTs") is not None else _row(u, "CLB LUTs"),
         "ff": _row(u, "Slice Registers") if _row(u, "Slice Registers") is not None else _row(u, "CLB Registers"),
         "lutram": _row(u, "LUT as Distributed RAM"), "srl": _row(u, "LUT as Shift Register"),
         "bram_tiles": _row(u, "Block RAM Tile"), "ramb36": _row(u, "RAMB36/FIFO"), "ramb18": _row(u, "RAMB18"),
         "dsp": _row(u, "DSPs")}
    t = (wd / "timing_summary.rpt").read_text()
    m = re.search(r"WNS\(ns\)\s+TNS\(ns\).*?\n\s*-+.*?\n\s*(-?\d+\.\d+)", t, re.S)
    r["wns_ns"] = float(m.group(1)) if m else None
    r["fmax_mhz"] = round(1000.0 / (clock_ns - r["wns_ns"]), 1) if r["wns_ns"] is not None else None
    p = (wd / "power.rpt").read_text()
    pw = {}
    for key, label in (("total", "Total On-Chip Power (W)"), ("dynamic", "Dynamic (W)"), ("static", "Device Static (W)")):
        m = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*([\d.]+)", p)
        pw[key] = float(m.group(1)) if m else None
    m = re.search(r"\|\s*Confidence Level\s*\|\s*(\w+)", p)
    pw["confidence"] = m.group(1) if m else None
    r["power_w"] = pw
    return r


def tool_version() -> str:
    """The Vivado version and build from the newest batch log."""
    for log in sorted(BUILD.glob("batch_*/vivado.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        m = re.search(r"Vivado v(\S+) \(64-bit\)\s*\n#?\s*SW Build (\d+)", log.read_text())
        if m:
            return f"Vivado {m.group(1)} (build {m.group(2)})"
    return "Vivado (version not read)"


def record(block: str, part: str, js: list[dict]) -> Path:
    y = yaml.safe_load((iv.IP / block / "ip.yaml").read_text())
    ch = y["characterisation"]
    f = iv.char_file(block, part)
    old = json.loads(f.read_text()) if f.exists() else {"results": []}
    rows = {(r["variant"], json.dumps(r["params"], sort_keys=True)): r for r in old["results"]}
    for j in js:
        r = {"variant": j["variant"], "params": j["params"], **parse(j["wd"], j["clock_ns"])}
        pr = iv.predict(block, j["variant"], j["params"])
        r["latency"], r["ii"] = pr.get("latency"), pr.get("ii")
        if r["status"] != "not run":
            rows[(j["variant"], json.dumps(j["params"], sort_keys=True))] = r
    out = {"schema": iv.SCHEMA, "block": block, "version": y["version"], "part": part, "clock_ns": ch["clock_ns"],
           "tool": tool_version() if js else old.get("tool"),
           "date": datetime.date.today().isoformat(),
           "flow": "out-of-context synth_design, opt_design, place_design, route_design; one thread; clock on port clk "
                   "only (I/O paths unconstrained); Fmax = 1000 / (period - WNS) after routing, an estimate from one "
                   "run at the target clock; power: report_power, vectorless, default toggle rates",
           "results": sorted(rows.values(), key=lambda r: (list(y["variants"]).index(r["variant"]),
                                                            [r["params"][k] for k in sorted(r["params"])]))}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1) + "\n")
    return f


def run(blocks: list[str], part: str, only: set[str], dry: bool) -> int:
    js = [j for b in blocks for j in jobs(b, part, only)]
    batch = BUILD / ("batch_" + "_".join(blocks))
    write_jobs(js, part, batch / "jobs.tcl")
    print(f"ipchar: {len(js)} jobs ({', '.join(blocks)}) listed in {batch / 'jobs.tcl'}")
    if dry:
        return 0
    for j in js:                                  # a rerun must not inherit an earlier run's verdict
        for marker in ("done.txt", "error.txt"):
            (j["wd"] / marker).unlink(missing_ok=True)
    unit = f"fda-ipchar-{os.getpid()}"
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", "MemoryMax=6G", "nice", "-n", "15",
           vivado(), "-mode", "batch", "-nojournal", "-log", str(batch / "vivado.log"),
           "-source", str(ROOT / "flow" / "ipchar.tcl"), "-tclargs", str(batch / "jobs.tcl")]
    print(f"ipchar: running {len(js)} jobs in one Vivado session (memory-capped scope {unit})")
    rc = subprocess.run(cmd, cwd=batch).returncode
    for b in blocks:
        print("ipchar: wrote", record(b, part, [j for j in js if j["block"] == b]).relative_to(ROOT))
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python3 -m flow.ipchar",
        description="Measure each implementation variant of an IP block with Vivado (built alone, no I/O constraints) "
                    "and write ip_lib/<block>/char/<part>.json. Each point takes minutes: run one at a time.")
    ap.add_argument("blocks", nargs="+", help="library entries to measure, e.g. fir dds_awg")
    ap.add_argument("--part", default=iv.DEFAULT_PART, help=f"device part (default {iv.DEFAULT_PART})")
    ap.add_argument("--only", default="", help="comma-separated variant names; rows of other variants are kept")
    ap.add_argument("--dry-run", action="store_true", help="list the jobs, run nothing")
    ap.add_argument("--parse-only", action="store_true", help="rebuild the JSON from earlier reports, run nothing")
    a = ap.parse_args(argv)
    only = set(filter(None, a.only.split(",")))
    if a.parse_only:
        for b in a.blocks:
            print("ipchar: wrote", record(b, a.part, jobs(b, a.part, only)).relative_to(ROOT))
        return 0
    return run(a.blocks, a.part, only, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
