"""Prepared (not run) out-of-context build descriptions of the square root (brief 139b); see the divider's counterpart."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from arith.common import buildcheck, sim
from arith.isqrt import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_isqrt.sv"


def test_build_descriptions_are_complete_and_current() -> None:
    assert buildcheck.check_descriptions("isqrt") == []


def test_ooc_wrapper_lints_and_is_functionally_exact_for_pipelines() -> None:
    assert buildcheck.lint_wrappers("isqrt", "isqrt_ooc", [{"VARIANT": v, "W": w, "PIPE": p} for v in range(3) for w, p in ((16, 1), (32, 4))]) == []
    for v in (1, 2):
        vin, vexp = M.stream(9)
        r = sim.run_stream("tb_isqrt", RTL, {"VARIANT": v, "W": 9, "PIPE": 2, "WRAP": 1}, vin, vexp, 9, 2 * M.rw(9) + 1, M.latency(v, 9, 2) + 2, gap_pct=20, extra_tb=[TB])
        assert sim.ok(r), (v, r)


def test_packaged_harness_runs_against_an_instance() -> None:
    """The harness a user reruns after integration (harness/run.py) passes on the library's own instance, with every coverage bin hit."""
    sim.need("iverilog")
    r = subprocess.run([sys.executable, str(D / "harness" / "run.py"), "--dut","isqrt_sel","--rtl",*map(str,RTL),"--param","VARIANT=1","--param","W=9","--param","PIPE=2","--variant","restoring_pipe"], capture_output=True, text=True, env=sim.env(), cwd=str(D.parents[1]))
    assert r.returncode == 0 and '"pass": true' in r.stdout, r.stdout[-1500:] + r.stderr[-800:]
