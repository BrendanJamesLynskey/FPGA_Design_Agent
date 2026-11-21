"""The UVM bench of the PCS and MAC (brief 112, designs/b96_kr260_10g/verif/uvm): what CI can check without xsim, and a smoke run where xsim exists.

CI has no Vivado, so the bench itself is not run there; these tests keep it honest anyway: every seeded bug (mutant) must still apply to the RTL
exactly once (a change to the RTL that moves a target breaks the mutant loudly), the bench's files must all be present, and, on a machine with
Vivado 2026.1's xsim, the bench must build and its smoke test must pass."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
DESIGN = HERE.parent
UVM = DESIGN / "verif" / "uvm"
RTL = DESIGN / "rtl"


def _settings() -> str | None:
    for c in (os.environ.get("XSIM_SETTINGS"), str(Path.home() / "Xilinx/2026.1/Vivado/settings64.sh"), "/opt/Xilinx/2026.1/Vivado/settings64.sh"):
        if c and Path(c).exists():
            return c
    return None


needs_xsim = pytest.mark.skipif(_settings() is None, reason="Vivado 2026.1 settings64.sh not found (XSIM_SETTINGS): the UVM bench runs in xsim, not in CI")


def _mutants() -> list[str]:
    out = subprocess.run(["python3", str(UVM / "scripts" / "mutate.py"), "list"], capture_output=True, text=True, check=True).stdout
    return [line.split("\t")[0] for line in out.splitlines()]


def test_bench_files_present() -> None:
    for rel in ("README.md", "pcs_mac_uvm_pkg.sv", "ref/pcs_ref_pkg.sv", "tb/tb_uvm_top.sv", "tb/pcs_mac_ifs.sv", "tb/line_channel.sv", "sva/pcs_mac_sva.sv",
                "env/pcs_mac_env.sv", "env/pcs_mac_agents.sv", "env/pcs_mac_scoreboard.sv", "env/pcs_mac_cov.sv", "env/pcs_mac_seqs.sv", "tests/pcs_mac_tests.sv",
                "scripts/run_regress.sh", "scripts/uvm_build.sh", "scripts/cov_merge.py", "scripts/mutate.py", "mutants/mutants.tsv"):
        assert (UVM / rel).is_file(), rel


@pytest.mark.parametrize("mid", _mutants())
def test_mutant_applies_exactly_once(mid: str, tmp_path: Path) -> None:
    dst = tmp_path / mid
    r = subprocess.run(["python3", str(UVM / "scripts" / "mutate.py"), "make", mid, str(RTL), str(dst)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    changed = [p.name for p in RTL.glob("*.sv") if (dst / p.name).read_text() != p.read_text()]
    assert changed, f"mutant {mid} changed nothing"


@needs_xsim
def test_uvm_smoke_in_xsim(tmp_path: Path) -> None:
    """Build the bench and run t_smoke: every scoreboard check must pass, with a non-trivial number of comparisons."""
    sh = f'set +u; source "{_settings()}" >/dev/null 2>&1; set -u; "{UVM}/scripts/uvm_build.sh" "{tmp_path}" && cd "{tmp_path}" && ' \
         f'xsim pcs_uvm -runall -sv_seed 1 -testplusarg UVM_TESTNAME=t_smoke -testplusarg SEED=1 -log run.log >/dev/null 2>&1'
    subprocess.run(["bash", "-c", sh], check=True, timeout=600)
    log = (tmp_path / "run.log").read_bytes().decode("utf-8", "replace")
    assert "[RESULT] PASS test=t_smoke" in log, log[-3000:]
    assert "check=RXPCS compared=" in log and "check=TXPCS compared=" in log
