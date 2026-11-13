"""gth_serdes_core against a behavioural stand-in of the GT Wizard (sim/gth_wiz_model.sv), with Icarus: register map, bring-up,
fabric and hard PRBS counting, error injection, snapshots, I2C, SYSMON and DRP windows. The real Wizard's simulation model is
refused by the free Vivado Simulator licence (54,716 instances against a limit of 50,000): results/56a_serdes/licences.md.

B56A_RECORD=<dir> writes the bench output there."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

DESIGN = Path(__file__).parent.parent
ROOT = DESIGN.parents[1]


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="Icarus Verilog not installed")
def test_core_with_standin(tmp_path: Path) -> None:
    out = tmp_path / "core.vvp"
    srcs = [ROOT / "flow/cdc_models/cdc_inj_pkg.sv", ROOT / "flow/cdc_models/xpm_cdc_models.sv", DESIGN / "rtl/prbs64.sv",
            DESIGN / "sim/gth_wiz_model.sv", DESIGN / "rtl/gth_serdes_core.sv", DESIGN / "sim/tb_gth_loopback.sv"]
    r = subprocess.run(["iverilog", "-g2012", "-DGT_STANDIN", "-s", "tb_gth_loopback", "-o", str(out), *map(str, srcs)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    r = subprocess.run(["vvp", str(out)], capture_output=True, text=True, timeout=600)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("CHECK", "RESULT", "TB-DONE"))]
    rec = os.environ.get("B56A_RECORD")
    if rec:
        Path(rec).mkdir(parents=True, exist_ok=True)
        (Path(rec) / "core_sim_standin.txt").write_text("\n".join(lines) + "\n")
    fails = [ln for ln in lines if " FAIL " in ln]
    assert not fails, "\n".join(fails)
    assert lines and lines[-1] == "TB-DONE 0", lines[-3:]
    assert sum(" PASS " in ln for ln in lines) >= 23
