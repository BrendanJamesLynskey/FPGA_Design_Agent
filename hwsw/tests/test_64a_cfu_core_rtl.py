"""Brief 64A+: ip_lib/crc32_step built into the pinned BRV32P core as a custom instruction (simulation only). The run
must pass (every CRC equal to zlib's, the killed-in-EX case included) and give the committed cycle counts when the
compiler and simulator are the ones that made them (results/64a_hwsw/cfu_crc32.json)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hwsw.cfu_core import run_bench

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = ROOT / "results" / "64a_hwsw" / "cfu_crc32.json"
pytestmark = pytest.mark.skipif(not shutil.which(f"{run_bench.CROSS}gcc") or not shutil.which("iverilog"),
                                reason="needs riscv64-unknown-elf-gcc and Icarus Verilog")


def test_crc32_custom_instruction_in_the_core(tmp_path: Path) -> None:
    rec = run_bench.run(["word", "byte"], baseline=True)       # raises unless every run ends in RESULT PASS
    (tmp_path / "cfu_crc32.json").write_text(json.dumps(rec, indent=1))
    assert rec["patch_is_transparent"]
    old = json.loads(COMMITTED.read_text())
    if (old["compiler"], old["simulator"]) != (rec["compiler"], rec["simulator"]):
        pytest.skip(f"tools differ from the committed record ({old['compiler']}, {old['simulator']}): cycles not compared")
    for cfg, c in old["configs"].items():
        assert rec["configs"][cfg]["kernels"] == c["kernels"], f"{cfg}: cycle counts differ from {COMMITTED}"
