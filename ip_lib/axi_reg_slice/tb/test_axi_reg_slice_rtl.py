"""ip_lib/axi_reg_slice under cocotb + Icarus: axil_reg_slice and axi4_reg_slice with every channel against the pipe_reg model,
at several per-channel MODE mixes and N; the elaboration of every mode. NET_RTL_AXI_REG_SLICE points the tests at a seeded-fault copy."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "ip_lib" / "axi_reg_slice" / "tb"

# (top, N, (MODE_AW, MODE_W, MODE_B, MODE_AR, MODE_R), extra parameters)
POINTS = [("axil_reg_slice", 1, (1, 1, 1, 1, 1), {}), ("axil_reg_slice", 2, (2, 3, 4, 0, 1), {}), ("axil_reg_slice", 0, (1, 1, 1, 1, 1), {}),
          ("axil_reg_slice", 3, (3, 3, 3, 3, 3), {"ADDR_W": 12, "DATA_W": 64}), ("axi4_reg_slice", 1, (1, 2, 1, 1, 2), {}),
          ("axi4_reg_slice", 2, (1, 4, 3, 1, 0), {"ID_W": 8, "DATA_W": 128}), ("axi4_reg_slice", 1, (4, 4, 4, 4, 4), {"ID_W": 1})]


@pytest.mark.parametrize("top,n,modes,extra", POINTS)
def test_five_channels(top, n, modes, extra):
    params = {"N": n, **{f"MODE_{c}": m for c, m in zip(("AW", "W", "B", "AR", "R"), modes)}, **extra}
    srcs = sim.rtl("axi_reg_slice") + sorted((ROOT / "ip_lib" / "pipe_reg" / "rtl").glob("*.sv"))
    name = f"{top}_n{n}_" + "".join(map(str, modes)) + "_" + "_".join(f"{k}{v}" for k, v in sorted(extra.items()))
    cocotb_run.run(name, top, srcs, "axi_slice_cocotb", TB, parameters=params, extra_env={"PYTHONPATH": str(ROOT)})


@pytest.mark.parametrize("params", [{"N": 17}, {"N": -1}, {"MODE_AW": 5}, {"MODE_R": -1}])
def test_guards(params):
    srcs = sim.rtl("axi_reg_slice") + sorted((ROOT / "ip_lib" / "pipe_reg" / "rtl").glob("*.sv"))
    bad, out = sim.elaborate_fails(srcs, "axil_reg_slice", params)
    assert bad, out
