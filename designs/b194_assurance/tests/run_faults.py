#!/usr/bin/env python3
"""Seeded single-event-upset campaign on the development design (brief 194): every variant, every target, one JSON record.

    python3 designs/b194_assurance/tests/run_faults.py [--trials 400] [--seed 1] [--out results/b194/faults.json]

Icarus Verilog runs the variants without the block RAM primitive; xsim (Vivado 2026.1, unisims) runs the variants that instantiate
RAMB36E1 (ECC = 2). Both read the same tb/tb_fault.sv and the same $random(seed) stream (the draws are the same; the two simulators schedule a few events differently, so a cell can differ by a few trials).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

D = Path(__file__).resolve().parents[1]
RTL = [D / "rtl" / f for f in ("a194_secded.sv", "a194_fifo.sv", "a194_ctrl.sv", "a194_core.sv")]
TB = D / "tb" / "tb_fault.sv"
VARIANTS = {   # name: (ECC, PAR, SAFE, TMR, WD)
    "u": (0, 0, 0, 0, 0), "ecc_fabric": (1, 0, 0, 0, 0), "ecc_prim": (2, 0, 0, 0, 0), "par": (0, 1, 0, 0, 0),
    "safe": (0, 0, 1, 0, 0), "tmr": (0, 0, 0, 1, 0), "wd": (0, 0, 0, 0, 1), "all": (2, 1, 1, 1, 1),
}
TARGETS = ["none", "state", "ram", "ram2", "cnt", "cnt2", "bus"]
RESULT = re.compile(r"RESULT target=(\S+) ecc=\d+ tmr=\d+ trials=(\d+) seed=(\d+) masked=(\d+) corrected=(\d+) detected=(\d+) silent=(\d+) hang=(\d+)")
sys.path.insert(0, str(D.parents[1]))
from flow.ipchar import vivado  # noqa: E402

XSETTINGS = os.environ.get("XSIM_SETTINGS") or str(Path(vivado()).parents[1] / "settings64.sh")   # beside the pinned Vivado (flow/version_pin.py)


def params(v: tuple) -> str:
    e, p, s, t, w = v
    return f"#(.ECC({e}),.PAR({p}),.SAFE({s}),.TMR({t}),.WD({w}))"


def run_variant(name: str, v: tuple, targets: list[str], trials: int, seed: int) -> dict:
    ecc, tmr = v[0], v[3]
    defs = {"DUT_PARAMS": params(v), "DATA_BITS": "72" if ecc == 1 else "64", "TMR_ON": str(tmr), "ECC_VAL": str(ecc), "A194_FI": None}
    out: dict = {}
    with tempfile.TemporaryDirectory(prefix=f"b194_{name}_") as td:
        td = Path(td)
        if ecc == 2:
            sh = f"source {XSETTINGS} >/dev/null 2>&1; cd {td}; "
            dd = " ".join(f"-d '{k}={x}'" if x is not None else f"-d {k}" for k, x in defs.items())
            sh += f"xvlog -sv {' '.join(map(str, RTL))} {TB} {dd} >/dev/null && xvlog $XILINX_VIVADO/data/verilog/src/glbl.v >/dev/null && xelab -L unisims_ver tb_fault glbl -s s >/dev/null 2>&1"
            r = subprocess.run(["bash", "-c", sh], capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(f"xsim compile failed for {name}: {r.stdout[-500:]}{r.stderr[-500:]}")
            run = lambda t: subprocess.run(["bash", "-c", f"source {XSETTINGS} >/dev/null 2>&1; cd {td}; xsim s -R -testplusarg target={t} -testplusarg trials={trials} -testplusarg seed={seed}"],
                                           capture_output=True, text=True).stdout
        else:
            argv = ["iverilog", "-g2012", "-o", str(td / "s.out")] + [f"-D{k}" + (f"={x}" if x is not None else "") for k, x in defs.items()] + [str(p) for p in RTL] + [str(TB)]
            r = subprocess.run(argv, capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(f"iverilog failed for {name}: {r.stderr[-800:]}")
            run = lambda t: subprocess.run(["vvp", str(td / "s.out"), f"+target={t}", f"+trials={trials}", f"+seed={seed}"], capture_output=True, text=True).stdout
        for t in targets:
            if t == "cnt2" and not tmr:
                continue
            t0 = time.time()
            m = RESULT.search(run(t))
            if not m:
                raise SystemExit(f"{name}/{t}: no RESULT line")
            out[t] = dict(zip(("masked", "corrected", "detected", "silent", "hang"), map(int, m.groups()[3:]))) | {"trials": int(m.group(2)), "wall_s": round(time.time() - t0, 1)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=400)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--variants", nargs="*", default=list(VARIANTS))
    ap.add_argument("--out", type=Path, default=D.parents[1] / "results" / "b194" / "faults.json")
    a = ap.parse_args()
    old = json.loads(a.out.read_text()) if a.out.is_file() else None
    if old and (old["seed"], old["trials"]) == (a.seed, a.trials) and set(a.variants) != set(VARIANTS):
        res = old                 # a partial re-run (some variants) updates its own rows; the seed and the trial count must match
    else:
        res = None
    res = res or {"seed": a.seed, "trials": a.trials, "simulators": {"icarus": subprocess.run(["iverilog", "-V"], capture_output=True, text=True).stdout.splitlines()[0],
                                                              "xsim": "Vivado 2026.1 xsim"}, "variants": {}}
    for n in a.variants:
        res["variants"][n] = {"params": dict(zip(("ECC", "PAR", "SAFE", "TMR", "WD"), VARIANTS[n])), "sim": "xsim" if VARIANTS[n][0] == 2 else "icarus",
                              "targets": run_variant(n, VARIANTS[n], TARGETS, a.trials, a.seed)}
        print(n, {t: (r["masked"], r["corrected"], r["detected"], r["silent"], r["hang"]) for t, r in res["variants"][n]["targets"].items()}, flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
