"""Brief 48: the exception gate on an ILA that is an IP in the netlist (Vivado 2026.1, free Basic licence tier). The fixture is
the route- and synth-stage exception reports and the XDC messages of a real t1_dimmer_counter ILA build (flow/tests/fixtures/
ila_ip_exceptions/ila_ip_base): 15 ignored exceptions from the ILA core, and the debug hub IP's own constraint script printing
CRITICAL WARNINGs from an xsdbm_*.xdc. No Vivado needed."""

from __future__ import annotations

import shutil
from pathlib import Path

from flow import exceptions_check as ec

FX = Path(__file__).parent / "fixtures"
GOLD = FX / "ila_ip_exceptions" / "ila_ip_base"
XDC = [FX / "ila_exceptions" / "xdc" / "t1_dimmer_counter.xdc"]
HUB_LINE = ("CRITICAL WARNING: [Common 17-1548] Command failed: can't read \"skew_value\": no such variable\n"
            " [/work/build/ila/.Xil/Vivado-1-host/dbg_hub_CV.0/out/xsdbm_cc_late_late.xdc:99]\n")


def _copy(tmp: Path) -> Path:
    d = tmp / "build"
    shutil.copytree(GOLD, d)
    return d


def test_ila_ip_build_passes_with_hub_messages_as_info(tmp_path: Path) -> None:
    for stage in ("synth", "route"):
        r = ec.evaluate(_copy(tmp_path / stage), stage, XDC)
        assert r["pass"], r["failures"]
    r = ec.evaluate(_copy(tmp_path / "s2"), "synth", XDC)
    hub = [i for i in r["info"] if i["rule"] == "EXC-XDC-DEBUG-HUB"]
    assert len(hub) == 1 and hub[0]["count"] == 10 and hub[0]["vivado"]["files"] == ["xsdbm_cc_late_late.xdc"]
    r = ec.evaluate(_copy(tmp_path / "r2"), "route", XDC)
    assert sum(1 for i in r["info"] if i["rule"] == "EXC-IGNORED-DEBUG-IP") == 15


def test_hub_messages_are_not_allowed_in_a_build_without_an_ila(tmp_path: Path) -> None:
    d = _copy(tmp_path)
    (d / "probe_map.txt").unlink()                       # only ILA builds write it
    r = ec.evaluate(d, "synth", XDC)
    assert not r["pass"] and {f["rule"] for f in r["failures"]} == {"EXC-XDC-MSG"}


def test_a_design_xdc_message_still_fails(tmp_path: Path) -> None:
    d = _copy(tmp_path)
    log = d / "vivado.log"
    log.write_text(log.read_text() + "CRITICAL WARNING: [Vivado 12-4739] set_false_path:No valid object(s) found for '-from [get_ports nope]'. "
                   "[/work/designs/t1_dimmer_counter/design.xdc:12]\n")
    r = ec.evaluate(d, "synth", XDC)
    assert not r["pass"] and [f["file"] for f in r["failures"]] == ["design.xdc"]
    assert any(i["rule"] == "EXC-XDC-DEBUG-HUB" for i in r["info"])      # the hub messages are still only info


def test_a_hub_looking_file_outside_the_hub_directory_still_fails(tmp_path: Path) -> None:
    d = _copy(tmp_path)
    log = d / "vivado.log"
    log.write_text(log.read_text() + HUB_LINE.replace("/.Xil/Vivado-1-host/dbg_hub_CV.0/out", "/work/designs/t1"))
    r = ec.evaluate(d, "synth", XDC)
    assert not r["pass"] and [f["rule"] for f in r["failures"]] == ["EXC-XDC-MSG"]


def test_a_design_touching_exception_still_fails(tmp_path: Path) -> None:
    d = _copy(tmp_path)
    p = d / "exceptions_ignored_route.rpt"
    row = "POS         [get_cells {{a_reg[*]} {b_reg[*]}}]  *               [get_cells en_reg]  cycles=2        -               Non-existent path\n"
    p.write_text(p.read_text().rstrip("\n") + "\n" + row.replace("POS", "2"))      # position 2 is one of our XDC's lines
    r = ec.evaluate(d, "route", XDC)
    assert not r["pass"] and [(f["rule"], f["position"], f["file"]) for f in r["failures"]] == [("EXC-IGNORED", 2, "t1_dimmer_counter.xdc")]
    p.write_text(p.read_text().replace("2         [get_cells {{a_reg", "60        [get_cells {{a_reg"))
    r = ec.evaluate(d, "route", XDC)      # after our positions but naming design cells: still a failure
    assert not r["pass"]


# --- the debug hub's JTAG crossing (flow/gates.py hub_crossings) --------------------------------------------------------------
from flow import gates

CI = GOLD / "clock_interaction_route.rpt"


def test_hub_crossing_of_the_real_ila_build_is_asynchronous() -> None:
    hub = gates.hub_crossings(gates.parse_clock_interaction(CI.read_text()))
    assert hub["pairs"] == 2 and hub["ok"] and hub["timed_as_synchronous"] == []


def test_hub_crossing_timed_as_synchronous_fails() -> None:
    """Vivado 2026.1 without the hub's properties timed TCK against sys_clk_pin (WNS -2.993 ns inside dbg_hub)."""
    for bad in ("Timed", "Partial False Path"):
        txt = CI.read_text().replace("Max Delay Datapath Only", bad, 1)
        hub = gates.hub_crossings(gates.parse_clock_interaction(txt))
        assert not hub["ok"] and len(hub["timed_as_synchronous"]) == 1 and bad in hub["timed_as_synchronous"][0]


def test_an_ila_build_without_hub_clock_pairs_fails() -> None:
    assert not gates.hub_crossings(gates.parse_clock_interaction("no table here"))["ok"]
