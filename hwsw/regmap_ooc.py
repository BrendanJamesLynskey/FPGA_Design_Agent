#!/usr/bin/env python3
"""What the unmapped-address setting and the error-capture registers cost: the example map
hwsw/examples/demo_accel.yaml generated with each setting and built out of context in Vivado, one after the other;
LUTs, flip-flops and WNS side by side in a JSON record, each run's raw reports in a folder beside it.

    python3 hwsw/regmap_ooc.py [--series 64a2|64a3|73] [--period 10]

Series 64a2 (brief 64A2): `okay` and `slverr`, with no error capture (the example then had none):
results/64a_hwsw/regmap_ooc.json, raw reports in regmap_ooc/<setting>/. Series 64a3 (brief 64A3): `okay`, `slverr`
and `split`, each with no capture, and `split` with the capture registers (the new default of both):
results/64a_hwsw/regmap_ooc_split.json, raw reports in regmap_ooc_split/<setting>/.

Series 73 (brief 73): the same map under each interface profile (house, amd_compatible, strict), no setting overridden:
results/73_profiles/regmap_ooc_profiles.json, raw reports in results/73_profiles/raw/<profile>/.

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
RESULTS = ROOT / "results" / "64a_hwsw"
# series -> (record file, raw folder, {setting: (unmapped, error_capture)})
SERIES = {
    "64a2": ("regmap_ooc.json", "regmap_ooc", {"okay": ("okay", False), "slverr": ("slverr", False)}),
    "73": ("regmap_ooc_profiles.json", "raw", {"house": "house", "amd_compatible": "amd_compatible", "strict": "strict"}),
    "64a3": ("regmap_ooc_split.json", "regmap_ooc_split",
             {"okay": ("okay", False), "slverr": ("slverr", False), "split": ("split", False),
              "split_capture": ("split", True)}),
}
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


def run_one(setting: str, unmapped: str, capture: bool, period: float, raw: Path, profile: str | None = None) -> dict:
    d = yaml.safe_load(MAP.read_text())
    if profile:                                 # brief 73: the same map under a profile (the map's own `unmapped:` removed)
        d.pop("unmapped", None)
        d["profile"] = profile
        m = regmap.from_dict(d, source=f"{MAP} under profile {profile}")
    else:
        d["unmapped"] = unmapped                # the same map with the settings under test (its own hash)
        d["error_capture"] = capture
        m = regmap.from_dict(d, source=f"{MAP} with unmapped: {unmapped}, error_capture: {capture}")
    d = OOC / setting
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / f"{m.name}_regs.sv").write_text(regmap.emit_sv(m))
    unit = f"fda-regmap-ooc-{setting}-{os.getpid()}"
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
    (raw / setting).mkdir(parents=True, exist_ok=True)
    for f in REPORTS:
        shutil.copy(d / "vivado" / f, raw / setting / f)
    return {"status": "ok", "settings": regmap.settings(m) if profile else None, "tool": f"Vivado {mv.group(1)} (build {mv.group(2)})" if mv else "Vivado (version not read)",
            "regmap_sha256": m.sha256, **_util((d / "vivado" / "utilization.rpt").read_text()),
            "wns_ns": float(kv["wns_ns"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 hwsw/regmap_ooc.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--period", type=float, default=10.0)
    ap.add_argument("--series", choices=sorted(SERIES), default="64a3")
    ap.add_argument("--out", default=None, help="record file (default: the series' file under results/64a_hwsw)")
    a = ap.parse_args(argv)
    fname, rawdir, settings = SERIES[a.series]
    out = a.out or str(RESULTS / fname)
    if a.series == "73":
        RESULTS_73 = ROOT / "results" / "73_profiles"
        out = a.out or str(RESULTS_73 / fname)
        raw = RESULTS_73 / rawdir
    else:
        raw = RESULTS / rawdir
    rec = {"schema": "regmap_ooc/1", "series": a.series, "map": "hwsw/examples/demo_accel.yaml (its own `unmapped:` removed in series 73)", "part": PART,
           "clock_ns": a.period,
           "date": datetime.date.today().isoformat(), "tcl": "hwsw/regmap_ooc.tcl",
           "flow": "out-of-context synth_design (clock read first), opt_design, place_design, route_design of the "
                   "generated block alone; one thread; one run per setting", "settings": {}}
    if a.series == "73":
        for s, prof in settings.items():
            rec["settings"][s] = {"profile": prof, **run_one(s, "", False, a.period, raw, profile=prof)}
            print(s, rec["settings"][s], flush=True)
    else:
        for s, (unm, cap) in settings.items():
            rec["settings"][s] = {"unmapped": unm, "error_capture": cap, **run_one(s, unm, cap, a.period, raw)}
            print(s, rec["settings"][s], flush=True)
    ok = all(v.get("status") == "ok" for v in rec["settings"].values())
    if ok and a.series == "73":
        S = rec["settings"]
        for k in ("amd_compatible", "strict"):
            rec[f"{k}_minus_house"] = {"lut": S[k]["lut"] - S["house"]["lut"], "ff": S[k]["ff"] - S["house"]["ff"]}
    elif ok:
        S = rec["settings"]
        rec["slverr_minus_okay"] = {"lut": S["slverr"]["lut"] - S["okay"]["lut"], "ff": S["slverr"]["ff"] - S["okay"]["ff"]}
        if "split" in S:
            rec["split_minus_okay"] = {"lut": S["split"]["lut"] - S["okay"]["lut"], "ff": S["split"]["ff"] - S["okay"]["ff"]}
            rec["split_capture_minus_split"] = {"lut": S["split_capture"]["lut"] - S["split"]["lut"],
                                                "ff": S["split_capture"]["ff"] - S["split"]["ff"]}
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    print("wrote", out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
