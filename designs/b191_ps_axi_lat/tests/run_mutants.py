#!/usr/bin/env python3
"""Seeded-fault run for the latency probe (brief 191): every mutant below must be killed by tests/b191_cocotb.py.

    python3 designs/b191_ps_axi_lat/tests/run_mutants.py [--json results/191_trading_variants/mutation_probe.json]

Each mutant replaces `old` (exactly once) by `new` in a copy of rtl/ (the real RTL is never touched) and runs tests/test_b191_rtl.py against the copy. Killed: the bench fails. Survived: it passes.
Invalid: the copy does not build. The unmutated RTL must pass first. Sim-only (Icarus)."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

D = Path(__file__).resolve().parents[1]
ROOT = D.parents[1]
WORK = ROOT / "build" / "b191_mut"

MUTANTS = [
    ("cnt_one_late", "12'h010: rd_val = cnt;", "12'h010: rd_val = cnt + 32'd1;", "a read of CNT returns the clock after the request was accepted"),
    ("wr_ts_one_late", "wr_ts <= cnt; wr_n <= wr_n + 32'd1;", "wr_ts <= cnt + 32'd1; wr_n <= wr_n + 32'd1;", "the write stamp is one clock late"),
    ("log_uses_old_stamp", "log_mem[log_n[LW-1:0]] <= cnt;", "log_mem[log_n[LW-1:0]] <= wr_ts;", "TRIG logs the stamp of the write before it"),
    ("partial_strobe_ok", "(c_strb != 4'hF) ||", "", "a write with a partial strobe takes effect"),
    ("log_overwrites", "log_n < 32'(LOG_DEPTH)", "log_n <= 32'(LOG_DEPTH)", "a full log wraps and overwrites its first entry"),
    ("bad_read_not_counted", "+ 32'(rd_fire && rd_bad);", "+ 32'd0;", "a bad read is answered SLVERR but not counted"),
    ("w_first_loses_data", "c_data  = w_p  ? w_data  : wdata;", "c_data  = wdata;", "when W comes before AW the data is taken from the idle W bus"),
    ("bid_not_echoed", "bvalid <= 1'b1; bid <= c_id;", "bvalid <= 1'b1; bid <= '0;", "the write response carries no id"),
    ("rid_not_echoed", "r_id_q <= arid;", "r_id_q <= '0;", "the read response carries no id"),
    ("clear_keeps_count", "begin log_n <= '0; wr_n <= '0; end", "begin log_n <= '0; end", "CTRL.CLEAR leaves the write count"),
    ("unmapped_write_ok", "|| !(w_off == 12'h00C || w_off == 12'h020 || w_off == 12'h024);", ";", "a write to an unmapped address is answered OKAY and not counted"),
    ("scratch_ignored", "if (w_off == 12'h00C) scratch <= c_data;", "if (w_off == 12'h00C) scratch <= scratch;", "SCRATCH keeps its old value"),
]


def run(rtl: Path, root: Path) -> str:
    env = dict(os.environ, B191_RTL_DIR=str(rtl), FDA_SIM_BUILD_ROOT=str(root), PYTHONPATH=str(ROOT))
    env.pop("B191_RECORD", None)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(D / "tests" / "test_b191_rtl.py")], cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode == 0:
        return "survived"
    return "killed" if (root / "b191_probe" / "results.xml").is_file() else "invalid"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    if run(D / "rtl", WORK / "baseline") != "survived":
        print("the unmutated RTL does not pass")
        return 2
    src = (D / "rtl" / "axi_lat_probe.sv").read_text()
    res = []
    for name, old, new, why in MUTANTS:
        if src.count(old) != 1:
            print(name, "does not apply exactly once")
            return 2
        d = WORK / name / "rtl"
        shutil.copytree(D / "rtl", d)
        (d / "axi_lat_probe.sv").write_text(src.replace(old, new))
        res.append({"name": name, "why": why, "status": run(d, WORK / name / "sim")})
        print(f"{res[-1]['status']:9s} {name}", flush=True)
    valid = [r for r in res if r["status"] != "invalid"]
    out = {"mutants": len(res), "valid": len(valid), "killed": sum(r["status"] == "killed" for r in valid), "survived": [r["name"] for r in valid if r["status"] == "survived"],
           "invalid": [r["name"] for r in res if r["status"] == "invalid"], "results": res}
    out["score_pct"] = round(100 * out["killed"] / max(1, len(valid)), 1)
    print(f"killed {out['killed']} of {len(valid)} ({out['score_pct']} %); survived: {out['survived']}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2) + "\n")
    return 0 if not out["survived"] else 1


if __name__ == "__main__":
    sys.exit(main())
