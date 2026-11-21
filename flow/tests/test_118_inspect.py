"""Brief 118: python -m flow inspect (flow/inspect_build.py, flow/inspect_views.py). A synthetic build directory; no Vivado."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from flow import inspect_build as I
from flow import inspect_views as V

UTIL = """| Instance | Module | Total LUTs | Logic LUTs | LUTRAMs | SRLs | FFs | RAMB36 | RAMB18 | URAM | DSP Blocks |
|---|---|---|---|---|---|---|---|---|---|---|
| top                  |   (top) |  30 | 30 | 0 | 0 | 40 | 0 | 0 | 0 | 0 |
|   (top)              |   (top) |   1 |  1 | 0 | 0 |  0 | 0 | 0 | 0 | 0 |
|   u_a                |     mod_a |  20 | 20 | 0 | 0 | 30 | 1 | 0 | 0 | 0 |
|     u_x              |   xpm_cdc_single__parameterized1__3 |   0 |  0 | 0 | 0 |  4 | 0 | 0 | 0 | 0 |
|   u_b                |     mod_b |   9 |  9 | 0 | 0 | 10 | 0 | 0 | 0 | 0 |
"""
TIMING = """Timing Report

Slack (MET) :             0.118ns  (required time - arrival time)
  Source:                 u_a/q_reg/C
                            (rising edge-triggered cell FDRE clocked by clk  {rise@0.000ns fall@3.103ns period=6.206ns})
  Destination:            u_b/d_reg/D
                            (rising edge-triggered cell FDRE clocked by clk  {rise@0.000ns fall@3.103ns period=6.206ns})
  Path Group:             clk
  Path Type:              Setup (Max at Slow Process Corner)
  Requirement:            6.206ns  (clk rise@6.206ns - clk rise@0.000ns)
  Data Path Delay:        5.929ns  (logic 1.802ns (30.392%)  route 4.127ns (69.608%))
  Logic Levels:           2  (LUT2=1 LUT3=1)
  Clock Path Skew:        -0.157ns (DCD - SCD + CPR)

    Location             Delay type                Incr(ns)  Path(ns)    Netlist Resource(s)
  -------------------------------------------------------------------    -------------------
    SLICE_X50Y159        FDRE                                         r  u_a/q_reg/C
  -------------------------------------------------------------------    -------------------
    SLICE_X50Y159        FDRE (Prop_HFF_SLICEL_C_Q)
                                                      0.113     2.612 r  u_a/q_reg/Q
                         net (fo=4, routed)           0.117     2.729    u_a/p_0
    SLICE_X50Y160        LUT4 (Prop_H6LUT_SLICEL_I1_O)
                                                      0.137     2.866 r  u_a/l_i_95/O
"""


def make_build(tmp: Path, src_text: str = "module mod_a; endmodule\n") -> tuple[Path, Path]:
    root = tmp / "repo"
    d = root / "designs" / "d1"
    (d / "rtl").mkdir(parents=True)
    (d / "sim").mkdir()
    (d / "rtl" / "a.sv").write_text(src_text)
    (d / "design.xdc").write_text("# xdc\n")
    (d / "sim" / "tb_a.sv").write_text("module tb_a; endmodule\n")
    files = ["designs/d1/rtl/a.sv", "designs/d1/design.xdc"]
    h = hashlib.sha256()
    for f in files:
        h.update(f.encode() + b"\0" + (root / f).read_bytes() + b"\0")
    b = d / "build" / "base"
    b.mkdir(parents=True)
    (b / "prepare.json").write_text(json.dumps({"design": "designs/d1", "variant": "base", "top": "top", "part": "xc7a100tcsg324-1", "board": "x",
                                                "sources_sha256": h.hexdigest(), "build_stamp": h.hexdigest()[:8], "files": files}))
    (b / "run.json").write_text(json.dumps({"git_commit": "a" * 40, "git_dirty": False, "vivado_version": "2026.1", "build_id": "12345678"}))
    (b / "manifest.json").write_text(json.dumps({"inputs": {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in files}, "build_id": "12345678"}))
    (b / "inputs.tcl").write_text(f"set top {{top}}\nset sources [list {{{root}/designs/d1/rtl/a.sv}}]\nset constraints [list {{{root}/designs/d1/design.xdc}}]\n"
                                  f"set generics [list {{A=1'b0}} {{BUILD_STAMP=32'h{h.hexdigest()[:8]}}}]\nset out {{{b}}}\n")
    (b / "post_synth.dcp").write_bytes(b"x" * 10)
    (b / "post_route.dcp").write_bytes(b"x" * 10)
    (b / "utilization_hier.rpt").write_text(UTIL)
    (b / "timing_worst_setup.rpt").write_text(TIMING)
    return root, d


def test_parse_util_and_tree():
    cols, rows = V.parse_util_hier(UTIL)
    assert cols[0] == "Total LUTs" and len(rows) == 6
    t = V.build_tree(rows)
    assert t["name"] == "top" and [c["name"] for c in t["children"]] == ["u_a", "u_b"] and t["own"]["Total LUTs"] == 1
    assert t["children"][0]["children"][0]["path"] == "u_a/u_x"
    assert V.strip_param("xpm_cdc_single__parameterized1__3") == "xpm_cdc_single"
    assert V.resolve_module("u_a/u_x/q_reg/C", V.flat_hier(t)).startswith("xpm_cdc")


def test_parse_paths():
    (p,) = V.parse_paths(TIMING)
    assert p["slack"] == 0.118 and p["source"] == "u_a/q_reg/C" and p["group"] == "clk" and p["src_clk"] == "clk"
    assert [(c["site"], c["type"], c["incr"]) for c in p["cells"]] == [("SLICE_X50Y159", "FDRE", 0.113), ("SLICE_X50Y160", "LUT4", 0.137)]


def test_stamp_fresh_then_stale(tmp_path):
    root, d = make_build(tmp_path)
    st = I.stamp_report(I.Build(d))
    assert st["stale"] is False and st["stamp_matches_tree"] is True
    (root / "designs/d1/rtl/a.sv").write_text("module mod_a; wire x; endmodule\n")
    st = I.stamp_report(I.Build(d))
    assert st["stale"] and st["changed_files"] == ["designs/d1/rtl/a.sv"] and st["stamp_matches_tree"] is False
    assert any("differ from the build" in w for w in st["warnings"])


def test_project_tcl_and_open_scripts(tmp_path):
    root, d = make_build(tmp_path)
    b = I.Build(d)
    out = tmp_path / "o"
    t = I.project_tcl(b, out, I.sim_benches(b))
    assert f"create_project -force d1_base_{b.stamp}" in t and "-part xc7a100tcsg324-1" in t
    assert "add_files -norecurse -fileset constrs_1" in t and "set_property top top" in t
    assert "set_property generic {A=1'b0 BUILD_STAMP=" in t and "tb_a.sv" in t and "set_property top tb_a [get_filesets sim_1]" in t
    o = I.open_tcl(b, out, "route", b.checkpoints()["route"], True)
    assert "open_checkpoint $fda_cp" in o and "INSPECT-WARNING" in o and ("a" * 40) in o and "start_gui" in o


def test_cli_no_project_writes_everything_and_vivado_is_guarded(tmp_path, monkeypatch):
    root, d = make_build(tmp_path)
    r = I.inspect(str(d), project=False, schematics=[])
    out = Path(r["out"])
    for f in ("INSPECT.md", "INSPECT_STAMP.txt", "make_project.tcl", "open_route.tcl", "open_synth.tcl", "index.html", "inspect.json"):
        assert (out / f).is_file(), f
    assert not (out / "open_place.tcl").exists()
    md = (out / "INSPECT.md").read_text()
    assert "post_place.dcp" in md and "not in this build" in md and "FDA_INSPECT_CKPTS=1" in md and "Is it still today's RTL?" in md
    assert "mod_a" in (out / "index.html").read_text() and (out / "src" / "designs__d1__rtl__a.sv.html").is_file()
    monkeypatch.delenv("FDA_HEAVY_SLOT", raising=False)
    with pytest.raises(I.InspectError, match="take a slot"):
        I.vivado_guard()
    lock = tmp_path / "lock"
    lock.write_text("x")
    monkeypatch.setenv("FDA_HEAVY_SLOT", str(lock))
    monkeypatch.setenv("FDA_TEST_VIVADO_RUNNING", "1")
    with pytest.raises(I.InspectError, match="FDA_VIVADO_MAX"):
        I.vivado_guard()
    with pytest.raises(I.InspectError, match="no post_opt.dcp|no post_place.dcp"):
        I.inspect(str(d), stage="place", project=False)


def test_module_entry_and_errors(tmp_path):
    r = subprocess.run([sys.executable, "-m", "flow", "inspect", str(tmp_path / "nothing")], capture_output=True, text=True)
    assert r.returncode == 2 and "no finished build" in r.stderr
