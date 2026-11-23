#!/usr/bin/env python3
"""The SYSMONE4 unisim model (Vivado 2026.1) with this design's INIT values: which analog readings raise the shutdown (brief 196).

    python3 designs/b196_secure_demo/tests/run_sysmon_sim.py [--out results/b196/sysmon_sim.json] [--ns 400000]

Each scenario is a stimulus file (TIME TEMP VCCINT VCCAUX VCCBRAM, the format of the model) that holds the nominal values for the first part of the run
and then the scenario's value. xsim runs the vendor model as it is; the question each answers is "does the model, configured by our INIT values, raise
an alarm for this reading, and does the latch hold it". It is the vendor's model, not silicon: the real part's ADC error (DS925 Table 127) is not in it.
No hardware, no Vivado implementation: a simulation only."""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

D = Path(__file__).resolve().parents[1]
ROOT = D.parents[1]
sys.path.insert(0, str(ROOT))
from flow import assurance, security  # noqa: E402

NOMINAL = {"temp": 60.0, "vccint": 0.72, "vccaux": 1.80, "vccbram": 0.85}
#: (name, field, reading, expect shutdown); limits from boards/kr260/board.yaml operating_limits
SCENARIOS = [("nominal", "temp", 60.0, False),
             ("temp 85.0 (the limit)", "temp", 85.0, False), ("temp 86.5", "temp", 86.5, True), ("temp 100", "temp", 100.0, True),
             ("vccint 0.700", "vccint", 0.700, False), ("vccint 0.690", "vccint", 0.690, True),
             ("vccint 0.740", "vccint", 0.740, False), ("vccint 0.750", "vccint", 0.750, True),
             ("vccaux 1.750", "vccaux", 1.750, False), ("vccaux 1.730", "vccaux", 1.730, True),
             ("vccaux 1.850", "vccaux", 1.850, False), ("vccaux 1.870", "vccaux", 1.870, True),
             ("vccbram 0.830", "vccbram", 0.830, False), ("vccbram 0.810", "vccbram", 0.810, True),
             ("vccbram 0.870", "vccbram", 0.870, False), ("vccbram 0.890", "vccbram", 0.890, True)]


def model_temp(c: float) -> float:
    """The temperature to give the vendor model so that it digitises the code the data sheet's transfer function gives for ``c`` degrees.
    The model (unisims/SYSMONE4.v, adc_temp_result) uses code16 = (T + 273.15) x 0.0020358 x 65535, i.e. a 10-bit code of (T + 273.15) x 2.0846; the
    function this repository read back on the owner's board (flow/security.py: code x 501.3743 / 1024 - 273.6777) gives a different code for the same
    temperature (13 codes apart at 85 C, about 6 C). The thresholds follow the second; the model is fed the matching code. results/b196/sysmon_sim.json
    records both."""
    code = (c + security.TEMP_OFFSET) * 1024.0 / security.TEMP_SCALE
    return code / ((0.0020358 * 65535.0) / 64.0) - 273.15


def stim(field, value, at_ns):
    if field == "temp":
        value = model_temp(value)
    cols = ["temp", "vccint", "vccaux", "vccbram"]
    base = {**NOMINAL, "temp": model_temp(NOMINAL["temp"])}
    row = lambda t, d: f"{t} " + " ".join(f"{d[c]:.4f}" for c in cols)           # noqa: E731
    return "TIME TEMP VCCINT VCCAUX VCCBRAM\n" + row(0, base) + "\n" + row(at_ns, {**base, field: value}) + "\n"


def run(td: Path, field: str, value: float, ns: int, at_ns: int) -> tuple[int, int]:
    f = td / "stim.txt"
    f.write_text(stim(field, value, at_ns))
    rtl = [ROOT / "designs" / "b196_secure_demo" / "rtl" / n for n in ("b196_sysmon_pkg.sv", "b196_shutdown.sv", "b196_sysmon_guard.sv")]
    sh = (f"source {assurance.xsim_settings()} >/dev/null 2>&1; cd {td}; rm -rf xsim.dir; "
          f"xvlog -sv -d SYNTHESIS -d 'SIM_FILE=\"{f}\"' -d SIM_NS={ns} {' '.join(map(str, rtl))} {D / 'tb' / 'tb_sysmon.sv'} >/dev/null && "
          "xvlog $XILINX_VIVADO/data/verilog/src/glbl.v >/dev/null && xelab -L unisims_ver tb_sysmon glbl -s s >/dev/null 2>&1 && xsim s -R")
    r = subprocess.run(["bash", "-c", sh], capture_output=True, text=True, timeout=1800)
    m = re.search(r"RESULT (-?\d+) (\d+)", r.stdout)
    if not m:
        raise RuntimeError("no RESULT line: " + (r.stdout + r.stderr)[-400:])
    return int(m.group(1)), int(m.group(2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--ns", type=int, default=400_000)
    ap.add_argument("--at-ns", type=int, default=150_000)
    ap.add_argument("--only", help="a substring of a scenario name")
    a = ap.parse_args()
    rows, t0 = [], time.time()
    with tempfile.TemporaryDirectory() as td:
        for name, field, value, expect in SCENARIOS:
            if a.only and a.only not in name:
                continue
            t1 = time.time()
            t_first, cause = run(Path(td), field, value, a.ns, a.at_ns)
            fired = t_first >= 0
            rows.append({"scenario": name, "field": field, "reading": value, "expect_shutdown": expect, "shutdown": fired,
                         "first_shutdown_ns": t_first if fired else None, "after_step_ns": (t_first - a.at_ns) if fired else None,
                         "cause_bits": f"{cause:05b}", "ok": fired == expect and (not fired or t_first >= a.at_ns), "wall_s": round(time.time() - t1, 1)})
            print(rows[-1], flush=True)
    res = {"tool": "xsim, UNISIM model SYSMONE4 (Vivado 2026.1)", "limits_from": "boards/kr260/board.yaml operating_limits", "sim_ns": a.ns,
           "step_at_ns": a.at_ns, "nominal": NOMINAL, "init": {k: f"16'h{v:04X}" for k, v in security.sysmon_init(security.limits_of("kr260")).items()},
           "scenarios": rows, "all_ok": all(r["ok"] for r in rows), "wall_s": round(time.time() - t0, 1),
           "temperature_scale_note": "the model's own temperature transfer function differs from the one the thresholds use (13 codes, about 6 C, at 85 C); readings are given on the data-sheet scale and converted for the model (model_temp)", "limits_of_the_method": "the vendor simulation model, not silicon; no ADC error; one reading step per run"}
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    return 0 if res["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
