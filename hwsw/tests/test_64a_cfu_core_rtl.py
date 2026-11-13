"""Brief 64A+: ip_lib/crc32_step built into the pinned BRV32P core as a custom instruction (simulation only). The run
must pass (every CRC equal to zlib's, after a misaligned-load trap and under timer interrupts) and give the committed
cycle counts when the compiler and simulator are the ones that made them (results/64a_hwsw/cfu_crc32.json). The
wrapper's monitor must show both kinds of kill the program sets up: one before the unit started (the trap, taken in the
instruction's first clock in EX) and at least one with the operation in flight (an interrupt, which the core takes
only in the clock the unit delivers). A retry that has to wait for a killed operation does not happen in this core (a
trap handler takes longer than the unit's latency); hwsw/tests/test_64a_cfu_wrapper_rtl.py drives that case.

Both integration styles run (brief 64A2): the EX-stall style (cfu_word, cfu_byte) and the MEM-completion style
(cfu_word_mem, cfu_byte_mem), which has no kill path (an instruction is issued only as it enters MEM, which it then
always leaves with its result), so it has no monitor; the same program, trap and interrupts included, must pass. The
directed stale-prediction program (bench/stale_btb.c) must lose the custom instruction on the EX style without the
mispredict-hold patch (the pinned core's behaviour: the case is reachable) and pass on every patched configuration."""
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
    rec = run_bench.run(["word", "byte"], baseline=True)       # raises unless every run ends as expected
    (tmp_path / "cfu_crc32.json").write_text(json.dumps(rec, indent=1))
    assert rec["patch_is_transparent"]
    assert set(rec["configs"]) == {"baseline", "cfu_word", "cfu_byte", "cfu_word_mem", "cfu_byte_mem"}
    st = rec["stale_btb"]["results"]
    assert st["cfu_word_pinned"].startswith("RESULT FAIL") and st["cfu_word_fixed"].startswith("RESULT PASS"), st
    assert st["cfu_word_mem_pinned"].startswith("RESULT PASS") and st["cfu_word_mem_fixed"].startswith("RESULT PASS"), st
    for cfg in ("cfu_word", "cfu_byte"):
        mon = rec["configs"][cfg]["monitor"]
        assert mon["kills"].get("before_start", 0) >= 1, f"{cfg}: the trap did not kill the instruction: {mon}"
        assert mon["kills"].get("in_flight", 0) >= 1, f"{cfg}: no interrupt landed on a custom instruction: {mon}"
    old = json.loads(COMMITTED.read_text())
    if (old["compiler"], old["simulator"]) != (rec["compiler"], rec["simulator"]):
        pytest.skip(f"tools differ from the committed record ({old['compiler']}, {old['simulator']}): cycles not compared")
    for cfg, c in old["configs"].items():
        assert rec["configs"][cfg]["kernels"] == c["kernels"], f"{cfg}: cycle counts differ from {COMMITTED}"
