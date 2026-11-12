#!/usr/bin/env python3
"""Formal proof of the brief 59A rule checkers (SymbiYosys, Yosys 0.33, z3), in the mutation style of brief 05k.

For axil_rules (9 rules) and axis_rules (5 rules), against the property restatements in formal_axil_rules.sv and
formal_axis_rules.sv:
  quiet     bounded proof: on legal traffic (every rule assumed to hold, resets anywhere) the checker never fires
  seed k    bounded proof: with every rule but k assumed, whenever rule k is broken the checker flags k, and only k;
            plus a cover that reaches a broken rule k flagged (so the proof is not vacuous)
Then the checker is mutated and each mutant must fail the proof that targets it:
  off k        viol[k] tied low                        -> seed k must fail
  unguard k    the reset guard (live / aresetn) removed -> quiet must fail
  payload k    (hold rules) the payload comparison removed, only a VALID drop counted -> seed k must fail

    python3 axi_tx/formal/run_formal.py [--depth 20] [--json results/59a_axi_tx/formal.json]
Needs sby, yosys and z3 on PATH (locally: source ~/.local/opt/formal-deb/env.sh; CI: apt yosys z3 + pinned sby).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
RTL = ROOT / "axi_tx" / "rtl"
OUT = ROOT / "build" / "59a" / "formal"
UNITS = {
    "axil": {"rtl": "axil_rules.sv", "harness": "formal_axil_rules.sv", "top": "formal_axil_rules", "n": 9,
             "hold": [0, 1, 2, 3, 4]},
    "axis": {"rtl": "axis_rules.sv", "harness": "formal_axis_rules.sv", "top": "formal_axis_rules", "n": 5, "hold": [0]},
}
VIOL = re.compile(r"^(\s*viol\[(\d)\]\s*=\s*)(.*);(.*)$")


def sby_text(unit: dict, define: str, mode: str, depth: int) -> str:
    return f"""[options]
mode {mode}
depth {depth}

[engines]
smtbmc z3

[script]
read_verilog -formal -sv {unit['rtl']}
read_verilog -formal -sv {define} {unit['harness']}
prep -top {unit['top']}

[files]
{unit['rtl']}
{HERE / unit['harness']}
"""


def run_job(name: str, unit: dict, rtl_text: str, define: str, mode: str, depth: int) -> dict:
    d = OUT / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / unit["rtl"]).write_text(rtl_text)
    (d / "job.sby").write_text(sby_text(unit, define, mode, depth).replace(f"\n{unit['rtl']}\n", f"\n{d / unit['rtl']}\n"))
    t0 = time.time()
    p = subprocess.run(["sby", "-f", "-d", str(d / "run"), str(d / "job.sby")], capture_output=True, text=True, cwd=d)
    status = (d / "run" / "status").read_text().split()[0] if (d / "run" / "status").exists() else "ERROR"
    (d / "sby.log").write_text(p.stdout + p.stderr)
    return {"job": name, "mode": mode, "status": status, "seconds": round(time.time() - t0, 1)}


def mutants(text: str, unit: dict) -> list[tuple[str, int, str, str]]:
    """(kind, rule, mutated text, proof that must fail)."""
    lines = text.splitlines(keepends=True)
    out = []
    for i, line in enumerate(lines):
        m = VIOL.match(line.rstrip("\n"))
        if not m:
            continue
        k, expr = int(m.group(2)), m.group(3)
        def sub(new_expr: str) -> str:
            return "".join(lines[:i] + [f"{m.group(1)}{new_expr};{m.group(4)}\n"] + lines[i + 1:])
        out.append(("off", k, sub("1'b0"), f"seed{k}"))
        g = re.sub(r"^(live|aresetn) && ", "", expr)
        if g != expr:
            out.append(("unguard", k, sub(g), "quiet"))
        if k in unit["hold"]:
            p = re.sub(r"\(!(\w+)\s*\|\|.*\)$", r"(!\1)", expr)
            if p != expr:
                out.append(("payload", k, sub(p), f"seed{k}"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--depth", type=int, default=20)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--unit", choices=list(UNITS))
    a = ap.parse_args(argv)
    res: dict = {"depth": a.depth, "tool": subprocess.run(["yosys", "-V"], capture_output=True, text=True).stdout.strip(),
                 "units": {}}
    ok = True
    for uname, unit in UNITS.items():
        if a.unit and uname != a.unit:
            continue
        text = (RTL / unit["rtl"]).read_text()
        u = {"proofs": [], "mutants": []}
        u["proofs"].append(run_job(f"{uname}_quiet", unit, text, "-DQUIET", "bmc", a.depth) | {"expect": "PASS"})
        for k in range(unit["n"]):
            u["proofs"].append(run_job(f"{uname}_seed{k}", unit, text, f"-DSEED={k}", "bmc", a.depth) | {"expect": "PASS"})
            u["proofs"].append(run_job(f"{uname}_seed{k}_cover", unit, text, f"-DSEED={k}", "cover", a.depth) | {"expect": "PASS"})
        for kind, k, mtext, proof in mutants(text, unit):
            define = "-DQUIET" if proof == "quiet" else f"-DSEED={k}"
            r = run_job(f"{uname}_mut_{kind}{k}", unit, mtext, define, "bmc", a.depth)
            u["mutants"].append(r | {"kind": kind, "rule": k, "proof": proof, "expect": "FAIL"})
        for r in u["proofs"] + u["mutants"]:
            r["ok"] = r["status"] == r["expect"]
            ok &= r["ok"]
            print(f"{r['job']:28s} {r['status']:6s} (expect {r['expect']}) {r['seconds']:6.1f}s {'ok' if r['ok'] else 'WRONG'}")
            if r["status"] == "ERROR":
                print("  " + (OUT / r["job"] / "sby.log").read_text()[-600:].replace("\n", "\n  "))
        u["summary"] = {"proofs_pass": sum(r["ok"] for r in u["proofs"]), "proofs": len(u["proofs"]),
                        "mutants_killed": sum(r["ok"] for r in u["mutants"]), "mutants": len(u["mutants"])}
        res["units"][uname] = u
    res["all_ok"] = ok
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res, indent=1) + "\n")
    print("formal:", "all as expected" if ok else "MISMATCH", {k: v["summary"] for k, v in res["units"].items()})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
