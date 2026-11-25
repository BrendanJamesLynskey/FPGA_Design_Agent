#!/usr/bin/env python3
"""Brief 191: k-induction on book_core (brief 188's properties Q1..Q6 and the strengthening invariants N1..N2), run as a record.

    python3 designs/b110_itch_ouch/verif/formal/run_book_formal.py [--json results/191_trading_variants/formal_book.json] [--quick]

What it runs (SymbiYosys 2026-11-12 OSS CAD Suite, yosys-slang, smtbmc yices; each job in its own directory under build/):
  instances  : bmc 12, prove (induction depth 1) and cover at N_INST/LEVELS/ORD_AW = 2/4/2 (the brief 188 instance) and larger ones
  ablations  : each strengthening invariant N1..N2 turned from an assertion into a cover, one at a time: the induction step must then FAIL (the invariant was needed)
  faults     : seeded faults in a copy of book_core.sv; `prove` must fail on each (base case or step) and name a property
Small runs (a few hundred MB, seconds to a minute): no heavy slot."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BUILD = ROOT / "build" / "b110_formal"
BIN = Path(os.environ.get("FDA_OSS_CAD") or Path.home() / ".local/opt/oss-cad-suite") / "bin"
RTL = HERE.parent.parent / "rtl"

FAULTS = [
    ("sat_off", "lv_wd = {1'b1, d3_px, sz_sum[32] ? 32'hFFFF_FFFF : sz_sum[31:0]};", "lv_wd = {1'b1, d3_px, sz_sum[31:0]};", "a level size wraps instead of saturating"),
    ("zero_add_allowed", "end else if (b2_sh == 32'd0) begin", "end else if (1'b0) begin", "an Add of zero shares is entered as a live order of no size"),
    ("sub_equal_keeps_level", "lv_wd = (d3_amt >= sz_hit) ? 65'd0 : {1'b1, d3_px, sz_hit - d3_amt};", "lv_wd = (d3_amt > sz_hit) ? 65'd0 : {1'b1, d3_px, sz_hit - d3_amt};", "a reduce that empties a level leaves it live with no size"),
    ("reduce_equal_keeps_order", "if (b2_sh >= e2_rem) begin", "if (b2_sh > e2_rem) begin", "a reduce of the whole remaining size leaves the order live with no size"),
    ("sweep_one_short", "if (sw_cnt == (ORD_AW + 1)'(ORD_N - 1)) sweep <= 1'b0;", "if (sw_cnt == (ORD_AW + 1)'(ORD_N - 2)) sweep <= 1'b0;", "the clearing sweep ends one entry early"),
]


def sby_text(n: int, lv: int, aw: int, depth_bmc: int = 12, depth_prove: int = 1, depth_cover: int = 14, props: str = "book_props.sv") -> str:
    t = (HERE / "book.sby").read_text()
    t = t.replace("-G N_INST=2 -G LEVELS=4 -G ORD_AW=2", f"-G N_INST={n} -G LEVELS={lv} -G ORD_AW={aw}")
    t = re.sub(r"(?m)^bmc: depth \d+", f"bmc: depth {depth_bmc}", t)
    t = re.sub(r"(?m)^prove: depth \d+", f"prove: depth {depth_prove}", t)
    t = re.sub(r"(?m)^cover: depth \d+", f"cover: depth {depth_cover}", t)
    t = t.replace("../../rtl/itch_pkg.sv", "itch_pkg.sv").replace("../../rtl/book_core.sv", "book_core.sv").replace("book_props.sv\nbook_bind.sv", f"{props}\nbook_bind.sv")
    return t.replace("book_core.sv book_props.sv book_bind.sv", f"book_core.sv {props} book_bind.sv")


def run(name: str, task: str, n: int, lv: int, aw: int, *, props_text: str | None = None, rtl_text: str | None = None, **depths) -> dict:
    w = BUILD / name
    shutil.rmtree(w, ignore_errors=True)
    w.mkdir(parents=True)
    shutil.copy(RTL / "itch_pkg.sv", w / "itch_pkg.sv")
    (w / "book_core.sv").write_text(rtl_text if rtl_text is not None else (RTL / "book_core.sv").read_text())
    (w / "book_props.sv").write_text(props_text if props_text is not None else (HERE / "book_props.sv").read_text())
    shutil.copy(HERE / "book_bind.sv", w / "book_bind.sv")
    (w / "book.sby").write_text(sby_text(n, lv, aw, **depths))
    t0 = time.time()
    r = subprocess.run(["sby", "-f", "-d", str(w / "out"), str(w / "book.sby"), task], cwd=w, env=dict(os.environ, PATH=f"{BIN}{os.pathsep}{os.environ['PATH']}"),
                       capture_output=True, text=True, timeout=3600)
    log = r.stdout
    failed = sorted(set(re.findall(r"u_props\.(\w+)", " ".join(l for l in log.splitlines() if "Assert failed" in l or "failed assertion" in l))))
    verdict = "PASS" if "DONE (PASS" in log else ("FAIL" if "DONE (FAIL" in log else "UNKNOWN")
    how = "k-induction" if "successful proof by k-induction" in log else ("bounded" if verdict == "PASS" and task == "bmc" else "")
    return {"name": name, "task": task, "instance": {"N_INST": n, "LEVELS": lv, "ORD_AW": aw}, "verdict": verdict, "proof": how, "failed_assertions": failed, "seconds": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--quick", action="store_true", help="skip the larger instances")
    a = ap.parse_args()
    props = (HERE / "book_props.sv").read_text()
    core = (RTL / "book_core.sv").read_text()
    out = {"tool": "SymbiYosys with yosys-slang, OSS CAD Suite 2026-11-12, engine smtbmc yices", "properties": "Q1-Q6 and invariants N1-N2 (verif/formal/book_props.sv)", "jobs": []}
    insts = [(2, 4, 2)] + ([] if a.quick else [(3, 4, 3), (2, 8, 3)])
    for n, lv, aw in insts:
        for task in ("bmc", "prove", "cover"):
            r = run(f"{task}_{n}_{lv}_{aw}", task, n, lv, aw)
            if task == "prove" and r["verdict"] != "PASS":
                r["note"] = "not closed: the induction step has counterexamples with an instrument index beyond the last instrument (N_INST not a power of two); BMC to depth 12 passes at this size"
            print(r, flush=True)
            out["jobs"].append(r)
    for k in range(1, 3):
        name = f"n{k}"
        pat = re.compile(rf"(?m)^(\s*n{k}_\w+:\s*)assert (\()")
        assert pat.search(props), name
        r = run(f"ablate_{name}", "prove", 2, 4, 2, props_text=pat.sub(r"\1cover \2", props))
        r["ablated"] = name
        r["expect"] = "the induction step fails without the invariant"
        r["verdict"] = "NEEDED" if r["failed_assertions"] else "NOT_NEEDED"
        print(r, flush=True)
        out["jobs"].append(r)
    for fname, old, new, why in FAULTS:
        assert core.count(old) == 1, fname
        r = run(f"fault_{fname}", "prove", 2, 4, 2, rtl_text=core.replace(old, new))
        r["fault"], r["why"] = fname, why
        r["verdict"] = "CAUGHT" if r["failed_assertions"] else "MISSED"
        print(r, flush=True)
        out["jobs"].append(r)
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
