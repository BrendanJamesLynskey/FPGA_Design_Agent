"""Brief 55: VHDL designs in the simulators (needs GHDL and Icarus; CI installs both in the rtl-sim job).

- A model-written VHDL translation of a development task passes that task's unchanged hidden bench through the GHDL
  netlist (flow/vhdl_score.py); the first translation, which re-wrote the shell's helpers under their own names, does
  not build (mistake M1).
- A VHDL block runs natively under GHDL with its SystemVerilog original's cocotb test (the brief 16 CDC fixtures):
  the asynchronous FIFO passes; the handshake translation fails on 'U' at time 0 (mistake M2) and passes once its two
  output registers get a start value (the hand fix).
- Formal on VHDL with PSL properties (GHDL Yosys plugin + SymbiYosys), when sby is installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from flow import vhdl

ROOT = Path(__file__).resolve().parents[2]
T = ROOT / "results" / "55_vhdl" / "translations"
pytestmark = pytest.mark.skipif(vhdl.ghdl_exe() is None or shutil.which("iverilog") is None,
                                reason="GHDL and Icarus are needed")


def test_translation_passes_the_hidden_bench(tmp_path):
    from flow.vhdl_score import score
    r = score(ROOT / "benchmark" / "tasks" / "t1_gray_stepper", T / "B" / "t1_gray_stepper" / "rtl", "icarus",
              build_root=tmp_path)
    assert r["built"] and r["pass"], r.get("error") or r["tests"]
    assert len(r["tests"]) == 9


def test_first_translation_clashes_with_the_shell(tmp_path):
    from flow.vhdl_score import score
    r = score(ROOT / "benchmark" / "tasks" / "t1_gray_stepper", T / "A" / "t1_gray_stepper" / "rtl", "icarus",
              build_root=tmp_path)
    assert not r["built"] and not r["pass"]


def _cdc(name: str, rtl: Path, tmp_path: Path, monkeypatch) -> None:
    from flow import cocotb_run
    monkeypatch.setenv("CDCFX_NAME", name)
    monkeypatch.setenv("SIM", "ghdl")
    monkeypatch.delenv("FDA_CDC_INJECT_SEED", raising=False)
    cocotb_run.run(f"b55_{name}", name, [rtl / f"{name}.vhd"], "cdcfx_tb",
                   ROOT / "flow" / "tests" / "fixtures" / "cdc_mutants" / "tb", seed=1, build_root=tmp_path)


def test_async_fifo_translation_native_ghdl(tmp_path, monkeypatch):
    _cdc("cdcfx_c10", T / "A" / "cdcfx_c10" / "rtl", tmp_path, monkeypatch)


def test_handshake_translation_needs_start_values(tmp_path, monkeypatch):
    with pytest.raises(AssertionError, match="Logic\(.U.\) to int"):
        _cdc("cdcfx_c8", T / "B" / "cdcfx_c8" / "rtl", tmp_path / "b", monkeypatch)
    _cdc("cdcfx_c8", T / "hand_fix" / "cdcfx_c8" / "rtl", tmp_path / "fix", monkeypatch)


def test_ghdl_refuses_mixed_sources(tmp_path, monkeypatch):
    from flow import cocotb_run
    monkeypatch.setenv("SIM", "ghdl")
    with pytest.raises(AssertionError, match="simulates VHDL only"):
        cocotb_run.run("b55_mixed", "t1_gray_stepper_top",
                       cocotb_run.SHELL_RTL + sorted((T / "B" / "t1_gray_stepper" / "rtl").glob("*.vhd")),
                       "x", ROOT / "flow" / "tests", build_root=tmp_path)


def _formal_env() -> dict | None:
    env = dict(os.environ)
    if shutil.which("sby") is None:
        local = Path.home() / ".local" / "opt" / "formal-deb" / "env.sh"
        if not local.is_file():
            return None
        out = subprocess.run(["bash", "-c", f"source {local} && env"], capture_output=True, text=True).stdout
        env.update(dict(l.split("=", 1) for l in out.splitlines() if "=" in l))
    return env


def test_formal_on_vhdl_with_psl():
    env = _formal_env()
    if env is None:
        pytest.skip("SymbiYosys not installed")
    r = subprocess.run([str(ROOT / "flow" / "formal.sh"), "flow/tests/fixtures/vhdl_formal"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=900)
    lines = dict(l.split(": ", 1) for l in r.stdout.splitlines() if l.startswith("formal "))
    if all(v.startswith("ABSENT") or v.startswith("ERROR") for v in lines.values()):
        pytest.skip("the GHDL Yosys plugin is not available: " + r.stdout[-300:])
    assert lines["formal psl_cnt_bmc"].startswith("PASS"), lines
    assert lines["formal psl_cnt_cover"].startswith("PASS"), lines
    assert lines["formal psl_cnt_mutant_bmc"].startswith("FAIL"), lines


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
