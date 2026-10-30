"""prepare.py: the Tcl it writes must load in a real Tcl interpreter, and the build stamp must be stable."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from flow import prepare

DESIGN = "designs/t1_dimmer_counter"


def run(tmp: Path, variant: str, capsys: pytest.CaptureFixture[str]) -> dict:
    assert prepare.main([DESIGN, "--variant", variant, "--out", str(tmp)]) == 0
    return json.loads(capsys.readouterr().out)


def test_stamp_is_the_sources_hash_and_stable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = run(tmp_path / "a", "base", capsys)
    b = run(tmp_path / "b", "base", capsys)
    assert a["sources_sha256"] == b["sources_sha256"] and a["build_stamp"] == a["sources_sha256"][:8]
    assert "designs/t1_dimmer_counter/design.xdc" in a["files"] and "shell/rtl/uart_rx.sv" in a["files"]
    assert f"BUILD_STAMP=32'h{a['build_stamp']}" in (tmp_path / "a" / "inputs.tcl").read_text()


@pytest.mark.skipif(shutil.which("tclsh") is None, reason="needs tclsh")
def test_generated_tcl_loads(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(tmp_path, "ila", capsys)
    script = (f"source {tmp_path / 'inputs.tcl'}; source $probes_tcl; "
              "puts [list $top $part $ila [llength $sources] [llength $ila_probes] [lindex $ila_probes 0]]")
    out = subprocess.run(["tclsh"], input=script, capture_output=True, text=True, check=True).stdout.strip()
    assert out == "t1_dimmer_counter_top xc7a100tcsg324-1 1 10 11 {count {u_dut/count_reg[*]/Q} 16}"
