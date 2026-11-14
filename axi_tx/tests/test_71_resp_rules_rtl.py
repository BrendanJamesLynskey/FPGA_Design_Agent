"""Brief 71: seeded faults for the missing-response rule (axi_tx/rtl/axil_resp_rules.sv) under Icarus.

A clean slave and a legal slave just inside the bound fire nothing; the AXI DMA register port's fault (brief 69: one B
for two accepted writes) fires the write bit and only it; a read never answered fires the read bit and only it. Each mode
must compile and finish (a mutant that does not compile is not "caught")."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = [ROOT / "axi_tx" / "rtl" / "axil_resp_rules.sv", Path(__file__).with_name("resp_rules_tb.sv")]


def _run(mode: int, tmp: Path) -> tuple[int, int]:
    out = tmp / f"tb{mode}.vvp"
    subprocess.run(["iverilog", "-g2012", "-o", str(out), f"-Presp_rules_tb.MODE={mode}", *map(str, SRC)], check=True)
    r = subprocess.run(["vvp", "-n", str(out)], capture_output=True, text=True, timeout=120, check=True)
    m = re.search(r"RESULT lost_w=(\d+) lost_r=(\d+)", r.stdout)
    assert m, r.stdout[-500:]
    return int(m.group(1)), int(m.group(2))


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog is not installed")
@pytest.mark.parametrize("mode,want", [(0, "none"), (1, "write"), (2, "read"), (3, "none"), (4, "none")])
def test_missing_response_rule(mode: int, want: str, tmp_path: Path) -> None:
    w, r = _run(mode, tmp_path)
    assert (w > 0, r > 0) == {"none": (False, False), "write": (True, False), "read": (False, True)}[want], (mode, w, r)
