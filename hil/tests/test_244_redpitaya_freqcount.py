"""Brief 244: the frequency counter's end-of-gate update split over two clocks (timing repair of build d2f617ca's span path; iverilog, skipped without it).

The repaired block (pilots/225/rp_freqcount/agent_244_rtl) must (a) pass brief 225's independent cross-check, (b) match agent_235_r2_rtl register for register
one clock later over a mixed run of gates (the diff testbench), and (c) the diff testbench must have teeth: a mutated span makes it fail."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "pilots" / "225" / "rp_freqcount"
NEW, OLD = D / "agent_244_rtl", D / "agent_235_r2_rtl"
pytestmark = pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")


def sim(tmp: Path, files: list[Path | tuple[str, str]]) -> str:
    srcs = []
    for i, f in enumerate(files):
        if isinstance(f, tuple):
            p = tmp / f"gen{i}.sv"
            p.write_text(f[1])
            srcs.append(str(p))
        else:
            srcs.append(str(f))
    subprocess.run(["iverilog", "-g2012", "-o", str(tmp / "a.out"), *srcs], check=True, capture_output=True)
    return subprocess.run(["vvp", str(tmp / "a.out")], check=True, capture_output=True, text=True, timeout=600).stdout


def old_copies() -> list[tuple[str, str]]:
    rtl = (OLD / "rp_freqcount.sv").read_text().replace("module rp_freqcount", "module rp_freqcount_old").replace("schmitt_edge u_edge", "schmitt_edge_old u_edge")
    edge = (OLD / "schmitt_edge.sv").read_text().replace("module schmitt_edge", "module schmitt_edge_old")
    return [("old", rtl), ("oldedge", edge)]


def test_the_independent_cross_check_passes_on_the_repaired_block(tmp_path: Path) -> None:
    out = sim(tmp_path, [D / "crosscheck_tb.sv", NEW / "rp_freqcount.sv", NEW / "schmitt_edge.sv"])
    assert "XCHECK PASS" in out and "access latency 1" in out


def test_the_repaired_block_equals_the_old_one_one_clock_later(tmp_path: Path) -> None:
    out = sim(tmp_path, [NEW / "diff_tb.sv", NEW / "rp_freqcount.sv", NEW / "schmitt_edge.sv", *old_copies()])
    assert "DIFF PASS" in out and " 0 mismatches" in out


def test_the_diff_testbench_has_teeth(tmp_path: Path) -> None:
    rtl = (NEW / "rp_freqcount.sv").read_text()
    for old, new in (("(fin_edges >= 32'd2) ? (fin_last - fin_first)", "(fin_edges >= 32'd3) ? (fin_last - fin_first)"),
                     ("span        <= span_f;", "span        <= span_f + 32'd1;"),
                     ("meas_done   <= meas_done + 32'd1;\n            end\n        end\n    end", "meas_done   <= meas_done + 32'd2;\n            end\n        end\n    end")):
        assert old in rtl
        out = sim(tmp_path, [NEW / "diff_tb.sv", ("mut", rtl.replace(old, new)), NEW / "schmitt_edge.sv", *old_copies()])
        assert "DIFF FAIL" in out


def test_the_documented_latency_is_in_the_file_header() -> None:
    head = "\n".join((NEW / "rp_freqcount.sv").read_text().splitlines()[:16])
    assert "ONE adc_clk later" in head and "START written in it is ignored" in head
