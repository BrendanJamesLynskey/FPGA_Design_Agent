"""Prepared (not run) out-of-context build descriptions of the reciprocal (brief 139c); see the divider's counterpart."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from arith.common import buildcheck, sim
from arith.recip import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_recip.sv"


def test_build_descriptions_are_complete_and_current() -> None:
    assert buildcheck.check_descriptions("recip") == []


def test_ooc_wrapper_lints_and_is_functionally_exact() -> None:
    assert buildcheck.lint_wrappers("recip", "recip_ooc", [{"VARIANT": v, "W": w, "A": a} for v in range(3) for w, a in ((16, 7), (32, 10))]) == []
    for v in range(3):
        vin, vexp = M.stream(8, 3, v)
        r = sim.run_stream("tb_recip", RTL, {"VARIANT": v, "W": 8, "A": 3, "WRAP": 1}, vin, vexp, 8, 9, M.latency(v) + 2, gap_pct=20, extra_tb=[TB])
        assert sim.ok(r), (v, r)


def test_packaged_harness_runs_against_an_instance() -> None:
    """The harness a user reruns after integration (harness/run.py) passes on the library's own instance, with every coverage bin hit."""
    sim.need("iverilog")
    r = subprocess.run([sys.executable, str(D / "harness" / "run.py"), "--dut", "recip_sel", "--rtl", *map(str, RTL), "--param", "VARIANT=1", "--param", "W=10",
                        "--param", "A=4", "--variant", "nr1"], capture_output=True, text=True, env=sim.env(), cwd=str(D.parents[1]))
    assert r.returncode == 0 and '"pass": true' in r.stdout, r.stdout[-1500:] + r.stderr[-800:]
