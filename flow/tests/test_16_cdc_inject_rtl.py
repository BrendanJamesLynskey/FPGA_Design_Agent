"""Brief 16: each CDC fixture's own cocotb test (Icarus), plain and with synchroniser-delay injection (flow/cdc_inject.py).
A test that passes plain and fails injected is a crossing that depends on its exact latency. Two seeds a fixture; CI runs
this file in the rtl-sim job. The expected set is the "injected sim flags" column of results/16_cdc_gate/mutant_table.md."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

FX = Path(__file__).parent / "fixtures" / "cdc_mutants"
sys.path.insert(0, str(FX))
NAMES = sorted(p.stem for p in (FX / "rtl").glob("*.sv"))

#: fixtures whose injected simulation fails while the plain one passes
SIM_CATCHES = {"cdcfx_m3", "cdcfx_m5", "cdcfx_m7"}


@pytest.mark.parametrize("name", NAMES)
def test_fixture_plain_then_injected(name: str, tmp_path: Path, monkeypatch) -> None:
    import run_fixture
    monkeypatch.delenv("FDA_CDC_INJECT_SEED", raising=False)
    run_fixture.run(name, 0, tmp_path)                       # the fixture's own test passes without injection
    failed = []
    for seed in (1, 2):
        try:
            run_fixture.run(name, seed, tmp_path)
        except AssertionError:
            failed.append(seed)
    monkeypatch.delenv("FDA_CDC_INJECT_SEED", raising=False)
    assert bool(failed) == (name in SIM_CATCHES), (name, failed)
    if name in SIM_CATCHES:
        assert failed == [1, 2]


@pytest.mark.parametrize("name,passes", [("cdcfx_c1", True), ("cdcfx_m5", False)])
def test_cdc_inject_run_on_a_small_design(name: str, passes: bool, tmp_path: Path) -> None:
    """flow/cdc_inject_run.py end to end: a design directory with rtl/ and tests/test_*_rtl.py; plain once, then seeds."""
    from flow import cdc_inject_run
    d = tmp_path / "des"
    (d / "rtl").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "rtl" / f"{name}.sv").write_text((FX / "rtl" / f"{name}.sv").read_text())
    (d / "tests" / "test_x_rtl.py").write_text(
        f"import os, sys\nfrom pathlib import Path\nsys.path.insert(0, {str(FX)!r})\nos.environ['CDCFX_NAME'] = {name!r}\n"
        "from flow import cocotb_run\nHERE = Path(__file__).parent\n"
        f"def test_x(tmp_path):\n    cocotb_run.run('des_{name}', {name!r}, sorted((HERE.parent / 'rtl').glob('*.sv')), 'cdcfx_tb', "
        f"Path({str(FX / 'tb')!r}), seed=1, build_root=tmp_path)\n")
    rep = cdc_inject_run.evaluate(d, seeds=2)
    assert rep["applicable"] and rep["plain"]["pass"]
    assert rep["pass"] is passes, rep.get("why")
    if not passes:
        assert "pass without injection and fail with injection" in rep["why"]
    else:
        assert rep["injection"]["sites"] == 1
