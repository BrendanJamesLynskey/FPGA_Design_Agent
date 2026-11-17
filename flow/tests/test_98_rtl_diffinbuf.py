"""Brief 98: Vivado 12-1411 from ``synth_design -rtl`` on an UltraScale+ differential input (the AUP-ZU3 smoke build, brief 95) is
information, not a gate failure, but only when the real synthesis does not print it too. Uses the brief 48 fixture's logs as a base;
no Vivado needed."""

from __future__ import annotations

import shutil
from pathlib import Path

from flow import exceptions_check as ec

FX = Path(__file__).parent / "fixtures"
GOLD = FX / "ila_ip_exceptions" / "ila_ip_base"
XDC = [FX / "ila_exceptions" / "xdc" / "t1_dimmer_counter.xdc"]
MSG = ("CRITICAL WARNING: [Vivado 12-1411] Cannot set LOC property of ports, u_clk_ibuf/DIFFINBUF_INST. Illegal to place instance "
       "u_clk_ibuf/DIFFINBUF_INST on site D7. The location site type (HPIOB_M) does not match the cell type (DIFFINBUF). Please choose a "
       "compatible site for the instance. [/work/boards/aup_zu3/smoke/design.xdc:5]\n")
RTL = "Command: synth_design -rtl -rtl_skip_ip -top t -part xczu3eg-sfvc784-2-e\n"
REAL = "Command: synth_design -top t -part xczu3eg-sfvc784-2-e\n"


def _build(tmp: Path, text: str) -> Path:
    d = tmp / "build"
    shutil.copytree(GOLD, d)
    (d / "probe_map.txt").unlink()
    (d / "vivado.log").write_text(text)
    return d


def test_message_in_rtl_elaboration_only_is_info(tmp_path: Path) -> None:
    r = ec.evaluate(_build(tmp_path, RTL + MSG + REAL), "synth", XDC)
    assert not [f for f in r["failures"] if f["rule"] == "EXC-XDC-MSG"]
    info = [i for i in r["info"] if i["rule"] == "EXC-XDC-RTL-DIFFINBUF"]
    assert len(info) == 1 and info[0]["vivado"]["lines"] == ["design.xdc:5"]


def test_message_that_recurs_in_the_real_synthesis_fails(tmp_path: Path) -> None:
    r = ec.evaluate(_build(tmp_path, RTL + MSG + REAL + MSG), "synth", XDC)
    assert [f["rule"] for f in r["failures"] if f["rule"] == "EXC-XDC-MSG"] == ["EXC-XDC-MSG"]


def test_message_with_no_rtl_stage_fails(tmp_path: Path) -> None:
    r = ec.evaluate(_build(tmp_path, REAL + MSG), "synth", XDC)
    assert any(f["rule"] == "EXC-XDC-MSG" for f in r["failures"])


def test_a_different_12_1411_still_fails(tmp_path: Path) -> None:
    other = MSG.replace("DIFFINBUF_INST", "OBUF_INST")
    r = ec.evaluate(_build(tmp_path, RTL + other + REAL), "synth", XDC)
    assert any(f["rule"] == "EXC-XDC-MSG" for f in r["failures"])
