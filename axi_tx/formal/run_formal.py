#!/usr/bin/env python3
"""Formal proof of the brief 59A rule checkers (SymbiYosys, Yosys 0.33, z3), in the mutation style of brief 05k.

For axil_rules (9 rules) and axis_rules (5 rules), against the property restatements in formal_axil_rules.sv and
formal_axis_rules.sv:
  quiet     bounded proof: on legal traffic (every rule assumed to hold, resets anywhere) the checker never fires
  seed k    bounded proof: with every rule but k assumed, whenever rule k is broken the checker flags k, and only k;
            plus a cover that reaches a broken rule k flagged (so the proof is not vacuous)
Then the checker is mutated, and every mutant must make at least one proof fail. Structural mutants: rule k tied low
(off), its reset guard removed (unguard), a hold rule's payload comparison removed (payload). Semantic mutants change a
rule's logic: a counter on the wrong handshake, a wrong response code, one payload field left out, a wrong cycle of history
(SEMANTIC). Every mutant runs against the quiet proof and its rule's seed proof; one that survives both runs against every
other seed proof, and is reported as surviving if none fails.

    python3 axi_tx/formal/run_formal.py [--depth 20] [--mutant-depth 12] [--jobs 2] [--json results/59a_axi_tx/formal.json]
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
RTL = ROOT / "axi_tx" / "rtl"
OUT = ROOT / "build" / "59a" / "formal"
UNITS = {
    "axil": {"rtl": "axil_rules.sv", "harness": "formal_axil_rules.sv", "top": "formal_axil_rules", "n": 10,
             "hold": [0, 1, 2, 3, 4]},
    "axis": {"rtl": "axis_rules.sv", "harness": "formal_axis_rules.sv", "top": "formal_axis_rules", "n": 5, "hold": [0]},
}
VIOL = re.compile(r"^(\s*viol\[(\d)\]\s*=\s*)(.*);(.*)$")
#: semantic mutants, which change the logic of one rule: (unit, name, rule, text in the RTL, replacement)
SEMANTIC = [
    ("axil", "b_early_aw_only", 5, "(aw_pend == '0 || w_pend == '0)", "(aw_pend == '0)"),
    ("axil", "w_pend_counts_aw", 5, "w_pend  <= upd(w_pend,  whs,  bhs);", "w_pend  <= upd(w_pend,  awhs,  bhs);"),
    ("axil", "ar_pend_dec_on_rvalid", 6, "ar_pend <= upd(ar_pend, arhs, rhs);", "ar_pend <= upd(ar_pend, arhs, rvalid);"),
    ("axil", "exokay_wrong_code", 8, "(bvalid && bresp == 2'b01)", "(bvalid && bresp == 2'b10)"),
    ("axil", "w_hold_no_wstrb", 1, " || wstrb  != p_wstrb", ""),
    ("axil", "aw_hold_no_prot", 0, " || awprot != p_awprot", ""),
    ("axil", "r_hold_no_resp", 4, " || rresp  != p_rresp", ""),
    ("axil", "b_hold_ignores_ready", 2, "p_bv  && !p_br  &&", "p_bv  &&"),
    ("axil", "reset_exit_never", 7, "aresetn && !p_rstn && (awvalid", "aresetn && !aresetn && (awvalid"),
    ("axil", "reset_exit_no_wvalid", 7, "!p_rstn && (awvalid || wvalid || arvalid)", "!p_rstn && (awvalid || arvalid)"),
    ("axil", "in_reset_first_cycle", 9, "!aresetn && !p_rstn &&", "!aresetn &&"),
    ("axil", "in_reset_no_bvalid", 9, "!p_rstn && (awvalid || wvalid || bvalid || arvalid || rvalid)", "!p_rstn && (awvalid || wvalid || arvalid || rvalid)"),
    ("axis", "hold_no_tlast", 0, " || tlast != p_last", ""),
    ("axis", "keep_strb_inverted", 1, "(~tkeep & tstrb)", "(tkeep & ~tstrb)"),
    ("axis", "maxlen_off_by_one", 3, "{1'b0, beats} + 1'b1 > {1'b0, maxlen}", "{1'b0, beats} > {1'b0, maxlen}"),
    ("axis", "beats_not_reset_by_tlast", 3, "else if (hs && tlast)  beats <= '0;", "else if (1'b0)  beats <= '0;"),
    ("axis", "packed_last_any_keep", 4, "(tkeep != '0) && ((tkeep & keep_p1) == '0)", "(tkeep != '0)"),
]


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
        g = re.sub(r"^!?(live|aresetn) && ", "", expr)
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
    ap.add_argument("--mutant-depth", type=int, default=12, help="BMC depth of the mutant runs (counterexamples are short)")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--unit", choices=list(UNITS))
    a = ap.parse_args(argv)
    res: dict = {"depth": a.depth, "mutant_depth": a.mutant_depth,
                 "tool": subprocess.run(["yosys", "-V"], capture_output=True, text=True).stdout.strip(), "units": {}}
    ok = True
    for uname, unit in UNITS.items():
        if a.unit and uname != a.unit:
            continue
        text = (RTL / unit["rtl"]).read_text()
        jobs = [(f"{uname}_quiet", "-DQUIET", "bmc")]
        for k in range(unit["n"]):
            jobs += [(f"{uname}_seed{k}", f"-DSEED={k}", "bmc"), (f"{uname}_seed{k}_cover", f"-DSEED={k}", "cover")]
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            proofs = list(ex.map(lambda j: run_job(j[0], unit, text, j[1], j[2], a.depth) | {"expect": "PASS"}, jobs))
        muts = [(kind, k, mtext) for kind, k, mtext, _ in mutants(text, unit)]
        for un, name, k, old, new in SEMANTIC:
            if un == uname:
                if old not in text:
                    raise SystemExit(f"semantic mutant {name}: its text is not in {unit['rtl']}")
                muts.append((name, k, text.replace(old, new, 1)))

        def campaign(m):
            kind, k, mtext = m
            structural = kind in ("off", "unguard", "payload")
            tag = f"{uname}_mut_{kind}{k}" if structural else f"{uname}_mut_{kind}"
            tried = [run_job(f"{tag}_quiet", unit, mtext, "-DQUIET", "bmc", a.mutant_depth),
                     run_job(f"{tag}_seed{k}", unit, mtext, f"-DSEED={k}", "bmc", a.mutant_depth)]
            if not any(t["status"] == "FAIL" for t in tried):
                for j in range(unit["n"]):
                    if j != k:
                        tried.append(run_job(f"{tag}_seed{j}", unit, mtext, f"-DSEED={j}", "bmc", a.mutant_depth))
                        if tried[-1]["status"] == "FAIL":
                            break
            killed = [t["job"][len(tag) + 1:] for t in tried if t["status"] == "FAIL"]
            errors = [t["job"] for t in tried if t["status"] not in ("PASS", "FAIL")]
            return {"job": tag, "kind": kind if structural else "semantic", "mutant": kind, "rule": k, "killed_by": killed,
                    "errors": errors, "status": "FAIL" if killed else ("ERROR" if errors else "PASS"), "expect": "FAIL",
                    "seconds": round(sum(t["seconds"] for t in tried), 1)}

        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            mres = list(ex.map(campaign, muts))
        u = {"proofs": proofs, "mutants": mres}
        for r in proofs + mres:
            r["ok"] = r["status"] == r["expect"]
            ok &= r["ok"]
            print(f"{r['job']:34s} {r['status']:6s} (expect {r['expect']}) {r['seconds']:6.1f}s {'ok' if r['ok'] else 'WRONG'}"
                  + (f"  killed by {','.join(r['killed_by'])}" if r.get("killed_by") else ""))
            for e in [r["job"]] if r["status"] == "ERROR" and "killed_by" not in r else r.get("errors", [])[:1]:
                if (OUT / e / "sby.log").exists():
                    print("  " + (OUT / e / "sby.log").read_text()[-600:].replace("\n", "\n  "))
        u["summary"] = {"proofs_pass": sum(r["ok"] for r in proofs), "proofs": len(proofs),
                        "mutants_killed": sum(r["ok"] for r in mres), "mutants": len(mres),
                        "semantic_killed": sum(r["ok"] for r in mres if r["kind"] == "semantic"),
                        "semantic": sum(r["kind"] == "semantic" for r in mres),
                        "killed_by_quiet": sum("quiet" in r["killed_by"] for r in mres),
                        "killed_by_own_seed": sum(f"seed{r['rule']}" in r["killed_by"] for r in mres)}
        res["units"][uname] = u
    res["all_ok"] = ok
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res, indent=1) + "\n")
    print("formal:", "all as expected" if ok else "MISMATCH", {k: v["summary"] for k, v in res["units"].items()})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
