#!/usr/bin/env python3
"""The FSM coverage evidence of brief 24: three designs with their real tests, and the test-removal mutants.

    python3 results/24_fsm/make_coverage.py        (needs the repo's venv: cocotb 2, Icarus)

Writes results/24_fsm/coverage/<design>.json and <design>__<mutant>.json (flow/fsm_coverage.py output) and coverage/summary.json.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "flow" / "tests" / "fixtures" / "fsm_discipline" / "bench"))
from flow import cocotb_run, fsm_coverage  # noqa: E402

OUT = Path(__file__).parent / "coverage"
FX = ROOT / "flow" / "tests" / "fixtures" / "fsm_discipline"


def board(design, tb, mod, params, name, tmp, case=None):
    d = ROOT / "designs" / design
    t = d / "tests"
    srcs = [s for s in sorted((d / "rtl").glob("*.sv")) if not s.name.endswith("_top.sv")] + [t / f"{tb}.sv"]
    cocotb_run.run(name, tb, srcs, mod, t, parameters=params, testcase=case)
    return tmp / f"{name}.fsmtrace"


def ref(name, tmp, case=None):
    srcs = [FX / "rtl" / f for f in ("fsm_front.sv", "ctl_sep.sv", "ctl_mono.sv", "tb_ctl.sv")]
    cocotb_run.run(name, "tb_ctl", srcs, "ctl_cocotb", FX / "bench", parameters={"MONO": 0, "OUT": 0}, testcase=case)
    return tmp / f"{name}.fsmtrace"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    os.environ["FDA_FSM_TRACE"] = str(tmp)
    cases = [
        ("b2_qspi_jedec", ROOT / "designs/b2_qspi_jedec", lambda n, c=None: board("b2_qspi_jedec", "tb_qspi", "qspi_cocotb", {"HALF": 4}, n, tmp, c),
         [("without_test_rdid_only", "test_writes_to_any_register_send_nothing_else")]),
        ("b2_tmp_adt7420", ROOT / "designs/b2_tmp_adt7420", lambda n, c=None: board("b2_tmp_adt7420", "tb_tmp", "tmp_cocotb", {"QUARTER": 5}, n, tmp, c),
         [("without_test_wrong_address_nacks", ["test_id_and_temperature", "test_clock_stretching", "test_one_byte_then_two_repeat"])]),
        ("fsm_discipline_ref", FX, lambda n, c=None: ref(n, tmp, c),
         [("without_test_timeout", ["test_burst_and_ack", "test_nack_retries_the_burst", "test_response_backpressure"])]),
    ]
    summary = []
    for name, d, run, muts in cases:
        rep = fsm_coverage.evaluate(d, [run(f"c24_{name}")])
        (OUT / f"{name}.json").write_text(json.dumps(rep, indent=1) + "\n")
        f = rep["fsms"][0]
        row = {"design": name, "states": f"{f['states_hit']}/{f['n_states']}", "transitions": f"{f['transitions_hit']}/{f['transitions_listed']}", "pass": f["pass"], "mutants": []}
        for mname, case in muts:
            r = fsm_coverage.evaluate(d, [run(f"c24_{name}_{mname}", case)])
            (OUT / f"{name}__{mname}.json").write_text(json.dumps(r, indent=1) + "\n")
            g = r["fsms"][0]
            row["mutants"].append({"removed": mname, "pass": g["pass"], "states_missed": g["states_missed"], "transitions_missed": g["transitions_missed"]})
        summary.append(row)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
