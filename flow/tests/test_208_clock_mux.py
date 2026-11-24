"""Brief 208: the clock-multiplexer check (flow/clock_mux_check.py, flow/clock_mux_dump.tcl, check ``clock_mux``).

The fixtures under flow/tests/fixtures/clock_mux/ are the dumps (flow/clock_mux_dump.tcl) and report_clock_interaction files of
the real Vivado 2026.1 runs recorded in results/208 (xc7a35tcpg236-1 ``a7_*``, xck26-sfvc784-2LV-c ``k26_*``). The property
the check stands for: a clock mux is a clock buffer, its modes are not timed against each other, and no clock group hides a
real path between a source clock's own registers and the mux fanout. Hand-made dumps cover the cases no run produced.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import clock_mux_check as CM
from flow.constraint_gates import parse_clock_pairs

FIX = Path(__file__).parent / "fixtures" / "clock_mux"


def run(arm: str) -> dict[str, bool]:
    d = FIX / arm
    dump = CM.parse_dump((d / "clock_mux.tsv").read_text())
    ci = d / "clock_interaction.rpt"
    pairs = parse_clock_pairs(ci.read_text()) if ci.is_file() else None
    return {f["code"]: f["blocking"] for f in CM.findings(dump, pairs)}


# arm -> the blocking codes expected (and only those), with the measured reason
BLOCKING = {
    "a7_u_none": {"CLKMUX-NO-GROUPS"},            # clk0/clk1 timed through the mux: 33 failing endpoints, WNS -6.63 ns
    "a7_u_noint_none": {"CLKMUX-NO-GROUPS"},
    "a7_u_srclog": {"CLKMUX-SRC-GROUPED"},        # groups on the sources hid WNS -6.63 ns and every report_cdc row
    "a7_u_async": {"CLKMUX-SRC-GROUPED"},         # -asynchronous on the sources: same timing loss (report_cdc still lists them)
    "a7_r_srclog": {"CLKMUX-SRC-GROUPED"},        # related clocks: hid a -6.72 ns setup failure; summary WNS +0.295
    "a7_u_gennog": {"CLKMUX-NO-GROUPS"},          # generated clocks without groups (Vivado: TIMING-56)
    "a7_u_genphys": set(),                        # UG949 p.174 template: path A stays visible (clk0 -> clk1mux)
    "a7_u_ctrl_genphys": set(),
    "a7_r_genphys": set(),                        # the -6.61 ns failure is reported, as it should be
    "a7_u_noint_srclog": set(),                   # no paths A/C: grouping the sources is correct (UG949 "no interaction")
    "a7_r_noint_srclog": set(),
    "a7_u_case": set(),                           # advisory only
    "a7_lut": {"CLKMUX-LUT"},                     # LUT3 -> BUFG; TIMING-14
    "a7_lut_tied": set(),                         # constant select: the LUT is gone
    "a7_bal4": {"CLKMUX-NO-GROUPS"},              # the cascade designs carry no clock groups
    "a7_bal3": {"CLKMUX-NO-GROUPS"},
    "a7_chain7": {"CLKMUX-NO-GROUPS"},
    "a7_chain17": {"CLKMUX-CASCADE"},             # dump only (synthesis): placement then failed
    # the same arms on xck26-sfvc784-2LV-c (UltraScale+): the same verdicts
    "k26_u_none": {"CLKMUX-NO-GROUPS"},
    "k26_u_srclog": {"CLKMUX-SRC-GROUPED"},       # routed: summary WNS +0.010 while the unconstrained arm shows -6.03 ns
    "k26_u_async": {"CLKMUX-SRC-GROUPED"},
    "k26_u_genphys": set(),
    "k26_u_gennog": {"CLKMUX-NO-GROUPS"},
    "k26_u_case": set(),
    "k26_u_noint_srclog": set(),
    "k26_r_srclog": {"CLKMUX-SRC-GROUPED"},
    "k26_r_genphys": set(),
    "k26_lut": {"CLKMUX-LUT"},
    "k26_lut_tied": set(),
    "k26_bal4": {"CLKMUX-NO-GROUPS"},
    "k26_chain7": {"CLKMUX-NO-GROUPS"},
    "k26_chain9": {"CLKMUX-NO-GROUPS", "CLKMUX-CASCADE"},
}


@pytest.mark.parametrize("arm", sorted(BLOCKING))
def test_recorded_arms_blocking(arm):
    if not (FIX / arm).is_dir():
        pytest.skip(f"no fixture {arm}")
    got = {c for c, b in run(arm).items() if b}
    assert got == BLOCKING[arm]


def test_advisories_on_recorded_arms():
    assert run("a7_u_case").get("CLKMUX-CASE") is False                 # set_case_analysis on the select
    assert run("a7_u_none").get("CLKMUX-CE-SELECT") is False            # BUFGMUX retargets to BUFGCTRL with CE0/CE1 driven
    assert "CLKMUX-CE-SELECT" not in run("a7_u_ctrl_genphys")           # BUFGMUX_CTRL: S0/S1 driven, CE tied
    assert run("a7_u_none").get("CLKMUX-STOP") is False                 # inputs straight from device pins, IGNORE tied
    assert "CLKMUX-STOP" not in run("a7_r_genphys")                     # inputs from an MMCM
    assert "CLKMUX-CASCADE" not in run("a7_bal4")                       # two levels for four inputs (UG949 Fig. 67)
    assert "CLKMUX-CASCADE" not in run("a7_chain7")                     # UG949 Fig. 69: a chain of 7 for 8:1
    assert run("a7_chain17").get("CLKMUX-CASCADE") is True              # 17 levels: placement failed (Place 30-120)
    assert run("k26_chain9").get("CLKMUX-CASCADE") is True              # 9 levels on UltraScale+: placement failed too
    assert "CLKMUX-CASCADE" not in run("k26_chain7")


def test_bufgce_is_not_a_mux():
    """7 series retargets BUFGCE to a BUFGCTRL with I1 tied to VCC and CE0 driven (a7_pwr_bufgce): no finding of any kind."""
    assert run("a7_pwr_bufgce") == {}
    assert run("k26_pwr_bufgce") == {}


def test_srcgrouped_needs_interaction():
    """The counter-case: the same source-clock group with and without paths A/C (same RTL, generic INTERACT)."""
    assert "CLKMUX-SRC-GROUPED" in run("a7_u_srclog")
    assert "CLKMUX-SRC-GROUPED" not in run("a7_u_noint_srclog")
    d = CM.parse_dump((FIX / "a7_u_srclog" / "clock_mux.tsv").read_text())
    m = next(iter(d["muxes"].values()))
    assert m["inter"]["A"] > 0 and m["inter"]["C"] > 0


def test_no_interaction_report_skips_group_rules():
    d = CM.parse_dump((FIX / "a7_u_srclog" / "clock_mux.tsv").read_text())
    codes = {f["code"] for f in CM.findings(d, None)}
    assert not codes & {"CLKMUX-NO-GROUPS", "CLKMUX-SRC-GROUPED"}


def _mux(name, ins, out, ctl=None, inter=(0, 0), ref="BUFGCTRL"):
    lines = [f"MUX\t{name}\t{ref}\t{ref}\t{len(ins)}"]
    for pin, drv, dref, clk in ins:
        lines.append(f"MUXIN\t{name}\t{pin}\t{drv}\t{dref}\t{clk}")
    lines.append(f"MUXOUT\t{name}\t{out}")
    for pin, const, drv in (ctl or [("S0", "-", "sel_reg"), ("S1", "-", "sel_reg"), ("CE0", "1", "VCC"), ("CE1", "1", "VCC"),
                                    ("IGNORE0", "0", "GND"), ("IGNORE1", "0", "GND")]):
        lines.append(f"MUXCTL\t{name}\t{pin}\t{const}\t{drv}\t-")
    lines += [f"FANOUT\t{name}\t8", f"INTER\t{name}\tA\t{inter[0]}\t-", f"INTER\t{name}\tC\t{inter[1]}\t-"]
    return lines


def test_cascade_three_levels_for_four_inputs():
    """A 4:1 mux built as a chain of three (not UG949's balanced tree) is advisory."""
    lines = ["PART\txck26-sfvc784-2LV-c\tzynquplus\tus"]
    lines += _mux("m1", [("I0", "mmcm", "MMCME4_ADV", "a"), ("I1", "mmcm", "MMCME4_ADV", "b")], "a,b")
    lines += _mux("m2", [("I0", "m1", "BUFGCTRL", "a,b"), ("I1", "mmcm", "MMCME4_ADV", "c")], "a,b,c")
    lines += _mux("m3", [("I0", "m2", "BUFGCTRL", "a,b,c"), ("I1", "mmcm", "MMCME4_ADV", "d")], "a,b,c,d")
    f = {x["code"]: x for x in CM.findings(CM.parse_dump("\n".join(lines)), None)}
    assert f["CLKMUX-CASCADE"]["where"] == "m3" and not f["CLKMUX-CASCADE"]["blocking"]
    assert "3 BUFGCTRL levels for 4 inputs" in f["CLKMUX-CASCADE"]["message"]


def test_cascade_limit_by_family():
    lines = ["PART\txck26-sfvc784-2LV-c\tzynquplus\tus"]
    prev = None
    for k in range(9):
        i0 = (prev, "BUFGCTRL", "x") if prev else ("mmcm", "MMCME4_ADV", "x")
        lines += _mux(f"s{k}", [("I0", *i0), ("I1", "mmcm", "MMCME4_ADV", "y")], "x,y")
        prev = f"s{k}"
    d = CM.parse_dump("\n".join(lines))
    assert any(f["code"] == "CLKMUX-CASCADE" and f["blocking"] for f in CM.findings(d, None))   # 9 > 8 on UltraScale
    assert not any(f["code"] == "CLKMUX-CASCADE" for f in CM.findings(d, None, family="7"))  # 9 <= 16 on 7 series


def test_ignore_driven_clears_stop_advisory():
    ctl = [("S0", "-", "s"), ("S1", "-", "s"), ("CE0", "1", "VCC"), ("CE1", "1", "VCC"), ("IGNORE0", "-", "ign0_reg"),
           ("IGNORE1", "-", "ign1_reg")]
    lines = _mux("m", [("I0", "clk0_IBUF_inst", "IBUF", "a"), ("I1", "clk1_IBUF_inst", "IBUF", "b")], "a,b", ctl=ctl)
    codes = {f["code"] for f in CM.findings(CM.parse_dump("\n".join(lines)), None)}
    assert "CLKMUX-STOP" not in codes and "CLKMUX-CE-SELECT" not in codes


def test_cli_exit_codes(capsys):
    assert CM.main([str(FIX / "a7_u_genphys" / "clock_mux.tsv"), "--clock-interaction",
                    str(FIX / "a7_u_genphys" / "clock_interaction.rpt")]) == 0
    assert CM.main([str(FIX / "a7_u_srclog" / "clock_mux.tsv"), "--clock-interaction",
                    str(FIX / "a7_u_srclog" / "clock_interaction.rpt")]) == 1
    assert "CLKMUX-SRC-GROUPED" in capsys.readouterr().out


def test_registered_in_check_suite():
    from flow import checks
    from flow.lint_ruleset import load_rules
    c = checks.CHECKS["clock_mux"]
    assert c.kind == "vivado" and "clock_mux" in c.reports
    rules = load_rules()
    rows = rules["rules"] if isinstance(rules, dict) and "rules" in rules else rules
    covered = set()
    for r in rows:
        for code in (r.get("checks") or {}).get("clock_mux", []):
            covered.add(code)
    assert set(c.codes["clock_mux"]) == covered
