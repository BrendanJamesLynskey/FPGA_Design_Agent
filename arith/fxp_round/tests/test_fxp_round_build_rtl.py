"""Prepared (not run) out-of-context build descriptions of the rounding unit (brief 139b); see the divider's counterpart."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from arith.common import buildcheck, sim
from arith.fxp_round import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_fxp_round.sv"


def test_build_descriptions_are_complete_and_current() -> None:
    assert buildcheck.check_descriptions("fxp_round") == []


def test_ooc_wrapper_lints_and_is_functionally_exact() -> None:
    pts = [{"VARIANT": v, "W_IN": 32, "S": 12, "W_OUT": 18, "MODE": 2, "SAT": 1} for v in range(3)] + [{"VARIANT": 0, "W_IN": 24, "S": 8, "W_OUT": 16, "MODE": 0, "SAT": 0}]
    assert buildcheck.lint_wrappers("fxp_round", "fxp_round_ooc", pts) == []
    for v in range(3):
        vin, vexp = M.stream(8, 3, 6, 2, 1)
        r = sim.run_stream("tb_fxp_round", RTL, {"VARIANT": v, "W_IN": 8, "S": 3, "W_OUT": 6, "MODE": 2, "SAT": 1, "WRAP": 1}, vin, vexp, 8, 6, M.latency(v) + 2, gap_pct=20, extra_tb=[TB])
        assert sim.ok(r), (v, r)


def test_packaged_harness_runs_against_an_instance() -> None:
    """The harness a user reruns after integration (harness/run.py) passes on the library's own instance, with every coverage bin hit."""
    sim.need("iverilog")
    r = subprocess.run([sys.executable, str(D / "harness" / "run.py"), "--dut","fxp_round_sel","--rtl",*map(str,RTL),"--param","VARIANT=0","--param","W_IN=8","--param","S=3","--param","W_OUT=6","--param","MODE=2","--param","SAT=1","--variant","fold_add"], capture_output=True, text=True, env=sim.env(), cwd=str(D.parents[1]))
    assert r.returncode == 0 and '"pass": true' in r.stdout, r.stdout[-1500:] + r.stderr[-800:]
