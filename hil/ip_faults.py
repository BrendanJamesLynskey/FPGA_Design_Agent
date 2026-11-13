#!/usr/bin/env python3
"""Seeded-fault runner for the brief-30 instrument library.

    python3 hil/ip_faults.py [--only name,name] [--json results/b30/faults.json]
    python3 hil/ip_faults.py --blocks fir --json results/b63a/faults.json      # other library entries

Each ip_lib/<block>/faults.yaml entry replaces one exact string (it must occur once) in a copy of the block's rtl/;
the block's tests (`test` = pytest node selection) are then run against the copy through HIL_RTL_<BLOCK>. A fault is
caught when the tests fail. The real RTL is never touched. Needs cocotb, Icarus and pytest, like the tests.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IP = ROOT / "ip_lib"
BLOCKS = ["freq_duty_counter", "frame_crc", "dds_awg", "logic_analyser", "adc_histogram"]


def faults(blocks=BLOCKS):
    for f in sorted(IP.glob("*/faults.yaml")):
        block = f.parent.name
        if block not in blocks:
            continue
        y = yaml.safe_load(f.read_text())
        if y.get("runner") != "hil/ip_faults.py":
            raise SystemExit(f"{f}: declares runner {y.get('runner')!r}, not hil/ip_faults.py")
        for m in y["faults"]:
            yield block, m


def run_one(block: str, m: dict, tmp: Path) -> dict:
    d = tmp / f"{block}_{m['name']}"
    shutil.copytree(IP / block / "rtl", d)
    src = d / m["file"]
    text = src.read_text()
    for e in m.get("edits") or [{"old": m["old"], "new": m["new"]}]:     # one edit, or several applied together
        n = text.count(e["old"])
        if n != 1:
            return {"name": m["name"], "block": block, "status": "invalid", "why": f"old string occurs {n} times"}
        text = text.replace(e["old"], e["new"])
    src.write_text(text)
    env = dict(os.environ, **{f"HIL_RTL_{block.upper()}": str(d)}, HIL_BUILD=str(tmp / "build"))
    t0 = time.time()
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *m["test"].split(" -k ")[0].split(), "-k", m["test"].split(" -k ")[1]]
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=1800)
    tail = (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]
    if "iverilog failed" in r.stdout or ("CalledProcessError" in r.stdout and "iverilog" in r.stdout):
        return {"name": m["name"], "block": block, "status": "invalid", "why": "the faulty copy does not compile"}
    return {"name": m["name"], "block": block, "class": m.get("class"), "why": m.get("why"),
            "status": "caught" if r.returncode != 0 else "SURVIVED", "seconds": round(time.time() - t0, 1),
            "pytest": tail[0]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--blocks", default="", help="comma-separated ip_lib entries (default: the brief-30 instruments)")
    a = ap.parse_args()
    blocks = [b for b in a.blocks.split(",") if b] or BLOCKS
    only = set(filter(None, a.only.split(",")))
    out = []
    with tempfile.TemporaryDirectory(prefix="b30faults_") as t:
        for block, m in faults(blocks):
            if only and m["name"] not in only:
                continue
            res = run_one(block, m, Path(t))
            print(f"{res['status']:9s} {block:16s} {m['name']}  {res.get('pytest', res.get('why'))}", flush=True)
            out.append(res)
    caught = sum(r["status"] == "caught" for r in out)
    valid = sum(r["status"] != "invalid" for r in out)
    summary = {"caught": caught, "valid": valid, "faults": out}
    print(f"caught {caught} of {valid}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(summary, indent=1) + "\n")
    return 0 if caught == valid and valid == len(out) else 1


if __name__ == "__main__":
    sys.exit(main())
