"""b102_managed_fcs: the whole design simulated with the CRC block from its functional netlist (needs the OSS CAD Suite and Icarus;
skipped with a notice without them), and the manifest facts the design depends on."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "designs" / "b102_managed_fcs" / "scripts"))

D = ROOT / "designs" / "b102_managed_fcs"
OSS = os.environ.get("FDA_OSS_CAD")
HAVE = bool(shutil.which("yosys", path=(f"{OSS}/bin:" if OSS else "") + os.environ["PATH"])) and bool(shutil.which("iverilog"))
need = pytest.mark.skipif(not HAVE, reason="needs yosys (the OSS CAD Suite, FDA_OSS_CAD) and iverilog")


@need
def test_the_self_test_passes_with_the_netlist_and_the_edit_saves_one_clock(tmp_path):
    if OSS:
        os.environ["PATH"] = f"{OSS}/bin:" + os.environ["PATH"]
    import measure_latency as m
    assert m.main(["--out", str(tmp_path / "l.json"), "--work", str(tmp_path / "w")]) == 0
    r = json.loads((tmp_path / "l.json").read_text())
    assert r["baseline"]["led0_at_end"] == 1 and r["edited"]["led0_at_end"] == 1
    assert r["clocks_saved"] == 1


def test_the_expected_crc_in_the_sequencer_is_the_ieee_value_of_the_frame():
    import zlib
    words = [(int(f"{i:02x}" * 2, 16) ^ 0x6978) for i in range(16)]
    want = zlib.crc32(b"".join(w.to_bytes(2, "little") for w in words)) ^ 0xFFFFFFFF      # the register is the complement of zlib's value
    assert f"32'h{want:08X}" in (D / "rtl/fcs_ctrl.sv").read_text()
