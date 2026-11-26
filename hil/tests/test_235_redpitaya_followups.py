"""Brief 235: the frequency meter's first-read-after-reset failure, root-caused (iverilog; skipped without it).

The final-spec RTL (pilots/225/rp_freqcount/agent_final_spec_rtl_fails_xcheck) decodes the bus address in an ``always @(*)`` block. A Verilog
``always @(*)`` does not run at time 0, only when an input changes. The cross-check's first read is at address 0 (the ID register), which is also the
address bus's initial value, so the decode never ran and ``sel`` stayed X: the first read answered rdata 0 and err X. The RTL is fine on the board (the
synthesised logic has no such gap); it is a simulation-only difference that SystemVerilog's ``always_comb`` removes."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "pilots" / "225" / "rp_freqcount"
RTL = D / "agent_final_spec_rtl_fails_xcheck" / "rp_freqcount.sv"
pytestmark = pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")


def run(tmp_path: Path, tb: str, rtl: str) -> str:
    (tmp_path / "tb.sv").write_text(tb)
    (tmp_path / "rtl.sv").write_text(rtl)
    subprocess.run(["iverilog", "-g2012", "-o", str(tmp_path / "a.out"), str(tmp_path / "tb.sv"), str(tmp_path / "rtl.sv")], check=True, capture_output=True)
    return subprocess.run(["vvp", str(tmp_path / "a.out")], check=True, capture_output=True, text=True).stdout


def test_the_failure_is_the_time_zero_decode(tmp_path: Path) -> None:
    tb, rtl = (D / "crosscheck_tb.sv").read_text(), RTL.read_text()
    out = run(tmp_path, tb, rtl)
    assert "XCHECK FAIL 1" in out and "ID read 00000000 err x" in out                  # as recorded in brief 225
    assert "XCHECK PASS" in run(tmp_path, tb, re.sub(r"always @\(\*\)", "always_comb", rtl))      # the decode runs at time 0
    assert "XCHECK PASS" in run(tmp_path, tb.replace("addr = 0,", "addr = 32'hFFFF0,"), rtl)        # or a first read away from the initial address


def test_the_overlay_is_added_after_the_vendors_constraints_and_only_once() -> None:
    from tools import rp_shell
    src = "add_files -fileset constrs_1 sdc/red_pitaya.xdc\nset gith [exec git log -1]\nlaunch_runs impl_1\n"
    out = rp_shell.overlay_tcl(src)
    assert out.index("sdc/red_pitaya.xdc") < out.index("sdc/fda_overlay.xdc") < out.index("set gith")
    assert "PROCESSING_ORDER LATE" in out and out.count("fda_overlay.xdc") == 2
    with pytest.raises(SystemExit):
        rp_shell.overlay_tcl(src + "set gith [exec git log]\n")
    with pytest.raises(SystemExit):
        rp_shell.overlay_tcl("nothing\n")


def test_the_overlay_names_only_flat_netlist_cells_and_carries_its_reasons() -> None:
    t = (ROOT / "boards" / "redpitaya_stemlab_125_14" / "shell" / "fda_overlay.xdc").read_text()
    code = [l for l in t.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    assert any("get_cells -quiet -hierarchical -filter" in l for l in code)            # leaf cells: a hierarchical cell is not a valid start or end point
    assert sum(l.startswith("set_false_path") for l in code) == 2
    assert "NOT make the vendor instruments work" in t or "do NOT make the vendor instruments work" in t.replace("\n# ", " ")
