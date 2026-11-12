"""pytest entry: trigger_core under cocotb + Icarus against the reference model.

B58A_RECORD=<dir> writes the latency, stale-parameter and loop results there (results/b58a when recorded)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
MAC = ROOT / "ip_lib" / "eth_mac_rgmii" / "rtl"
CORE = ["feed_rx", "book", "rules", "interlocks", "order_ctl", "lat_hist", "mdio_master", "feed_gen", "trigger_core"]
SOURCES = [ROOT / "ip_lib/eth_mac_rmii/rtl/eth_crc32.sv", MAC / "mac_rx.sv", MAC / "mac_tx.sv"] + \
    [DESIGN / "rtl" / f"{m}.sv" for m in CORE]


def _env(tag: str) -> dict[str, str]:
    env = {"PYTHONPATH": str(ROOT)}
    rec = os.environ.get("B58A_RECORD")
    if rec:
        Path(rec).mkdir(parents=True, exist_ok=True)
        env.update({"B58A_LAT_OUT": str(Path(rec) / f"latency_sim{tag}.json"),
                    "B58A_STALE_OUT": str(Path(rec) / "stale_parameters_sim.json"),
                    "B58A_LOOP_OUT": str(Path(rec) / "loop_sim.json"),
                    "B58A_PINS_OUT": str(Path(rec) / "pins_sim.json")})
    return env


def test_b58a_core() -> None:
    env = _env("") | {"B58A_BUILD_MODE": "0"}
    cocotb_run.run("b58a_core", "trigger_core", SOURCES, "b58a_cocotb", HERE,
                   parameters={"BUILD_MODE": 0, "MDIO_DIV": 4}, seed=int(os.environ.get("B58A_SEED", "1")),
                   extra_env=env)


@pytest.mark.parametrize("mode,tag", [(1, "_csum_after"), (2, "_assemble")])
def test_b58a_build_modes(mode: int, tag: str) -> None:
    """The comparison builds: 1 computes the IPv4 checksum after the decision (streamed as the MAC asks); 2 stores and
    assembles the whole frame after the decision, then sends it."""
    env = _env(tag) | {"B58A_BUILD_MODE": str(mode)}
    cocotb_run.run(f"b58a_core_mode{mode}", "trigger_core", SOURCES, "b58a_cocotb", HERE,
                   parameters={"BUILD_MODE": mode, "MDIO_DIV": 4},
                   testcase=["stage_latency", "speculative_undo_both_ways"], extra_env=env)


def test_b58a_pins() -> None:
    """kr260_top with RGMII looped from port B to port A (simulation models of the DDR registers and the XPM FIFO)."""
    top = [MAC / f"{m}.sv" for m in ("rgmii_rx", "rgmii_tx", "gmii_cdc")] + \
        [DESIGN / "rtl" / f"{m}.sv" for m in ("jtag_bus", "kr260_top")]
    cocotb_run.run("b58a_pins", "kr260_top", SOURCES + top, "b58a_pins_cocotb", HERE, extra_env=_env(""))
