#!/usr/bin/env python3
"""Seeded-fault runner for the packet-processing library (brief 40).

    python3 flow/net/faults.py [--only name,name] [--json results/b40/faults.json]

Each ip_lib/<block>/faults.yaml entry replaces one exact string (it must occur once) in a copy of the block's rtl/;
the block's tests (`test` = pytest node selection, optionally followed by " -k <expression>") are then run against the
copy through NET_RTL_<BLOCK>. A fault is caught when the tests fail. The real RTL is never touched. Needs scapy, Icarus
and pytest, like the tests. Only blocks whose faults.yaml declares `runner: flow/net/faults.py` are run here; the others
belong to their declared runner (hil/ip_faults.py), whose testbenches do not read NET_RTL_<BLOCK>.
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

ROOT = Path(__file__).resolve().parents[2]
IP = ROOT / "ip_lib"


RUNNER = "flow/net/faults.py"


def faults():
    for f in sorted(IP.glob("*/faults.yaml")):
        block = f.parent.name
        y = yaml.safe_load(f.read_text())
        if "runner" not in y:
            raise SystemExit(f"{f}: no `runner:` field (flow/net/faults.py or hil/ip_faults.py)")
        if y["runner"] != RUNNER:
            continue
        for m in y["faults"]:
            yield block, m


def pytest_args(test: str) -> list[str]:
    """`path[::node] ... [-k expression]`: the expression may contain spaces ("-k a and b")."""
    paths, _, expr = test.partition(" -k ")
    return paths.split() + (["-k", expr.strip()] if expr.strip() else [])


def run_one(block: str, m: dict, tmp: Path) -> dict:
    d = tmp / f"{block}_{m['name']}"
    shutil.copytree(IP / block / "rtl", d)
    src = d / m["file"]
    text = src.read_text()
    n = text.count(m["old"])
    if n != 1:
        return {"name": m["name"], "block": block, "status": "invalid", "why": f"old string occurs {n} times"}
    src.write_text(text.replace(m["old"], m["new"]))
    env = dict(os.environ, **{f"NET_RTL_{block.upper()}": str(d)}, NET_BUILD=str(tmp / "build"))
    t0 = time.time()
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *pytest_args(m["test"])]
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
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    out = []
    with tempfile.TemporaryDirectory(prefix="b40faults_") as t:
        for block, m in faults():
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
