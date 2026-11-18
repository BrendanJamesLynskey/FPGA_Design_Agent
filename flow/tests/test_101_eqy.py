"""Brief 101: the eqy equivalence gate (flow/eqy_gate.py) and the Yosys synthesis tool (flow/oss_synth.py).

Tool-free tests: the netlist fault injector, the eqy configuration text, the notice when the suite is absent, the comparison
parser. Tool tests (skipped with a reason where the OSS CAD Suite is not installed; CI's ``reset-elab`` job installs the pinned
release 20261112): a clean netlist of a small accumulator passes, and each planted fault fails, for both families; the Yosys
EDIF has the expected cells. Locally: ``FDA_OSS_CAD=<suite dir> python -m pytest flow/tests/test_101_eqy.py``."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from flow import eqy_gate as E
from flow import oss_synth as O
from flow.oss_compare import run as P

DATA = Path(__file__).parent / "data" / "b101"
RTL = [str(DATA / "tiny_acc.sv")]
needs_suite = pytest.mark.skipif(E.find_eqy() is None, reason="eqy (OSS CAD Suite 20261112) not installed: set FDA_OSS_CAD or install it "
                                                              "under ~/.local/opt/oss-cad-suite; the reset-elab CI job runs these")

NET = """module top(clk, rst, d, q);
  input clk; input rst; input [1:0] d; output [1:0] q;
  wire w0, w1;
  LUT2 #(
    .INIT(4'h6)
  ) _1_ (
    .I0(d[0]),
    .I1(d[1]),
    .O(w0)
  );
  LUT3 #(
    .INIT(8'hE8)
  ) _2_ (
    .I0(d[0]),
    .I1(d[1]),
    .I2(rst),
    .O(w1)
  );
  FDSE #(
    .INIT(1'hx)
  ) _3_ (
    .C(clk),
    .CE(1'h1),
    .D(w0),
    .Q(q[0]),
    .S(rst)
  );
  FDRE #(
    .INIT(1'hx)
  ) _4_ (
    .C(clk),
    .CE(1'h1),
    .D(w1),
    .Q(q[1]),
    .R(rst)
  );
endmodule
"""


def test_plant_lut_init_flips_one_bit():
    new, desc = E.plant(NET, "lut_init", 0)
    assert "flipped INIT bit 0 of LUT _1_" in desc and ".INIT(4'h7)" in new and ".INIT(8'hE8)" in new
    new2, _ = E.plant(NET, "lut_init", 1)
    assert ".INIT(4'h6)" in new2 and ".INIT(8'hE8)" not in new2


def test_plant_swap_regs_exchanges_d_nets():
    new, desc = E.plant(NET, "swap_regs", 0)
    assert "swapped the D inputs" in desc
    assert re.search(r"\.D\(w1\),\s*\.Q\(q\[0\]\)", new) or re.search(r"\.D\(w0\),\s*\.Q\(q\[1\]\)", new)
    assert new.count(".D(w0)") == 1 and new.count(".D(w1)") == 1


def test_plant_reset_value_turns_fdse_into_fdre():
    new, desc = E.plant(NET, "reset_value", 0)
    assert "FDSE" not in new.replace("set-by-reset (FDSE)", "") and new.count("FDRE") == 2 and ".R(rst)" in new and ".S(rst)" not in new


def test_plant_reset_drop_ties_the_pin_low():
    new, desc = E.plant(NET, "reset_drop", 0)
    assert ".S(1'h0)" in new and "reset pin S tied low" in desc


def test_plant_refuses_what_it_cannot_plant():
    with pytest.raises(ValueError):
        E.plant("module m; endmodule", "reset_value")
    with pytest.raises(ValueError):
        E.plant(NET, "no_such_fault")


def test_config_states_the_strategy():
    c = E.config("top", ["a.sv"], "n.v", "name", 2, "smtbmc bitwuzla", Path("."), "rst")
    assert "read_slang --top top" in c and "sim -w -clock clk -reset rst" in c and "cells_sim.v" in c and "smtbmc bitwuzla" in c
    assert "rename -hide c:*" in c and "[collect" not in c
    g = E.config("top", ["a.sv"], "n.v", "group", 2, "abc pdr", Path("."), None, True)
    assert "group *" in g and "engine abc pdr" in g and "-reset" not in g


def test_funcsim_glbl_scaffolding_is_stripped_for_the_read_only(tmp_path):
    nl = tmp_path / "n.v"
    nl.write_text("module top (input a);\nendmodule\n\nmodule glbl ();\n  tri1 p_up_tmp;\n  tri (weak1, strong0) PLL_LOCKG = p_up_tmp;\nendmodule\n")
    out = Path(E._strip_glbl(str(nl), tmp_path))
    assert out != nl and "glbl" not in out.read_text() and "module top" in out.read_text()
    assert "glbl" in nl.read_text()                       # the netlist as written (the one hashed) is untouched
    plain = tmp_path / "p.v"
    plain.write_text("module top (input a);\nendmodule\n")
    assert E._strip_glbl(str(plain), tmp_path) == str(plain)


def test_gate_is_skipped_with_a_notice_when_the_suite_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(E, "find_eqy", lambda: None)
    r = E.check("top", RTL, str(DATA / "none.v"), tmp_path)
    assert r.status == "SKIPPED" and not r.ok() and "nothing is claimed" in r.message and "SKIPPED" in r.notice()


def test_oss_synth_scripts_are_recorded_verbatim():
    for k, v in O.SCRIPTS.items():
        assert "synth_xilinx" in v or "abc" in v
    cmds = O.yosys_script("t", ["a.sv"], "xcup", "abc_d", "e.edif", "n.v", 500)
    assert "abc -luts 2:2,3,6:5,10,20 -D 500" in cmds and "write_edif" in cmds and "-noiopad -noclkbuf" in cmds
    assert O.family_of_part("xck26-sfvc784-2LV-c") == "xcup" and O.family_of_part("xc7a100tcsg324-1") == "xc7"
    with pytest.raises(O.OssError):
        O.yosys_script("t", ["a.sv"], "xcup", "nope", "e", "n")


def test_comparison_parser_reads_a_vivado_pass(tmp_path):
    (tmp_path / "done.txt").write_text("42\n")
    (tmp_path / "utilization.rpt").write_text("| CLB LUTs* | 10 | 0 | 0 | 134600 | 0.01 |\n| CLB Registers | 20 | 0 | 0 | 269200 | 0.01 |\n| CARRY8 | 1 | 0 | 0 | 16825 | 0.01 |\n")
    (tmp_path / "timing_summary.rpt").write_text("""    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints     WPWS(ns)     TPWS(ns)  TPWS Failing Endpoints  TPWS Total Endpoints
    -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------     --------     --------  ----------------------  --------------------
      0.211        0.000                      0                   20        0.040        0.000                      0                   20        0.350        0.000                      0                    21
""")
    (tmp_path / "timing_worst.rpt").write_text("  Data Path Delay:        0.912ns  (logic 0.300ns (32.9%)  route 0.612ns (67.1%))\n  Logic Levels:           3  (LUT6=2 FDRE=1)\n")
    r = P.parse(tmp_path, 1.5)
    assert r["closed"] and r["lut"] == 10 and r["ff"] == 20 and r["carry"] == 1 and r["lut_levels"] == 3 and r["data_path_ns"] == 0.912
    assert P.achievable(r) == pytest.approx(1.5 - 0.211)
    (tmp_path / "timing_summary.rpt").write_text((tmp_path / "timing_summary.rpt").read_text().replace("0.211", "-0.100"))
    r = P.parse(tmp_path, 1.5)
    assert not r["closed"] and P.achievable(r) == pytest.approx(1.6)


@needs_suite
@pytest.mark.parametrize("part", ["xck26-sfvc784-2LV-c", "xc7a100tcsg324-1"])
def test_yosys_netlist_is_proved_and_every_planted_fault_fails(part, tmp_path):
    rec = O.synth("tiny_acc", RTL, O.family_of_part(part), "abc9", tmp_path / "ys")
    assert rec["lut"] > 0 and rec["ff"] == 16 and "LUT" in Path(rec["edif"]).read_text()
    clean = E.check("tiny_acc", RTL, rec["netlist"], tmp_path / "clean")
    assert clean.status == "PASS", clean.message
    txt = Path(rec["netlist"]).read_text()
    for kind in E.FAULT_KINDS if hasattr(E, "FAULT_KINDS") else ("lut_init", "swap_regs", "reset_value", "reset_drop"):
        new, desc = E.plant(txt, kind, 1)
        f = tmp_path / f"{kind}.v"
        f.write_text(new)
        r = E.check("tiny_acc", RTL, str(f), tmp_path / kind)
        assert r.status == "FAIL", f"{kind} ({desc}) was not caught: {r.status} {r.message}"
