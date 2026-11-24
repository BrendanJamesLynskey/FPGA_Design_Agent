"""Prepared (not run) out-of-context build descriptions of the square root (brief 139c); see the divider's counterpart."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from arith.common import buildcheck, sim
from arith.sqrt_r4 import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_sqrt_r4.sv"


def test_build_descriptions_are_complete_and_current() -> None:
    assert buildcheck.check_descriptions("sqrt_r4") == []


def test_ooc_wrapper_lints_and_is_functionally_exact_for_pipelines() -> None:
    assert buildcheck.lint_wrappers("sqrt_r4", "sqrt_r4_ooc", [{"VARIANT": v, "W": w, "PIPE": p} for v in range(2) for w, p in ((16, 1), (32, 2))]) == []
    for v in (1,):
        vin, vexp = M.stream(9)
        r = sim.run_stream("tb_sqrt_r4", RTL, {"VARIANT": v, "W": 9, "PIPE": 2, "WRAP": 1}, vin, vexp, 9, 2 * M.rw(9) + 1, M.latency(v, 9, 2) + 2, gap_pct=20, extra_tb=[TB])
        assert sim.ok(r), (v, r)


def test_packaged_harness_runs_against_an_instance() -> None:
    """The harness a user reruns after integration (harness/run.py) passes on the library's own instance, with every coverage bin hit."""
    sim.need("iverilog")
    r = subprocess.run([sys.executable, str(D / "harness" / "run.py"), "--dut","sqrt_r4_sel","--rtl",*map(str,RTL),"--param","VARIANT=1","--param","W=9","--param","PIPE=2","--variant","pipe"], capture_output=True, text=True, env=sim.env(), cwd=str(D.parents[1]))
    assert r.returncode == 0 and '"pass": true' in r.stdout, r.stdout[-1500:] + r.stderr[-800:]
