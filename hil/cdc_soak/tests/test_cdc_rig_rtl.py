"""pytest entry: the CDC soak rig under cocotb + Icarus with metastability injection and reset storms.

Each run builds rig_core (through sim/tb_rig.sv) with +define+CDC_SIM, records the UART byte stream, parses it with
host/read_counters.py and checks it against the design's predictions (reports/11_cdc_soak_rig_design.md section 2):
every correct variant 0 errors and 0 lock-ups; every mutant predicted to fail in seconds caught; the "probably 0"
mutants reported as they come out. The run's summary is written to hil/cdc_soak/results/.

CDC_SIM_QUICK=1 runs one copy per variant and two epochs (the CI setting); the default is three copies per variant
(each direction once) and four epochs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
RIG = HERE.parent
ROOT = RIG.parents[1]
sys.path.insert(0, str(RIG / "host"))
import read_counters as rc  # noqa: E402

RTL = [RIG / "rtl" / f for f in ("rig_pkg.sv", "cdc_lib.sv", "rig_check.sv", "afifo16.sv", "rig_copy.sv",
                                  "rig_ctrl.sv", "rig_core.sv")] + [RIG / "sim" / "xpm_models.sv", RIG / "sim" / "tb_rig.sv"]

QUICK = os.environ.get("CDC_SIM_QUICK") == "1"

# Predictions (design section 2). "fast": caught within the run; "zero": expected 0 (reported, not asserted);
# per-direction exceptions where the mechanism needs a slower destination.
FAST = {"M2", "M3", "M5", "M6c", "M7", "M8", "M9", "M10", "M11"}
REPORT_ONLY = {"M1": "uncertain (real metastability; not modelled beyond one extra cycle)",
               "M1b": "probably 0 (a single flop with full slack behaves like a synchroniser)",
               "M6a": "probably 0 (skew below one source period)",
               "M6b": "seconds once routed skew > 4 ns; the model's 4 x 1 ns padding sits exactly at the limit",
               "M4": "seconds far/boundary, possibly 0 near"}


def build_and_run(name: str, ncopy: int, epochs: int, inject: int, tj_stop: bool, seed: int) -> Path:
    from cocotb_tools.runner import get_runner

    build = ROOT / "build" / "sim" / name
    log = build / "uart.log"
    params = {"NCOPY": ncopy}
    runner = get_runner("icarus")
    runner.build(sources=[str(s) for s in RTL], hdl_toplevel="tb_rig", defines={"CDC_SIM": 1}, parameters=params,
                 build_dir=build, timescale=("1ns", "1ps"), always=True, build_args=["-g2012"])
    env = {"CDC_LOG": str(log), "CDC_EPOCHS": str(epochs), "CDC_INJECT": str(inject),
           "CDC_TJ_STOP": "1" if tj_stop else "0", "CDC_NTOT": str(28 * ncopy),
           "PYTHONPATH": os.pathsep.join([str(RIG / "sim"), os.environ.get("PYTHONPATH", "")])}
    runner.test(test_module="cdc_rig_cocotb", hdl_toplevel="tb_rig", build_dir=build, test_dir=RIG / "sim",
                extra_env=env, parameters=params, seed=seed, results_xml=str(build / "results.xml"),
                log_file=build / "sim.log", timescale=("1ns", "1ps"), plusargs=[f"+CDC_SEED={seed}"])
    return log                           # (runner.test exits non-zero when the cocotb test fails)


def judge(run: rc.Run, inject: int) -> dict:
    """Compare the last readout with the predictions; returns the per-variant table and the list of violations."""
    rows, bad = {}, []
    for v in rc.VARIANTS:
        cs = [r for r in run.copies.values() if r["variant"] == v]
        per = [{"copy": r["copy"], "dir": r["dir"], "cls": r["cls"], "errors": r["errors"], "events": r["events"],
                "lockups": r["lockups"], "relocks": r["relocks"], "sat": r["sat"]} for r in sorted(cs, key=lambda r: r["copy"])]
        if v.startswith("C"):
            pred = "0 errors, 0 lock-ups"
            clean = [p for p in per if p["copy"] != inject]
            ok = all(p["errors"] == 0 and p["lockups"] == 0 and p["sat"] == 0 for p in clean)
            if not ok:
                bad.append(f"{v}: a correct variant reported errors or lock-ups: {clean}")
            if any(p["events"] == 0 for p in per):
                bad.append(f"{v}: a copy moved no traffic: {per}")
            verdict = "as predicted (0)" if ok else "VIOLATION"
        elif v in FAST:
            pred = "caught in seconds"
            # M5 loses pulses only into a slower (or equal, sliding) destination; b->a is a faster destination.
            # M10's raw reset request is launched in clk_a, so in b->a copies (flops in clk_a) its release is
            # synchronous to the flops: no release skew to find (the same holds in hardware, where that path is timed)
            need = [p for p in per if not (v in ("M5", "M10") and p["dir"] == "b->a")]
            caught = [p for p in need if p["errors"] > 0 or p["lockups"] > 0]
            ok = len(caught) == len(need)
            if not ok:
                bad.append(f"{v}: predicted to fail fast, but some copies were not caught: {need}")
            verdict = "caught (as predicted)" if ok else "NOT CAUGHT"
        else:
            pred = REPORT_ONLY[v]
            n = sum(p["errors"] > 0 for p in per)
            verdict = f"reported: {n} of {len(per)} copies with errors"
        rows[v] = {"prediction": pred, "verdict": verdict, "copies": per}
    return {"variants": rows, "violations": bad}


def _check(name: str, ncopy: int, epochs: int, inject: int, tj_stop: bool, seed: int) -> dict:
    log = build_and_run(name, ncopy, epochs, inject, tj_stop, seed)
    return judge_log(log, name, ncopy, epochs, inject, tj_stop, seed)


def judge_log(log: Path, name: str, ncopy: int, epochs: int, inject: int, tj_stop: bool, seed: int) -> dict:
    """Parse a recorded UART log, check it against the predictions and write results/<name>.json."""
    run = rc.Run()
    for r in rc.parse_stream(log.read_text().splitlines()):
        run.add(r)
    assert run.bad == 0, f"{run.bad} lines failed the CRC/format check"
    assert run.hello and run.hello["copies"] == 28 * ncopy
    assert len(run.complete_epochs()) >= epochs, run.complete_epochs()
    out = judge(run, inject)
    out.update({"run": name, "copies_per_variant": ncopy, "epochs": len(run.epochs), "seed": seed,
                "injected_copy": inject, "stop": run.stop,
                "cfgmclk_count_per_ms_tick": [e["cfgmclk_khz"] for e in run.epochs]})
    if inject >= 0:
        r = run.copies[inject]
        out["injected_errors"] = r["errors"]
        assert r["errors"] >= 1, f"the forced extra event in copy {inject} was not counted: {r}"
    if tj_stop:
        assert run.stop and run.stop["reason"] == "TJ", "no temperature stop record"
    dest = RIG / "results" / f"{name}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, indent=1) + "\n")
    return out


def test_rig_injection_storms() -> None:
    """Clean run: injection on, reset storms on; one forced error in copy 0 (a C1 copy); ends with the Tj stop."""
    ncopy, epochs = (1, 2) if QUICK else (3, 4)
    out = _check("cdc_rig_quick" if QUICK else "cdc_rig_sim", ncopy, epochs, inject=0, tj_stop=True, seed=11)
    assert not out["violations"], "\n".join(out["violations"])


@pytest.mark.skipif(QUICK, reason="second seed only in the full local run")
def test_rig_second_seed() -> None:
    out = _check("cdc_rig_sim_seed2", 3, 4, inject=-1, tj_stop=False, seed=23)
    assert not out["violations"], "\n".join(out["violations"])
