"""Brief 231 item 8: the Yosys logic-depth estimate (flow/yosys_depth.py)."""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flow import yosys_depth as yd  # noqa: E402


def cell(t, **pins):
    return {"type": t, "connections": {k: v for k, v in pins.items()}}


def net(cells):
    return {"modules": {"top": {"attributes": {"top": 1}, "cells": cells}}}


def test_lut_chain_between_registers_counts_each_lut():
    n = net({"ff0": cell("FDRE", Q=[2], D=[9]),
             "l1": cell("LUT2", I0=[2], I1=[3], O=[4]), "l2": cell("LUT6", I0=[4], O=[5]), "l3": cell("LUT3", I0=[5], O=[6]),
             "ff1": cell("FDRE", D=[6], Q=[7])})
    r = yd.depth_from_json(n, "top")
    assert r["depth"] == 3 and r["levels"] == 3 and r["path"] == ["LUT2", "LUT6", "LUT3"] and r["cells"] == 3


def test_the_longest_branch_wins_and_a_register_breaks_the_path():
    n = net({"a": cell("LUT2", I0=[1], O=[2]), "b": cell("LUT2", I0=[2], O=[3]), "c": cell("LUT2", I0=[1], O=[4]),
             "d": cell("LUT4", I0=[3], I1=[4], O=[5]),
             "ff": cell("FDRE", D=[5], Q=[6]), "e": cell("LUT2", I0=[6], O=[7])})
    assert yd.depth_from_json(n, "top")["depth"] == 3          # a, b, d; e starts again after the register


def test_carry4_counts_half_a_level_since_vivado_converts_it_to_carry8():
    n = net({"c0": cell("CARRY4", CI=[1], CO=[2, 3, 4, 5], O=[6, 7, 8, 9]), "c1": cell("CARRY4", CI=[5], CO=[10, 11, 12, 13], O=[14, 15, 16, 17]),
             "l": cell("LUT2", I0=[13], O=[20])})
    r = yd.depth_from_json(n, "top")
    assert r["depth"] == 2.0 and r["levels"] == 2 and r["path"] == ["CARRY4", "CARRY4", "LUT2"]
    assert yd.cell_weight("CARRY8") == 1.0 and yd.cell_weight("MUXF7") == 1.0


def test_a_combinational_loop_does_not_hang():
    n = net({"a": cell("LUT2", I0=[2], O=[1]), "b": cell("LUT2", I0=[1], O=[2])})
    assert yd.depth_from_json(n, "top")["depth"] >= 1


def test_an_empty_design_has_depth_zero():
    assert yd.depth_from_json(net({}), "top")["depth"] == 0


@pytest.mark.skipif(yd.find_yosys() is None, reason="Yosys (OSS CAD Suite) not installed")
def test_a_real_synthesis_of_a_small_design(tmp_path):
    src = tmp_path / "t.sv"
    src.write_text("module t(input logic clk, input logic [5:0] a, output logic y);\n  logic r;\n  always_ff @(posedge clk) r <= &a ^ a[0];\n"
                   "  assign y = r;\nendmodule\n")
    try:
        r = yd.run_yosys([src], "t", "xcup")
    except RuntimeError as e:                                  # slang plugin missing in this installation
        pytest.skip(str(e))
    assert 1 <= r["depth"] <= 3 and r["cells"] >= 1
