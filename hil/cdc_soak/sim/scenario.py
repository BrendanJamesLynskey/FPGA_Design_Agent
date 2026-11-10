"""Focused rig simulations for brief 11c: a chosen set of variants, real clock ratios, staggered clock starts, board-like
reset storms; built from any RTL directory (so the first board runs' RTL can be re-run against the fixed bench).

    python sim/scenario.py <name> [--rtl DIR] [--sel C1,C6,M6C] [--copies 3] [--epochs 3] [--seed 11]
        [--hb-ps 7687] [--hc-ps 5004] [--c-start-ns 0] [--storm-maskw 9] [--storm-delay-s 2] [--epoch-s 20]
        [--define NAME=VAL ...] [--out results/11c/<name>.json]

Result: per copy, the errors / events / lockups / relocks in each epoch (the records are cumulative, so an error that
appears at epoch 0 and stays shows as a constant column). Uses cocotb + Icarus (tb_rig.sv); keep it under
systemd-run --user --scope -p MemoryMax=4G on the shared PC.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RIG = HERE.parent
ROOT = RIG.parents[1]
sys.path.insert(0, str(RIG / "host"))
import read_counters as rc  # noqa: E402

ORDER = ["C1", "C2", "C3a", "C3b", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13",
         "M1", "M1b", "M2", "M3", "M4", "M5", "M6a", "M6b", "M6c", "M7", "M8", "M9", "M10", "M11"]
RTL_FILES = ("rig_pkg.sv", "cdc_lib.sv", "rig_check.sv", "afifo16.sv", "rig_copy.sv", "rig_ctrl.sv", "rig_core.sv")


def _num(v):
    """A numeric define must reach Icarus as a number: the cocotb runner quotes strings (CDC_LUT_NS="0.5" is a string
    literal, which a real parameter reads as the bits of its characters)."""
    for t in (int, float):
        try:
            return t(v)
        except (TypeError, ValueError):
            pass
    return v


def sel_mask(names: list[str]) -> int:
    up = {n.upper(): i for i, n in enumerate(ORDER)}
    m = 0
    for n in names:
        m |= 1 << up[n.upper()]
    return m


def run(name: str, rtl_dir: Path, sel: list[str], copies: int = 3, epochs: int = 3, seed: int = 11,
        hb_ps: int = 7687, hc_ps: int = 5004, c_start_ns: int = 0, b_start_ns: int = 0, storm_maskw: int = 9,
        storm_delay_s: int = 2, epoch_s: int = 20, defines: dict | None = None, tick: int = 2000) -> dict:
    from cocotb_tools.runner import get_runner

    build = ROOT / "build" / "sim" / name
    log = build / "uart.log"
    ntot = copies * len(sel)
    srcs = [rtl_dir / f for f in RTL_FILES] + [RIG / "sim" / "xpm_models.sv", RIG / "sim" / "tb_rig.sv"]
    params = {"NCOPY": copies, "SEL": sel_mask(sel), "HB_PS": hb_ps, "HC_PS": hc_ps, "CLKC_T0_NS": c_start_ns,
              "CLKF_T0_NS": c_start_ns, "CLKB_T0_NS": b_start_ns, "STORM_MASKW": storm_maskw,
              "STORM_DELAY_S": storm_delay_s, "EPOCH_S": epoch_s, "TICK": tick}
    d = {"CDC_SIM": 1}
    d.update(defines or {})
    r = get_runner("icarus")
    r.build(sources=[str(s) for s in srcs], hdl_toplevel="tb_rig", defines=d, parameters=params, build_dir=build,
            timescale=("1ns", "1ps"), always=True, build_args=["-g2012"])
    env = {"CDC_LOG": str(log), "CDC_EPOCHS": str(epochs), "CDC_INJECT": "-1", "CDC_TJ_STOP": "0",
           "CDC_NTOT": str(ntot), "PYTHONPATH": os.pathsep.join([str(RIG / "sim"), os.environ.get("PYTHONPATH", "")])}
    r.test(test_module="cdc_rig_cocotb", hdl_toplevel="tb_rig", build_dir=build, test_dir=RIG / "sim", extra_env=env,
           parameters=params, seed=seed, results_xml=str(build / "results.xml"), log_file=build / "sim.log",
           timescale=("1ns", "1ps"), plusargs=[f"+CDC_SEED={seed}"])
    run_ = rc.Run()
    for rec in rc.parse_stream(log.read_text().splitlines()):
        run_.add(rec)
    assert run_.bad == 0, f"{run_.bad} bad lines"
    out: dict = {"name": name, "rtl": str(rtl_dir), "sel": sel, "copies_per_variant": copies, "seed": seed,
                 "params": params, "defines": d, "epochs": len(run_.epochs), "variants": {}}
    for v in sel:
        vv = next(x for x in rc.VARIANTS if x.upper() == v.upper())
        rows = []
        for g in sorted(g for g, r_ in run_.copies.items() if r_["variant"] == vv):
            per = [{k: run_.by_epoch[e][g][k] for k in ("errors", "events", "lockups", "relocks")}
                   for e in sorted(run_.by_epoch) if g in run_.by_epoch[e]]
            rows.append({"copy": g, "dir": run_.copies[g]["dir"], "cls": run_.copies[g]["cls"], "epochs": per})
        out["variants"][vv] = rows
    return out


def summary(out: dict) -> str:
    lines = []
    for v, rows in out["variants"].items():
        for r in rows:
            lines.append(f"{v:4} copy {r['copy']:3} {r['dir']:5} errors/epoch {[e['errors'] for e in r['epochs']]} "
                         f"relocks {[e['relocks'] for e in r['epochs']][-1]} lockups {[e['lockups'] for e in r['epochs']][-1]}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--rtl", type=Path, default=RIG / "rtl")
    ap.add_argument("--sel", default="C1")
    ap.add_argument("--copies", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--hb-ps", type=int, default=7687)
    ap.add_argument("--hc-ps", type=int, default=5004)
    ap.add_argument("--c-start-ns", type=int, default=0)
    ap.add_argument("--storm-maskw", type=int, default=9)
    ap.add_argument("--storm-delay-s", type=int, default=2)
    ap.add_argument("--epoch-s", type=int, default=20)
    ap.add_argument("--define", action="append", default=[])
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    defs = dict(x.split("=", 1) if "=" in x else (x, 1) for x in a.define)
    defs = {k: _num(v) for k, v in defs.items()}
    out = run(a.name, a.rtl, a.sel.split(","), a.copies, a.epochs, a.seed, a.hb_ps, a.hc_ps, a.c_start_ns, 0,
              a.storm_maskw, a.storm_delay_s, a.epoch_s, defs)
    print(summary(out))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
