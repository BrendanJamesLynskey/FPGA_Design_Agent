"""Brief 27B P0: the generated contract tests run on fixture RTL (cocotb + Icarus; CI's rtl-sim job runs this file).

Each fixture under ``fixtures/`` is a module directory (``contract.yaml`` and ``rtl/``). The correct RTL (``MUT = 0``)
passes every generated test. Each mutant breaks one promise of its contract and must fail exactly the generated tests
listed for it in ``CASES`` (the test of that promise, plus the tests a broken promise visibly upsets downstream), and
every other generated test must pass.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from project import contract_test

FX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]

#: (fixture, MUT) -> the generated tests that must fail (every other generated test must pass)
CASES = {
    ("fx_axis_slice", 0): set(),
    ("fx_axis_slice", 1): {"contract_axis_master_out", "contract_throughput_0_out"},
    ("fx_axis_slice", 2): {"contract_axis_master_out"},
    ("fx_axis_slice", 3): {"contract_reset"},
    ("fx_video_delay", 0): set(),
    # a sink that drops tready also loses the beats offered then, so the output has gaps and too few beats
    ("fx_video_delay", 4): {"contract_axis_slave_video_in", "contract_axis_master_video_out",
                            "contract_throughput_0_video_out"},
    ("fx_video_delay", 5): {"contract_latency_0_video_in_video_out"},
    ("fx_video_delay", 6): {"contract_ports"},
    ("fx_win_regs", 0): set(),
    ("fx_win_regs", 7): {"contract_registers"},
    ("fx_win_regs", 8): {"contract_registers"},
    ("fx_axil_regs", 0): set(),
    ("fx_axil_regs", 9): {"contract_registers"},
    ("fx_axil_regs", 10): {"contract_registers"},
}


def _run(name: str, mut: int, tmp: Path) -> dict[str, bool]:
    """Generate the fixture's contract test, run it with MUT, return {test: passed} from cocotb's results.xml."""
    import xml.etree.ElementTree as ET

    from flow import cocotb_run
    mod = tmp / name
    shutil.copytree(FX / name, mod)
    contract_test.write(mod)
    c = yaml.safe_load((mod / "contract.yaml").read_text())
    params = {p["name"]: p["default"] for p in c.get("parameters") or []}
    params["MUT"] = mut
    try:
        cocotb_run.run(f"{name}_m{mut}", name, sorted((mod / "rtl").glob("*.sv")), contract_test.TB_NAME,
                       mod / "tests", parameters=params, seed=1, build_root=tmp / "sim")
    except AssertionError:
        pass
    res = tmp / "sim" / f"{name}_m{mut}" / "results.xml"
    assert res.is_file(), f"{name} MUT={mut}: no results.xml (the build failed?)"
    out = {}
    for tc in ET.parse(res).getroot().iter("testcase"):
        out[tc.get("name")] = tc.find("failure") is None and tc.find("error") is None
    return out


@pytest.mark.parametrize("name,mut", sorted(CASES))
def test_generated_contract_tests_pass_the_reference_and_fail_each_mutant(name: str, mut: int, tmp_path: Path) -> None:
    got = _run(name, mut, tmp_path)
    expected_tests = {t for t, _ in contract_test.tests_for(yaml.safe_load((FX / name / "contract.yaml").read_text()))}
    assert set(got) == expected_tests, (sorted(got), sorted(expected_tests))
    failed = {t for t, ok in got.items() if not ok}
    assert failed == CASES[(name, mut)], f"{name} MUT={mut}: failed {sorted(failed)}, expected {sorted(CASES[(name, mut)])}"


def test_the_generated_runner_runs_on_its_own(tmp_path: Path) -> None:
    """The generated tests/test_contract_rtl.py is a working pytest file in a module directory."""
    mod = tmp_path / "fx_axis_slice"
    shutil.copytree(FX / "fx_axis_slice", mod)
    contract_test.write(mod)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(mod / "tests" / "test_contract_rtl.py")],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
