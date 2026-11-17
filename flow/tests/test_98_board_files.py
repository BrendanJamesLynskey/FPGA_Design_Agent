"""Brief 98: the board files the agent can now target (KR260) or use more of (ZedBoard buttons and switches), through the agent's own
constraints writer, and the facts brief 98 recorded."""

from __future__ import annotations

from pathlib import Path

import yaml

from agent.core import constraints as con

ROOT = Path(__file__).resolve().parents[2]
BOARDS = ROOT / "boards"


def test_kr260_is_targetable_and_the_writer_gives_its_pins():
    cat = yaml.safe_load((BOARDS / "catalogue.yaml").read_text())["boards"]["kr260"]
    assert cat["targetable"] is True
    r = con.generate_xdc(BOARDS / "kr260", [{"port": "clk", "resource": "clk"}, {"port": "led", "resource": "led"},
                                           {"port": "sfp_tx_disable", "resource": "sfp_tx_disable"}])
    assert not r.get("errors"), r
    x = r["xdc"]
    assert "PACKAGE_PIN C3 " in x and "PACKAGE_PIN F8 " in x and "PACKAGE_PIN E8 " in x and "PACKAGE_PIN Y10 " in x
    assert "create_clock" in x and "-period 40.00" in x          # 25 MHz, the frequency stays unconfirmed in the board file
    y = yaml.safe_load((BOARDS / "kr260" / "board.yaml").read_text())
    assert y["slow_ports"] and y["measured_on_board"]["not_measured"]


def test_zedboard_vadj_pins_are_lvcmos18_and_pmods_lvcmos33_with_the_owner_fact():
    y = yaml.safe_load((BOARDS / "zedboard" / "board.yaml").read_text())
    f = next(i for i in y["facts"] if i["item"] == "Vadj banks")
    assert f["confirmed_by"] == "owner" and f["confirmed_on"] == "2026-11-17" and "1V8" in f["value"] and "JP6" in f["value"]
    master, _ = con.parse_xdc((BOARDS / "zedboard" / "zedboard-pins.xdc").read_text())
    for p in ("BTNC", "BTND", "BTNL", "BTNR", "BTNU", *[f"SW[{i}]" for i in range(8)]):
        assert master[p][1] == "LVCMOS18", p
    for p in ("JA1", "JB10", "JC1_N", "JD4_P"):
        assert master[p][1] == "LVCMOS33", p
    assert master["BTNC"][0] == "P16" and master["SW[7]"][0] == "M15"
    assert y["resources"]["btn"] == "BTNC" and len(y["resources"]["sw"]) == 8


def test_arty_s7_internal_vref_is_documented_not_derived():
    y = yaml.safe_load((BOARDS / "arty_s7_50" / "board.yaml").read_text())
    iv = y["internal_vref"]
    assert iv["status"] == "documented" and iv["volts"] == 0.675 and set(iv["source"]) == {"UG471", "UG912"} <= set(y["sources"])
