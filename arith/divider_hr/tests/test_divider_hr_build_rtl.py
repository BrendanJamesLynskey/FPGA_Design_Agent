"""Prepared (not run) out-of-context build descriptions of the high-radix divider (brief 139c); see the divider's counterpart."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from arith.common import buildcheck, sim
from arith.divider_hr import model as M

D = Path(__file__).resolve().parents[1]
RTL = sorted((D / "rtl").glob("*.sv"))
TB = D / "tb" / "tb_divider_hr.sv"


def test_build_descriptions_are_complete_and_current() -> None:
    assert buildcheck.check_descriptions("divider_hr") == []


def test_ooc_wrapper_lints_and_is_functionally_exact_for_the_pipeline() -> None:
    assert buildcheck.lint_wrappers("divider_hr", "divider_hr_ooc", [{"VARIANT": v, "W": w, "K": k, "PIPE": p} for v in range(3) for w, k, p in ((16, 8, 1), (32, 16, 3))]) == []
    vin, vexp = M.stream(8, 4)
    r = sim.run_stream("tb_divider_hr", RTL, {"VARIANT": 2, "W": 8, "K": 4, "PIPE": 2, "WRAP": 1}, vin, vexp, 16, M.out_width(8, 4), M.latency(2, 8, 4, 2) + 2, gap_pct=20, extra_tb=[TB])
    assert sim.ok(r), r


def test_packaged_harness_runs_against_an_instance() -> None:
    """The harness a user reruns after integration (harness/run.py) passes on the library's own instance, with every coverage bin hit."""
    sim.need("iverilog")
    r = subprocess.run([sys.executable, str(D / "harness" / "run.py"), "--dut", "divider_hr_sel", "--rtl", *map(str, RTL), "--param", "VARIANT=2", "--param", "W=8",
                        "--param", "K=4", "--param", "PIPE=2", "--variant", "srt4_pipe"], capture_output=True, text=True, env=sim.env(), cwd=str(D.parents[1]))
    assert r.returncode == 0 and '"pass": true' in r.stdout, r.stdout[-1500:] + r.stderr[-800:]
